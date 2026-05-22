package backend

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"actress-classifier/pkg/database"
	"actress-classifier/pkg/pathutil"
)

// newTestApp builds an App ready for unit testing.
// It uses a temporary directory so tests are hermetic.
func newTestApp(t *testing.T) *App {
	t.Helper()
	tmp := t.TempDir()

	// Write a minimal config.ini
	cfgPath := filepath.Join(tmp, "config.ini")
	cfg := "[database]\njson_data_dir = " + filepath.Join(tmp, "db") + "\n[go_integration]\nlog_dir = " + filepath.Join(tmp, "logs") + "\n"
	if err := os.WriteFile(cfgPath, []byte(cfg), 0600); err != nil {
		t.Fatalf("failed to write test config.ini: %v", err)
	}

	app := NewApp()
	app.cfgPath = cfgPath
	app.mover.LogDir = filepath.Join(tmp, "logs")
	app.Startup(context.Background())
	// Phase A3: DualWriteStore holds a SQLite handle that Windows
	// refuses to delete while open. Close it before t.TempDir cleanup.
	t.Cleanup(func() {
		if app.db != nil {
			_ = app.db.Close()
			app.db = nil
		}
	})
	return app
}

func withFakeExecutable(t *testing.T, exePath string) {
	t.Helper()
	old := osExecutable
	osExecutable = func() (string, error) { return exePath, nil }
	t.Cleanup(func() { osExecutable = old })
}

func writeExecutableScript(t *testing.T, path, content string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(content), 0o755); err != nil {
		t.Fatalf("failed to write executable %s: %v", path, err)
	}
}

// ============================================================================
// ScanDirectory
// ============================================================================

func TestScanDirectory_Empty(t *testing.T) {
	app := newTestApp(t)
	tmp := t.TempDir()
	results := app.ScanDirectory(tmp, 4, true)
	if len(results) != 0 {
		t.Errorf("expected 0 results for empty dir, got %d", len(results))
	}
}

func TestScanDirectory_FindsCode(t *testing.T) {
	app := newTestApp(t)
	tmp := t.TempDir()

	// Create a fake video file with a recognisable code
	fakeFile := filepath.Join(tmp, "STARS-707.mp4")
	if err := os.WriteFile(fakeFile, []byte("fake"), 0600); err != nil {
		t.Fatal(err)
	}

	results := app.ScanDirectory(tmp, 4, true)
	if len(results) == 0 {
		t.Fatal("expected at least 1 result")
	}
	if results[0].Code == "" {
		t.Error("expected non-empty Code")
	}
}

func TestScanDirectory_IgnoresNonVideoFiles(t *testing.T) {
	app := newTestApp(t)
	tmp := t.TempDir()

	if err := os.WriteFile(filepath.Join(tmp, "STARS-707.mp4"), []byte("video"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(tmp, "IMAGE-001.jpg"), []byte("image"), 0600); err != nil {
		t.Fatal(err)
	}

	results := app.ScanDirectory(tmp, 4, true)
	if len(results) != 1 {
		t.Fatalf("expected only video files to be scanned, got %d results", len(results))
	}
	if results[0].Code != "STARS-707" {
		t.Fatalf("expected STARS-707, got %q", results[0].Code)
	}
}

func TestScanDirectory_NonRecursive(t *testing.T) {
	app := newTestApp(t)
	tmp := t.TempDir()

	sub := filepath.Join(tmp, "sub")
	if err := os.Mkdir(sub, 0700); err != nil {
		t.Fatal(err)
	}
	// File in sub directory should not be found when recursive=false
	if err := os.WriteFile(filepath.Join(sub, "ABW-001.mp4"), []byte("fake"), 0600); err != nil {
		t.Fatal(err)
	}

	results := app.ScanDirectory(tmp, 4, false)
	if len(results) != 0 {
		t.Errorf("expected 0 results with recursive=false, got %d", len(results))
	}
}

// ============================================================================
// BatchSearch
// ============================================================================

func TestBatchSearch_UsesLegacyCacheWhenSourceEmpty(t *testing.T) {
	app := newTestApp(t)
	if err := app.db.AddVideo(&database.VideoData{
		Code:         "ABP-001",
		Title:        "cached-title",
		Studio:       "cached-studio",
		ReleaseDate:  "2024-01-01",
		URL:          "https://cached.example",
		Actresses:    []string{"cached-actress"},
		SearchStatus: "searched_found",
		SearchMethod: "cached-method",
	}); err != nil {
		t.Fatalf("failed to seed cached video: %v", err)
	}

	runnerCalled := false
	app.batchSearchRunner = func(codes []string, workers int, source string) []SearchResult {
		runnerCalled = true
		return []SearchResult{{
			Code:   "ABP-001",
			Title:  "fresh-title",
			Method: "runner",
		}}
	}

	results := app.batchSearch([]string{"ABP-001"}, 3, "")
	if runnerCalled {
		t.Fatal("expected empty-source BatchSearch to use legacy cache instead of runner")
	}
	if len(results) != 1 {
		t.Fatalf("expected 1 cached result, got %d", len(results))
	}
	if results[0].Title != "cached-title" {
		t.Fatalf("expected cached title, got %q", results[0].Title)
	}
	if results[0].Method != "cached-method" {
		t.Fatalf("expected cached method, got %q", results[0].Method)
	}
}

func TestBatchSearchAVWiki_BypassesLegacyCache(t *testing.T) {
	app := newTestApp(t)
	if err := app.db.AddVideo(&database.VideoData{
		Code:         "ABP-001",
		Title:        "cached-title",
		Studio:       "cached-studio",
		ReleaseDate:  "2024-01-01",
		URL:          "https://cached.example",
		Actresses:    []string{"cached-actress"},
		SearchStatus: "searched_found",
		SearchMethod: "cached-method",
	}); err != nil {
		t.Fatalf("failed to seed cached video: %v", err)
	}

	runnerCalled := false
	var capturedCodes []string
	var capturedSource string
	app.batchSearchRunner = func(codes []string, workers int, source string) []SearchResult {
		runnerCalled = true
		capturedCodes = append([]string(nil), codes...)
		capturedSource = source
		return []SearchResult{{
			Code:   "ABP-001",
			Title:  "fresh-title",
			Method: "avwiki",
		}}
	}

	results := app.BatchSearchAVWiki([]string{"ABP-001"}, 3)
	if !runnerCalled {
		t.Fatal("expected source-specific BatchSearchAVWiki to bypass legacy cache and call runner")
	}
	if len(capturedCodes) != 1 || capturedCodes[0] != "ABP-001" {
		t.Fatalf("expected runner to receive cached code, got %+v", capturedCodes)
	}
	if capturedSource != batchSearchSourceAVWiki {
		t.Fatalf("expected source=%q, got %q", batchSearchSourceAVWiki, capturedSource)
	}
	if len(results) != 1 {
		t.Fatalf("expected 1 fresh result, got %d", len(results))
	}
	if results[0].Title != "fresh-title" {
		t.Fatalf("expected fresh title from runner, got %q", results[0].Title)
	}
	if results[0].Method != "avwiki" {
		t.Fatalf("expected fresh method from runner, got %q", results[0].Method)
	}
}

func TestBatchSearchJAVDB_BypassesLegacyCache(t *testing.T) {
	app := newTestApp(t)
	if err := app.db.AddVideo(&database.VideoData{
		Code:         "ABP-001",
		Title:        "cached-title",
		Studio:       "cached-studio",
		ReleaseDate:  "2024-01-01",
		URL:          "https://cached.example",
		Actresses:    []string{"cached-actress"},
		SearchStatus: "searched_found",
		SearchMethod: "cached-method",
	}); err != nil {
		t.Fatalf("failed to seed cached video: %v", err)
	}

	runnerCalled := false
	var capturedCodes []string
	var capturedSource string
	app.batchSearchRunner = func(codes []string, workers int, source string) []SearchResult {
		runnerCalled = true
		capturedCodes = append([]string(nil), codes...)
		capturedSource = source
		return []SearchResult{{
			Code:   "ABP-001",
			Title:  "fresh-title",
			Method: "javdb",
		}}
	}

	results := app.BatchSearchJAVDB([]string{"ABP-001"}, 3)
	if !runnerCalled {
		t.Fatal("expected source-specific BatchSearchJAVDB to bypass legacy cache and call runner")
	}
	if len(capturedCodes) != 1 || capturedCodes[0] != "ABP-001" {
		t.Fatalf("expected runner to receive cached code, got %+v", capturedCodes)
	}
	if capturedSource != batchSearchSourceJAVDB {
		t.Fatalf("expected source=%q, got %q", batchSearchSourceJAVDB, capturedSource)
	}
	if len(results) != 1 {
		t.Fatalf("expected 1 fresh result, got %d", len(results))
	}
	if results[0].Title != "fresh-title" {
		t.Fatalf("expected fresh title from runner, got %q", results[0].Title)
	}
	if results[0].Method != "javdb" {
		t.Fatalf("expected fresh method from runner, got %q", results[0].Method)
	}
}

func TestBatchSearchAVWiki_NotFoundCreatesMinimalSourceStatusRecord(t *testing.T) {
	app := newTestApp(t)
	app.batchSearchRunner = func(codes []string, workers int, source string) []SearchResult {
		return []SearchResult{{
			Code:      "NEW-001",
			Error:     "未找到結果",
			ErrorKind: "not_found",
		}}
	}

	results := app.BatchSearchAVWiki([]string{"NEW-001"}, 1)
	if len(results) != 1 {
		t.Fatalf("expected 1 result, got %d", len(results))
	}

	video, err := app.db.GetVideo("NEW-001")
	if err != nil {
		t.Fatalf("expected not_found result to create db record: %v", err)
	}
	if video.AVWikiActressStatus != "not_found" {
		t.Fatalf("expected avwiki_actress_status=not_found, got %q", video.AVWikiActressStatus)
	}
	if video.AVWikiLastSearchDate == "" {
		t.Fatal("expected avwiki_last_search_date to be recorded")
	}
	if video.CreatedAt == "" {
		t.Fatal("expected created_at to be initialized for brand-new record")
	}
	if video.UpdatedAt == "" {
		t.Fatal("expected updated_at to be initialized for brand-new record")
	}
	if video.LastSearchDate == "" {
		t.Fatal("expected last_search_date to use NewVideo defaults")
	}
	if video.SearchStatus != "searched_not_found" {
		t.Fatalf("expected search_status=%q for not-found result, got %q", "searched_not_found", video.SearchStatus)
	}
	if video.Actresses == nil {
		t.Fatal("expected actresses slice to be initialized, got nil")
	}
}

func TestBatchSearchJAVDB_NotFoundPreservesExistingOverallSuccess(t *testing.T) {
	app := newTestApp(t)
	if err := app.db.AddVideo(&database.VideoData{
		Code:                 "KEEP-001",
		Title:                "Existing Title",
		Studio:               "S1",
		ReleaseDate:          "2024-01-01",
		URL:                  "https://example.com/keep-001",
		Actresses:            []string{"A"},
		SearchStatus:         "searched_found",
		SearchMethod:         "avwiki",
		LastSearchDate:       "2026-04-10T00:00:00Z",
		AVWikiActressStatus:  "found",
		AVWikiLastSearchDate: "2026-04-10T00:00:00Z",
	}); err != nil {
		t.Fatalf("failed to seed existing video: %v", err)
	}
	app.batchSearchRunner = func(codes []string, workers int, source string) []SearchResult {
		return []SearchResult{{
			Code:      "KEEP-001",
			Error:     "未找到結果",
			ErrorKind: "not_found",
		}}
	}

	_ = app.BatchSearchJAVDB([]string{"KEEP-001"}, 1)

	video, err := app.db.GetVideo("KEEP-001")
	if err != nil {
		t.Fatalf("expected existing video to remain in db: %v", err)
	}
	if video.SearchStatus != "searched_found" {
		t.Fatalf("expected search_status to stay searched_found, got %q", video.SearchStatus)
	}
	if video.SearchMethod != "avwiki" {
		t.Fatalf("expected search_method to stay avwiki, got %q", video.SearchMethod)
	}
	if video.JAVDBActressStatus != "not_found" {
		t.Fatalf("expected javdb_actress_status=not_found, got %q", video.JAVDBActressStatus)
	}
	if video.AVWikiActressStatus != "found" {
		t.Fatalf("expected avwiki_actress_status to stay found, got %q", video.AVWikiActressStatus)
	}
}

func TestBatchSearchAVWiki_SuccessPreservesOtherSourceStatusAndUpdatesOverallSummary(t *testing.T) {
	app := newTestApp(t)
	if err := app.db.AddVideo(&database.VideoData{
		Code:                "MERGE-001",
		SearchStatus:        "imported",
		SearchMethod:        "legacy-import",
		LastSearchDate:      "2026-04-09T00:00:00Z",
		JAVDBActressStatus:  "not_found",
		JAVDBLastSearchDate: "2026-04-09T00:00:00Z",
	}); err != nil {
		t.Fatalf("failed to seed existing video: %v", err)
	}
	app.batchSearchRunner = func(codes []string, workers int, source string) []SearchResult {
		return []SearchResult{{
			Code:      "MERGE-001",
			Title:     "Merged Title",
			Studio:    "MOODYZ",
			Release:   "2024-02-02",
			URL:       "https://example.com/merge-001",
			Actresses: []string{"Merged Actress"},
			Method:    "avwiki",
		}}
	}

	_ = app.BatchSearchAVWiki([]string{"MERGE-001"}, 1)

	video, err := app.db.GetVideo("MERGE-001")
	if err != nil {
		t.Fatalf("expected merged video to remain in db: %v", err)
	}
	if video.JAVDBActressStatus != "not_found" {
		t.Fatalf("expected javdb_actress_status to stay not_found, got %q", video.JAVDBActressStatus)
	}
	if video.AVWikiActressStatus != "found" {
		t.Fatalf("expected avwiki_actress_status=found, got %q", video.AVWikiActressStatus)
	}
	if video.SearchStatus != "searched_found" {
		t.Fatalf("expected overall search_status to become searched_found, got %q", video.SearchStatus)
	}
	if video.SearchMethod != "avwiki" {
		t.Fatalf("expected overall search_method to become avwiki, got %q", video.SearchMethod)
	}
	if video.Title != "Merged Title" {
		t.Fatalf("expected title to update from source-specific success, got %q", video.Title)
	}
}

func TestDbGetVideo_ReturnsEnsureDBLoadError(t *testing.T) {
	tmp := t.TempDir()
	cfgPath := filepath.Join(tmp, "config.ini")
	dbDir := filepath.Join(tmp, "db")
	if err := os.MkdirAll(dbDir, 0o755); err != nil {
		t.Fatalf("failed to create db dir: %v", err)
	}
	cfg := "[database]\njson_data_dir = " + dbDir + "\n"
	if err := os.WriteFile(cfgPath, []byte(cfg), 0o600); err != nil {
		t.Fatalf("failed to write config: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dbDir, "data.json"), []byte("{broken json"), 0o600); err != nil {
		t.Fatalf("failed to write broken data.json: %v", err)
	}

	app := NewApp()
	app.cfgPath = cfgPath

	_, err := app.DbGetVideo("BROKEN-001")
	if err == nil {
		t.Fatal("expected DbGetVideo to surface ensureDB load error")
	}
	if !strings.Contains(err.Error(), "failed to parse database JSON") {
		t.Fatalf("expected parse error from ensureDB, got %v", err)
	}
}

func TestEnsureDB_ClearsInstanceWhenLoadFails(t *testing.T) {
	tmp := t.TempDir()
	cfgPath := filepath.Join(tmp, "config.ini")
	dbDir := filepath.Join(tmp, "db")
	if err := os.MkdirAll(dbDir, 0o755); err != nil {
		t.Fatalf("failed to create db dir: %v", err)
	}
	cfg := "[database]\njson_data_dir = " + dbDir + "\n"
	if err := os.WriteFile(cfgPath, []byte(cfg), 0o600); err != nil {
		t.Fatalf("failed to write config: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dbDir, "data.json"), []byte("{broken json"), 0o600); err != nil {
		t.Fatalf("failed to write broken data.json: %v", err)
	}

	app := NewApp()
	app.cfgPath = cfgPath
	if err := app.ensureDB(); err == nil {
		t.Fatal("expected ensureDB to return error on load failure")
	}
	if app.db != nil {
		t.Fatal("expected ensureDB to clear db instance after load failure")
	}
}

func TestBatchSearch_ReturnsNoResultsWhenEnsureDBFails(t *testing.T) {
	tmp := t.TempDir()
	cfgPath := filepath.Join(tmp, "config.ini")
	dbDir := filepath.Join(tmp, "db")
	if err := os.MkdirAll(dbDir, 0o755); err != nil {
		t.Fatalf("failed to create db dir: %v", err)
	}
	cfg := "[database]\njson_data_dir = " + dbDir + "\n"
	if err := os.WriteFile(cfgPath, []byte(cfg), 0o600); err != nil {
		t.Fatalf("failed to write config: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dbDir, "data.json"), []byte("{broken json"), 0o600); err != nil {
		t.Fatalf("failed to write broken data.json: %v", err)
	}

	app := NewApp()
	app.cfgPath = cfgPath
	results := app.BatchSearch([]string{"BROKEN-001"}, 1)
	if len(results) != 0 {
		t.Fatalf("expected BatchSearch to abort on ensureDB failure, got %d results", len(results))
	}
	if app.db != nil {
		t.Fatal("expected db to remain nil after failed BatchSearch init")
	}
}

func TestGetActressPrimaryStudios_ReturnsEmptyWhenEnsureDBFails(t *testing.T) {
	tmp := t.TempDir()
	cfgPath := filepath.Join(tmp, "config.ini")
	dbDir := filepath.Join(tmp, "db")
	if err := os.MkdirAll(dbDir, 0o755); err != nil {
		t.Fatalf("failed to create db dir: %v", err)
	}
	cfg := "[database]\njson_data_dir = " + dbDir + "\n"
	if err := os.WriteFile(cfgPath, []byte(cfg), 0o600); err != nil {
		t.Fatalf("failed to write config: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dbDir, "data.json"), []byte("{broken json"), 0o600); err != nil {
		t.Fatalf("failed to write broken data.json: %v", err)
	}

	app := NewApp()
	app.cfgPath = cfgPath
	result := app.GetActressPrimaryStudios([]string{"葵司"})
	if len(result) != 0 {
		t.Fatalf("expected empty result when ensureDB fails, got %#v", result)
	}
}

func TestPythonSearch_UsesRealScriptPathAndSubprocess(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("test relies on POSIX shell script shims")
	}
	tmp := t.TempDir()
	exeDir := filepath.Join(tmp, "bin")
	scriptDir := filepath.Join(tmp, "src", "scrapers")
	if err := os.MkdirAll(exeDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(scriptDir, 0o755); err != nil {
		t.Fatal(err)
	}
	fakeExe := filepath.Join(exeDir, "app.exe")
	if err := os.WriteFile(fakeExe, []byte(""), 0o644); err != nil {
		t.Fatal(err)
	}
	withFakeExecutable(t, fakeExe)

	pythonDir := filepath.Join(tmp, "py")
	if err := os.MkdirAll(pythonDir, 0o755); err != nil {
		t.Fatal(err)
	}
	python3 := filepath.Join(pythonDir, "python3")
	writeExecutableScript(t, python3, "#!/bin/sh\nif [ \"$1\" = \"-X\" ]; then\n  shift 2\nfi\nexec /bin/sh \"$1\" \"$2\"\n")
	oldPath := os.Getenv("PATH")
	t.Setenv("PATH", pythonDir+string(os.PathListSeparator)+oldPath)

	writeExecutableScript(t, filepath.Join(scriptDir, "run_search.py"), "#!/bin/sh\nprintf '{\"code\":\"%s\",\"title\":\"real subprocess\",\"method\":\"python\"}' \"$1\"\n")

	app := newTestApp(t)
	app.ctx = context.Background()
	res, err := app.PythonSearch("ABP-123")
	if err != nil {
		t.Fatalf("PythonSearch() error = %v", err)
	}
	if res.Code != "ABP-123" || res.Title != "real subprocess" || res.Method != "python" {
		t.Fatalf("PythonSearch() = %+v", res)
	}
}

func TestBatchSearch_StreamsRealScriptOutputAndPersistsResults(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("test relies on POSIX shell script shims")
	}
	tmp := t.TempDir()
	exeDir := filepath.Join(tmp, "bin")
	scriptDir := filepath.Join(tmp, "src", "scrapers")
	if err := os.MkdirAll(exeDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(scriptDir, 0o755); err != nil {
		t.Fatal(err)
	}
	fakeExe := filepath.Join(exeDir, "app.exe")
	if err := os.WriteFile(fakeExe, []byte(""), 0o644); err != nil {
		t.Fatal(err)
	}
	withFakeExecutable(t, fakeExe)

	pythonDir := filepath.Join(tmp, "py")
	if err := os.MkdirAll(pythonDir, 0o755); err != nil {
		t.Fatal(err)
	}
	writeExecutableScript(t, filepath.Join(pythonDir, "python3"), "#!/bin/sh\nif [ \"$1\" = \"-X\" ]; then\n  shift 2\nfi\nexec /bin/sh \"$1\" \"$2\"\n")
	oldPath := os.Getenv("PATH")
	t.Setenv("PATH", pythonDir+string(os.PathListSeparator)+oldPath)
	writeExecutableScript(t, filepath.Join(scriptDir, "run_batch_search.py"), "#!/bin/sh\nread -r input\nprintf '{\"code\":\"%s\",\"title\":\"first\",\"method\":\"batch\"}\\n' \"A1\"\nprintf '{\"code\":\"%s\",\"error\":\"未找到結果\",\"error_kind\":\"not_found\"}\\n' \"A2\"\n")

	app := newTestApp(t)
	app.ctx = context.Background()
	results := app.BatchSearchAVWiki([]string{"A1", "A2"}, 2)
	if len(results) != 2 {
		t.Fatalf("expected 2 results, got %d", len(results))
	}
	if results[0].Code != "A1" || results[0].Title != "first" {
		t.Fatalf("unexpected first result: %+v", results[0])
	}
	video, err := app.db.GetVideo("A1")
	if err != nil {
		t.Fatalf("expected persisted A1: %v", err)
	}
	if video.AVWikiActressStatus != "found" {
		t.Fatalf("expected found status, got %q", video.AVWikiActressStatus)
	}
	video2, err := app.db.GetVideo("A2")
	if err != nil {
		t.Fatalf("expected persisted A2: %v", err)
	}
	if video2.AVWikiActressStatus != "not_found" {
		t.Fatalf("expected not_found status, got %q", video2.AVWikiActressStatus)
	}
}

// ============================================================================
// MoveFile
// ============================================================================

func TestMoveFile_BasicMove(t *testing.T) {
	app := newTestApp(t)
	tmp := t.TempDir()

	src := filepath.Join(tmp, "src.txt")
	dst := filepath.Join(tmp, "sub", "dst.txt")
	if err := os.WriteFile(src, []byte("hello"), 0600); err != nil {
		t.Fatal(err)
	}

	result := app.MoveFile(src, dst, "skip")
	if !result.Success {
		t.Errorf("expected success, got error: %s", result.Error)
	}
	if _, err := os.Stat(dst); err != nil {
		t.Errorf("destination file not found: %v", err)
	}
}

func TestMoveFile_SkipConflict(t *testing.T) {
	app := newTestApp(t)
	tmp := t.TempDir()

	src := filepath.Join(tmp, "src.txt")
	dst := filepath.Join(tmp, "dst.txt")
	if err := os.WriteFile(src, []byte("hello"), 0600); err != nil {
		t.Fatal(err)
	}
	// Pre-create destination
	if err := os.WriteFile(dst, []byte("existing"), 0600); err != nil {
		t.Fatal(err)
	}

	result := app.MoveFile(src, dst, "skip")
	if !result.Success || !result.Skipped {
		t.Errorf("expected skipped=true, got success=%v skipped=%v", result.Success, result.Skipped)
	}
}

// ============================================================================
// BatchMove
// ============================================================================

func TestBatchMove_Empty(t *testing.T) {
	app := newTestApp(t)
	result := app.BatchMove(nil, "skip")
	if result.TotalItems != 0 {
		t.Errorf("expected 0 total items, got %d", result.TotalItems)
	}
}

func TestBatchMoveJSON_ValidJSON(t *testing.T) {
	app := newTestApp(t)
	tmp := t.TempDir()

	src := filepath.Join(tmp, "a.txt")
	dst := filepath.Join(tmp, "b.txt")
	if err := os.WriteFile(src, []byte("data"), 0600); err != nil {
		t.Fatal(err)
	}

	items := []MoveItemRequest{{Source: src, Destination: dst}}
	jsonBytes, _ := json.Marshal(items)

	result := app.BatchMoveJSON(string(jsonBytes), "skip")
	if result.SuccessCount != 1 {
		t.Errorf("expected 1 success, got %d (failed=%d)", result.SuccessCount, result.FailedCount)
	}
}

func TestBatchMoveJSON_InvalidJSON(t *testing.T) {
	app := newTestApp(t)
	result := app.BatchMoveJSON("not-json", "skip")
	if result.Status != "failed" {
		t.Errorf("expected status=failed for invalid JSON, got %s", result.Status)
	}
}

func TestPlanDirMergeMoves(t *testing.T) {
	app := newTestApp(t)
	tmp := t.TempDir()

	srcDir := filepath.Join(tmp, "src")
	dstDir := filepath.Join(tmp, "dst")
	subDir := filepath.Join(srcDir, "sub")

	if err := os.MkdirAll(subDir, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(srcDir, "video.mp4"), []byte("video"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(subDir, "note.txt"), []byte("note"), 0600); err != nil {
		t.Fatal(err)
	}

	items, err := app.PlanDirMergeMoves([]DirMoveItem{{
		Source:      srcDir,
		Destination: dstDir,
		OnConflict:  "rename",
	}})
	if err != nil {
		t.Fatalf("expected nil error, got %v", err)
	}

	if len(items) != 2 {
		t.Fatalf("expected 2 move items, got %d", len(items))
	}

	bySource := make(map[string]MoveItemRequest, len(items))
	for _, item := range items {
		bySource[item.Source] = item
		if item.OnConflict != "rename" {
			t.Errorf("expected on_conflict=rename for %q, got %q", item.Source, item.OnConflict)
		}
	}

	videoSrc := filepath.Join(srcDir, "video.mp4")
	videoItem, ok := bySource[videoSrc]
	if !ok {
		t.Fatalf("missing move item for %q", videoSrc)
	}
	if videoItem.Destination != filepath.Join(dstDir, "video.mp4") {
		t.Errorf("unexpected video destination: got %q", videoItem.Destination)
	}

	noteSrc := filepath.Join(subDir, "note.txt")
	noteItem, ok := bySource[noteSrc]
	if !ok {
		t.Fatalf("missing move item for %q", noteSrc)
	}
	if noteItem.Destination != filepath.Join(dstDir, "sub", "note.txt") {
		t.Errorf("unexpected note destination: got %q", noteItem.Destination)
	}
}

func TestPlanDirMergeMoves_DestinationInsideSource(t *testing.T) {
	app := newTestApp(t)
	tmp := t.TempDir()

	srcDir := filepath.Join(tmp, "src")
	dstDir := filepath.Join(srcDir, "nested-dst")

	if err := os.MkdirAll(srcDir, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(srcDir, "video.mp4"), []byte("video"), 0600); err != nil {
		t.Fatal(err)
	}

	_, err := app.PlanDirMergeMoves([]DirMoveItem{{
		Source:      srcDir,
		Destination: dstDir,
	}})
	if err == nil {
		t.Fatal("expected error when destination is inside source")
	}
}

func TestIsSameOrNestedPath_DifferentVolumes(t *testing.T) {
	sameOrNested, err := pathutil.IsSameOrNestedPath(`C:\source`, `D:\dest`)
	if err != nil {
		t.Fatalf("expected nil error for different volumes, got %v", err)
	}
	if sameOrNested {
		t.Fatal("expected different volumes to not be treated as same or nested")
	}
}

func TestPlanDirMergeMoves_SourceNotFound(t *testing.T) {
	app := newTestApp(t)
	tmp := t.TempDir()

	srcDir := filepath.Join(tmp, "missing")
	dstDir := filepath.Join(tmp, "dst")

	_, err := app.PlanDirMergeMoves([]DirMoveItem{{
		Source:      srcDir,
		Destination: dstDir,
	}})
	if err == nil {
		t.Fatal("expected error when source directory does not exist")
	}
}

func TestCheckConflicts_DetectsExistingMergeTargets(t *testing.T) {
	app := newTestApp(t)
	tmp := t.TempDir()

	srcDir := filepath.Join(tmp, "天羽りりか")
	dstDir := filepath.Join(tmp, "SOD", "天羽りりか")

	if err := os.MkdirAll(srcDir, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(dstDir, 0700); err != nil {
		t.Fatal(err)
	}

	srcFile := filepath.Join(srcDir, "OFSD-040.mp4")
	dstFile := filepath.Join(dstDir, "OFSD-040.mp4")
	if err := os.WriteFile(srcFile, []byte("src"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(dstFile, []byte("dst"), 0600); err != nil {
		t.Fatal(err)
	}

	items, err := app.PlanDirMergeMoves([]DirMoveItem{{
		Source:      srcDir,
		Destination: dstDir,
	}})
	if err != nil {
		t.Fatalf("expected nil error, got %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("expected 1 move item, got %d", len(items))
	}

	conflicts := app.CheckConflicts(items)
	if len(conflicts) != 1 {
		t.Fatalf("expected 1 conflict, got %d", len(conflicts))
	}
	if conflicts[0].Source != srcFile {
		t.Fatalf("unexpected conflict source: got %q", conflicts[0].Source)
	}
	if conflicts[0].Destination != dstFile {
		t.Fatalf("unexpected conflict destination: got %q", conflicts[0].Destination)
	}
}

func TestCheckDirConflicts_IgnoresSameSourceAndDestination(t *testing.T) {
	app := newTestApp(t)
	tmp := t.TempDir()

	dir := filepath.Join(tmp, "SOD", "天羽りりか")
	if err := os.MkdirAll(dir, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "OFSD-040.mp4"), []byte("video"), 0600); err != nil {
		t.Fatal(err)
	}

	conflicts := app.CheckDirConflicts([]DirMoveItem{{
		Source:      dir,
		Destination: dir,
	}})
	if len(conflicts) != 0 {
		t.Fatalf("expected same source and destination to be ignored, got %d conflicts", len(conflicts))
	}
}

// ============================================================================
// Preferences
// ============================================================================

func TestGetPreferences_Defaults(t *testing.T) {
	app := newTestApp(t)
	// Use a non-existent config path to get defaults
	app.cfgPath = filepath.Join(t.TempDir(), "nonexistent.ini")

	prefs, err := app.GetPreferences()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if prefs.BatchSize != 10 {
		t.Errorf("expected default BatchSize=10, got %d", prefs.BatchSize)
	}
}

func TestUpdateAndGetPreferences(t *testing.T) {
	app := newTestApp(t)

	prefs, err := app.GetPreferences()
	if err != nil {
		t.Fatal(err)
	}
	prefs.BatchSize = 42
	prefs.Mode = "auto"

	if err := app.UpdatePreferences(prefs); err != nil {
		t.Fatalf("UpdatePreferences failed: %v", err)
	}

	got, err := app.GetPreferences()
	if err != nil {
		t.Fatal(err)
	}
	if got.BatchSize != 42 {
		t.Errorf("expected BatchSize=42, got %d", got.BatchSize)
	}
	if got.Mode != "auto" {
		t.Errorf("expected Mode=auto, got %s", got.Mode)
	}
}

func TestResetPreferences(t *testing.T) {
	app := newTestApp(t)

	// Write non-default prefs
	p := defaultPreferences()
	p.BatchSize = 99
	_ = app.UpdatePreferences(p)

	if err := app.ResetPreferences(); err != nil {
		t.Fatal(err)
	}
	got, _ := app.GetPreferences()
	if got.BatchSize != 10 {
		t.Errorf("expected reset BatchSize=10, got %d", got.BatchSize)
	}
}

// ============================================================================
// Ini parser helpers
// ============================================================================

func TestBuildIni_RoundTrip(t *testing.T) {
	original := defaultPreferences()
	original.BatchSize = 7
	original.Mode = "auto"
	original.PythonExePath = `venv\Scripts\python.exe`

	iniContent := buildIni(original)

	parsed := defaultPreferences()
	parseIni(iniContent, &parsed)

	if parsed.BatchSize != 7 {
		t.Errorf("BatchSize round-trip failed: got %d", parsed.BatchSize)
	}
	if parsed.Mode != "auto" {
		t.Errorf("Mode round-trip failed: got %s", parsed.Mode)
	}
	if parsed.PythonExePath != `venv\Scripts\python.exe` {
		t.Errorf("PythonExePath round-trip failed: got %q", parsed.PythonExePath)
	}
}

// ============================================================================
// IdentifyStudio / ListStudios
// ============================================================================

func TestIdentifyStudio_NoStudio(t *testing.T) {
	app := newTestApp(t)
	// studio may be nil if studios.json not found; IdentifyStudio must not panic
	info := app.IdentifyStudio("STARS-707")
	_ = info // just check no panic
}

func TestListStudios_ReturnsSlice(t *testing.T) {
	app := newTestApp(t)
	studios := app.ListStudios()
	if studios == nil {
		t.Error("expected non-nil slice")
	}
}

func TestLoadCodeStudioMap_FromRealFile(t *testing.T) {
	tmp := t.TempDir()
	path := filepath.Join(tmp, "studios.json")
	content := `{"SOD":["sod", "s1"], "MOODYZ":["mda", " md-01 "]}`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	got := loadCodeStudioMap(path)
	if got["SOD"] != "SOD" || got["S1"] != "SOD" || got["MDA"] != "MOODYZ" || got["MD-01"] != "MOODYZ" {
		t.Fatalf("unexpected code studio map: %#v", got)
	}
}

func TestGetStudioByCode_UsesLoadedMap(t *testing.T) {
	app := newTestApp(t)
	app.codeStudioMap = map[string]string{"STARS": "S1", "MIDE": "MOODYZ"}
	app.majorStudios = map[string]bool{"S1": true, "MOODYZ": true}
	if got := app.GetStudioByCode("STARS-707"); got != "S1" {
		t.Fatalf("GetStudioByCode() = %q, want %q", got, "S1")
	}
	if got := app.GetStudioByCode("mide123"); got != "MOODYZ" {
		t.Fatalf("GetStudioByCode() = %q, want %q", got, "MOODYZ")
	}
}

func TestGetStudioByCode_ReturnsNonMajorStudioSentinel(t *testing.T) {
	app := newTestApp(t)
	app.codeStudioMap = map[string]string{"IDEA": "IDEAPOCKET"}
	app.majorStudios = map[string]bool{"S1": true}
	if got := app.GetStudioByCode("IDEA-001"); got != "單體企劃女優" {
		t.Fatalf("GetStudioByCode() = %q, want %q", got, "單體企劃女優")
	}
}

func TestGetStudiosByCodes_BatchMapping(t *testing.T) {
	app := newTestApp(t)
	app.codeStudioMap = map[string]string{"STARS": "S1", "MIDE": "MOODYZ"}
	app.majorStudios = map[string]bool{"S1": true, "MOODYZ": true}
	got := app.GetStudiosByCodes([]string{"STARS-707", "MIDE-001", "UNKNOWN-1"})
	if got["STARS-707"] != "S1" || got["MIDE-001"] != "MOODYZ" || got["UNKNOWN-1"] != "" {
		t.Fatalf("unexpected studio mapping: %#v", got)
	}
}

// ============================================================================
// ListOperations on empty log dir
// ============================================================================

func TestListOperations_Empty(t *testing.T) {
	app := newTestApp(t)
	ops, err := app.ListOperations()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(ops) != 0 {
		t.Errorf("expected 0 ops, got %d", len(ops))
	}
}

// ============================================================================
// RollbackLast on empty history
// ============================================================================

func TestRollbackLast_EmptyHistory(t *testing.T) {
	app := newTestApp(t)
	_, err := app.RollbackLast()
	if err == nil {
		t.Error("expected error when no operations to rollback")
	}
	if !strings.Contains(err.Error(), "沒有可回滾") {
		t.Errorf("unexpected error message: %v", err)
	}
}

// ============================================================================
// matchesMajorStudio / canonicalMajorStudio
// ============================================================================

func TestMatchesMajorStudio(t *testing.T) {
	ms := map[string]bool{
		"S1":  true,
		"SOD": true,
	}
	tests := []struct {
		studio string
		want   bool
	}{
		{"S1", true},
		{"SOD", true},
		{"SOD CREATE", true}, // prefix match
		{"UNKNOWN", false},
		{"", false},
		{"S1 NO.1 STYLE", true}, // multi-word suffix with dot (plan-specified edge case)
		{"sod create", true},    // case-insensitive prefix match
		{"SODCREATE", false},    // no space separator → no prefix match
	}
	for _, tc := range tests {
		t.Run(tc.studio, func(t *testing.T) {
			got := matchesMajorStudio(tc.studio, ms)
			if got != tc.want {
				t.Errorf("matchesMajorStudio(%q) = %v, want %v", tc.studio, got, tc.want)
			}
		})
	}
}

func TestMatchesMajorStudio_EmptyMap(t *testing.T) {
	if matchesMajorStudio("SOD", map[string]bool{}) {
		t.Error("empty majorStudios should always return false")
	}
	if matchesMajorStudio("", map[string]bool{}) {
		t.Error("empty studio with empty map should return false")
	}
}

func TestBatchSearchRunnerPathReturnsPartialResultsWhenRunnerProducesThem(t *testing.T) {
	app := newTestApp(t)
	app.batchSearchRunner = func(codes []string, workers int, source string) []SearchResult {
		return []SearchResult{{Code: "OK-001", Title: "ok-title"}}
	}

	results := app.BatchSearchAVWiki([]string{"OK-001", "MISS-001"}, 1)
	if len(results) != 1 {
		t.Fatalf("expected partial results to be returned, got %d", len(results))
	}
	if results[0].Code != "OK-001" {
		t.Fatalf("expected returned result to match runner output, got %#v", results[0])
	}
}

func TestBatchSearchRunnerPathHandlesEmptyRunnerResult(t *testing.T) {
	app := newTestApp(t)
	app.batchSearchRunner = func(codes []string, workers int, source string) []SearchResult {
		return nil
	}

	results := app.BatchSearchJAVDB([]string{"EMPTY-001"}, 1)
	if len(results) != 0 {
		t.Fatalf("expected no results when runner returns none, got %d", len(results))
	}
}

func TestBatchSearchFailureDetail_PrefersScannerError(t *testing.T) {
	detail := batchSearchFailureDetail(context.Canceled, nil, "stderr text")
	if !strings.Contains(detail, "scanner error") {
		t.Fatalf("expected scanner error detail, got %q", detail)
	}
	if !strings.Contains(detail, "stderr text") {
		t.Fatalf("expected stderr to be preserved, got %q", detail)
	}
}

func TestBatchSearchFailureDetail_FallsBackToWaitError(t *testing.T) {
	detail := batchSearchFailureDetail(nil, context.DeadlineExceeded, "")
	if !strings.Contains(detail, context.DeadlineExceeded.Error()) {
		t.Fatalf("expected wait error detail, got %q", detail)
	}
}

func TestBatchSearchFailureDetail_CombinesErrorsAndStderr(t *testing.T) {
	detail := batchSearchFailureDetail(context.Canceled, context.DeadlineExceeded, "python stderr")
	if !strings.Contains(detail, "scanner error") || !strings.Contains(detail, "wait error") || !strings.Contains(detail, "python stderr") {
		t.Fatalf("expected combined detail, got %q", detail)
	}
}

func TestBatchSearchFailureDetail_UsesFallbackWhenEmpty(t *testing.T) {
	detail := batchSearchFailureDetail(nil, nil, "")
	if detail != "Python batch search 子程序異常結束" {
		t.Fatalf("expected fallback detail, got %q", detail)
	}
}

func TestResolvePythonExe_PrefersFirstAvailableUnixBinary(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("unix path lookup behavior differs on windows")
	}
	tmp := t.TempDir()
	binDir := filepath.Join(tmp, "bin")
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		t.Fatal(err)
	}
	shim := filepath.Join(binDir, "python3")
	if err := os.WriteFile(shim, []byte("#!/bin/sh\nexit 0\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	oldPath := os.Getenv("PATH")
	if err := os.Setenv("PATH", binDir+string(os.PathListSeparator)+oldPath); err != nil {
		t.Fatal(err)
	}
	defer os.Setenv("PATH", oldPath)

	if got := resolvePythonExe(""); got != shim {
		t.Fatalf("resolvePythonExe(\"\") = %q, want %q", got, shim)
	}
}

func TestResolvePythonExe_PrefersConfiguredRelativePath(t *testing.T) {
	tmp := t.TempDir()
	configPath := filepath.Join(tmp, "config.ini")
	pythonDir := filepath.Join(tmp, "venv", "Scripts")
	if runtime.GOOS != "windows" {
		pythonDir = filepath.Join(tmp, "venv", "bin")
	}
	if err := os.MkdirAll(pythonDir, 0o755); err != nil {
		t.Fatal(err)
	}

	pythonExe := filepath.Join(pythonDir, "python.exe")
	configValue := filepath.Join("venv", "Scripts", "python.exe")
	if runtime.GOOS != "windows" {
		pythonExe = filepath.Join(pythonDir, "python3")
		configValue = filepath.Join("venv", "bin", "python3")
	}
	if err := os.WriteFile(pythonExe, []byte(""), 0o755); err != nil {
		t.Fatal(err)
	}

	prefs := defaultPreferences()
	prefs.PythonExePath = configValue
	if err := os.WriteFile(configPath, []byte(buildIni(prefs)), 0o644); err != nil {
		t.Fatal(err)
	}

	if got := resolvePythonExe(configPath); got != pythonExe {
		t.Fatalf("resolvePythonExe(%q) = %q, want %q", configPath, got, pythonExe)
	}
}

func TestResolvePythonExe_PrefersExecutableRelativeVenv(t *testing.T) {
	tmp := t.TempDir()
	fakeExe := filepath.Join(tmp, "build", "bin", "backend-test")
	if err := os.MkdirAll(filepath.Dir(fakeExe), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(fakeExe, []byte(""), 0o755); err != nil {
		t.Fatal(err)
	}

	pythonDir := filepath.Join(tmp, "build", "bin", "venv", "Scripts")
	pythonExe := filepath.Join(pythonDir, "python.exe")
	if runtime.GOOS != "windows" {
		pythonDir = filepath.Join(tmp, "build", "bin", "venv", "bin")
		pythonExe = filepath.Join(pythonDir, "python3")
	}
	if err := os.MkdirAll(pythonDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(pythonExe, []byte(""), 0o755); err != nil {
		t.Fatal(err)
	}

	oldExecutable := osExecutable
	osExecutable = func() (string, error) { return fakeExe, nil }
	defer func() { osExecutable = oldExecutable }()

	if got := resolvePythonExe(""); got != pythonExe {
		t.Fatalf("resolvePythonExe(\"\") = %q, want %q", got, pythonExe)
	}
}

func TestResolveRunSearchScript_PrefersExecutableRelativePath(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("test relies on POSIX executable shim")
	}
	tmp := t.TempDir()
	fakeExe := filepath.Join(tmp, "bin", "backend-test")
	if err := os.MkdirAll(filepath.Dir(fakeExe), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(fakeExe, []byte("#!/bin/sh\nexit 0\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	relativeScript := filepath.Join(tmp, "bin", "src", "scrapers", "run_search.py")
	if err := os.MkdirAll(filepath.Dir(relativeScript), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(relativeScript, []byte("print('ok')\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	oldExecutable := osExecutable
	osExecutable = func() (string, error) { return fakeExe, nil }
	defer func() { osExecutable = oldExecutable }()

	got := resolveRunSearchScript()
	if got != relativeScript {
		t.Fatalf("resolveRunSearchScript() = %q, want %q", got, relativeScript)
	}
}

func TestPythonSearch_ExecutesRealScriptViaTempPython(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("test relies on POSIX shell script shim")
	}
	tmp := t.TempDir()
	binDir := filepath.Join(tmp, "bin")
	scriptDir := filepath.Join(tmp, "src", "scrapers")
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(scriptDir, 0o755); err != nil {
		t.Fatal(err)
	}
	pythonShim := filepath.Join(binDir, "python3")
	pythonScript := "#!/bin/sh\nshift 2\nscript=\"$1\"\ncode=\"$2\"\nexec /bin/sh \"$script\" \"$code\"\n"
	if err := os.WriteFile(pythonShim, []byte(pythonScript), 0o755); err != nil {
		t.Fatal(err)
	}
	searchScript := filepath.Join(scriptDir, "run_search.py")
	searchBody := "#!/bin/sh\ncat <<EOF\n{\"Code\":\"$1\",\"Title\":\"Title from script\",\"Method\":\"real-subprocess\"}\nEOF\n"
	if err := os.WriteFile(searchScript, []byte(searchBody), 0o755); err != nil {
		t.Fatal(err)
	}

	oldPath := os.Getenv("PATH")
	if err := os.Setenv("PATH", binDir+string(os.PathListSeparator)+oldPath); err != nil {
		t.Fatal(err)
	}
	defer os.Setenv("PATH", oldPath)

	oldExecutable := osExecutable
	osExecutable = func() (string, error) { return filepath.Join(tmp, "backend-test"), nil }
	defer func() { osExecutable = oldExecutable }()

	app := &App{ctx: context.Background()}
	result, err := app.PythonSearch("ABP-123")
	if err != nil {
		t.Fatalf("PythonSearch() error = %v", err)
	}
	if result.Code != "ABP-123" || result.Title != "Title from script" || result.Method != "real-subprocess" {
		t.Fatalf("unexpected result: %#v", result)
	}
}

func TestResolveRunBatchSearchScript_PrefersExecutableRelativePath(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("test relies on POSIX executable shim")
	}
	tmp := t.TempDir()
	fakeExe := filepath.Join(tmp, "bin", "backend-test")
	if err := os.MkdirAll(filepath.Dir(fakeExe), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(fakeExe, []byte("#!/bin/sh\nexit 0\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	relativeScript := filepath.Join(tmp, "bin", "src", "scrapers", "run_batch_search.py")
	if err := os.MkdirAll(filepath.Dir(relativeScript), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(relativeScript, []byte("print('ok')\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	oldExecutable := osExecutable
	osExecutable = func() (string, error) { return fakeExe, nil }
	defer func() { osExecutable = oldExecutable }()

	got := resolveRunBatchSearchScript()
	if got != relativeScript {
		t.Fatalf("resolveRunBatchSearchScript() = %q, want %q", got, relativeScript)
	}
}

func TestResolveConfigPath_PrefersExecutableDirectoryConfig(t *testing.T) {
	tmp := t.TempDir()
	fakeExe := filepath.Join(tmp, "bin", "backend-test")
	if err := os.MkdirAll(filepath.Dir(fakeExe), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(fakeExe, []byte("#!/bin/sh\nexit 0\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	exeConfig := filepath.Join(tmp, "bin", "config.ini")
	if err := os.WriteFile(exeConfig, []byte("[database]\njson_data_dir = db\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	oldExecutable := osExecutable
	osExecutable = func() (string, error) { return fakeExe, nil }
	defer func() { osExecutable = oldExecutable }()

	got := resolveConfigPath()
	if got != exeConfig {
		t.Fatalf("resolveConfigPath() = %q, want %q", got, exeConfig)
	}
}

func TestResolveDataDirAndLogDir_UseConfigRelativeToConfigFile(t *testing.T) {
	tmp := t.TempDir()
	cfgPath := filepath.Join(tmp, "conf", "config.ini")
	if err := os.MkdirAll(filepath.Dir(cfgPath), 0o755); err != nil {
		t.Fatal(err)
	}
	content := "[database]\njson_data_dir = data/json_db\n[go_integration]\nlog_dir = logs/test\n"
	if err := os.WriteFile(cfgPath, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	if got := resolveDataDir(cfgPath); got != filepath.Join(tmp, "conf", "data", "json_db") {
		t.Fatalf("resolveDataDir() = %q", got)
	}
	if got := resolveLogDir(cfgPath); got != filepath.Join(tmp, "conf", "logs", "test") {
		t.Fatalf("resolveLogDir() = %q", got)
	}
}

func TestLoadMajorStudios_NormalizesNames(t *testing.T) {
	tmp := t.TempDir()
	fakeExe := filepath.Join(tmp, "bin", "backend-test")
	if err := os.MkdirAll(filepath.Dir(fakeExe), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(fakeExe, []byte("#!/bin/sh\nexit 0\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	majorPath := filepath.Join(tmp, "bin", "major_studios.json")
	if err := os.WriteFile(majorPath, []byte(`["sod", " Moodyz ", "ideapocket"]`), 0o644); err != nil {
		t.Fatal(err)
	}

	oldExecutable := osExecutable
	osExecutable = func() (string, error) { return fakeExe, nil }
	defer func() { osExecutable = oldExecutable }()

	app := &App{}
	got := app.loadMajorStudios()
	for _, name := range []string{"SOD", "MOODYZ", "IDEAPOCKET"} {
		if !got[name] {
			t.Fatalf("expected major studio %q to be loaded, got %#v", name, got)
		}
	}
}

func TestCanonicalMajorStudio_LongestPrefixWins(t *testing.T) {
	got, ok := canonicalMajorStudio("MOODYZ SPECIAL LABEL", map[string]bool{"MOODYZ": true, "MOODYZ SPECIAL": true})
	if !ok {
		t.Fatal("expected canonicalMajorStudio to match")
	}
	if got != "MOODYZ SPECIAL" {
		t.Fatalf("canonicalMajorStudio() = %q, want %q", got, "MOODYZ SPECIAL")
	}
}

func TestBatchSearch_RealSubprocessUsesResolvedExecutableAndScript(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("test relies on POSIX shell script shims")
	}
	tmp := t.TempDir()
	binDir := filepath.Join(tmp, "bin")
	scriptDir := filepath.Join(binDir, "src", "scrapers")
	if err := os.MkdirAll(scriptDir, 0o755); err != nil {
		t.Fatal(err)
	}

	pythonShim := filepath.Join(binDir, "python3")
	pythonBody := "#!/bin/sh\nif [ \"$1\" = \"-X\" ]; then\n  shift 2\nfi\nexec /bin/sh \"$1\" \"$2\"\n"
	if err := os.WriteFile(pythonShim, []byte(pythonBody), 0o755); err != nil {
		t.Fatal(err)
	}

	scriptPath := filepath.Join(scriptDir, "run_batch_search.py")
	scriptBody := "#!/bin/sh\ncat <<'EOF'\n{\"Code\":\"REAL-001\",\"Title\":\"From real subprocess\",\"Method\":\"real-cli\"}\n{\"Code\":\"REAL-002\",\"Error\":\"未找到結果\",\"ErrorKind\":\"not_found\"}\nEOF\n"
	if err := os.WriteFile(scriptPath, []byte(scriptBody), 0o755); err != nil {
		t.Fatal(err)
	}

	oldPath := os.Getenv("PATH")
	if err := os.Setenv("PATH", binDir+string(os.PathListSeparator)+oldPath); err != nil {
		t.Fatal(err)
	}
	defer os.Setenv("PATH", oldPath)

	oldExecutable := osExecutable
	osExecutable = func() (string, error) { return filepath.Join(binDir, "backend-test"), nil }
	defer func() { osExecutable = oldExecutable }()

	app := newTestApp(t)

	results := app.BatchSearchAVWiki([]string{"REAL-001", "REAL-002"}, 1)
	if len(results) != 2 {
		t.Fatalf("expected 2 results from real subprocess, got %d", len(results))
	}
	if results[0].Code != "REAL-001" || results[1].Code != "REAL-002" {
		t.Fatalf("unexpected results: %#v", results)
	}
}

func TestBatchMoveJSON_RealFilesystemMovesNestedFiles(t *testing.T) {
	app := newTestApp(t)
	tmp := t.TempDir()
	srcDir := filepath.Join(tmp, "source")
	dstDir := filepath.Join(tmp, "dest")
	if err := os.MkdirAll(filepath.Join(srcDir, "nested"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(srcDir, "movie.mp4"), []byte("movie-bytes"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(srcDir, "nested", "poster.jpg"), []byte("poster-bytes"), 0o644); err != nil {
		t.Fatal(err)
	}

	plan, err := app.PlanDirMergeMoves([]DirMoveItem{{Source: srcDir, Destination: dstDir, OnConflict: "overwrite"}})
	if err != nil {
		t.Fatalf("PlanDirMergeMoves() error = %v", err)
	}
	payload, err := json.Marshal(plan)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}

	result := app.BatchMoveJSON(string(payload), "overwrite")
	if result.Status != "completed" {
		t.Fatalf("BatchMoveJSON() status = %q, want completed (failed=%d, success=%d)", result.Status, result.FailedCount, result.SuccessCount)
	}
	if result.SuccessCount != 2 {
		t.Fatalf("BatchMoveJSON() success=%d, want 2", result.SuccessCount)
	}
	if _, err := os.Stat(filepath.Join(dstDir, "movie.mp4")); err != nil {
		t.Fatalf("destination movie missing: %v", err)
	}
	if _, err := os.Stat(filepath.Join(dstDir, "nested", "poster.jpg")); err != nil {
		t.Fatalf("destination nested poster missing: %v", err)
	}
	if _, err := os.Stat(filepath.Join(srcDir, "movie.mp4")); !os.IsNotExist(err) {
		t.Fatalf("source movie should have been moved, stat err=%v", err)
	}
}

func TestLoadCodeStudioMap_ParsesRealJSON(t *testing.T) {
	tmp := t.TempDir()
	mappingPath := filepath.Join(tmp, "studios.json")
	content := `{"SOD":[" sod ","SOD-"],"MOODYZ":["moodyz"]}`
	if err := os.WriteFile(mappingPath, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	got := loadCodeStudioMap(mappingPath)
	if got["SOD"] != "SOD" || got["SOD-"] != "SOD" || got["MOODYZ"] != "MOODYZ" {
		t.Fatalf("unexpected studio map: %#v", got)
	}
}

func TestBatchSearchAVWiki_ExecutesRealBatchSubprocess(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("test relies on POSIX shell script shim")
	}

	tmp := t.TempDir()
	binDir := filepath.Join(tmp, "bin")
	scriptDir := filepath.Join(tmp, "src", "scrapers")
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(scriptDir, 0o755); err != nil {
		t.Fatal(err)
	}

	pythonShim := filepath.Join(binDir, "python3")
	pythonBody := "#!/bin/sh\nshift 2\nscript=\"$1\"\nexec /bin/sh \"$script\"\n"
	if err := os.WriteFile(pythonShim, []byte(pythonBody), 0o755); err != nil {
		t.Fatal(err)
	}

	batchScript := filepath.Join(scriptDir, "run_batch_search.py")
	batchBody := "#!/bin/sh\ncat <<'EOF'\n{\"Code\":\"REAL-001\",\"Title\":\"first title\",\"Method\":\"batch-real\"}\n{\"Code\":\"REAL-002\",\"Title\":\"second title\",\"Method\":\"batch-real\"}\nEOF\n"
	if err := os.WriteFile(batchScript, []byte(batchBody), 0o755); err != nil {
		t.Fatal(err)
	}

	oldPath := os.Getenv("PATH")
	if err := os.Setenv("PATH", binDir+string(os.PathListSeparator)+oldPath); err != nil {
		t.Fatal(err)
	}
	defer os.Setenv("PATH", oldPath)

	oldExecutable := osExecutable
	osExecutable = func() (string, error) { return filepath.Join(tmp, "backend-test"), nil }
	defer func() { osExecutable = oldExecutable }()

	app := &App{ctx: context.Background()}
	results := app.BatchSearchAVWiki([]string{"REAL-001", "REAL-002"}, 1)
	if len(results) != 2 {
		t.Fatalf("expected 2 results from real subprocess, got %d", len(results))
	}
	if results[0].Code != "REAL-001" || results[1].Code != "REAL-002" {
		t.Fatalf("unexpected results: %#v", results)
	}
	if results[0].Method != "batch-real" || results[1].Method != "batch-real" {
		t.Fatalf("unexpected methods from real subprocess: %#v", results)
	}
}
