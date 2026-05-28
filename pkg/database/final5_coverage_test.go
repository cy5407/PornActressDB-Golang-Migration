package database

import (
	"os"
	"path/filepath"
	"testing"
)

// --- restoreBackupDataFile pre-clean + rename failure branches ---------

func TestRestoreBackupDataFile_StaleTempIsDirectoryErrors(t *testing.T) {
	dir := t.TempDir()
	dataFile := filepath.Join(dir, "data.json")
	if err := os.WriteFile(dataFile, []byte("orig"), 0o600); err != nil {
		t.Fatal(err)
	}
	// A NON-EMPTY directory at the temp path → os.Remove fails with a
	// non-IsNotExist error, exercising the stale-temp-clear branch.
	staleTmp := dataFile + ".restore.tmp"
	if err := os.MkdirAll(filepath.Join(staleTmp, "child"), 0o750); err != nil {
		t.Fatal(err)
	}
	if err := restoreBackupDataFile(dataFile, []byte("new")); err == nil {
		t.Error("restoreBackupDataFile with undeletable stale temp returned nil")
	}
}

func TestRestoreBackupDataFile_StaleBakIsDirectoryErrors(t *testing.T) {
	dir := t.TempDir()
	dataFile := filepath.Join(dir, "data.json")
	if err := os.WriteFile(dataFile, []byte("orig"), 0o600); err != nil {
		t.Fatal(err)
	}
	staleBak := dataFile + ".restore.bak"
	if err := os.MkdirAll(filepath.Join(staleBak, "child"), 0o750); err != nil {
		t.Fatal(err)
	}
	if err := restoreBackupDataFile(dataFile, []byte("new")); err == nil {
		t.Error("restoreBackupDataFile with undeletable stale bak returned nil")
	}
}

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

// --- DeleteVideo journal-write warn path via corrupt journal ----------

func TestJSONDeleteVideo_JournalWriteFailureWarnsButSucceeds(t *testing.T) {
	db := loadedJSONDB(t)
	if err := db.AddVideo(&Video{Code: "DEL-1", Title: "d"}); err != nil {
		t.Fatalf("AddVideo: %v", err)
	}
	db.mu.Lock()
	db.journalFile = "bad\x00journal.jsonl"
	db.mu.Unlock()
	// DeleteVideo only warns on journal failure; the in-memory delete
	// still applies and the call returns nil.
	if err := db.DeleteVideo("DEL-1"); err != nil {
		t.Errorf("DeleteVideo returned %v, want nil (journal failure only warns)", err)
	}
	if _, err := db.GetVideo("DEL-1"); err == nil {
		t.Error("DEL-1 should be deleted in-memory despite journal failure")
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
