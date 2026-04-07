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

	"actress-classifier/pkg/database"
	"actress-classifier/pkg/extractor"
	"actress-classifier/pkg/mover"
	"actress-classifier/pkg/studio"
)

// App is the main application struct exposed as Wails bindings.
type App struct {
	ctx       context.Context
	extractor *extractor.CodeExtractor
	mover     *mover.Mover
	db        *database.JSONDatabase
	studio    *studio.StudioIdentifier
	cfgPath   string
	dbOnce    sync.Once
}

// NewApp creates a new App instance.
func NewApp() *App {
	// Resolve config.ini relative to the executable directory
	cfgPath := resolveConfigPath()

	// Initialise studio identifier (best-effort; errors are non-fatal)
	si, _ := studio.NewStudioIdentifier(resolveStudiosPath())

	// Determine log directory for mover
	logDir := resolveLogDir(cfgPath)

	return &App{
		extractor: extractor.NewCodeExtractor(),
		mover:     mover.NewMover(logDir),
		studio:    si,
		cfgPath:   cfgPath,
	}
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
// Preferences (config.ini read/write)
// ============================================================================

// Preferences holds the application settings.
type Preferences struct {
	// [database]
	JSONDataDir string `json:"json_data_dir"`
	// [paths]
	DefaultInputDir string `json:"default_input_dir"`
	// [search]
	BatchSize              int     `json:"batch_size"`
	ThreadCount            int     `json:"thread_count"`
	BatchDelay             float64 `json:"batch_delay"`
	RequestTimeout         int     `json:"request_timeout"`
	AvwikiConcurrentEnabled bool   `json:"avwiki_concurrent_enabled"`
	AvwikiMaxConcurrent    int     `json:"avwiki_max_concurrent"`
	// [classification]
	Mode                 string `json:"mode"`
	AutoApplyPreferences bool   `json:"auto_apply_preferences"`
	// [cache]
	CacheTTLDays          int    `json:"cache_ttl_days"`
	CacheMaxSizeMB        int    `json:"cache_max_size_mb"`
	CacheAutoCleanOnExit  bool   `json:"cache_auto_cleanup_on_exit"`
	// [go_integration]
	GoEnabled            bool   `json:"go_enabled"`
	GoExePath            string `json:"go_exe_path"`
	ScanWorkers          int    `json:"scan_workers"`
	MoveConflictStrategy string `json:"move_conflict_strategy"`
	EnableOperationLog   bool   `json:"enable_operation_log"`
	LogDir               string `json:"log_dir"`
}

// defaultPreferences returns the built-in defaults.
func defaultPreferences() Preferences {
	return Preferences{
		JSONDataDir:             "data/json_db",
		DefaultInputDir:         "",
		BatchSize:               10,
		ThreadCount:             5,
		BatchDelay:              2.0,
		RequestTimeout:          20,
		AvwikiConcurrentEnabled: true,
		AvwikiMaxConcurrent:     15,
		Mode:                    "interactive",
		AutoApplyPreferences:    true,
		CacheTTLDays:            7,
		CacheMaxSizeMB:          500,
		CacheAutoCleanOnExit:    true,
		GoEnabled:               true,
		GoExePath:               "",
		ScanWorkers:             10,
		MoveConflictStrategy:    "skip",
		EnableOperationLog:      true,
		LogDir:                  "logs",
	}
}

// GetPreferences reads preferences from config.ini.
func (a *App) GetPreferences() (Preferences, error) {
	prefs := defaultPreferences()
	data, err := os.ReadFile(a.cfgPath)
	if err != nil {
		// Return defaults when file not found
		return prefs, nil
	}
	parseIni(string(data), &prefs)
	return prefs, nil
}

// UpdatePreferences writes new preferences to config.ini.
func (a *App) UpdatePreferences(prefs Preferences) error {
	content := buildIni(prefs)
	return os.WriteFile(a.cfgPath, []byte(content), 0600)
}

// ResetPreferences resets config.ini to built-in defaults.
func (a *App) ResetPreferences() error {
	return a.UpdatePreferences(defaultPreferences())
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
	data, err := os.ReadFile(cfgPath)
	if err == nil {
		scanner := bufio.NewScanner(strings.NewReader(string(data)))
		for scanner.Scan() {
			line := strings.TrimSpace(scanner.Text())
			if strings.HasPrefix(line, "json_data_dir") {
				parts := strings.SplitN(line, "=", 2)
				if len(parts) == 2 {
					return strings.TrimSpace(parts[1])
				}
			}
		}
	}
	return "data/json_db"
}

func resolveLogDir(cfgPath string) string {
	data, err := os.ReadFile(cfgPath)
	if err == nil {
		scanner := bufio.NewScanner(strings.NewReader(string(data)))
		for scanner.Scan() {
			line := strings.TrimSpace(scanner.Text())
			if strings.HasPrefix(line, "log_dir") {
				parts := strings.SplitN(line, "=", 2)
				if len(parts) == 2 {
					v := strings.TrimSpace(parts[1])
					if v != "" {
						return v
					}
				}
			}
		}
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

// ============================================================================
// Minimal ini parser / writer
// ============================================================================

func parseIni(content string, p *Preferences) {
	var section string
	scanner := bufio.NewScanner(strings.NewReader(content))
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, ";") || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			section = line[1 : len(line)-1]
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		k, v := strings.TrimSpace(parts[0]), strings.TrimSpace(parts[1])
		setPreferenceField(p, section, k, v)
	}
}

func setPreferenceField(p *Preferences, section, key, value string) {
	boolVal := func(s string) bool { s = strings.ToLower(s); return s == "true" || s == "1" || s == "yes" }
	intVal := func(s string) int {
		var n int
		fmt.Sscanf(s, "%d", &n)
		return n
	}
	floatVal := func(s string) float64 {
		var f float64
		fmt.Sscanf(s, "%f", &f)
		return f
	}

	switch section + "." + key {
	case "database.json_data_dir":
		p.JSONDataDir = value
	case "paths.default_input_dir":
		p.DefaultInputDir = value
	case "search.batch_size":
		p.BatchSize = intVal(value)
	case "search.thread_count":
		p.ThreadCount = intVal(value)
	case "search.batch_delay":
		p.BatchDelay = floatVal(value)
	case "search.request_timeout":
		p.RequestTimeout = intVal(value)
	case "search.avwiki_concurrent_enabled":
		p.AvwikiConcurrentEnabled = boolVal(value)
	case "search.avwiki_max_concurrent":
		p.AvwikiMaxConcurrent = intVal(value)
	case "classification.mode":
		p.Mode = value
	case "classification.auto_apply_preferences":
		p.AutoApplyPreferences = boolVal(value)
	case "cache.ttl_days":
		p.CacheTTLDays = intVal(value)
	case "cache.max_size_mb":
		p.CacheMaxSizeMB = intVal(value)
	case "cache.auto_cleanup_on_exit":
		p.CacheAutoCleanOnExit = boolVal(value)
	case "go_integration.enabled":
		p.GoEnabled = boolVal(value)
	case "go_integration.exe_path":
		p.GoExePath = value
	case "go_integration.scan_workers":
		p.ScanWorkers = intVal(value)
	case "go_integration.move_conflict_strategy":
		p.MoveConflictStrategy = value
	case "go_integration.enable_operation_log":
		p.EnableOperationLog = boolVal(value)
	case "go_integration.log_dir":
		p.LogDir = value
	}
}

func boolStr(b bool) string {
	if b {
		return "true"
	}
	return "false"
}

func buildIni(p Preferences) string {
	var sb strings.Builder
	sb.WriteString("[database]\n")
	sb.WriteString("json_data_dir = " + p.JSONDataDir + "\n\n")

	sb.WriteString("[paths]\n")
	sb.WriteString("default_input_dir = " + p.DefaultInputDir + "\n\n")

	sb.WriteString("[search]\n")
	sb.WriteString(fmt.Sprintf("batch_size = %d\n", p.BatchSize))
	sb.WriteString(fmt.Sprintf("thread_count = %d\n", p.ThreadCount))
	sb.WriteString(fmt.Sprintf("batch_delay = %.1f\n", p.BatchDelay))
	sb.WriteString(fmt.Sprintf("request_timeout = %d\n", p.RequestTimeout))
	sb.WriteString("avwiki_concurrent_enabled = " + boolStr(p.AvwikiConcurrentEnabled) + "\n")
	sb.WriteString(fmt.Sprintf("avwiki_max_concurrent = %d\n\n", p.AvwikiMaxConcurrent))

	sb.WriteString("[classification]\n")
	sb.WriteString("mode = " + p.Mode + "\n")
	sb.WriteString("auto_apply_preferences = " + boolStr(p.AutoApplyPreferences) + "\n\n")

	sb.WriteString("[cache]\n")
	sb.WriteString(fmt.Sprintf("ttl_days = %d\n", p.CacheTTLDays))
	sb.WriteString(fmt.Sprintf("max_size_mb = %d\n", p.CacheMaxSizeMB))
	sb.WriteString("auto_cleanup_on_exit = " + boolStr(p.CacheAutoCleanOnExit) + "\n\n")

	sb.WriteString("[go_integration]\n")
	sb.WriteString("enabled = " + boolStr(p.GoEnabled) + "\n")
	sb.WriteString("exe_path = " + p.GoExePath + "\n")
	sb.WriteString(fmt.Sprintf("scan_workers = %d\n", p.ScanWorkers))
	sb.WriteString("move_conflict_strategy = " + p.MoveConflictStrategy + "\n")
	sb.WriteString("enable_operation_log = " + boolStr(p.EnableOperationLog) + "\n")
	sb.WriteString("log_dir = " + p.LogDir + "\n")

	return sb.String()
}

