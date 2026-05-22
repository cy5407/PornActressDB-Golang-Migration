package database

import (
	"os"
	"path/filepath"
	"testing"
)

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

func TestNewStore_DualWriteOpensSQLiteSibling(t *testing.T) {
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

	if store.sqlite == nil {
		t.Fatal("sqlite is nil in ModeDualWrite")
	}
	// SQLite sibling lives at <dir>/db.sqlite for custom data-dirs.
	wantSQLite := filepath.Join(dataDir, "db.sqlite")
	if got := store.sqlite.Path(); got != wantSQLite {
		t.Errorf("sqlite path = %q, want %q", got, wantSQLite)
	}
}

func TestNewStore_JSONOnlySkipsSQLite(t *testing.T) {
	tmp := t.TempDir()
	dataDir := filepath.Join(tmp, "json_db")
	writeFixtureAt(t, dataDir)

	store, err := NewStore(StoreConfig{
		Mode:    ModeJSONOnly,
		DataDir: dataDir,
	})
	if err != nil {
		t.Fatalf("NewStore JSONOnly: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })

	if store.sqlite != nil {
		t.Errorf("sqlite expected nil in ModeJSONOnly, got %+v", store.sqlite)
	}
	// The SQLite file must not have been created either.
	if _, err := os.Stat(filepath.Join(dataDir, "db.sqlite")); err == nil {
		t.Errorf("SQLite file unexpectedly created in ModeJSONOnly")
	}
}

func TestNewStore_JSONOnlyMutationStillFlowsThroughEmbed(t *testing.T) {
	tmp := t.TempDir()
	dataDir := filepath.Join(tmp, "json_db")
	writeFixtureAt(t, dataDir)

	store, err := NewStore(StoreConfig{
		Mode:    ModeJSONOnly,
		DataDir: dataDir,
	})
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })

	v, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	v.Title = "json-only-write"
	if err := store.UpdateVideo("STARS-707", v); err != nil {
		t.Fatalf("UpdateVideo: %v", err)
	}
	// Spec § 4.1 rollback path: SyncDegradedTotal stays 0 since no
	// mirror was attempted.
	if got := store.SyncDegradedTotal(); got != 0 {
		t.Errorf("SyncDegradedTotal = %d in JSON-only, want 0", got)
	}
}

func TestResolveStoreMode_RecognisesEnvVar(t *testing.T) {
	cases := []struct {
		env  string
		want StoreMode
	}{
		{"", ModeDualWrite},
		{"json_only", ModeJSONOnly},
		{"JSON_ONLY", ModeJSONOnly},
		{"json-only", ModeJSONOnly},
		{"jsononly", ModeJSONOnly},
		{"dual_write", ModeDualWrite},
		{"anything-else", ModeDualWrite},
	}
	for _, c := range cases {
		t.Setenv("ACTRESS_DB_MODE", c.env)
		got := ResolveStoreMode()
		if got != c.want {
			t.Errorf("ACTRESS_DB_MODE=%q → mode=%v, want %v", c.env, got, c.want)
		}
	}
}

func TestNewStore_DefaultDegradedLogIsBesideSQLiteFile(t *testing.T) {
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

	wantLog := filepath.Join(dataDir, "sync_degraded.jsonl")
	if got := store.degraded.Path(); got != wantLog {
		t.Errorf("degraded log path = %q, want %q", got, wantLog)
	}
}

func TestNewStore_ReplaysExistingDegradedLogAtStartup(t *testing.T) {
	tmp := t.TempDir()
	dataDir := filepath.Join(tmp, "json_db")
	writeFixtureAt(t, dataDir)

	// Pre-seed a degraded entry: a video.upsert that will succeed when
	// the live SQLite store comes online. The startup replay should
	// drain it.
	logPath := filepath.Join(dataDir, "sync_degraded.jsonl")
	entry := degradedEntry{
		Op:   degradedOpVideoUpsert,
		Key:  "STARS-707",
		Data: mustMarshal(t, &VideoData{Code: "STARS-707", Title: "from-degraded"}),
		Err:  "pre-stash",
	}
	if err := NewDegradedLog(logPath).Record(entry); err != nil {
		t.Fatalf("Record: %v", err)
	}

	store, err := NewStore(StoreConfig{
		Mode:    ModeDualWrite,
		DataDir: dataDir,
	})
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })

	// Startup replay should have drained the log.
	if _, err := os.Stat(logPath); err == nil {
		t.Errorf("degraded log still exists after startup replay: %s", logPath)
	}
	// And the SQLite row should reflect the replayed upsert.
	var title string
	if err := store.sqlite.db.QueryRow(
		`SELECT title FROM videos WHERE code='STARS-707'`,
	).Scan(&title); err != nil {
		t.Fatalf("read sqlite STARS-707: %v", err)
	}
	if title != "from-degraded" {
		t.Errorf("SQLite title after startup replay = %q, want from-degraded", title)
	}
}
