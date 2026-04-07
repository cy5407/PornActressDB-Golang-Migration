package backend

import (
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
	dbOnce     sync.Once
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
	a.dbOnce.Do(func() {
		dataDir := resolveDataDir(a.cfgPath)
		a.db = database.NewJSONDatabase(dataDir)
		_ = a.db.Load(ctx)
	})
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
	return services.NewConfigService(a.cfgPath).Save(prefs)
}

// ResetPreferences resets config.ini to built-in defaults.
func (a *App) ResetPreferences() error {
	return services.NewConfigService(a.cfgPath).Reset()
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

// BatchSearch invokes PythonSearch for each code concurrently (up to workers goroutines).
// Progress and individual results are emitted as Wails Events so the frontend can update
// the UI in real time. The full result slice is also returned for the caller's convenience.
func (a *App) BatchSearch(codes []string, workers int) []SearchResult {
	if workers <= 0 {
		workers = 5
	}
	total := len(codes)
	results := make([]SearchResult, total)

	sem := make(chan struct{}, workers)
	var wg sync.WaitGroup
	var mu sync.Mutex
	done := 0

	for i, code := range codes {
		wg.Add(1)
		go func(idx int, c string) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()

			res, _ := a.PythonSearch(c)
			if res == nil {
				res = &SearchResult{Code: c, Error: "未知錯誤", ErrorKind: SearchErrorStderr}
			}

			mu.Lock()
			results[idx] = *res
			done++
			current := done
			mu.Unlock()

			// 發送 Wails 事件到前端
			wailsRuntime.EventsEmit(a.ctx, "search:progress", current, total, c)
			wailsRuntime.EventsEmit(a.ctx, "search:result", res)
		}(i, code)
	}

	wg.Wait()

	success := 0
	for _, r := range results {
		if r.Error == "" {
			success++
		}
	}
	summary := fmt.Sprintf("%d 成功 / %d 失敗", success, total-success)
	wailsRuntime.EventsEmit(a.ctx, "search:done", summary)

	return results
}

// ============================================================================
// Internal helpers
// ============================================================================

func (a *App) ensureDB() {
	a.dbOnce.Do(func() {
		dataDir := resolveDataDir(a.cfgPath)
		a.db = database.NewJSONDatabase(dataDir)
		_ = a.db.Load(context.Background())
	})
}

func resolveConfigPath() string {
	// Try next to executable first, then fall back to CWD
	exe, err := os.Executable()
	if err == nil {
		candidate := filepath.Join(filepath.Dir(exe), "config.ini")
		if _, err2 := os.Stat(candidate); err2 == nil {
			return candidate
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
	return prefs.JSONDataDir
}

func resolveLogDir(cfgPath string) string {
	cfgSvc := services.NewConfigService(cfgPath)
	prefs, _ := cfgSvc.Load()
	if prefs.LogDir != "" {
		return prefs.LogDir
	}
	return "logs"
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


