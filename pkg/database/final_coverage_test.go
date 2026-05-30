package database

import (
	"os"
	"path/filepath"
	"testing"
)

// JSON-side write error tails (corruptedJournalDB / JournalWriteFailure*)
// and restoreBackupDataFile rollback tests moved to
// pkg/database/jsonfixture/final_coverage_test.go.

// --- NewStore error branches -------------------------------------------

func TestNewStore_MkdirParentFailureErrors(t *testing.T) {
	// Null byte in SQLitePath → MkdirAll(Dir(path)) fails.
	_, err := NewStore(StoreConfig{SQLitePath: "bad\x00/x.sqlite", SkipBootstrap: true})
	if err == nil {
		t.Error("NewStore with bad sqlite parent returned nil error")
	}
}

func TestNewStore_SkipBootstrapReturnsEmptyStore(t *testing.T) {
	dir := t.TempDir()
	store, err := NewStore(StoreConfig{
		SQLitePath:    filepath.Join(dir, "db.sqlite"),
		DataDir:       dir,
		SkipBootstrap: true,
	})
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}
	defer store.Close()
	n, err := store.GetVideoCount()
	if err != nil {
		t.Fatalf("GetVideoCount: %v", err)
	}
	if n != 0 {
		t.Errorf("video count = %d, want 0 (skip bootstrap, fresh)", n)
	}
}

func TestNewStore_GreenfieldNoJSONComesUpEmpty(t *testing.T) {
	dir := t.TempDir()
	// No data.json present → bootstrap is a no-op, store comes up empty.
	store, err := NewStore(StoreConfig{
		SQLitePath: filepath.Join(dir, "db.sqlite"),
		DataDir:    dir,
	})
	if err != nil {
		t.Fatalf("NewStore greenfield: %v", err)
	}
	defer store.Close()
	if n, _ := store.GetVideoCount(); n != 0 {
		t.Errorf("greenfield video count = %d, want 0", n)
	}
}

func TestNewStore_BootstrapsFromPresentJSON(t *testing.T) {
	dir := t.TempDir()
	// Place a valid data.json at the resolved DataFile location. Use the
	// jsonfixture JSONDatabase to populate one in the right shape.
	paths := ResolveDataDirPaths(dir)
	if err := os.MkdirAll(filepath.Dir(paths.DataFile), 0o750); err != nil {
		t.Fatal(err)
	}
	raw := writeJSONDB(t, minimalRoot())
	content, err := os.ReadFile(raw)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(paths.DataFile, content, 0o600); err != nil {
		t.Fatal(err)
	}

	store, err := NewStore(StoreConfig{DataDir: dir})
	if err != nil {
		t.Fatalf("NewStore bootstrap: %v", err)
	}
	defer store.Close()
	if n, _ := store.GetVideoCount(); n != 3 {
		t.Errorf("bootstrapped video count = %d, want 3", n)
	}
}
