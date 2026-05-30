package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
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

	current, err := db.GetVideo("ABF-062")
	if err != nil {
		t.Fatalf("Failed to fetch video: %v", err)
	}
	assertActressesEqual(t, current.Actresses, []string{"蒼乃美月", "顔射の美学", "蒼乃美月蒼乃美月"})
}

func TestCleanActressesActionWriteBacksUpAndMutates(t *testing.T) {
	db, _ := setupScannerTestDB(t)
	video := database.NewVideo("ABF-177")
	video.Actresses = []string{"絶対", "瀧本雫葉", "リミットブレイク"}
	if err := db.UpdateVideo("ABF-177", video); err != nil {
		t.Fatalf("Failed to seed video: %v", err)
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

	current, err := db.GetVideo("ABF-177")
	if err != nil {
		t.Fatalf("Failed to fetch video: %v", err)
	}
	assertActressesEqual(t, current.Actresses, []string{"瀧本雫葉"})
}

// setupScannerTestDB builds a SQLite-only runtime store rooted in a
// fresh tempdir. SkipBootstrap keeps SQLite empty (no data.json present
// anyway) so each test starts from a clean slate. The data dir is
// returned so callers can probe artefacts under <dir>/backup/, etc.
func setupScannerTestDB(t *testing.T) (*database.SQLiteStore, string) {
	t.Helper()
	dir := t.TempDir()
	store, err := database.NewStore(database.StoreConfig{
		DataDir:       dir,
		SkipBootstrap: true,
	})
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })
	return store, dir
}

func TestRunDBStats_JSONOutputIncludesContractKeys(t *testing.T) {
	// Drive the same code path runDBStats walks (SQLiteStore.GetStats)
	// and assert the Python-parsable contract: the A0 keys plus the
	// retired Phase A3 / B1 counters MUST all appear (Python's helper
	// reads every one of these).
	store, _ := setupScannerTestDB(t)

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
		// A3 additions (now retired but key must remain).
		"sync_degraded_total", "sync_degraded_log_size",
		// B1 addition (now retired but key must remain).
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

// ---------------------------------------------------------------------------
// Slice C1 — compact -json no-op + backup-restore mutual exclusion
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Slice B2 — structured not-found signal (exit 3 + stdout JSON envelope)
//
// Lock the contract that the Python helper (_is_not_found_error in
// src/services/go_cli.py) depends on: exit code 3 is reserved for the
// "lookup miss" case and the stdout payload carries a stable shape so
// future callers (GUI, log surfacing) can decode it without scraping
// stderr.
// ---------------------------------------------------------------------------

func TestNotFoundExitCode_IsThree(t *testing.T) {
	// Reordering this constant breaks Python's _is_not_found_error. If you
	// genuinely want a different code, update the Python side and the
	// docs (docs/boundary-cleanup-tasks.md, docs/ARCHITECTURE.md) in the
	// same change.
	if notFoundExitCode != 3 {
		t.Fatalf("notFoundExitCode = %d, want 3 (Python wrapper contract)", notFoundExitCode)
	}
}

func TestBuildNotFoundPayload_VideoShape(t *testing.T) {
	payload := buildNotFoundPayload("video", "code", "MISSING-001")

	if payload["success"] != false {
		t.Errorf("success = %v, want false", payload["success"])
	}
	if payload["error_kind"] != "not_found" {
		t.Errorf("error_kind = %v, want not_found", payload["error_kind"])
	}
	if payload["kind"] != "video" {
		t.Errorf("kind = %v, want video", payload["kind"])
	}
	if payload["code"] != "MISSING-001" {
		t.Errorf("code = %v, want MISSING-001", payload["code"])
	}
	if msg, _ := payload["message"].(string); !strings.Contains(msg, "video") {
		t.Errorf("message = %q, expected to mention 'video'", msg)
	}
	// Videos use `code`; `id` must NOT leak into the payload (otherwise
	// downstream consumers might mis-route a video miss as an actress one).
	if _, leaked := payload["id"]; leaked {
		t.Errorf("payload should not carry `id` for a video lookup miss: %#v", payload)
	}
}

func TestBuildNotFoundPayload_ActressShape(t *testing.T) {
	payload := buildNotFoundPayload("actress", "id", "ghost-actress")

	if payload["kind"] != "actress" {
		t.Errorf("kind = %v, want actress", payload["kind"])
	}
	if payload["id"] != "ghost-actress" {
		t.Errorf("id = %v, want ghost-actress", payload["id"])
	}
	if msg, _ := payload["message"].(string); !strings.Contains(msg, "actress") {
		t.Errorf("message = %q, expected to mention 'actress'", msg)
	}
	// Actresses use `id`; `code` must NOT leak into the payload.
	if _, leaked := payload["code"]; leaked {
		t.Errorf("payload should not carry `code` for an actress lookup miss: %#v", payload)
	}
}

func TestBuildNotFoundPayload_SerialisesAsValidJSON(t *testing.T) {
	// _is_not_found_error in src/services/go_cli.py json.loads() this
	// stdout, so any encoding regression must light up here first.
	payload := buildNotFoundPayload("video", "code", "MISSING-001")
	buf, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("json.Marshal: %v", err)
	}
	var round map[string]any
	if err := json.Unmarshal(buf, &round); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}
	if round["error_kind"] != "not_found" {
		t.Errorf("round-trip error_kind = %v, want not_found", round["error_kind"])
	}
}

func TestCompactNoopPayload_HasAllPhaseCFields(t *testing.T) {
	payload := compactNoopPayload("custom-db")

	required := []string{"success", "noop", "journal_size", "needs_compact", "reason"}
	for _, key := range required {
		if _, ok := payload[key]; !ok {
			t.Errorf("compact no-op payload missing required key %q", key)
		}
	}
	if payload["success"] != true {
		t.Errorf("success = %v, want true", payload["success"])
	}
	if payload["noop"] != true {
		t.Errorf("noop = %v, want true", payload["noop"])
	}
	if payload["journal_size"] != 0 {
		t.Errorf("journal_size = %v, want 0", payload["journal_size"])
	}
	if payload["needs_compact"] != false {
		t.Errorf("needs_compact = %v, want false", payload["needs_compact"])
	}
	if reason, _ := payload["reason"].(string); !strings.Contains(reason, "sqlite") {
		t.Errorf("reason = %q, expected to mention sqlite", reason)
	}
	if payload["action"] != "compact" {
		t.Errorf("action = %v, want compact (legacy compat)", payload["action"])
	}
	if payload["data_dir"] != "custom-db" {
		t.Errorf("data_dir = %v, want custom-db (legacy compat)", payload["data_dir"])
	}
}

func TestCompactNoopPayload_SerialisesAsValidJSON(t *testing.T) {
	// IncrementalJSONDB.compact() in src/models/incremental_json_database.py
	// only inspects `success`, but the reply must still round-trip as JSON
	// (run.py / Python's json.loads consume it verbatim).
	payload := compactNoopPayload("custom-db")
	buf, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("Marshal: %v", err)
	}
	var roundtrip map[string]any
	if err := json.Unmarshal(buf, &roundtrip); err != nil {
		t.Fatalf("Unmarshal: %v", err)
	}
	for _, key := range []string{"success", "noop", "journal_size", "needs_compact", "reason"} {
		if _, ok := roundtrip[key]; !ok {
			t.Errorf("round-trip missing %q", key)
		}
	}
}

func TestValidateBackupRestoreInputs_BothFlagsFails(t *testing.T) {
	vErr := validateBackupRestoreInputs("foo.sqlite", "bar.json")
	if vErr == nil {
		t.Fatal("expected validation error when both flags are set")
	}
	if vErr.exitCode != 2 {
		t.Errorf("exitCode = %d, want 2", vErr.exitCode)
	}
	if !strings.Contains(vErr.message, "mutually exclusive") {
		t.Errorf("message = %q, want it to mention mutually exclusive", vErr.message)
	}
	if !strings.Contains(vErr.message, "-backup-path") || !strings.Contains(vErr.message, "-from-json") {
		t.Errorf("message = %q, want both flag names cited", vErr.message)
	}
	// The exact wording is pinned by the C1 contract; Python helpers
	// surface it back to the user verbatim.
	want := "error: -backup-path and -from-json are mutually exclusive; pass exactly one"
	if vErr.message != want {
		t.Errorf("message = %q\nwant   = %q", vErr.message, want)
	}
}

func TestValidateBackupRestoreInputs_NeitherFlagFails(t *testing.T) {
	vErr := validateBackupRestoreInputs("", "   ")
	if vErr == nil {
		t.Fatal("expected validation error when both flags are empty")
	}
	if vErr.exitCode != 2 {
		t.Errorf("exitCode = %d, want 2", vErr.exitCode)
	}
	want := "error: db backup-restore requires either -backup-path <sqlite> or -from-json <json>"
	if vErr.message != want {
		t.Errorf("message = %q\nwant   = %q", vErr.message, want)
	}
}

func TestValidateBackupRestoreInputs_OnlyBackupPath(t *testing.T) {
	if vErr := validateBackupRestoreInputs("backup.sqlite", ""); vErr != nil {
		t.Errorf("unexpected validation error: %+v", vErr)
	}
}

func TestValidateBackupRestoreInputs_OnlyFromJSON(t *testing.T) {
	if vErr := validateBackupRestoreInputs("", "export.json"); vErr != nil {
		t.Errorf("unexpected validation error: %+v", vErr)
	}
}

func TestParseDBCommandOptions_ParsesFromJSONFlag(t *testing.T) {
	opts, remaining := parseDBCommandOptions("backup-restore", []string{
		"-data-dir", "custom-db",
		"-from-json", "data/backup/snap.json",
	})
	if opts.fromJSON != "data/backup/snap.json" {
		t.Errorf("fromJSON = %q, want data/backup/snap.json", opts.fromJSON)
	}
	if opts.dataDir != "custom-db" {
		t.Errorf("dataDir = %q, want custom-db", opts.dataDir)
	}
	if opts.backupPath != "" {
		t.Errorf("backupPath = %q, want empty", opts.backupPath)
	}
	if len(remaining) != 0 {
		t.Errorf("remaining = %#v, want empty", remaining)
	}
}

// TestCreateDualBackup_ProducesBothSnapshots drives the dual-backup
// helper end-to-end against the SQLite-only runtime store and asserts
// both files land on disk with the expected extensions and the JSON has
// a parsable schema.
func TestCreateDualBackup_ProducesBothSnapshots(t *testing.T) {
	store, dir := setupScannerTestDB(t)
	// Seed one video so the backups have non-trivial content.
	video := database.NewVideo("STARS-707")
	video.Title = "備份測試"
	if err := store.UpdateVideo("STARS-707", video); err != nil {
		t.Fatalf("UpdateVideo: %v", err)
	}

	ctx := dbCommandContext{db: store, opts: dbCommandOptions{dataDir: dir}}
	jsonPath, sqlitePath, err := createDualBackup(ctx)
	if err != nil {
		t.Fatalf("createDualBackup: %v", err)
	}
	if !strings.HasSuffix(strings.ToLower(jsonPath), ".json") {
		t.Errorf("jsonPath = %q, want .json suffix", jsonPath)
	}
	if !strings.HasSuffix(strings.ToLower(sqlitePath), ".sqlite") {
		t.Errorf("sqlitePath = %q, want .sqlite suffix", sqlitePath)
	}
	if filepath.Dir(jsonPath) != filepath.Dir(sqlitePath) {
		t.Errorf("backups not co-located: json=%q sqlite=%q", jsonPath, sqlitePath)
	}
	if _, err := os.Stat(jsonPath); err != nil {
		t.Fatalf("json backup not produced: %v", err)
	}
	if _, err := os.Stat(sqlitePath); err != nil {
		t.Fatalf("sqlite backup not produced: %v", err)
	}

	// The SQLite backup must reopen as a valid v3 DB.
	restored, err := database.OpenSQLiteStore(sqlitePath)
	if err != nil {
		t.Fatalf("OpenSQLiteStore(backup): %v", err)
	}
	defer restored.Close()
	v, err := restored.SchemaVersion()
	if err != nil {
		t.Fatalf("SchemaVersion(backup): %v", err)
	}
	if v != database.SQLiteSchemaVersion {
		t.Errorf("backup user_version = %d, want %d", v, database.SQLiteSchemaVersion)
	}
}

// TestCreateDualBackup_JSONExportReflectsSQLiteState writes one video,
// then verifies the JSON export produced alongside the SQLite snapshot
// faithfully reflects the SQLite-side state. The C1 reviewer's worry
// was that an earlier implementation fell back to `data.json` and
// produced a stale JSON snapshot; the SQLite-only runtime in C2
// removes the JSON side entirely, so the regression risk is the
// opposite: the JSON export must come from ExportToJSON, not from
// some never-touched data.json.
func TestCreateDualBackup_JSONExportReflectsSQLiteState(t *testing.T) {
	store, dir := setupScannerTestDB(t)

	const code = "STARS-808"
	const expectedTitle = "SQLite 端標題"

	v := database.NewVideo(code)
	v.Title = expectedTitle
	if err := store.UpdateVideo(code, v); err != nil {
		t.Fatalf("UpdateVideo: %v", err)
	}

	ctx := dbCommandContext{db: store, opts: dbCommandOptions{dataDir: dir}}
	jsonPath, _, err := createDualBackup(ctx)
	if err != nil {
		t.Fatalf("createDualBackup: %v", err)
	}

	raw, err := os.ReadFile(jsonPath)
	if err != nil {
		t.Fatalf("read json export: %v", err)
	}
	var exported struct {
		Videos map[string]struct {
			Title string `json:"title"`
		} `json:"videos"`
	}
	if err := json.Unmarshal(raw, &exported); err != nil {
		t.Fatalf("unmarshal json export: %v", err)
	}
	got, ok := exported.Videos[code]
	if !ok {
		t.Fatalf("json export missing video %s; payload=%s", code, string(raw))
	}
	if got.Title != expectedTitle {
		t.Fatalf("json export title = %q, want %q — createDualBackup must use sqlite.ExportToJSON",
			got.Title, expectedTitle)
	}
}
