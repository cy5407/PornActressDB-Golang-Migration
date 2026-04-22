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
	"actress-classifier/pkg/pathutil"
	"actress-classifier/pkg/studio"
	"wails-app/backend/services"
)

var osExecutable = os.Executable

// App is the main application struct exposed as Wails bindings.
type App struct {
	ctx           context.Context
	extractor     *extractor.CodeExtractor
	mover         *mover.Mover
	db            *database.JSONDatabase
	dbFileModTime time.Time
	studio        *studio.StudioIdentifier
	cfgSvc        *services.ConfigService
	cfgPath       string
	dbMu          sync.Mutex         // 取代 dbOnce，支援設定變更後重置
	cancelScan    context.CancelFunc // 取消掃描/搜尋用
	cancelMu      sync.Mutex
	majorStudios  map[string]bool   // 從 major_studios.json 載入
	codeStudioMap map[string]string // 番號前綴 → 片商名，從 studios.json 載入
	// batchSearchRunner 僅供測試替換批次搜尋執行路徑，避免直接啟動 Python 子程序。
	batchSearchRunner func(codes []string, workers int, source string) []SearchResult
}

// NewApp creates a new App instance.
func NewApp() *App {
	cfgPath := resolveConfigPath()
	cfgSvc := services.NewConfigService(cfgPath)

	// Initialise studio identifier (best-effort; errors are non-fatal)
	si, _ := studio.NewStudioIdentifier(resolveStudiosPath())

	// Determine log directory from config
	logDir := resolveLogDir(cfgPath)

	app := &App{
		extractor: extractor.NewCodeExtractor(),
		mover:     mover.NewMover(logDir),
		studio:    si,
		cfgSvc:    cfgSvc,
		cfgPath:   cfgPath,
	}
	app.majorStudios = app.loadMajorStudios()
	app.codeStudioMap = loadCodeStudioMap(resolveStudiosPath())
	return app
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
	if err := a.ensureDB(); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: failed to initialize database: %v\n", err)
		a.emitEvent("error", fmt.Sprintf("資料庫初始化失敗：%v", err))
	}
}

func (a *App) emitEvent(eventName string, optionalData ...interface{}) {
	if a.ctx == nil || a.ctx.Value("events") == nil {
		return
	}
	wailsRuntime.EventsEmit(a.ctx, eventName, optionalData...)
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
	supportedFormats := make(map[string]bool, len(extractor.SupportedFormats))
	for _, ext := range extractor.SupportedFormats {
		supportedFormats[ext] = true
	}
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
		if !supportedFormats[strings.ToLower(filepath.Ext(path))] {
			return nil
		}
		scanned++
		code := a.extractor.ExtractCode(filepath.Base(path))
		if code != "" && !seen[code] {
			seen[code] = true
			results = append(results, ScanResult{Path: path, Code: code})
			a.emitEvent("scan:progress", len(results), code)
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

// DirMoveItem 表示單一目錄移動請求。
type DirMoveItem struct {
	Source      string `json:"source"`
	Destination string `json:"destination"`
	OnConflict  string `json:"on_conflict,omitempty"` // skip | overwrite | rename；空值使用全域 strategy
}

// PlanDirMergeMoves 將資料夾移動請求展開為檔案層級的移動清單。
// 目的地會保留來源資料夾內的相對路徑，供前端直接交給 CheckConflicts / BatchMove 使用。
func (a *App) PlanDirMergeMoves(items []DirMoveItem) ([]MoveItemRequest, error) {
	moveItems := make([]MoveItemRequest, 0)
	for _, item := range items {
		sameOrNested, err := pathutil.IsSameOrNestedPath(item.Source, item.Destination)
		if err != nil {
			return nil, fmt.Errorf("failed to validate source %q and destination %q: %w", item.Source, item.Destination, err)
		}
		if sameOrNested {
			sourceAbs, absErr := filepath.Abs(item.Source)
			if absErr != nil {
				return nil, fmt.Errorf("failed to resolve source %q: %w", item.Source, absErr)
			}
			destinationAbs, absErr := filepath.Abs(item.Destination)
			if absErr != nil {
				return nil, fmt.Errorf("failed to resolve destination %q: %w", item.Destination, absErr)
			}
			if strings.EqualFold(filepath.Clean(sourceAbs), filepath.Clean(destinationAbs)) {
				// 來源與目標相同（女優已在正確位置），略過該項目
				continue
			}
			return nil, fmt.Errorf("destination %q cannot be inside source %q", item.Destination, item.Source)
		}

		onConflict := mover.ConflictStrategy(item.OnConflict)
		itemMoves := make([]MoveItemRequest, 0)
		err = filepath.Walk(item.Source, func(path string, info os.FileInfo, walkErr error) error {
			if walkErr != nil {
				return fmt.Errorf("failed to read %q: %w", path, walkErr)
			}
			if info == nil || info.IsDir() {
				return nil
			}

			relPath, relErr := filepath.Rel(item.Source, path)
			if relErr != nil {
				return fmt.Errorf("failed to compute relative path for %q: %w", path, relErr)
			}

			itemMoves = append(itemMoves, MoveItemRequest{
				Source:      path,
				Destination: filepath.Join(item.Destination, relPath),
				OnConflict:  onConflict,
			})
			return nil
		})
		if err != nil {
			return nil, fmt.Errorf("failed to plan directory merge from %q to %q: %w", item.Source, item.Destination, err)
		}
		moveItems = append(moveItems, itemMoves...)
	}
	return moveItems, nil
}

// BatchMoveDirs 以資料夾為單位批次移動。
// 每個 item.Source 為來源資料夾，item.Destination 為目標資料夾（含最終目錄名）。
// 操作記錄會寫入 mover opLog，支援 RollbackOperation。
// strategy 為全域預設衝突策略；可透過 item.OnConflict 覆蓋個別項目。
func (a *App) BatchMoveDirs(items []DirMoveItem, strategy string) BatchMoveResult {
	cs := mover.ConflictStrategy(strategy)
	moveItems := make([]mover.MoveItem, len(items))
	for i, item := range items {
		oc := mover.ConflictStrategy(item.OnConflict)
		if oc == "" {
			oc = cs
		}
		moveItems[i] = mover.MoveItem{
			Source:      item.Source,
			Destination: item.Destination,
			OnConflict:  oc,
		}
	}
	return a.mover.BatchMoveDirs(a.ctx, moveItems)
}

// CheckDirConflicts 返回目的地目錄已存在（非空）的移動項目列表。
// 前端可呼叫此方法在執行 BatchMoveDirs 前偵測衝突，讓使用者選擇處理方式。
func (a *App) CheckDirConflicts(items []DirMoveItem) []ConflictItem {
	conflicts := make([]ConflictItem, 0)
	for _, item := range items {
		absSrc, errSrc := filepath.Abs(item.Source)
		absDst, errDst := filepath.Abs(item.Destination)
		if errSrc == nil && errDst == nil && strings.EqualFold(absSrc, absDst) {
			continue
		}
		entries, err := os.ReadDir(item.Destination)
		if err == nil && len(entries) > 0 {
			conflicts = append(conflicts, ConflictItem{
				Source:      item.Source,
				Destination: item.Destination,
			})
		}
	}
	return conflicts
}

// ConflictItem 代表一個目的地已存在的移動項目。
type ConflictItem struct {
	Source      string `json:"source"`
	Destination string `json:"destination"`
}

// CheckConflicts 返回目的地檔案已存在的移動項目列表。
// 前端可呼叫此方法在執行批次移動前偵測衝突，讓使用者選擇處理方式。
// 注意：source == destination 的項目不視為衝突（會被 MoveFile 直接略過）。
func (a *App) CheckConflicts(items []MoveItemRequest) []ConflictItem {
	conflicts := make([]ConflictItem, 0)
	for _, item := range items {
		absSrc, errSrc := filepath.Abs(item.Source)
		absDst, errDst := filepath.Abs(item.Destination)
		if errSrc == nil && errDst == nil && absSrc == absDst {
			// source == destination：MoveFile 會視為 skip，不是真正衝突
			continue
		}
		if _, err := os.Stat(item.Destination); err == nil {
			conflicts = append(conflicts, ConflictItem{
				Source:      item.Source,
				Destination: item.Destination,
			})
		}
	}
	return conflicts
}

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
	if err := a.ensureDB(); err != nil {
		return nil, err
	}
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
	if err := a.ensureDB(); err != nil {
		return nil, err
	}
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

	batchSearchSourceAVWiki = "avwiki"
	batchSearchSourceJAVDB  = "javdb"
	batchSearchResultFound  = "found"
	batchSearchResultMiss   = "not_found"
	batchSearchResultError  = "error"
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
	Current   int      `json:"current,omitempty"`
	Total     int      `json:"total,omitempty"`
}

type batchSearchRequest struct {
	Codes   []string `json:"codes"`
	Workers int      `json:"workers"`
	Source  string   `json:"source_mode,omitempty"`
}

func buildBatchSearchInput(codes []string, workers int, source string) ([]byte, error) {
	return json.Marshal(batchSearchRequest{
		Codes:   codes,
		Workers: workers,
		Source:  source,
	})
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
	return a.batchSearch(codes, workers, "")
}

// BatchSearchAVWiki 僅要求 Python 批次腳本搜尋 AV-WIKI。
// source 欄位為 split-search-go-api 的最小契約；Python 端尚未消費時會安全忽略。
func (a *App) BatchSearchAVWiki(codes []string, workers int) []SearchResult {
	return a.batchSearch(codes, workers, batchSearchSourceAVWiki)
}

// BatchSearchJAVDB 僅要求 Python 批次腳本搜尋 JAVDB。
// source 欄位為 split-search-go-api 的最小契約；Python 端尚未消費時會安全忽略。
func (a *App) BatchSearchJAVDB(codes []string, workers int) []SearchResult {
	return a.batchSearch(codes, workers, batchSearchSourceJAVDB)
}

func batchSearchSourceFields(source string) (statusField string, dateField string, ok bool) {
	switch source {
	case batchSearchSourceAVWiki:
		return "avwiki_actress_status", "avwiki_last_search_date", true
	case batchSearchSourceJAVDB:
		return "javdb_actress_status", "javdb_last_search_date", true
	default:
		return "", "", false
	}
}

func inferBatchSearchSourceStatus(res SearchResult) string {
	if res.Error == "" {
		return batchSearchResultFound
	}
	if strings.EqualFold(res.ErrorKind, batchSearchResultMiss) || strings.Contains(res.Error, "未找到結果") {
		return batchSearchResultMiss
	}
	return batchSearchResultError
}

func batchSearchFailureDetail(scanErr error, waitErr error, stderr string) string {
	parts := make([]string, 0, 3)
	if scanErr != nil {
		parts = append(parts, fmt.Sprintf("scanner error: %v", scanErr))
	}
	if waitErr != nil {
		parts = append(parts, fmt.Sprintf("wait error: %v", waitErr))
	}
	if stderr != "" {
		parts = append(parts, stderr)
	}
	if len(parts) == 0 {
		return "Python batch search 子程序異常結束"
	}
	return strings.Join(parts, "; ")
}

func applyBatchSearchSourceStatus(video *database.VideoData, source string, status string, timestamp string) {
	switch source {
	case batchSearchSourceAVWiki:
		video.AVWikiActressStatus = status
		video.AVWikiLastSearchDate = timestamp
	case batchSearchSourceJAVDB:
		video.JAVDBActressStatus = status
		video.JAVDBLastSearchDate = timestamp
	}
}

func (a *App) persistBatchSearchResult(res SearchResult, source string) {
	if a.db == nil || res.Code == "" {
		return
	}

	now := time.Now().UTC().Format("2006-01-02T15:04:05Z")
	_, err := a.db.GetVideo(res.Code)
	if source == "" {
		if res.Error != "" {
			return
		}
		updates := map[string]any{
			"title":            res.Title,
			"studio":           res.Studio,
			"release_date":     res.Release,
			"url":              res.URL,
			"actresses":        res.Actresses,
			"search_status":    "searched_found",
			"search_method":    res.Method,
			"last_search_date": now,
			"updated_at":       now,
		}
		if err == nil {
			_ = a.db.UpdateVideoFields(res.Code, updates)
			return
		}
		_ = a.db.AddVideo(&database.VideoData{
			Code:           res.Code,
			Title:          res.Title,
			Studio:         res.Studio,
			ReleaseDate:    res.Release,
			URL:            res.URL,
			Actresses:      res.Actresses,
			SearchStatus:   "searched_found",
			SearchMethod:   res.Method,
			LastSearchDate: now,
		})
		return
	}

	statusField, dateField, ok := batchSearchSourceFields(source)
	if !ok {
		return
	}

	sourceStatus := inferBatchSearchSourceStatus(res)
	updates := map[string]any{
		statusField:  sourceStatus,
		dateField:    now,
		"updated_at": now,
	}
	if res.Error == "" {
		updates["title"] = res.Title
		updates["studio"] = res.Studio
		updates["release_date"] = res.Release
		updates["url"] = res.URL
		updates["actresses"] = res.Actresses
		updates["search_status"] = "searched_found"
		updates["search_method"] = res.Method
		updates["last_search_date"] = now
	}

	if err == nil {
		_ = a.db.UpdateVideoFields(res.Code, updates)
		return
	}

	newVideo := database.NewVideo(res.Code)
	applyBatchSearchSourceStatus(newVideo, source, sourceStatus, now)
	if res.Error == "" {
		newVideo.Title = res.Title
		newVideo.Studio = res.Studio
		newVideo.ReleaseDate = res.Release
		newVideo.URL = res.URL
		newVideo.Actresses = res.Actresses
		newVideo.SearchStatus = "searched_found"
		newVideo.SearchMethod = res.Method
		newVideo.LastSearchDate = now
	} else if sourceStatus == batchSearchResultMiss {
		newVideo.SearchStatus = "searched_not_found"
	} else {
		newVideo.SearchStatus = "search_error"
	}
	_ = a.db.AddVideo(newVideo)
}

func (a *App) batchSearch(codes []string, workers int, source string) []SearchResult {
	if workers <= 0 {
		if prefs, err := a.cfgSvc.Load(); err == nil && prefs.ThreadCount > 0 {
			workers = prefs.ThreadCount
		} else {
			workers = 20
		}
	}
	total := len(codes)
	if total == 0 {
		a.emitEvent("search:done", "0 成功 / 0 失敗")
		return nil
	}

	// --- DB 快取過濾：舊 BatchSearch 才使用整體 cache；source-specific API 必須重跑該來源 ---
	if err := a.ensureDB(); err != nil {
		a.emitEvent("error", fmt.Sprintf("資料庫初始化失敗：%v", err))
		a.emitEvent("search:done", fmt.Sprintf("0 成功 / %d 失敗（資料庫初始化失敗）", total))
		return nil
	}
	results := make([]SearchResult, 0, total)
	codesToSearch := make([]string, 0, len(codes))
	done := 0
	useLegacyCache := source == ""
	for _, code := range codes {
		video, err := a.db.GetVideo(code)
		if useLegacyCache && err == nil && video.SearchStatus == "searched_found" {
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
			cached.Current = done
			cached.Total = total
			a.emitEvent("search:progress", done, total, code)
			a.emitEvent("search:result", &cached)
		} else {
			codesToSearch = append(codesToSearch, code)
		}
	}

	// 全部都在快取中
	if len(codesToSearch) == 0 {
		success := len(results)
		// journal 有未合併資料時，趁機寫入 data.json
		if a.db != nil {
			_, _ = a.db.CompactIfNeeded()
		}
		a.emitEvent("search:done", fmt.Sprintf("%d 成功 / 0 失敗（已快取）", success))
		return results
	}

	var mu sync.Mutex
	handleResult := func(res SearchResult) {
		mu.Lock()
		results = append(results, res)
		done++
		current := done
		mu.Unlock()

		res.Current = current
		res.Total = total
		a.emitEvent("search:progress", current, total, res.Code)
		a.emitEvent("search:result", &res)
		a.persistBatchSearchResult(res, source)
	}

	if a.batchSearchRunner != nil {
		runnerResults := a.batchSearchRunner(codesToSearch, workers, source)
		if len(runnerResults) == 0 {
			a.emitEvent("search:done", fmt.Sprintf("%d 成功 / %d 失敗（批次搜尋執行器未回傳結果）", len(results), len(codesToSearch)))
			return results
		}
		for _, res := range runnerResults {
			handleResult(res)
		}
		if a.db != nil {
			_ = a.db.Compact()
		}
		success := 0
		for _, r := range results {
			if r.Error == "" {
				success++
			}
		}
		a.emitEvent("search:done", fmt.Sprintf("%d 成功 / %d 失敗", success, total-success))
		return results
	}

	scriptPath := resolveRunBatchSearchScript()
	pythonExe := resolvePythonExe()

	input, err := buildBatchSearchInput(codesToSearch, workers, source)
	if err != nil {
		a.emitEvent("search:done", fmt.Sprintf("0 成功 / %d 失敗（輸入序列化失敗）", total))
		return nil
	}

	cmd := exec.CommandContext(a.ctx, pythonExe, "-X", "utf8", scriptPath)
	cmd.Stdin = bytes.NewReader(input)
	cmd.Env = append(os.Environ(), "PYTHONIOENCODING=utf-8", "PYTHONUTF8=1")
	hideWindow(cmd)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		a.emitEvent("search:done", "0 成功 / 0 失敗（啟動失敗）")
		return nil
	}
	var stderrBuf bytes.Buffer
	cmd.Stderr = &stderrBuf

	if err := cmd.Start(); err != nil {
		a.emitEvent("search:done", fmt.Sprintf("0 成功 / %d 失敗（%s）", total, err))
		return nil
	}

	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, 1024*1024), 1024*1024) // 支援長標題
	for scanner.Scan() {
		var res SearchResult
		if err2 := json.Unmarshal(scanner.Bytes(), &res); err2 == nil {
			handleResult(res)
		}
	}

	scanErr := scanner.Err()
	waitErr := cmd.Wait()
	if scanErr != nil || waitErr != nil {
		failureDetail := batchSearchFailureDetail(scanErr, waitErr, stderrBuf.String())
		success := 0
		for _, r := range results {
			if r.Error == "" {
				success++
			}
		}
		a.emitEvent("search:done", fmt.Sprintf("%d 成功 / %d 失敗（%s）", success, total-success, failureDetail))
		return results
	}

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
	a.emitEvent("search:done", fmt.Sprintf("%d 成功 / %d 失敗", success, total-success))
	return results
}

// ============================================================================
// Studio Classification
// ============================================================================

// GetActressPrimaryStudios 批次查詢女優的主要片商資料夾名稱。
//
// 返回 map[女優名] → 片商資料夾：
//   - 大片商（major_studios.json 內）→ 片商名（如 "S1"）
//   - 非大片商或跨多片商（作品最多但不是大片商）→ "單體企劃女優"
//   - 無任何 studio 記錄 → ""（前端應歸入「未分類」）
func (a *App) GetActressPrimaryStudios(actressNames []string) map[string]string {
	result := make(map[string]string, len(actressNames))
	if err := a.ensureDB(); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: failed to initialize database for actress studio lookup: %v\n", err)
		a.emitEvent("error", fmt.Sprintf("資料庫初始化失敗：%v", err))
		return result
	}
	seen := map[string]bool{}
	for _, name := range actressNames {
		if seen[name] {
			continue
		}
		seen[name] = true
		if isGarbageActressName(name) {
			result[name] = "" // 垃圾值（如 ＊＊＊），不分類
			continue
		}
		studio := a.db.GetActressPrimaryStudio(name)
		switch {
		case studio == "":
			result[name] = "" // 無資料，前端決定路徑
		case matchesMajorStudio(studio, a.majorStudios):
			canonical, _ := canonicalMajorStudio(studio, a.majorStudios)
			result[name] = canonical
		default:
			result[name] = "單體企劃女優" // 非大片商
		}
	}
	return result
}

// isGarbageActressName 判斷是否為明顯垃圾值（全形或半形星號組成，如 ＊＊＊）。
func isGarbageActressName(name string) bool {
	if name == "" {
		return false
	}
	for _, r := range name {
		if r != '＊' && r != '*' {
			return false
		}
	}
	return true
}

// GetStudioByCode 依番號前綴查片商名稱（真實來源：studios.json）。
// 返回值：大片商名稱（如 "MOODYZ"）、"單體企劃女優"（非大片商）或 ""（未知）。
func (a *App) GetStudioByCode(code string) string {
	prefix := extractCodePrefix(code)
	if prefix == "" {
		return ""
	}
	studioName, ok := a.codeStudioMap[strings.ToUpper(prefix)]
	if !ok {
		return ""
	}
	upper := strings.ToUpper(studioName)
	if a.majorStudios[upper] {
		return upper
	}
	return "單體企劃女優"
}

// GetStudiosByCodes 批次依番號前綴查片商（真實來源：studios.json）。
// 回傳 map[code → studio]；未知前綴的 code 對應值為 ""。
func (a *App) GetStudiosByCodes(codes []string) map[string]string {
	result := make(map[string]string, len(codes))
	for _, code := range codes {
		result[code] = a.GetStudioByCode(code)
	}
	return result
}

// extractCodePrefix 從番號擷取字母前綴，例如 "MIDA-583" → "MIDA"。
func extractCodePrefix(code string) string {
	code = strings.TrimSpace(code)
	for i, ch := range code {
		if ch == '-' || (ch >= '0' && ch <= '9') {
			return strings.ToUpper(code[:i])
		}
	}
	return strings.ToUpper(code)
}

// loadCodeStudioMap 解析 studios.json（格式：{片商名: [前綴…]}），
// 建立並返回反向映射 prefix(uppercase) → 片商名。
func loadCodeStudioMap(path string) map[string]string {
	data, err := os.ReadFile(path)
	if err != nil {
		return map[string]string{}
	}
	var raw map[string][]string
	if err := json.Unmarshal(data, &raw); err != nil {
		return map[string]string{}
	}
	result := make(map[string]string)
	for studioName, prefixes := range raw {
		for _, p := range prefixes {
			result[strings.ToUpper(strings.TrimSpace(p))] = studioName
		}
	}
	return result
}

func (a *App) ensureDB() error {
	a.dbMu.Lock()
	defer a.dbMu.Unlock()
	dataDir := resolveDataDir(a.cfgPath)
	dataFile := filepath.Join(dataDir, "data.json")

	if a.db != nil {
		if info, err := os.Stat(dataFile); err == nil && !info.ModTime().Equal(a.dbFileModTime) {
			a.db = nil
		}
	}

	if a.db == nil {
		db := database.NewJSONDatabase(dataDir)
		if err := db.Load(context.Background()); err != nil {
			a.db = nil
			a.dbFileModTime = time.Time{}
			return err
		}
		// 啟動時若 journal 有未合併資料，立即寫入 data.json，
		// 避免下次搜尋因全部命中快取（早期返回）而永遠跳過 Compact。
		if _, err := db.CompactIfNeeded(); err != nil {
			a.db = nil
			a.dbFileModTime = time.Time{}
			return err
		}
		a.db = db
	}

	if info, err := os.Stat(dataFile); err == nil {
		a.dbFileModTime = info.ModTime()
	} else {
		a.dbFileModTime = time.Time{}
	}
	return nil
}

func (a *App) resetDB() {
	a.dbMu.Lock()
	defer a.dbMu.Unlock()
	a.db = nil
	a.dbFileModTime = time.Time{}
}

func resolveConfigPath() string {
	// Priority: exe dir → project root (dev: 3 levels up from build/bin) → CWD
	exe, err := osExecutable()
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
	exe, err := osExecutable()
	if err == nil {
		candidate := filepath.Join(filepath.Dir(exe), "studios.json")
		if _, err2 := os.Stat(candidate); err2 == nil {
			return candidate
		}
	}
	return "studios.json"
}

// resolveMajorStudiosPath 以與 resolveStudiosPath 相同邏輯尋找 major_studios.json。
func resolveMajorStudiosPath() string {
	exe, err := osExecutable()
	if err == nil {
		candidate := filepath.Join(filepath.Dir(exe), "major_studios.json")
		if _, err2 := os.Stat(candidate); err2 == nil {
			return candidate
		}
	}
	return "major_studios.json"
}

// loadMajorStudios 載入 major_studios.json，返回片商名稱 set。
// 若檔案不存在或解析失敗，返回空 map（不 fatal）。
func (a *App) loadMajorStudios() map[string]bool {
	path := resolveMajorStudiosPath()
	data, err := os.ReadFile(path)
	if err != nil {
		return map[string]bool{}
	}
	var names []string
	if err := json.Unmarshal(data, &names); err != nil {
		return map[string]bool{}
	}
	result := make(map[string]bool, len(names))
	for _, name := range names {
		result[strings.ToUpper(strings.TrimSpace(name))] = true
	}
	return result
}

// canonicalMajorStudio returns the normalized key from majorStudios if studio
// matches (case-insensitive exact or prefix-with-space).
// Returns ("", false) if not matched.
// majorStudios keys must already be uppercase (guaranteed by loadMajorStudios).
func canonicalMajorStudio(studio string, majorStudios map[string]bool) (string, bool) {
	upper := strings.ToUpper(strings.TrimSpace(studio))
	if upper == "" {
		return "", false
	}
	if majorStudios[upper] {
		return upper, true
	}
	best := ""
	for major := range majorStudios {
		if strings.HasPrefix(upper, major+" ") {
			if len(major) > len(best) { // longest (most specific) match wins
				best = major
			}
		}
	}
	if best != "" {
		return best, true
	}
	return "", false
}

// matchesMajorStudio returns true if studio belongs to any major studio.
func matchesMajorStudio(studio string, majorStudios map[string]bool) bool {
	_, ok := canonicalMajorStudio(studio, majorStudios)
	return ok
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
	exe, err := osExecutable()
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
	exe, err := osExecutable()
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
