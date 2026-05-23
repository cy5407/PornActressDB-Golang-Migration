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
