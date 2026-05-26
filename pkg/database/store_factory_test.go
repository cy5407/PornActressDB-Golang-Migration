package database

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// writeFixtureAt seeds a JSON DB at dir so NewStore's bootstrap-from-
// JSON branch has something to import. Used by every NewStore test
// that wants to exercise the C2 bootstrap pass.
func writeFixtureAt(t *testing.T, dir string) {
	t.Helper()
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatalf("mkdir %s: %v", dir, err)
	}
	if err := os.WriteFile(
		filepath.Join(dir, DataFileName),
		mustMarshal(t, minimalRoot()),
		0o600,
	); err != nil {
		t.Fatalf("write data.json: %v", err)
	}
}

func mustMarshal(t *testing.T, v any) []byte {
	t.Helper()
	raw, err := json.Marshal(v)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return raw
}

func TestNewStore_OpensSQLiteSibling(t *testing.T) {
	tmp := t.TempDir()
	dataDir := filepath.Join(tmp, "json_db")
	writeFixtureAt(t, dataDir)

	store, err := NewStore(StoreConfig{DataDir: dataDir})
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })

	wantSQLite := filepath.Join(dataDir, "db.sqlite")
	if got := store.Path(); got != wantSQLite {
		t.Errorf("sqlite path = %q, want %q", got, wantSQLite)
	}
}

func TestNewStore_DefaultDataDirCompatibilityLookup(t *testing.T) {
	// spec § 7.1 / user task: the default -data-dir value (data/json_db)
	// must map to the sibling SQLite file (data/db.sqlite). NewStore
	// must NEVER create a db.sqlite *inside* the default JSON dir, even
	// if the JSON dir already exists.
	tmp := t.TempDir()
	cwd, err := os.Getwd()
	if err != nil {
		t.Fatalf("Getwd: %v", err)
	}
	if chdirErr := os.Chdir(tmp); chdirErr != nil {
		t.Fatalf("Chdir: %v", chdirErr)
	}
	t.Cleanup(func() { _ = os.Chdir(cwd) })

	if mkdirErr := os.MkdirAll(filepath.Join(tmp, DefaultDataDir), 0o755); mkdirErr != nil {
		t.Fatalf("mkdir default data dir: %v", mkdirErr)
	}

	store, err := NewStore(StoreConfig{}) // DataDir empty → DefaultDataDir
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })

	wantSQLite := filepath.Join(filepath.Dir(DefaultDataDir), SQLiteFileName) // data/db.sqlite
	if got := store.Path(); got != wantSQLite {
		t.Errorf("sqlite path = %q, want %q (sibling of %q)", got, wantSQLite, DefaultDataDir)
	}
	if _, err := os.Stat(filepath.Join(DefaultDataDir, SQLiteFileName)); err == nil {
		t.Errorf("NewStore created db.sqlite inside the JSON dir %q — must use sibling instead",
			DefaultDataDir)
	}
}

func TestNewStore_BootstrapsFromJSONOnFirstOpen(t *testing.T) {
	// SQLite file doesn't exist yet AND a sibling data.json is present
	// → NewStore should one-shot migrate-from-json so the runtime is
	// usable without an explicit `db migrate-from-json` step.
	tmp := t.TempDir()
	dataDir := filepath.Join(tmp, "json_db")
	writeFixtureAt(t, dataDir)

	store, err := NewStore(StoreConfig{DataDir: dataDir})
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })

	count, err := store.GetVideoCount()
	if err != nil {
		t.Fatalf("GetVideoCount: %v", err)
	}
	if count != 3 {
		t.Errorf("video count after bootstrap = %d, want 3 (minimalRoot fixture)", count)
	}
}

func TestNewStore_SkipsBootstrapWhenSQLiteAlreadyPopulated(t *testing.T) {
	// SQLite file exists with rows → the bootstrap must NOT re-import
	// JSON on top, otherwise running NewStore twice would double-count
	// or fail with duplicate-key errors.
	tmp := t.TempDir()
	dataDir := filepath.Join(tmp, "json_db")
	writeFixtureAt(t, dataDir)

	first, err := NewStore(StoreConfig{DataDir: dataDir})
	if err != nil {
		t.Fatalf("first NewStore: %v", err)
	}
	_ = first.Close()

	// Mutate the JSON side so any re-bootstrap would show up.
	writeFixtureAt(t, dataDir) // identical, but bumps mtime

	second, err := NewStore(StoreConfig{DataDir: dataDir})
	if err != nil {
		t.Fatalf("second NewStore: %v", err)
	}
	t.Cleanup(func() { _ = second.Close() })

	count, err := second.GetVideoCount()
	if err != nil {
		t.Fatalf("GetVideoCount: %v", err)
	}
	if count != 3 {
		t.Errorf("video count after re-open = %d, want 3 (no re-bootstrap)", count)
	}
}

func TestNewStore_SkipsBootstrapWhenJSONAbsent(t *testing.T) {
	// Greenfield install: no JSON DB anywhere → SQLite is brand-new
	// and empty, and NewStore must not error out.
	tmp := t.TempDir()
	dataDir := filepath.Join(tmp, "json_db")
	if err := os.MkdirAll(dataDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	store, err := NewStore(StoreConfig{DataDir: dataDir})
	if err != nil {
		t.Fatalf("NewStore (greenfield): %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })

	count, err := store.GetVideoCount()
	if err != nil {
		t.Fatalf("GetVideoCount: %v", err)
	}
	if count != 0 {
		t.Errorf("greenfield video count = %d, want 0", count)
	}
}

func TestNewStore_BootstrapFailureReturnsError(t *testing.T) {
	// Bootstrap is the cutover safety gate. If SQLite is empty AND a
	// data.json is sitting next to it, NewStore MUST surface any
	// migrate-from-json failure — silently coming up with an empty
	// SQLite store would look indistinguishable from a clean
	// greenfield install to anything that inspects video_count.
	tmp := t.TempDir()
	dataDir := filepath.Join(tmp, "json_db")
	if err := os.MkdirAll(dataDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	// Garbage that loadJSONDatabaseRoot's json.Unmarshal will reject.
	if err := os.WriteFile(filepath.Join(dataDir, DataFileName), []byte("{not json"), 0o600); err != nil {
		t.Fatalf("write broken data.json: %v", err)
	}

	store, err := NewStore(StoreConfig{DataDir: dataDir})
	if err == nil {
		_ = store.Close()
		t.Fatal("expected NewStore to fail when bootstrap-from-json hits a broken data.json")
	}
	if store != nil {
		t.Errorf("expected nil store on bootstrap failure, got %#v", store)
	}
}

func TestNewStore_BrokenJSONIgnoredWhenSQLitePopulated(t *testing.T) {
	// SQLite already populated → bootstrap must be skipped entirely,
	// even if a hand-edit (or a botched backup restore) has left
	// data.json in an unparseable state. Otherwise a stale JSON file
	// would block runtime startup for no reason.
	tmp := t.TempDir()
	dataDir := filepath.Join(tmp, "json_db")
	writeFixtureAt(t, dataDir)

	first, err := NewStore(StoreConfig{DataDir: dataDir})
	if err != nil {
		t.Fatalf("first NewStore: %v", err)
	}
	_ = first.Close()

	// Now corrupt the JSON file behind SQLite's back.
	if writeErr := os.WriteFile(filepath.Join(dataDir, DataFileName), []byte("{garbage"), 0o600); writeErr != nil {
		t.Fatalf("corrupt data.json: %v", writeErr)
	}

	second, err := NewStore(StoreConfig{DataDir: dataDir})
	if err != nil {
		t.Fatalf("populated SQLite + broken JSON must still open: %v", err)
	}
	t.Cleanup(func() { _ = second.Close() })

	count, err := second.GetVideoCount()
	if err != nil {
		t.Fatalf("GetVideoCount: %v", err)
	}
	if count != 3 {
		t.Errorf("video count after re-open with broken JSON = %d, want 3", count)
	}
}

func TestNewStore_SkipBootstrapHonoursFlag(t *testing.T) {
	// SkipBootstrap=true keeps SQLite empty even when a JSON fixture
	// is present. Used by tests that want a clean slate.
	tmp := t.TempDir()
	dataDir := filepath.Join(tmp, "json_db")
	writeFixtureAt(t, dataDir)

	store, err := NewStore(StoreConfig{DataDir: dataDir, SkipBootstrap: true})
	if err != nil {
		t.Fatalf("NewStore (SkipBootstrap): %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })

	count, err := store.GetVideoCount()
	if err != nil {
		t.Fatalf("GetVideoCount: %v", err)
	}
	if count != 0 {
		t.Errorf("video count with SkipBootstrap = %d, want 0", count)
	}
}

func TestNewStore_GetStatsRetainsPythonContractKeys(t *testing.T) {
	// Spec § 7.1: Phase A0 keys (and the retired A3 / B1 keys) MUST
	// keep appearing in the stats dict so the Python helper / Wails
	// frontend don't KeyError. The retired counters report zero.
	tmp := t.TempDir()
	dataDir := filepath.Join(tmp, "json_db")
	writeFixtureAt(t, dataDir)

	store, err := NewStore(StoreConfig{DataDir: dataDir})
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })

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
			t.Errorf("GetStats missing required key %q", key)
		}
	}
	// Retired counters must be zero/false on a SQLite-only runtime.
	for _, key := range []string{"journal_size", "dirty_videos", "dirty_actresses", "dirty_links"} {
		if v, _ := stats[key].(int); v != 0 {
			t.Errorf("%s = %v, want 0 on SQLite-only runtime", key, v)
		}
	}
	if v, _ := stats["needs_compact"].(bool); v {
		t.Errorf("needs_compact = true, want false on SQLite-only runtime")
	}
	for _, key := range []string{
		"sync_degraded_total", "sync_degraded_log_size", "sqlite_read_fallback_total",
	} {
		if v, _ := stats[key].(int64); v != 0 {
			t.Errorf("%s = %v, want int64 0 on SQLite-only runtime", key, v)
		}
	}
}
