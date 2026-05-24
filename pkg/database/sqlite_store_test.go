package database

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func newSQLiteStoreForTest(t *testing.T, name string) *SQLiteStore {
	t.Helper()
	path := filepath.Join(t.TempDir(), name)
	store, err := OpenSQLiteStore(path)
	if err != nil {
		t.Fatalf("OpenSQLiteStore(%q): %v", path, err)
	}
	t.Cleanup(func() { _ = store.Close() })
	return store
}

func TestSQLiteStore_SchemaVersion_FreshDBIsZero(t *testing.T) {
	store := newSQLiteStoreForTest(t, "fresh.sqlite")

	v, err := store.SchemaVersion()
	if err != nil {
		t.Fatalf("SchemaVersion: %v", err)
	}
	if v != 0 {
		t.Errorf("user_version on fresh DB = %d, want 0", v)
	}
}

func TestSQLiteStore_InitSchema_SetsUserVersion(t *testing.T) {
	store := newSQLiteStoreForTest(t, "init.sqlite")

	if err := store.InitSchema(); err != nil {
		t.Fatalf("InitSchema: %v", err)
	}

	v, err := store.SchemaVersion()
	if err != nil {
		t.Fatalf("SchemaVersion: %v", err)
	}
	if v != SQLiteSchemaVersion {
		t.Errorf("user_version after InitSchema = %d, want %d", v, SQLiteSchemaVersion)
	}
}

func TestSQLiteStore_InitSchema_CreatesAllTablesAndViews(t *testing.T) {
	store := newSQLiteStoreForTest(t, "tables.sqlite")

	if err := store.InitSchema(); err != nil {
		t.Fatalf("InitSchema: %v", err)
	}

	for _, name := range []string{
		"db_meta",
		"videos",
		"actresses",
		"actress_aliases",
		"video_actress_links",
		"legacy_video_actress_links",
	} {
		var got string
		err := store.db.QueryRow(
			`SELECT name FROM sqlite_master WHERE type='table' AND name=?`, name,
		).Scan(&got)
		if err != nil {
			t.Errorf("table %q not found after InitSchema: %v", name, err)
		}
	}

	for _, name := range []string{
		"actress_video_counts",
		"studio_statistics",
		"enhanced_actress_studio_statistics",
	} {
		var got string
		err := store.db.QueryRow(
			`SELECT name FROM sqlite_master WHERE type='view' AND name=?`, name,
		).Scan(&got)
		if err != nil {
			t.Errorf("view %q not found after InitSchema: %v", name, err)
		}
	}
}

func TestSQLiteStore_InitSchema_SeedsDBMeta(t *testing.T) {
	store := newSQLiteStoreForTest(t, "seed.sqlite")

	if err := store.InitSchema(); err != nil {
		t.Fatalf("InitSchema: %v", err)
	}

	for _, key := range []string{
		"schema_version",
		"description",
		"encoding",
		"data_hash",
		"created_at",
		"updated_at",
	} {
		var value string
		err := store.db.QueryRow(`SELECT value FROM db_meta WHERE key=?`, key).Scan(&value)
		if err != nil {
			t.Errorf("db_meta missing key %q: %v", key, err)
		}
	}

	// spec § 2.1: schema_version mirrors the JSON-semantic version string.
	var schemaVer string
	if err := store.db.QueryRow(
		`SELECT value FROM db_meta WHERE key='schema_version'`,
	).Scan(&schemaVer); err != nil {
		t.Fatalf("read schema_version: %v", err)
	}
	if schemaVer != SchemaVersion {
		t.Errorf("db_meta.schema_version = %q, want %q", schemaVer, SchemaVersion)
	}

	// data_hash is the reserved/empty field per spec § 2.1.
	var hash string
	if err := store.db.QueryRow(
		`SELECT value FROM db_meta WHERE key='data_hash'`,
	).Scan(&hash); err != nil {
		t.Fatalf("read data_hash: %v", err)
	}
	if hash != "" {
		t.Errorf("db_meta.data_hash = %q, want empty string", hash)
	}
}

func TestSQLiteStore_InitSchema_IsIdempotentOnExistingV3(t *testing.T) {
	store := newSQLiteStoreForTest(t, "idem.sqlite")

	if err := store.InitSchema(); err != nil {
		t.Fatalf("first InitSchema: %v", err)
	}
	if err := store.InitSchema(); err != nil {
		t.Errorf("second InitSchema on v3 must be no-op, got: %v", err)
	}

	v, err := store.SchemaVersion()
	if err != nil {
		t.Fatalf("SchemaVersion: %v", err)
	}
	if v != SQLiteSchemaVersion {
		t.Errorf("user_version after 2nd init = %d, want %d", v, SQLiteSchemaVersion)
	}
}

func TestSQLiteStore_InitSchema_AppliesAdditiveObjectsOnExistingV3(t *testing.T) {
	store := newSQLiteStoreForTest(t, "additive.sqlite")

	if err := store.InitSchema(); err != nil {
		t.Fatalf("first InitSchema: %v", err)
	}
	if _, err := store.db.Exec(`DROP TABLE legacy_video_actress_links`); err != nil {
		t.Fatalf("drop additive table: %v", err)
	}
	if err := store.InitSchema(); err != nil {
		t.Fatalf("InitSchema on existing v3: %v", err)
	}

	var name string
	err := store.db.QueryRow(
		`SELECT name FROM sqlite_master WHERE type='table' AND name='legacy_video_actress_links'`,
	).Scan(&name)
	if err != nil {
		t.Fatalf("legacy_video_actress_links not recreated: %v", err)
	}
}

func TestSQLiteStore_InitSchema_RejectsOlderVersions(t *testing.T) {
	for _, oldVer := range []int{1, 2} {
		oldVer := oldVer
		t.Run(fmt.Sprintf("v%d", oldVer), func(t *testing.T) {
			store := newSQLiteStoreForTest(t, fmt.Sprintf("v%d.sqlite", oldVer))

			// Pretend the file was created by an older schema version.
			if _, err := store.db.Exec(
				fmt.Sprintf("PRAGMA user_version = %d", oldVer),
			); err != nil {
				t.Fatalf("seed user_version=%d: %v", oldVer, err)
			}

			err := store.InitSchema()
			if !errors.Is(err, ErrSchemaVersionMismatch) {
				t.Errorf("InitSchema on v%d returned %v, want ErrSchemaVersionMismatch",
					oldVer, err)
			}
		})
	}
}

func TestSQLiteStore_InitSchema_RejectsNewerVersions(t *testing.T) {
	// Future-proofing: an unknown forward version must also fail loudly
	// rather than be silently downgraded.
	store := newSQLiteStoreForTest(t, "future.sqlite")
	if _, err := store.db.Exec("PRAGMA user_version = 99"); err != nil {
		t.Fatalf("seed user_version=99: %v", err)
	}
	err := store.InitSchema()
	if !errors.Is(err, ErrSchemaVersionMismatch) {
		t.Errorf("InitSchema on v99 returned %v, want ErrSchemaVersionMismatch", err)
	}
}

func TestSQLiteStore_AppliesForeignKeysAndWAL(t *testing.T) {
	store := newSQLiteStoreForTest(t, "pragma.sqlite")

	var fk int
	if err := store.db.QueryRow("PRAGMA foreign_keys").Scan(&fk); err != nil {
		t.Fatalf("read foreign_keys: %v", err)
	}
	if fk != 1 {
		t.Errorf("foreign_keys = %d, want 1", fk)
	}

	var journal string
	if err := store.db.QueryRow("PRAGMA journal_mode").Scan(&journal); err != nil {
		t.Fatalf("read journal_mode: %v", err)
	}
	if journal != "wal" {
		t.Errorf("journal_mode = %q, want \"wal\"", journal)
	}
}

func TestSQLiteStore_Close_IsIdempotent(t *testing.T) {
	path := filepath.Join(t.TempDir(), "close.sqlite")
	store, err := OpenSQLiteStore(path)
	if err != nil {
		t.Fatalf("OpenSQLiteStore: %v", err)
	}

	if err := store.Close(); err != nil {
		t.Errorf("first Close: %v", err)
	}
	if err := store.Close(); err != nil {
		t.Errorf("second Close should be no-op, got: %v", err)
	}
}

func TestSQLiteStore_Close_NilReceiverIsSafe(t *testing.T) {
	var s *SQLiteStore
	if err := s.Close(); err != nil {
		t.Errorf("Close on nil receiver should be no-op, got: %v", err)
	}
}

func TestOpenSQLiteStore_RejectsEmptyPath(t *testing.T) {
	if _, err := OpenSQLiteStore(""); err == nil {
		t.Error("OpenSQLiteStore(\"\") returned nil error, want non-nil")
	}
}

// TestSQLiteSchemaSQL_MatchesCanonicalFile guards against the Go embed
// drifting away from the on-disk canonical schema. tools-rs reads the same
// pkg/database/sqlite_schema.sql via include_str! (see
// tools-rs/src/v3_schema.rs and tools-rs/tests/integration_db_tool.rs).
// Together the two tests pin Go and Rust to identical bytes.
func TestSQLiteSchemaSQL_MatchesCanonicalFile(t *testing.T) {
	onDisk, err := os.ReadFile("sqlite_schema.sql")
	if err != nil {
		t.Fatalf("read sqlite_schema.sql: %v", err)
	}
	if string(onDisk) != sqliteSchemaSQL {
		t.Fatal("embedded sqliteSchemaSQL drifted from sqlite_schema.sql on disk")
	}
}

func TestSQLiteSchemaSQL_ContainsExpectedV3Markers(t *testing.T) {
	for _, table := range []string{
		"db_meta",
		"videos",
		"actresses",
		"actress_aliases",
		"video_actress_links",
		"legacy_video_actress_links",
	} {
		marker := "CREATE TABLE IF NOT EXISTS " + table
		if !strings.Contains(sqliteSchemaSQL, marker) {
			t.Errorf("schema missing table marker %q", marker)
		}
	}
	for _, view := range []string{
		"actress_video_counts",
		"studio_statistics",
		"enhanced_actress_studio_statistics",
	} {
		marker := "CREATE VIEW " + view
		if !strings.Contains(sqliteSchemaSQL, marker) {
			t.Errorf("schema missing view marker %q", marker)
		}
	}
}

func TestSQLiteStore_Path_ReturnsOpenedPath(t *testing.T) {
	path := filepath.Join(t.TempDir(), "pathcheck.sqlite")
	store, err := OpenSQLiteStore(path)
	if err != nil {
		t.Fatalf("OpenSQLiteStore: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })

	if got := store.Path(); got != path {
		t.Errorf("Path() = %q, want %q", got, path)
	}
}
