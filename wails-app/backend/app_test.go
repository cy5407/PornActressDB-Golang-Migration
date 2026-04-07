package backend

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
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
	return app
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

	iniContent := buildIni(original)

	parsed := defaultPreferences()
	parseIni(iniContent, &parsed)

	if parsed.BatchSize != 7 {
		t.Errorf("BatchSize round-trip failed: got %d", parsed.BatchSize)
	}
	if parsed.Mode != "auto" {
		t.Errorf("Mode round-trip failed: got %s", parsed.Mode)
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
		{"SOD CREATE", true},        // prefix match
		{"UNKNOWN", false},
		{"", false},
		{"S1 NO.1 STYLE", true},     // multi-word suffix with dot (plan-specified edge case)
		{"sod create", true},        // case-insensitive prefix match
		{"SODCREATE", false},        // no space separator → no prefix match
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
