package database

import (
	"os"
	"path/filepath"
	"testing"
)

// restoreBackupDataFile branches + JSON-side DeleteVideo journal-warn
// tests moved to pkg/database/jsonfixture/final5_coverage_test.go.

// --- NewStore: SQLitePath is a directory → open/init fails -------------

func TestNewStore_SQLitePathIsDirectoryErrors(t *testing.T) {
	dir := t.TempDir()
	// Make the intended sqlite path an existing directory so the driver
	// cannot open it as a database file.
	sqlitePath := filepath.Join(dir, "db.sqlite")
	if err := os.MkdirAll(sqlitePath, 0o750); err != nil {
		t.Fatal(err)
	}
	if _, err := NewStore(StoreConfig{SQLitePath: sqlitePath, DataDir: dir, SkipBootstrap: true}); err == nil {
		t.Error("NewStore with directory sqlite path returned nil error")
	}
}

// --- runImport: ResyncFromJSON full round trip (wipe + repopulate) -----

func TestResyncFromJSON_FullRoundTripRepopulates(t *testing.T) {
	store := runtimeTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	rep, err := store.ResyncFromJSON(src, MigrationOptions{})
	if err != nil {
		t.Fatalf("ResyncFromJSON: %v", err)
	}
	if !rep.Success {
		t.Error("resync report not Success")
	}
	if rep.VideosImported != 3 {
		t.Errorf("VideosImported = %d, want 3", rep.VideosImported)
	}
}
