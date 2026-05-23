package main

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"actress-classifier/pkg/database"
)

func TestParseHistoryCommandOptions_PreservesRollbackLast(t *testing.T) {
	opts, remaining := parseHistoryCommandOptions("rollback", []string{"--last", "-log-dir", "custom-logs", "-json"})

	if opts.logDir != "custom-logs" {
		t.Fatalf("logDir = %q, want custom-logs", opts.logDir)
	}
	if !opts.jsonOutput {
		t.Fatal("jsonOutput should be true")
	}
	if len(remaining) != 1 || remaining[0] != "--last" {
		t.Fatalf("remaining = %#v, want [\"--last\"]", remaining)
	}
}

func TestParseDBCommandOptions_ParsesFlagsAndRemainingArgs(t *testing.T) {
	opts, remaining := parseDBCommandOptions("list", []string{"-data-dir", "custom-db", "-json", "-full", "CODE-001"})

	if opts.dataDir != "custom-db" {
		t.Fatalf("dataDir = %q, want custom-db", opts.dataDir)
	}
	if !opts.jsonOutput {
		t.Fatal("jsonOutput should be true")
	}
	if !opts.fullOutput {
		t.Fatal("fullOutput should be true")
	}
	if len(remaining) != 1 || remaining[0] != "CODE-001" {
		t.Fatalf("remaining = %#v, want [\"CODE-001\"]", remaining)
	}
}

func TestParseMoveCommandOptions_ParsesBatchAndStrategy(t *testing.T) {
	opts := parseMoveCommandOptions([]string{"-batch", "moves.json", "-strategy", "rename", "-dry-run", "-log-dir", "custom-logs"})

	if opts.batch != "moves.json" {
		t.Fatalf("batch = %q, want moves.json", opts.batch)
	}
	if opts.strategy != "rename" {
		t.Fatalf("strategy = %q, want rename", opts.strategy)
	}
	if !opts.dryRun {
		t.Fatal("dryRun should be true")
	}
	if opts.logDir != "custom-logs" {
		t.Fatalf("logDir = %q, want custom-logs", opts.logDir)
	}
}

func TestParseIdentifyCommandOptions_ParsesFlagsAndArgs(t *testing.T) {
	opts, remaining := parseIdentifyCommandOptions([]string{"-rules", "custom.json", "-major", "-json", "STARS-001"})

	if opts.rulesFile != "custom.json" {
		t.Fatalf("rulesFile = %q, want custom.json", opts.rulesFile)
	}
	if !opts.checkMajor {
		t.Fatal("checkMajor should be true")
	}
	if !opts.jsonOutput {
		t.Fatal("jsonOutput should be true")
	}
	if len(remaining) != 1 || remaining[0] != "STARS-001" {
		t.Fatalf("remaining = %#v, want [\"STARS-001\"]", remaining)
	}
}

func TestParseIdentifyCommandOptions_ParsesNormalizeFlags(t *testing.T) {
	opts, remaining := parseIdentifyCommandOptions([]string{
		"-normalize",
		"-studio", "MOODYZ DIVA",
		"-code", "SSIS-123",
		"-rules", "custom.json",
	})

	if !opts.normalizeStudio {
		t.Fatal("normalizeStudio should be true")
	}
	if opts.normalizeInput != "MOODYZ DIVA" {
		t.Fatalf("normalizeInput = %q, want MOODYZ DIVA", opts.normalizeInput)
	}
	if opts.normalizeCode != "SSIS-123" {
		t.Fatalf("normalizeCode = %q, want SSIS-123", opts.normalizeCode)
	}
	if opts.rulesFile != "custom.json" {
		t.Fatalf("rulesFile = %q, want custom.json", opts.rulesFile)
	}
	if len(remaining) != 0 {
		t.Fatalf("remaining = %#v, want empty", remaining)
	}
}

func TestBuildStudioFixPlan_RequiresForceForKnownStudio(t *testing.T) {
	video := database.NewVideo("STARS-001")
	video.Studio = "S1"

	plan := buildStudioFixPlan(video, "MOODYZ", false)
	if plan.status != studioFixAlreadyCorrect {
		t.Fatalf("status = %q, want %q", plan.status, studioFixAlreadyCorrect)
	}
}

func TestBuildStudioFixPlan_UpdatesUnknownStudio(t *testing.T) {
	video := database.NewVideo("SSIS-001")
	video.Studio = "UNKNOWN"

	plan := buildStudioFixPlan(video, "S1", false)
	if plan.status != studioFixUpdate {
		t.Fatalf("status = %q, want %q", plan.status, studioFixUpdate)
	}
	if plan.change.From != "UNKNOWN" || plan.change.To != "S1" {
		t.Fatalf("change = %#v, want UNKNOWN -> S1", plan.change)
	}
}

func TestCleanActressesActionDryRunDoesNotBackupOrMutate(t *testing.T) {
	db, dir := setupScannerTestDB(t)
	video := database.NewVideo("ABF-062")
	video.Actresses = []string{"蒼乃美月", "顔射の美学", "蒼乃美月蒼乃美月"}
	if err := db.UpdateVideo("ABF-062", video); err != nil {
		t.Fatalf("Failed to seed video: %v", err)
	}
	if err := db.CompactJournal(); err != nil {
		t.Fatalf("Failed to compact seed data: %v", err)
	}

	result, err := cleanActressesAction(db, false)
	if err != nil {
		t.Fatalf("cleanActressesAction returned error: %v", err)
	}

	if !result.DryRun {
		t.Fatalf("expected dry-run result")
	}
	if result.BackupPath != "" {
		t.Fatalf("expected no backup path during dry-run, got %q", result.BackupPath)
	}
	if _, statErr := os.Stat(filepath.Join(dir, "backup")); !os.IsNotExist(statErr) {
		t.Fatalf("expected backup dir to be absent, got err=%v", statErr)
	}

	reloaded := database.NewJSONDatabase(dir)
	if loadErr := reloaded.Load(context.Background()); loadErr != nil {
		t.Fatalf("Failed to reload db: %v", loadErr)
	}
	current, err := reloaded.GetVideo("ABF-062")
	if err != nil {
		t.Fatalf("Failed to fetch video: %v", err)
	}
	assertActressesEqual(t, current.Actresses, []string{"蒼乃美月", "顔射の美学", "蒼乃美月蒼乃美月"})
}

func TestCleanActressesActionWriteBacksUpAndMutates(t *testing.T) {
	db, dir := setupScannerTestDB(t)
	video := database.NewVideo("ABF-177")
	video.Actresses = []string{"絶対", "瀧本雫葉", "リミットブレイク"}
	if err := db.UpdateVideo("ABF-177", video); err != nil {
		t.Fatalf("Failed to seed video: %v", err)
	}
	if err := db.CompactJournal(); err != nil {
		t.Fatalf("Failed to compact seed data: %v", err)
	}

	result, err := cleanActressesAction(db, true)
	if err != nil {
		t.Fatalf("cleanActressesAction returned error: %v", err)
	}

	if result.DryRun {
		t.Fatalf("expected write result")
	}
	if result.BackupPath == "" {
		t.Fatalf("expected backup path to be populated")
	}
	if _, statErr := os.Stat(result.BackupPath); statErr != nil {
		t.Fatalf("expected backup file to exist: %v", statErr)
	}

	reloaded := database.NewJSONDatabase(dir)
	if loadErr := reloaded.Load(context.Background()); loadErr != nil {
		t.Fatalf("Failed to reload db: %v", loadErr)
	}
	current, err := reloaded.GetVideo("ABF-177")
	if err != nil {
		t.Fatalf("Failed to fetch video: %v", err)
	}
	assertActressesEqual(t, current.Actresses, []string{"瀧本雫葉"})
}

func setupScannerTestDB(t *testing.T) (*database.DualWriteStore, string) {
	t.Helper()
	dir := t.TempDir()
	jsonDB := database.NewJSONDatabase(dir)
	if err := jsonDB.Load(context.Background()); err != nil {
		t.Fatalf("Failed to load db: %v", err)
	}
	// Tests don't exercise the SQLite mirror; pass sqlite=nil to use
	// the JSON-only embed pattern, identical to ACTRESS_DB_MODE=json_only.
	store, err := database.NewDualWriteStore(jsonDB, nil, nil)
	if err != nil {
		t.Fatalf("NewDualWriteStore: %v", err)
	}
	return store, dir
}

// loadDBWithFreshFixture builds a real classifier.exe-style data dir and
// drives loadDBOrExit through it so the env→StoreConfig wiring is
// exercised end-to-end (NewStore observes USE_SQLITE_READS via the
// resolver inside loadDBOrExit). The fixture keeps SQLite available so
// the shadow-read flag actually does something observable.
func loadDBWithFreshFixture(t *testing.T) *database.DualWriteStore {
	t.Helper()
	dir := t.TempDir()
	jsonDB := database.NewJSONDatabase(dir)
	if err := jsonDB.Load(context.Background()); err != nil {
		t.Fatalf("Failed to load db: %v", err)
	}
	if err := jsonDB.Save(); err != nil {
		t.Fatalf("Failed to seed json db: %v", err)
	}
	store := loadDBOrExit(dir)
	t.Cleanup(func() { _ = store.Close() })
	return store
}

func TestLoadDBOrExit_EnablesSQLiteReadsWhenEnvTruthy(t *testing.T) {
	cases := []string{"true", "1", "yes", "on", "TRUE", " YES "}
	for _, env := range cases {
		t.Run(env, func(t *testing.T) {
			t.Setenv("USE_SQLITE_READS", env)
			store := loadDBWithFreshFixture(t)
			if !store.UseSQLiteReads() {
				t.Errorf("USE_SQLITE_READS=%q should enable shadow reads", env)
			}
		})
	}
}

func TestLoadDBOrExit_DefaultsToJSONReads(t *testing.T) {
	for _, env := range []string{"", "false", "0", "off", "no", "garbage"} {
		t.Run(env, func(t *testing.T) {
			t.Setenv("USE_SQLITE_READS", env)
			store := loadDBWithFreshFixture(t)
			if store.UseSQLiteReads() {
				t.Errorf("USE_SQLITE_READS=%q must NOT enable shadow reads", env)
			}
		})
	}
}

func TestRunDBStats_JSONOutputIncludesSQLiteReadFallbackTotal(t *testing.T) {
	// Drive the same code path runDBStats walks (DualWriteStore.GetStats)
	// and assert the contract surfaced through `classifier.exe db stats`:
	// the new B1 counter must be present alongside Phase A3 keys and the
	// Python-parsable A0 keys.
	t.Setenv("USE_SQLITE_READS", "true")
	store := loadDBWithFreshFixture(t)

	stats, err := store.GetStats()
	if err != nil {
		t.Fatalf("GetStats: %v", err)
	}
	required := []string{
		// A0 contract keys (Python parses these).
		"video_count", "actress_count", "link_count",
		"schema_version", "created_at", "updated_at",
		"journal_size", "journal_age_seconds",
		"dirty_videos", "dirty_actresses", "dirty_links",
		"needs_compact", "total_videos",
		// A3 additions.
		"sync_degraded_total", "sync_degraded_log_size",
		// B1 addition.
		"sqlite_read_fallback_total",
	}
	for _, key := range required {
		if _, ok := stats[key]; !ok {
			t.Errorf("db stats output missing key %q (have %v)", key, keysOf(stats))
		}
	}
	if _, ok := stats["sqlite_read_fallback_total"].(int64); !ok {
		t.Errorf("sqlite_read_fallback_total type = %T, want int64", stats["sqlite_read_fallback_total"])
	}
}

func keysOf(m map[string]any) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	return out
}

func assertActressesEqual(t *testing.T, got, want []string) {
	t.Helper()
	if len(got) != len(want) {
		t.Fatalf("expected %#v, got %#v", want, got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("expected %#v, got %#v", want, got)
		}
	}
}
