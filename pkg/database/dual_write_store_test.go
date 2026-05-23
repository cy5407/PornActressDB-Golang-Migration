package database

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// dualStoreFixture builds a DualWriteStore on top of:
//   - a JSONDatabase rooted in a fresh tempdir, seeded with one video +
//     two actresses so we can exercise update / delete paths,
//   - a SQLiteStore initialised from the same fixture via MigrateFromJSON.
//
// Returns the store, the tempdir (caller can probe files), and the
// degraded log path.
func dualStoreFixture(t *testing.T) (store *DualWriteStore, dataDir, degradedPath string) {
	t.Helper()
	dataDir = t.TempDir()

	// JSONDatabase seeded with minimalRoot content.
	if err := os.WriteFile(
		filepath.Join(dataDir, DataFileName),
		mustMarshal(t, minimalRoot()),
		0o600,
	); err != nil {
		t.Fatalf("seed data.json: %v", err)
	}
	jsonDB := NewJSONDatabase(dataDir)
	if err := jsonDB.Load(context.Background()); err != nil {
		t.Fatalf("Load: %v", err)
	}

	sqlite, err := OpenSQLiteStore(filepath.Join(dataDir, "db.sqlite"))
	if err != nil {
		t.Fatalf("OpenSQLiteStore: %v", err)
	}
	if err := sqlite.InitSchema(); err != nil {
		t.Fatalf("InitSchema: %v", err)
	}
	if _, err := sqlite.MigrateFromJSON(filepath.Join(dataDir, DataFileName), MigrationOptions{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	degradedPath = filepath.Join(dataDir, "sync_degraded.jsonl")
	degraded := NewDegradedLog(degradedPath)

	store, err = NewDualWriteStore(jsonDB, sqlite, degraded)
	if err != nil {
		t.Fatalf("NewDualWriteStore: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })
	return store, dataDir, degradedPath
}

func mustMarshal(t *testing.T, v any) []byte {
	t.Helper()
	raw, err := json.Marshal(v)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return raw
}

func TestDualWriteStore_UpdateVideo_WritesBothSides(t *testing.T) {
	store, _, degraded := dualStoreFixture(t)

	v, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	v.Title = "dual-write title"
	if err := store.UpdateVideo("STARS-707", v); err != nil {
		t.Fatalf("UpdateVideo: %v", err)
	}

	// JSON side
	got, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("re-GetVideo: %v", err)
	}
	if got.Title != "dual-write title" {
		t.Errorf("JSON title = %q, want dual-write title", got.Title)
	}

	// SQLite side
	var sqliteTitle string
	if err := store.sqlite.db.QueryRow(
		`SELECT title FROM videos WHERE code='STARS-707'`,
	).Scan(&sqliteTitle); err != nil {
		t.Fatalf("read sqlite: %v", err)
	}
	if sqliteTitle != "dual-write title" {
		t.Errorf("SQLite title = %q, want dual-write title", sqliteTitle)
	}

	// No degraded log on the happy path.
	if _, err := os.Stat(degraded); err == nil {
		t.Errorf("degraded log unexpectedly exists at %s", degraded)
	}

	if store.SyncDegradedTotal() != 0 {
		t.Errorf("SyncDegradedTotal = %d, want 0", store.SyncDegradedTotal())
	}
}

func TestDualWriteStore_FailedSQLiteRecordsDegraded(t *testing.T) {
	store, _, degraded := dualStoreFixture(t)

	// Close SQLite to make every subsequent SQLite write fail.
	_ = store.sqlite.Close()

	v, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	v.Title = "json-only"
	if err := store.UpdateVideo("STARS-707", v); err != nil {
		t.Fatalf("UpdateVideo should not propagate SQLite failure, got: %v", err)
	}

	got, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("re-GetVideo: %v", err)
	}
	if got.Title != "json-only" {
		t.Errorf("JSON title = %q, want json-only", got.Title)
	}

	if store.SyncDegradedTotal() < 1 {
		t.Errorf("SyncDegradedTotal = %d, want >= 1", store.SyncDegradedTotal())
	}

	raw, err := os.ReadFile(degraded)
	if err != nil {
		t.Fatalf("read degraded log: %v", err)
	}
	if len(raw) == 0 {
		t.Errorf("degraded log is empty")
	}
	var entry degradedEntry
	if err := json.Unmarshal(raw[:len(raw)-1] /* trim trailing newline */, &entry); err != nil {
		t.Fatalf("parse first degraded line: %v", err)
	}
	if entry.Op != degradedOpVideoUpsert {
		t.Errorf("degraded op = %q, want %q", entry.Op, degradedOpVideoUpsert)
	}
	if entry.Key != "STARS-707" {
		t.Errorf("degraded key = %q, want STARS-707", entry.Key)
	}
}

func TestDualWriteStore_JSONFailureDoesNotTouchSQLite(t *testing.T) {
	store, _, degraded := dualStoreFixture(t)

	// JSONDatabase.UpdateVideo returns an error when video is nil.
	// SQLite must NOT be touched in that case — the JSON contract
	// hasn't yielded a write to mirror.
	if err := store.UpdateVideo("STARS-707", nil); err == nil {
		t.Fatal("UpdateVideo(_, nil) should fail")
	}

	// SQLite STARS-707 still has its seeded title ("A") — untouched.
	var sqliteTitle string
	if err := store.sqlite.db.QueryRow(
		`SELECT title FROM videos WHERE code='STARS-707'`,
	).Scan(&sqliteTitle); err != nil {
		t.Fatalf("read sqlite: %v", err)
	}
	if sqliteTitle != "A" {
		t.Errorf("SQLite title = %q, want unchanged seed title \"A\"", sqliteTitle)
	}

	if _, err := os.Stat(degraded); err == nil {
		t.Errorf("degraded log unexpectedly created on JSON failure: %s", degraded)
	}
}

func TestDualWriteStore_DeleteVideo_MirrorsToSQLite(t *testing.T) {
	store, _, _ := dualStoreFixture(t)

	if err := store.DeleteVideo("MIDV-567"); err != nil {
		t.Fatalf("DeleteVideo: %v", err)
	}

	var n int
	if err := store.sqlite.db.QueryRow(
		`SELECT COUNT(*) FROM videos WHERE code='MIDV-567'`,
	).Scan(&n); err != nil {
		t.Fatalf("count: %v", err)
	}
	if n != 0 {
		t.Errorf("SQLite videos count for MIDV-567 = %d, want 0", n)
	}
}

func TestDualWriteStore_UpdateVideoFields_FlowsDiffToSQLite(t *testing.T) {
	store, _, _ := dualStoreFixture(t)

	if err := store.UpdateVideoFields("STARS-707", map[string]any{"studio": "MOODYZ"}); err != nil {
		t.Fatalf("UpdateVideoFields: %v", err)
	}
	var studio string
	if err := store.sqlite.db.QueryRow(
		`SELECT studio FROM videos WHERE code='STARS-707'`,
	).Scan(&studio); err != nil {
		t.Fatalf("read sqlite: %v", err)
	}
	if studio != "MOODYZ" {
		t.Errorf("SQLite studio = %q, want MOODYZ", studio)
	}
}

func TestDualWriteStore_ReplayDrainsDegradedLog(t *testing.T) {
	store, _, degraded := dualStoreFixture(t)

	// Force a degraded entry by closing SQLite.
	_ = store.sqlite.Close()
	v, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	v.Title = "replay-test"
	if err := store.UpdateVideo("STARS-707", v); err != nil {
		t.Fatalf("UpdateVideo: %v", err)
	}
	// Verify entry was recorded.
	if size := store.degraded.SizeBytes(); size == 0 {
		t.Fatal("degraded log expected non-empty")
	}

	// Re-open SQLite so replay can succeed.
	newSqlite, err := OpenSQLiteStore(filepath.Join(filepath.Dir(degraded), "db.sqlite"))
	if err != nil {
		t.Fatalf("reopen sqlite: %v", err)
	}
	t.Cleanup(func() { _ = newSqlite.Close() })
	if err := newSqlite.InitSchema(); err != nil {
		t.Fatalf("InitSchema: %v", err)
	}
	store.sqlite = newSqlite

	// Now Replay should drain the log.
	if err := store.Replay(); err != nil {
		t.Fatalf("Replay: %v", err)
	}

	// Degraded log file should be gone (drain emptied it).
	if _, err := os.Stat(degraded); !errors.Is(err, os.ErrNotExist) {
		t.Errorf("degraded log not removed after drain: err=%v", err)
	}

	// SQLite must have the replayed title.
	var sqliteTitle string
	if err := store.sqlite.db.QueryRow(
		`SELECT title FROM videos WHERE code='STARS-707'`,
	).Scan(&sqliteTitle); err != nil {
		// STARS-707 row was wiped when we re-init'd schema. The replay
		// upserts the row, so it must exist after replay.
		t.Fatalf("read sqlite after replay: %v", err)
	}
	if sqliteTitle != "replay-test" {
		t.Errorf("SQLite title after replay = %q, want replay-test", sqliteTitle)
	}

	succ, fail := store.degraded.SuccessesAndFailures()
	if succ < 1 {
		t.Errorf("replay successes = %d, want >= 1", succ)
	}
	if fail != 0 {
		t.Errorf("replay failures = %d, want 0", fail)
	}
}

func TestDualWriteStore_ReplayKeepsUnreplayableEntries(t *testing.T) {
	store, _, degraded := dualStoreFixture(t)

	// Inject a degraded entry directly that targets an unknown actress
	// (so it'll fail to replay; the entry must be retained).
	if err := store.degraded.Record(degradedEntry{
		Op:   degradedOpActressUpsert,
		Key:  "", // empty id triggers UpsertActress's "id is empty" error
		Data: []byte(`{"id":""}`),
		Err:  "synthetic",
	}); err != nil {
		t.Fatalf("Record: %v", err)
	}

	if err := store.Replay(); err != nil {
		t.Fatalf("Replay: %v", err)
	}
	info, err := os.Stat(degraded)
	if err != nil {
		t.Fatalf("degraded log should still exist (retain): %v", err)
	}
	if info.Size() == 0 {
		t.Errorf("degraded log empty after retain replay")
	}
}

func TestDualWriteStore_PostWriteHookFiresBackgroundReplay(t *testing.T) {
	store, _, _ := dualStoreFixture(t)

	// Pre-stash a degraded entry. The next successful write should
	// trigger a background replay that drains it.
	v, _ := store.GetVideo("STARS-707")
	rawV, _ := json.Marshal(v)
	if err := store.degraded.Record(degradedEntry{
		Op:   degradedOpVideoUpsert,
		Key:  "STARS-707",
		Data: rawV,
		Err:  "pre-stashed",
	}); err != nil {
		t.Fatalf("Record: %v", err)
	}

	// Trigger any happy-path write to fire postWriteHook.
	v.Title = "trigger-hook"
	if err := store.UpdateVideo("STARS-707", v); err != nil {
		t.Fatalf("UpdateVideo: %v", err)
	}

	// Background replay is fire-and-forget; poll briefly for the log to
	// drain. 200ms is plenty for a local in-memory SQLite hit.
	deadline := time.Now().Add(2 * time.Second)
	for {
		succ, _ := store.degraded.SuccessesAndFailures()
		if succ >= 1 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("background replay did not drain pre-stashed entry within 2s")
		}
		time.Sleep(20 * time.Millisecond)
	}
}

func TestDualWriteStore_SyncDegradedTotalReportsHistory(t *testing.T) {
	store, _, _ := dualStoreFixture(t)
	_ = store.sqlite.Close()

	v, _ := store.GetVideo("STARS-707")
	v.Title = "fail1"
	_ = store.UpdateVideo("STARS-707", v)
	v.Title = "fail2"
	_ = store.UpdateVideo("STARS-707", v)

	if got := store.SyncDegradedTotal(); got < 2 {
		t.Errorf("SyncDegradedTotal = %d, want >= 2", got)
	}
}

func TestDualWriteStore_NewRejectsNilJSONDatabase(t *testing.T) {
	_, err := NewDualWriteStore(nil, &SQLiteStore{}, nil)
	if err == nil {
		t.Error("NewDualWriteStore(nil, _, _) returned nil error")
	}
}

func TestDualWriteStore_NilSQLiteCollapsesToJSONOnly(t *testing.T) {
	// sqlite=nil is the explicit JSON-only fallback for the
	// ACTRESS_DB_MODE=json_only rollback path. Mirror calls become noops;
	// the degraded log is never touched.
	dataDir := t.TempDir()
	if err := os.WriteFile(
		filepath.Join(dataDir, DataFileName),
		mustMarshal(t, minimalRoot()),
		0o600,
	); err != nil {
		t.Fatalf("seed data.json: %v", err)
	}
	jsonDB := NewJSONDatabase(dataDir)
	if err := jsonDB.Load(context.Background()); err != nil {
		t.Fatalf("Load: %v", err)
	}
	store, err := NewDualWriteStore(jsonDB, nil, nil)
	if err != nil {
		t.Fatalf("NewDualWriteStore(_, nil, _) should be allowed (JSON-only fallback): %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })

	v, _ := store.GetVideo("STARS-707")
	v.Title = "json-only-mode"
	if err := store.UpdateVideo("STARS-707", v); err != nil {
		t.Fatalf("UpdateVideo: %v", err)
	}
	if got := store.SyncDegradedTotal(); got != 0 {
		t.Errorf("SyncDegradedTotal = %d, want 0 in JSON-only mode", got)
	}
}

// Ensure DualWriteStore's embedded JSONDatabase keeps read methods
// transparent (sanity test guarding the embed pattern).
func TestDualWriteStore_GetVideoFlowsThroughEmbed(t *testing.T) {
	store, _, _ := dualStoreFixture(t)
	v, err := store.GetVideo("MIDV-567")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	if v == nil || v.Code != "MIDV-567" {
		t.Errorf("GetVideo via embed = %+v, want code=MIDV-567", v)
	}
}

// Compile-time guard: ensure DualWriteStore has the same surface as
// JSONDatabase for the read methods cmd/scanner / wails use. If a
// future refactor breaks this we want a clear pointer to the location.
var _ interface {
	GetVideo(string) (*Video, error)
	GetAllVideos() ([]*VideoData, error)
	ListVideos() ([]string, error)
	GetStats() (map[string]any, error)
} = (*DualWriteStore)(nil)

func TestDualWriteStore_StoreCompileSanity(t *testing.T) {
	// kept as a place to expand the surface guard with comments.
	_ = (*DualWriteStore)(nil)
	_ = fmt.Sprintf // keep imports stable
}

func TestDualWriteStore_GetStats_HappyPathHasZeroDegradedFields(t *testing.T) {
	store, _, _ := dualStoreFixture(t)

	stats, err := store.GetStats()
	if err != nil {
		t.Fatalf("GetStats: %v", err)
	}

	// Existing JSON keys must still be present (Python helper relies on them).
	for _, key := range []string{
		"video_count", "actress_count", "link_count",
		"journal_size", "journal_age_seconds", "needs_compact", "total_videos",
	} {
		if _, ok := stats[key]; !ok {
			t.Errorf("GetStats missing pre-existing key %q", key)
		}
	}

	total, ok := stats["sync_degraded_total"].(int64)
	if !ok {
		t.Fatalf("sync_degraded_total missing or wrong type: %T", stats["sync_degraded_total"])
	}
	if total != 0 {
		t.Errorf("sync_degraded_total = %d, want 0 on happy path", total)
	}

	size, ok := stats["sync_degraded_log_size"].(int64)
	if !ok {
		t.Fatalf("sync_degraded_log_size missing or wrong type: %T", stats["sync_degraded_log_size"])
	}
	if size != 0 {
		t.Errorf("sync_degraded_log_size = %d, want 0 on happy path", size)
	}
}

func TestDualWriteStore_GetStats_ReportsDegradedTotalAndSize(t *testing.T) {
	store, _, _ := dualStoreFixture(t)
	_ = store.sqlite.Close()

	v, _ := store.GetVideo("STARS-707")
	v.Title = "stats-degrade-1"
	_ = store.UpdateVideo("STARS-707", v)
	v.Title = "stats-degrade-2"
	_ = store.UpdateVideo("STARS-707", v)

	stats, err := store.GetStats()
	if err != nil {
		t.Fatalf("GetStats: %v", err)
	}

	total, _ := stats["sync_degraded_total"].(int64)
	if total < 2 {
		t.Errorf("sync_degraded_total = %d, want >= 2", total)
	}

	size, _ := stats["sync_degraded_log_size"].(int64)
	if size <= 0 {
		t.Errorf("sync_degraded_log_size = %d, want > 0 after degraded writes", size)
	}
}

func TestDualWriteStore_GetStats_NilSQLiteHasZeroDegradedFields(t *testing.T) {
	// JSON-only (ACTRESS_DB_MODE=json_only) rollback path — even when the
	// degraded log was constructed with no path, GetStats must still emit
	// the two new fields so Python parsing stays uniform.
	dataDir := t.TempDir()
	if err := os.WriteFile(
		filepath.Join(dataDir, DataFileName),
		mustMarshal(t, minimalRoot()),
		0o600,
	); err != nil {
		t.Fatalf("seed: %v", err)
	}
	jsonDB := NewJSONDatabase(dataDir)
	if err := jsonDB.Load(context.Background()); err != nil {
		t.Fatalf("Load: %v", err)
	}
	store, err := NewDualWriteStore(jsonDB, nil, nil)
	if err != nil {
		t.Fatalf("NewDualWriteStore: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })

	stats, err := store.GetStats()
	if err != nil {
		t.Fatalf("GetStats: %v", err)
	}
	if got, _ := stats["sync_degraded_total"].(int64); got != 0 {
		t.Errorf("sync_degraded_total = %d, want 0 in JSON-only mode", got)
	}
	if got, _ := stats["sync_degraded_log_size"].(int64); got != 0 {
		t.Errorf("sync_degraded_log_size = %d, want 0 in JSON-only mode", got)
	}
}

// --- B1a: UseSQLiteReads shadow-read tests --------------------------------

// dualStoreWithSQLiteReads is dualStoreFixture + the shadow-read flag.
// Returns the store and the data dir; cleanup is t-registered upstream.
func dualStoreWithSQLiteReads(t *testing.T) (*DualWriteStore, string) {
	t.Helper()
	store, dataDir, _ := dualStoreFixture(t)
	store.SetUseSQLiteReads(true)
	return store, dataDir
}

func TestDualWriteStore_GetVideo_FlagFalseStaysOnJSON(t *testing.T) {
	store, _, _ := dualStoreFixture(t)
	if store.UseSQLiteReads() {
		t.Fatal("default UseSQLiteReads should be false")
	}

	// Force JSON and SQLite to diverge: bump SQLite title only. With the
	// flag off, GetVideo must keep returning the JSON title — Phase A3
	// behaviour is preserved exactly.
	if _, err := store.sqlite.db.Exec(
		`UPDATE videos SET title='sqlite-side' WHERE code='STARS-707'`,
	); err != nil {
		t.Fatalf("UPDATE: %v", err)
	}

	v, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	if v.Title != "A" {
		t.Errorf("title = %q, want JSON-side \"A\" when flag is false", v.Title)
	}
	if got := store.SQLiteReadFallbackTotal(); got != 0 {
		t.Errorf("SQLiteReadFallbackTotal = %d, want 0 when flag is false", got)
	}
}

func TestDualWriteStore_GetVideo_FlagTrueReadsFromSQLite(t *testing.T) {
	store, _ := dualStoreWithSQLiteReads(t)

	// Same divergence trick: only SQLite knows the new title. The flag
	// must route the read there.
	if _, err := store.sqlite.db.Exec(
		`UPDATE videos SET title='sqlite-side' WHERE code='STARS-707'`,
	); err != nil {
		t.Fatalf("UPDATE: %v", err)
	}

	v, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	if v.Title != "sqlite-side" {
		t.Errorf("title = %q, want SQLite-side value with flag=true", v.Title)
	}
	if got := store.SQLiteReadFallbackTotal(); got != 0 {
		t.Errorf("SQLiteReadFallbackTotal = %d, want 0 on happy path", got)
	}
}

func TestDualWriteStore_GetVideo_DriftReturnsSQLiteAnswer(t *testing.T) {
	// Drift case: SQLite has no row for STARS-707 while JSON still does.
	// flag=true must report the SQLite answer (ErrNotFound) rather than
	// silently falling back. The whole point of the shadow-read window
	// is to surface divergence, not paper over it.
	store, _ := dualStoreWithSQLiteReads(t)
	if _, err := store.sqlite.db.Exec(`DELETE FROM videos WHERE code='STARS-707'`); err != nil {
		t.Fatalf("DELETE: %v", err)
	}

	v, err := store.GetVideo("STARS-707")
	if !errors.Is(err, ErrNotFound) {
		t.Errorf("err = %v, want ErrNotFound from SQLite drift", err)
	}
	if v != nil {
		t.Errorf("video = %+v, want nil on ErrNotFound", v)
	}
	if got := store.SQLiteReadFallbackTotal(); got != 0 {
		t.Errorf("SQLiteReadFallbackTotal = %d, want 0 — drift must NOT trigger fallback", got)
	}
}

func TestDualWriteStore_GetVideo_UnavailableFallsBackToJSON(t *testing.T) {
	store, _ := dualStoreWithSQLiteReads(t)
	// Close SQLite so every read errors with ErrSQLiteStoreClosed.
	_ = store.sqlite.Close()

	v, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	if v.Title != "A" {
		t.Errorf("title = %q, want JSON fallback \"A\"", v.Title)
	}
	if got := store.SQLiteReadFallbackTotal(); got != 1 {
		t.Errorf("SQLiteReadFallbackTotal = %d, want 1 after one fallback", got)
	}
}

func TestDualWriteStore_ListVideos_FlagFalseStaysOnJSON(t *testing.T) {
	store, _, _ := dualStoreFixture(t)
	// Add a phantom row in SQLite that does not exist in JSON.
	if _, err := store.sqlite.db.Exec(
		`INSERT INTO videos(code) VALUES('PHANTOM-001')`,
	); err != nil {
		t.Fatalf("INSERT phantom: %v", err)
	}

	codes, err := store.ListVideos()
	if err != nil {
		t.Fatalf("ListVideos: %v", err)
	}
	for _, c := range codes {
		if c == "PHANTOM-001" {
			t.Errorf("ListVideos returned SQLite-only code %q while flag=false", c)
		}
	}
}

func TestDualWriteStore_ListVideos_FlagTrueIncludesSQLiteOnlyRow(t *testing.T) {
	store, _ := dualStoreWithSQLiteReads(t)
	if _, err := store.sqlite.db.Exec(
		`INSERT INTO videos(code) VALUES('PHANTOM-001')`,
	); err != nil {
		t.Fatalf("INSERT phantom: %v", err)
	}

	codes, err := store.ListVideos()
	if err != nil {
		t.Fatalf("ListVideos: %v", err)
	}
	got := false
	for _, c := range codes {
		if c == "PHANTOM-001" {
			got = true
			break
		}
	}
	if !got {
		t.Errorf("ListVideos missing SQLite-only code with flag=true: got=%v", codes)
	}
}

func TestDualWriteStore_ListVideos_UnavailableFallsBackToJSON(t *testing.T) {
	store, _ := dualStoreWithSQLiteReads(t)
	_ = store.sqlite.Close()

	codes, err := store.ListVideos()
	if err != nil {
		t.Fatalf("ListVideos: %v", err)
	}
	if len(codes) == 0 {
		t.Errorf("ListVideos returned empty after SQLite unavailable — expected JSON fallback")
	}
	if got := store.SQLiteReadFallbackTotal(); got != 1 {
		t.Errorf("SQLiteReadFallbackTotal = %d, want 1", got)
	}
}

func TestDualWriteStore_GetAllVideos_FlagTrueReadsFromSQLite(t *testing.T) {
	store, _ := dualStoreWithSQLiteReads(t)
	if _, err := store.sqlite.db.Exec(
		`UPDATE videos SET title='sqlite-allvids' WHERE code='STARS-707'`,
	); err != nil {
		t.Fatalf("UPDATE: %v", err)
	}

	videos, err := store.GetAllVideos()
	if err != nil {
		t.Fatalf("GetAllVideos: %v", err)
	}
	found := false
	for _, v := range videos {
		if v.Code == "STARS-707" {
			found = true
			if v.Title != "sqlite-allvids" {
				t.Errorf("STARS-707.Title = %q, want sqlite-allvids", v.Title)
			}
		}
	}
	if !found {
		t.Error("STARS-707 missing from GetAllVideos result")
	}
}

func TestDualWriteStore_GetAllVideos_UnavailableFallsBackToJSON(t *testing.T) {
	store, _ := dualStoreWithSQLiteReads(t)
	_ = store.sqlite.Close()

	videos, err := store.GetAllVideos()
	if err != nil {
		t.Fatalf("GetAllVideos: %v", err)
	}
	if len(videos) == 0 {
		t.Errorf("GetAllVideos returned empty after SQLite unavailable — expected JSON fallback")
	}
	if got := store.SQLiteReadFallbackTotal(); got != 1 {
		t.Errorf("SQLiteReadFallbackTotal = %d, want 1", got)
	}
}

func TestDualWriteStore_GetStats_ReportsFallbackCounterAndKeepsKeys(t *testing.T) {
	store, _ := dualStoreWithSQLiteReads(t)
	_ = store.sqlite.Close()

	// Trigger two fallbacks of different shapes.
	_, _ = store.GetVideo("STARS-707")
	_, _ = store.ListVideos()

	stats, err := store.GetStats()
	if err != nil {
		t.Fatalf("GetStats: %v", err)
	}

	// All existing JSON keys must remain — Python parsing relies on
	// these and the dual-write contract requires GetStats to be a
	// superset, not a replacement.
	for _, key := range []string{
		"video_count", "actress_count", "link_count",
		"schema_version", "created_at", "updated_at",
		"journal_size", "journal_age_seconds",
		"dirty_videos", "dirty_actresses", "dirty_links",
		"needs_compact", "total_videos",
		// Phase A3 additions
		"sync_degraded_total", "sync_degraded_log_size",
	} {
		if _, ok := stats[key]; !ok {
			t.Errorf("GetStats missing key %q", key)
		}
	}

	fallback, ok := stats["sqlite_read_fallback_total"].(int64)
	if !ok {
		t.Fatalf("sqlite_read_fallback_total missing or wrong type: %T", stats["sqlite_read_fallback_total"])
	}
	if fallback < 2 {
		t.Errorf("sqlite_read_fallback_total = %d, want >= 2", fallback)
	}
}

func TestDualWriteStore_GetStats_FallbackCounterZeroByDefault(t *testing.T) {
	store, _, _ := dualStoreFixture(t)
	stats, err := store.GetStats()
	if err != nil {
		t.Fatalf("GetStats: %v", err)
	}
	got, ok := stats["sqlite_read_fallback_total"].(int64)
	if !ok {
		t.Fatalf("sqlite_read_fallback_total missing or wrong type: %T", stats["sqlite_read_fallback_total"])
	}
	if got != 0 {
		t.Errorf("sqlite_read_fallback_total = %d, want 0 on happy path", got)
	}
}

func TestDualWriteStore_GetStats_NilSQLiteHasFallbackZero(t *testing.T) {
	// JSON-only collapse path: even when there is no SQLite handle, the
	// shadow-read flag does nothing (shouldReadFromSQLite returns false)
	// so the fallback counter never moves. GetStats must still emit the
	// key uniformly for downstream parsers.
	store, _, _ := dualStoreFixture(t)
	_ = store.sqlite.Close()
	store.sqlite = nil
	store.SetUseSQLiteReads(true)

	if _, err := store.GetVideo("STARS-707"); err != nil {
		t.Fatalf("GetVideo: %v", err)
	}

	stats, err := store.GetStats()
	if err != nil {
		t.Fatalf("GetStats: %v", err)
	}
	got, _ := stats["sqlite_read_fallback_total"].(int64)
	if got != 0 {
		t.Errorf("sqlite_read_fallback_total = %d, want 0 when sqlite handle is nil", got)
	}
}

func TestNewStore_PassesUseSQLiteReadsThrough(t *testing.T) {
	tmp := t.TempDir()
	dataDir := filepath.Join(tmp, "json_db")
	writeFixtureAt(t, dataDir)

	store, err := NewStore(StoreConfig{
		Mode:           ModeDualWrite,
		DataDir:        dataDir,
		UseSQLiteReads: true,
	})
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })

	if !store.UseSQLiteReads() {
		t.Error("NewStore did not propagate UseSQLiteReads=true onto DualWriteStore")
	}
}

func TestNewStore_DefaultUseSQLiteReadsIsFalse(t *testing.T) {
	tmp := t.TempDir()
	dataDir := filepath.Join(tmp, "json_db")
	writeFixtureAt(t, dataDir)

	store, err := NewStore(StoreConfig{
		Mode:    ModeDualWrite,
		DataDir: dataDir,
	})
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })

	if store.UseSQLiteReads() {
		t.Error("NewStore default UseSQLiteReads should be false")
	}
}

func TestDualWriteStore_CloseWaitsForBackgroundReplays(t *testing.T) {
	// Directly exercises the lifecycle fix: after writes that spawn
	// background replays, Close must block until those goroutines drain
	// — otherwise on Windows the tmp-file rewrite races TempDir cleanup.
	store, _, degraded := dualStoreFixture(t)
	_ = store.sqlite.Close()

	v, _ := store.GetVideo("STARS-707")
	for i := 0; i < 5; i++ {
		v.Title = fmt.Sprintf("close-wait-%d", i)
		_ = store.UpdateVideo("STARS-707", v)
	}

	if err := store.Close(); err != nil {
		t.Fatalf("Close: %v", err)
	}

	// After Close returns, no further writes should spawn goroutines —
	// stat the tmp sibling to make sure no rewrite is in flight.
	tmp := degraded + ".tmp"
	if _, err := os.Stat(tmp); err == nil {
		t.Errorf("degraded log tmp file still present after Close: %s", tmp)
	}
}
