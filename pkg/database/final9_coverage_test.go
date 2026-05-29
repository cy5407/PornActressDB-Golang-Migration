package database

import (
	"os"
	"path/filepath"
	"testing"
)

// copyFile with a DIRECTORY source: os.Open succeeds on a dir but the
// subsequent io.Copy read fails, exercising the io.Copy-error branch
// (which closes + removes the partial destination).
func TestSQLiteBackupCopyFile_DirectorySourceIoCopyError(t *testing.T) {
	srcDir := t.TempDir() // a directory, not a file
	dst := filepath.Join(t.TempDir(), "out.sqlite")
	if err := copyFile(srcDir, dst); err == nil {
		t.Error("copyFile with directory source returned nil error")
	}
	// Partial destination must have been removed.
	if _, err := os.Stat(dst); !os.IsNotExist(err) {
		t.Error("partial destination should be removed after io.Copy failure")
	}
}

// MigrateFromJSON / ResyncFromJSON on a closed store hit runImport's
// nil-db guard.
func TestMigrateFromJSON_ClosedStoreGuard(t *testing.T) {
	closed := &SQLiteStore{}
	src := writeJSONDB(t, minimalRoot())
	if _, err := closed.MigrateFromJSON(src, MigrationOptions{}); err == nil {
		t.Error("MigrateFromJSON on closed store returned nil error")
	}
	if _, err := closed.ResyncFromJSON(src, MigrationOptions{}); err == nil {
		t.Error("ResyncFromJSON on closed store returned nil error")
	}
}

// MigrateFromJSON with a missing source file hits loadJSONDatabaseRoot's
// read-error path inside runImport.
func TestMigrateFromJSON_MissingSourceFile(t *testing.T) {
	store := migrateTestStore(t)
	if _, err := store.MigrateFromJSON(filepath.Join(t.TempDir(), "absent.json"), MigrationOptions{}); err == nil {
		t.Error("MigrateFromJSON missing source returned nil error")
	}
}

// MigrateFromJSON with corrupt source JSON hits the parse-error path.
func TestMigrateFromJSON_CorruptSourceJSON(t *testing.T) {
	store := migrateTestStore(t)
	bad := filepath.Join(t.TempDir(), "bad.json")
	if err := os.WriteFile(bad, []byte("{not json"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := store.MigrateFromJSON(bad, MigrationOptions{}); err == nil {
		t.Error("MigrateFromJSON corrupt source returned nil error")
	}
}
