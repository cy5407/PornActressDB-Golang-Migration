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

	"actress-classifier/pkg/database"
	"actress-classifier/pkg/extractor"
	"actress-classifier/pkg/mover"
	"actress-classifier/pkg/studio"
	"wails-app/backend/services"
)

// App is the main application struct exposed as Wails bindings.
type App struct {
	ctx       context.Context
	extractor *extractor.CodeExtractor
	mover     *mover.Mover
	db        *database.JSONDatabase
	studio    *studio.StudioIdentifier
	cfgSvc    *services.ConfigService
	dbOnce    sync.Once
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
	}
}

// Startup is called when the app starts.
func (a *App) Startup(ctx context.Context) {
	a.ctx = ctx
	a.dbOnce.Do(func() {
		dataDir := resolveDataDir(a.cfgSvc.CfgPath())
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
// workers is unused in the pure-Go walk implementation but kept for API symmetry with the CLI.
func (a *App) ScanDirectory(dir string, workers int, recursive bool) []ScanResult {
	var results []ScanResult

	_ = filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return nil
		}
		if info.IsDir() {
			if !recursive && path != dir {
				return filepath.SkipDir
			}
			return nil
		}
		code := a.extractor.ExtractCode(filepath.Base(path))
		if code != "" {
			results = append(results, ScanResult{Path: path, Code: code})
		}
		return nil
	})

	return results
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
	return a.cfgSvc.Load()
}

// UpdatePreferences writes new preferences to config.ini.
func (a *App) UpdatePreferences(prefs Preferences) error {
	return a.cfgSvc.Save(prefs)
}

// ResetPreferences resets config.ini to built-in defaults.
func (a *App) ResetPreferences() error {
	return a.cfgSvc.Reset()
}

// ============================================================================
// Python search bridge
// ============================================================================

// SearchResult is the payload returned from the Python search subprocess.
type SearchResult struct {
	Code    string   `json:"code"`
	Title   string   `json:"title"`
	Studio  string   `json:"studio"`
	Release string   `json:"release_date"`
	URL     string   `json:"url"`
	Actresses []string `json:"actresses"`
	Method  string   `json:"method"`
	Error   string   `json:"error,omitempty"`
}

// PythonSearch invokes src/scrapers/run_search.py to search metadata for a video code.
func (a *App) PythonSearch(code string) (*SearchResult, error) {
	pythonExe := resolvePythonExe()
	scriptPath := resolveRunSearchScript()

	cmd := exec.CommandContext(a.ctx, pythonExe, scriptPath, code)
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr

	if err := cmd.Run(); err != nil {
		errMsg := strings.TrimSpace(stderr.String())
		if errMsg == "" {
			errMsg = err.Error()
		}
		return &SearchResult{Code: code, Error: errMsg}, fmt.Errorf("Python 搜尋失敗: %w", err)
	}

	var result SearchResult
	if err := json.Unmarshal(stdout.Bytes(), &result); err != nil {
		return nil, fmt.Errorf("解析 Python 回傳 JSON 失敗: %w", err)
	}
	return &result, nil
}

// ============================================================================
// Internal helpers
// ============================================================================

func (a *App) ensureDB() {
	a.dbOnce.Do(func() {
		dataDir := resolveDataDir(a.cfgSvc.CfgPath())
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
		return "python"
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


