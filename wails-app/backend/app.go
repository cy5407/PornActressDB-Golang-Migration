package backend

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"

	wailsRuntime "github.com/wailsapp/wails/v2/pkg/runtime"

	"actress-classifier/pkg/database"
	"actress-classifier/pkg/extractor"
	"actress-classifier/pkg/mover"
	"actress-classifier/pkg/studio"
	"wails-app/backend/services"
)

// App is the main application struct exposed as Wails bindings.
type App struct {
	ctx        context.Context
	extractor  *extractor.CodeExtractor
	mover      *mover.Mover
	db         *database.JSONDatabase
	studio     *studio.StudioIdentifier
	cfgSvc     *services.ConfigService
	cfgPath    string
	dbMu       sync.Mutex // 取代 dbOnce，支援設定變更後重置
	cancelScan context.CancelFunc // 取消掃描/搜尋用
	cancelMu   sync.Mutex
}

// NewApp creates a new App instance.
func NewApp() *App {
	cfgPath := resolveConfigPath()
	cfgSvc := services.NewConfigService(cfgPath)

	// Initialise studio identifier (best-effort; errors are non-fatal)
	si, _ := studio.NewStudioIdentifier(resolveStudiosPath())

	// Determine log directory from config
	logDir := resolveLogDir(cfgPath)

	return &App{
		extractor: extractor.NewCodeExtractor(),
		mover:     mover.NewMover(logDir),
		studio:    si,
		cfgSvc:    cfgSvc,
		cfgPath:   cfgPath,
	}
}

// ============================================================================
// backend-package helpers (re-exported for test access)
// ============================================================================

func defaultPreferences() services.Preferences {
	return services.DefaultPreferences()
}

func buildIni(p services.Preferences) string {
	svc := services.NewConfigService("")
	_ = svc
	// Use ConfigService.Save logic via a temp path approach is complex;
	// delegate directly to the exported package-level helper.
	return services.BuildIni(p)
}

func parseIni(content string, p *services.Preferences) {
	services.ParseIni(content, p)
}

// Startup is called when the app starts.
func (a *App) Startup(ctx context.Context) {
	a.ctx = ctx
	a.ensureDB()
}

// ============================================================================
// Scan
// ============================================================================

// ScanResult represents a single scanned video file.
type ScanResult struct {
	Path string `json:"path"`
	Code string `json:"code"`
}

// ScanDirectory scans the given directory for video files and extracts their codes.
// When recursive=true (default), scans all subdirectories to any depth.
// Duplicate codes are deduplicated: first occurrence wins.
// Supports cancellation via CancelOperation. Emits "scan:progress" events during walk.
func (a *App) ScanDirectory(dir string, workers int, recursive bool) []ScanResult {
	scanCtx, cancel := context.WithCancel(a.ctx)
	a.cancelMu.Lock()
	a.cancelScan = cancel
	a.cancelMu.Unlock()
	defer func() {
		a.cancelMu.Lock()
		a.cancelScan = nil
		a.cancelMu.Unlock()
	}()

	var results []ScanResult
	seen := make(map[string]bool) // 去重：相同番號只保留第一個路徑
	scanned := 0

	_ = filepath.WalkDir(dir, func(path string, d os.DirEntry, err error) error {
		// 檢查取消訊號
		select {
		case <-scanCtx.Done():
			return filepath.SkipAll
		default:
		}
		if err != nil {
			// 無法存取（權限不足等）：略過並繼續
			return nil
		}
		if d.IsDir() {
			if !recursive && path != dir {
				return filepath.SkipDir
			}
			return nil
		}
		scanned++
		code := a.extractor.ExtractCode(filepath.Base(path))
		if code != "" && !seen[code] {
			seen[code] = true
			results = append(results, ScanResult{Path: path, Code: code})
			wailsRuntime.EventsEmit(a.ctx, "scan:progress", len(results), code)
		}
		return nil
	})

	return results
}

// CancelOperation cancels the current running scan or search.
func (a *App) CancelOperation() {
	a.cancelMu.Lock()
	defer a.cancelMu.Unlock()
	if a.cancelScan != nil {
		a.cancelScan()
		a.cancelScan = nil
	}
}

// ============================================================================
// Move
// ============================================================================

// MoveFileResult wraps mover.MoveResult for the frontend.
type MoveFileResult = mover.MoveResult

// MoveDirResult wraps mover.MergeResult for the frontend.
type MoveDirResult = mover.MergeResult

// BatchMoveResult wraps mover.BatchResult for the frontend.
type BatchMoveResult = mover.BatchResult

// MoveItemRequest is the input shape for BatchMove.
type MoveItemRequest = mover.MoveItem

// MoveFile moves a single file from src to dst using the given conflict strategy.
// strategy: "skip" | "overwrite" | "rename"
func (a *App) MoveFile(src, dst, strategy string) MoveFileResult {
	return a.mover.MoveFile(src, dst, mover.ConflictStrategy(strategy))
}

// MoveDir moves an entire directory from src to dst.
func (a *App) MoveDir(src, dst, strategy string) MoveDirResult {
	return a.mover.MoveDir(src, dst, mover.ConflictStrategy(strategy))
}

// BatchMove performs a batch file move operation.
func (a *App) BatchMove(items []MoveItemRequest, strategy string) BatchMoveResult {
	for i := range items {
		if items[i].OnConflict == "" {
			items[i].OnConflict = mover.ConflictStrategy(strategy)
		}
	}
	return a.mover.BatchMove(a.ctx, items)
}

// BatchMoveJSON performs a batch file move from a JSON-encoded list of move items.
// This mirrors the CLI "batch move from stdin" behaviour for Wails frontend use.
func (a *App) BatchMoveJSON(jsonStr, strategy string) BatchMoveResult {
	var items []MoveItemRequest
	if err := json.Unmarshal([]byte(jsonStr), &items); err != nil {
		return BatchMoveResult{Status: "failed", Summary: fmt.Sprintf("JSON 解析失敗: %v", err)}
	}
	return a.BatchMove(items, strategy)
}

// ============================================================================
// Rollback
// ============================================================================

// RollbackOperation rolls back the operation identified by operationID.
func (a *App) RollbackOperation(operationID string) (BatchMoveResult, error) {
	return a.mover.Rollback(operationID)
}

// RollbackLast rolls back the most recent operation.
func (a *App) RollbackLast() (BatchMoveResult, error) {
	ops, err := a.mover.ListOperations()
	if err != nil {
		return BatchMoveResult{}, fmt.Errorf("無法列出操作: %w", err)
	}
	if len(ops) == 0 {
		return BatchMoveResult{}, fmt.Errorf("沒有可回滾的操作")
	}
	return a.mover.Rollback(ops[0].ID)
}

// ============================================================================
// Operations history
// ============================================================================

// OperationLog is an alias for the mover.OperationLog type.
type OperationLog = mover.OperationLog

// ListOperations returns all recorded move operations sorted newest-first.
func (a *App) ListOperations() ([]OperationLog, error) {
	return a.mover.ListOperations()
}

// GetOperation returns the detail of a single operation by ID.
func (a *App) GetOperation(operationID string) (*OperationLog, error) {
	return a.mover.GetOperation(operationID)
}

// ============================================================================
// Database
// ============================================================================

// VideoData is an alias for database.VideoData.
type VideoData = database.VideoData

// DbGetVideo retrieves a video record by its code.
func (a *App) DbGetVideo(code string) (*VideoData, error) {
	a.ensureDB()
	return a.db.GetVideo(code)
}

// DbUpdateVideo updates specific fields of a video record.
// fields is a JSON-encoded map of field updates.
func (a *App) DbUpdateVideo(code string, fieldsJSON string) error {
	a.ensureDB()
	var updates map[string]any
	if err := json.Unmarshal([]byte(fieldsJSON), &updates); err != nil {
		return fmt.Errorf("JSON 解析失敗: %w", err)
	}
	return a.db.UpdateVideoFields(code, updates)
}

// DbListVideos returns all video records in the database.
func (a *App) DbListVideos() ([]*VideoData, error) {
	a.ensureDB()
	return a.db.GetAllVideos()
}

// ============================================================================
// Studio identification
// ============================================================================

// StudioInfo carries the result of a studio identification.
type StudioInfo struct {
	Studio string `json:"studio"`
}

// IdentifyStudio identifies the studio for a given video code.
func (a *App) IdentifyStudio(code string) StudioInfo {
	if a.studio == nil {
		return StudioInfo{}
	}
	return StudioInfo{Studio: a.studio.IdentifyStudio(code)}
}

// ListStudios returns all known studio names.
func (a *App) ListStudios() []string {
	if a.studio == nil {
		return []string{}
	}
	return a.studio.GetAllStudios()
}

// ============================================================================
// Preferences (config.ini read/write) — delegated to services.ConfigService
// ============================================================================

// Preferences is an alias for the services.Preferences type so that Wails can
// auto-generate the correct TypeScript bindings while the implementation lives
// in the dedicated ConfigService.
type Preferences = services.Preferences

// GetPreferences reads preferences from config.ini.
func (a *App) GetPreferences() (Preferences, error) {
	return services.NewConfigService(a.cfgPath).Load()
}

// UpdatePreferences writes new preferences to config.ini.
func (a *App) UpdatePreferences(prefs Preferences) error {
	err := services.NewConfigService(a.cfgPath).Save(prefs)
	if err == nil {
		a.resetDB() // 讓下次操作以新設定重新初始化 DB
	}
	return err
}

// ResetPreferences resets config.ini to built-in defaults.
func (a *App) ResetPreferences() error {
	err := services.NewConfigService(a.cfgPath).Reset()
	if err == nil {
		a.resetDB()
	}
	return err
}

// ============================================================================
// Native dialogs
// ============================================================================

// SelectDirectory opens a native directory picker dialog and returns the chosen path.
// Returns an empty string if the user cancels.
func (a *App) SelectDirectory(title string) string {
	dir, err := wailsRuntime.OpenDirectoryDialog(a.ctx, wailsRuntime.OpenDialogOptions{
		Title: title,
	})
	if err != nil {
		return ""
	}
	return dir
}



// SearchErrorKind classifies the failure reason from a Python subprocess call.
// Values: "" (success), "timeout", "stderr", "json_parse", "not_found"
type SearchErrorKind = string

const (
	SearchErrorNone      SearchErrorKind = ""
	SearchErrorTimeout   SearchErrorKind = "timeout"
	SearchErrorStderr    SearchErrorKind = "stderr"
	SearchErrorJSONParse SearchErrorKind = "json_parse"
)

// searchTimeout is the per-code subprocess execution deadline.
const searchTimeout = 60 * time.Second

// SearchResult is the payload returned from the Python search subprocess.
type SearchResult struct {
	Code      string   `json:"code"`
	Title     string   `json:"title"`
	Studio    string   `json:"studio"`
	Release   string   `json:"release_date"`
	URL       string   `json:"url"`
	Actresses []string `json:"actresses"`
	Method    string   `json:"method"`
	Error     string   `json:"error,omitempty"`
	ErrorKind string   `json:"error_kind,omitempty"`
}

// PythonSearch invokes src/scrapers/run_search.py to search metadata for a video code.
// Failure is classified into three kinds: timeout, stderr, json_parse.
func (a *App) PythonSearch(code string) (*SearchResult, error) {
	pythonExe := resolvePythonExe()
	scriptPath := resolveRunSearchScript()

	ctx, cancel := context.WithTimeout(a.ctx, searchTimeout)
	defer cancel()

	// -X utf8 強制 Python stdout/stderr 使用 UTF-8
	cmd := exec.CommandContext(ctx, pythonExe, "-X", "utf8", scriptPath, code)
	cmd.Env = append(os.Environ(), "PYTHONIOENCODING=utf-8", "PYTHONUTF8=1")
	hideWindow(cmd) // Windows: 不彈出 CMD 視窗
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		// 區分 timeout vs stderr 兩種失敗
		if ctx.Err() == context.DeadlineExceeded {
			return &SearchResult{
				Code:      code,
				Error:     fmt.Sprintf("搜尋逾時（超過 %s）", searchTimeout),
				ErrorKind: SearchErrorTimeout,
			}, fmt.Errorf("Python 搜尋逾時: %w", ctx.Err())
		}
		stderrMsg := strings.TrimSpace(stderr.String())
		if stderrMsg == "" {
			stderrMsg = err.Error()
		}
		return &SearchResult{
			Code:      code,
			Error:     stderrMsg,
			ErrorKind: SearchErrorStderr,
		}, fmt.Errorf("Python 搜尋程序失敗: %w", err)
	}

	// 解析 JSON stdout
	var result SearchResult
	if err := json.Unmarshal(stdout.Bytes(), &result); err != nil {
		rawSnippet := strings.TrimSpace(stdout.String())
		if len(rawSnippet) > 200 {
			rawSnippet = rawSnippet[:200] + "…"
		}
		return &SearchResult{
			Code:      code,
			Error:     fmt.Sprintf("JSON 解析失敗: %v — 輸出片段: %s", err, rawSnippet),
			ErrorKind: SearchErrorJSONParse,
		}, fmt.Errorf("解析 Python 回傳 JSON 失敗: %w", err)
	}
	return &result, nil
}

// BatchSearch invokes run_batch_search.py with ALL codes at once (single Python process).
// Results are streamed line-by-line (JSON Lines) so the frontend receives real-time updates.
// This eliminates N×Python-startup overhead; estimated 10-20x faster than the old per-code approach.
// DB integration: codes already in DB (search_status=success) are served from cache; new results are persisted.
func (a *App) BatchSearch(codes []string, workers int) []SearchResult {
	if workers <= 0 {
		if prefs, err := a.cfgSvc.Load(); err == nil && prefs.ThreadCount > 0 {
			workers = prefs.ThreadCount
		} else {
			workers = 20
		}
	}
	total := len(codes)
	if total == 0 {
		wailsRuntime.EventsEmit(a.ctx, "search:done", "0 成功 / 0 失敗")
		return nil
	}

	// --- DB 快取過濾：已有記錄的 code 直接回傳，不重複搜尋 ---
	a.ensureDB()
	results := make([]SearchResult, 0, total)
	codesToSearch := make([]string, 0, len(codes))
	done := 0
	for _, code := range codes {
		video, err := a.db.GetVideo(code)
		if err == nil && (video.SearchStatus == database.SearchStatusSuccess || video.SearchStatus == "searched_found") {
			done++
			cached := SearchResult{
				Code:      video.Code,
				Title:     video.Title,
				Studio:    video.Studio,
				Release:   video.ReleaseDate,
				URL:       video.URL,
				Actresses: video.Actresses,
				Method:    video.SearchMethod,
			}
			results = append(results, cached)
			wailsRuntime.EventsEmit(a.ctx, "search:progress", done, total, code)
			wailsRuntime.EventsEmit(a.ctx, "search:result", &cached)
		} else {
			codesToSearch = append(codesToSearch, code)
		}
	}

	// 全部都在快取中
	if len(codesToSearch) == 0 {
		success := len(results)
		wailsRuntime.EventsEmit(a.ctx, "search:done", fmt.Sprintf("%d 成功 / 0 失敗（已快取）", success))
		return results
	}

	scriptPath := resolveRunBatchSearchScript()
	pythonExe := resolvePythonExe()

	input, _ := json.Marshal(map[string]interface{}{
		"codes":   codesToSearch,
		"workers": workers,
	})

	cmd := exec.CommandContext(a.ctx, pythonExe, "-X", "utf8", scriptPath)
	cmd.Stdin = bytes.NewReader(input)
	cmd.Env = append(os.Environ(), "PYTHONIOENCODING=utf-8", "PYTHONUTF8=1")
	hideWindow(cmd)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		wailsRuntime.EventsEmit(a.ctx, "search:done", "0 成功 / 0 失敗（啟動失敗）")
		return nil
	}
	var stderrBuf bytes.Buffer
	cmd.Stderr = &stderrBuf

	if err := cmd.Start(); err != nil {
		wailsRuntime.EventsEmit(a.ctx, "search:done", fmt.Sprintf("0 成功 / %d 失敗（%s）", total, err))
		return nil
	}

	var mu sync.Mutex

	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, 1024*1024), 1024*1024) // 支援長標題
	for scanner.Scan() {
		var res SearchResult
		if err2 := json.Unmarshal(scanner.Bytes(), &res); err2 == nil {
			mu.Lock()
			results = append(results, res)
			done++
			current := done
			mu.Unlock()

			wailsRuntime.EventsEmit(a.ctx, "search:progress", current, total, res.Code)
			wailsRuntime.EventsEmit(a.ctx, "search:result", &res)

			// 搜尋結果寫入 DB（僅成功結果）
			if res.Error == "" {
				now := time.Now().UTC().Format("2006-01-02T15:04:05Z")
				video := &database.VideoData{
					Code:           res.Code,
					Title:          res.Title,
					Studio:         res.Studio,
					ReleaseDate:    res.Release,
					URL:            res.URL,
					Actresses:      res.Actresses,
					SearchStatus:   database.SearchStatusSuccess,
					SearchMethod:   res.Method,
					LastSearchDate: now,
				}
				// 先嘗試新增，若已存在則更新
				if err3 := a.db.AddVideo(video); err3 != nil {
					_ = a.db.UpdateVideo(res.Code, video)
				}
			}
		}
	}

	cmd.Wait()

	// 搜尋完成後強制 compact：無論 journal 大小，立即合併進 data.json
	if a.db != nil {
		_ = a.db.Compact()
	}

	success := 0
	for _, r := range results {
		if r.Error == "" {
			success++
		}
	}
	wailsRuntime.EventsEmit(a.ctx, "search:done", fmt.Sprintf("%d 成功 / %d 失敗", success, total-success))
	return results
}

// ============================================================================
// Internal helpers
// ============================================================================

func (a *App) ensureDB() {
	a.dbMu.Lock()
	defer a.dbMu.Unlock()
	if a.db != nil {
		return
	}
	dataDir := resolveDataDir(a.cfgPath)
	a.db = database.NewJSONDatabase(dataDir)
	_ = a.db.Load(context.Background())
}

func (a *App) resetDB() {
	a.dbMu.Lock()
	defer a.dbMu.Unlock()
	a.db = nil
}

func resolveConfigPath() string {
	// Priority: exe dir → project root (dev: 3 levels up from build/bin) → CWD
	exe, err := os.Executable()
	if err == nil {
		exeDir := filepath.Dir(exe)
		candidates := []string{
			filepath.Join(exeDir, "config.ini"),
			filepath.Join(exeDir, "..", "..", "..", "config.ini"), // wails-app/build/bin → project root
		}
		for _, c := range candidates {
			if abs, err2 := filepath.Abs(c); err2 == nil {
				if _, err3 := os.Stat(abs); err3 == nil {
					return abs
				}
			}
		}
	}
	return "config.ini"
}

func resolveStudiosPath() string {
	exe, err := os.Executable()
	if err == nil {
		candidate := filepath.Join(filepath.Dir(exe), "studios.json")
		if _, err2 := os.Stat(candidate); err2 == nil {
			return candidate
		}
	}
	return "studios.json"
}

func resolveDataDir(cfgPath string) string {
	cfgSvc := services.NewConfigService(cfgPath)
	prefs, _ := cfgSvc.Load()
	dir := prefs.JSONDataDir
	if filepath.IsAbs(dir) {
		return dir
	}
	// Relative path: resolve relative to the config file's directory.
	// This ensures "data/json_db" in project root's config.ini resolves to
	// the project root's data/json_db, not the exe's working directory.
	if cfgPath != "" && cfgPath != "config.ini" {
		if abs, err := filepath.Abs(filepath.Join(filepath.Dir(cfgPath), dir)); err == nil {
			return abs
		}
	}
	return dir
}

func resolveLogDir(cfgPath string) string {
	cfgSvc := services.NewConfigService(cfgPath)
	prefs, _ := cfgSvc.Load()
	dir := "logs"
	if prefs.LogDir != "" {
		dir = prefs.LogDir
	}
	if filepath.IsAbs(dir) {
		return dir
	}
	if cfgPath != "" && cfgPath != "config.ini" {
		if abs, err := filepath.Abs(filepath.Join(filepath.Dir(cfgPath), dir)); err == nil {
			return abs
		}
	}
	return dir
}

func resolvePythonExe() string {
	if runtime.GOOS == "windows" {
		// Windows：依序嘗試 venv、python、py
		candidates := []string{"python", "python3", "py"}
		for _, c := range candidates {
			if path, err := exec.LookPath(c); err == nil {
				return path
			}
		}
		return "python"
	}
	// Unix：優先使用 venv 的 python3，其次是系統 python3/python
	candidates := []string{"python3", "python3.11", "python3.10", "python3.9", "python"}
	for _, c := range candidates {
		if path, err := exec.LookPath(c); err == nil {
			return path
		}
	}
	return "python3"
}

func resolveRunSearchScript() string {
	// Try project root relative to executable, then CWD
	exe, err := os.Executable()
	if err == nil {
		candidate := filepath.Join(filepath.Dir(exe), "src", "scrapers", "run_search.py")
		if _, err2 := os.Stat(candidate); err2 == nil {
			return candidate
		}
		// Wails dev: executable is in wails-app/build/bin, project root is ../../..
		candidate2 := filepath.Join(filepath.Dir(exe), "..", "..", "..", "src", "scrapers", "run_search.py")
		if abs, err3 := filepath.Abs(candidate2); err3 == nil {
			if _, err4 := os.Stat(abs); err4 == nil {
				return abs
			}
		}
	}
	return filepath.Join("src", "scrapers", "run_search.py")
}

func resolveRunBatchSearchScript() string {
	exe, err := os.Executable()
	if err == nil {
		candidate := filepath.Join(filepath.Dir(exe), "src", "scrapers", "run_batch_search.py")
		if _, err2 := os.Stat(candidate); err2 == nil {
			return candidate
		}
		candidate2 := filepath.Join(filepath.Dir(exe), "..", "..", "..", "src", "scrapers", "run_batch_search.py")
		if abs, err3 := filepath.Abs(candidate2); err3 == nil {
			if _, err4 := os.Stat(abs); err4 == nil {
				return abs
			}
		}
	}
	return filepath.Join("src", "scrapers", "run_batch_search.py")
}
