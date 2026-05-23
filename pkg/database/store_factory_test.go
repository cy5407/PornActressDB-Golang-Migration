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

func TestResolveUseSQLiteReads_RecognisesTruthySpellings(t *testing.T) {
	cases := []struct {
		env  string
		want bool
	}{
		// Truthy: case-insensitive, surrounding whitespace tolerated.
		{"true", true},
		{"TRUE", true},
		{"True", true},
		{"1", true},
		{"yes", true},
		{"YES", true},
		{"on", true},
		{"ON", true},
		{"  true  ", true},
		{"\tyes\n", true},

		// Falsy / unrecognised — must default to false.
		{"", false},
		{"false", false},
		{"FALSE", false},
		{"0", false},
		{"no", false},
		{"off", false},
		{"2", false},
		{"truthy", false},
		{"y", false},
		{"   ", false},
	}
	for _, c := range cases {
		t.Setenv("USE_SQLITE_READS", c.env)
		if got := ResolveUseSQLiteReads(); got != c.want {
			t.Errorf("USE_SQLITE_READS=%q → %v, want %v", c.env, got, c.want)
		}
	}
}

func TestResolveUseSQLiteReads_UnsetIsFalse(t *testing.T) {
	// Explicitly unset (not just empty string): t.Setenv with "" still
	// sets the var to empty, so this case is already covered above. Here
	// we make sure os.Unsetenv() yields false too.
	if err := os.Unsetenv("USE_SQLITE_READS"); err != nil {
		t.Fatalf("Unsetenv: %v", err)
	}
	if ResolveUseSQLiteReads() {
		t.Error("ResolveUseSQLiteReads with var unset should be false")
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

// TestNewStore_OpenFailureCountsFallbackWhenUseSQLiteReads forces
// openAndInitSQLite to fail (by pointing SQLitePath at a child of a
// regular file, so MkdirAll on the parent errors), then asserts the
// open-time fallback counter behaviour spelled out in spec § 4.1 /
// Phase B1 plan:
//
//   - UseSQLiteReads=true   → counted once (operator must see the
//     downgrade through sqlite_read_fallback_total).
//   - UseSQLiteReads=false  → NOT counted (silent collapse, Phase A3
//     behaviour preserved).
//   - ModeJSONOnly+true     → NOT counted (explicit rollback, not an
//     availability failure).
func TestNewStore_OpenFailureCountsFallbackWhenUseSQLiteReads(t *testing.T) {
	cases := []struct {
		name           string
		mode           StoreMode
		useSQLiteReads bool
		wantCount      int64
	}{
		{"DualWrite_ReadsOn_CountsOnce", ModeDualWrite, true, 1},
		{"DualWrite_ReadsOff_NotCounted", ModeDualWrite, false, 0},
		{"JSONOnly_ReadsOn_NotCounted", ModeJSONOnly, true, 0},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			tmp := t.TempDir()
			dataDir := filepath.Join(tmp, "json_db")
			writeFixtureAt(t, dataDir)

			// Force openAndInitSQLite to fail in ModeDualWrite by
			// pointing SQLitePath at a child of a regular file —
			// MkdirAll on the "parent" (a file) returns an error.
			// ModeJSONOnly skips SQLite entirely, so the bogus path is
			// inert there; we still pass it to prove no open attempt
			// happens.
			blocker := filepath.Join(tmp, "blocker")
			if err := os.WriteFile(blocker, []byte("not a directory"), 0o600); err != nil {
				t.Fatalf("seed blocker file: %v", err)
			}
			sqlitePath := filepath.Join(blocker, "db.sqlite")

			store, err := NewStore(StoreConfig{
				Mode:           c.mode,
				DataDir:        dataDir,
				SQLitePath:     sqlitePath,
				UseSQLiteReads: c.useSQLiteReads,
			})
			if err != nil {
				t.Fatalf("NewStore: %v", err)
			}
			t.Cleanup(func() { _ = store.Close() })

			if store.sqlite != nil {
				t.Fatalf("expected sqlite to be nil after open/init failure or json_only, got %+v", store.sqlite)
			}
			if got := store.SQLiteReadFallbackTotal(); got != c.wantCount {
				t.Errorf("SQLiteReadFallbackTotal = %d, want %d", got, c.wantCount)
			}

			// db stats must surface the same number — that is the
			// observable contract Python / Wails consumers rely on.
			stats, err := store.GetStats()
			if err != nil {
				t.Fatalf("GetStats: %v", err)
			}
			gotStat, ok := stats["sqlite_read_fallback_total"].(int64)
			if !ok {
				t.Fatalf("sqlite_read_fallback_total missing or wrong type: %T (%v)",
					stats["sqlite_read_fallback_total"], stats["sqlite_read_fallback_total"])
			}
			if gotStat != c.wantCount {
				t.Errorf("stats sqlite_read_fallback_total = %d, want %d", gotStat, c.wantCount)
			}
		})
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
