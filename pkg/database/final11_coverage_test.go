package database

import (
	"runtime"
	"testing"
)

// JSON-side BackupCreate / GetStats / GetDeletedCodes tests moved to
// pkg/database/jsonfixture/final11_coverage_test.go.

// resolveMergeSourcePath rejects a path that does not survive Clean
// round-trip (defensive branch) — exercised via a path with a null byte
// which makes filepath.Abs fail.
func TestResolveMergeSourcePath_BadPathErrors(t *testing.T) {
	// resolveMergeSourcePath errors only when filepath.Abs fails; a
	// null-byte path triggers that on Windows only (Linux/macOS accept it).
	if runtime.GOOS != "windows" {
		t.Skip("filepath.Abs rejects null-byte paths only on Windows")
	}
	if _, err := resolveMergeSourcePath("bad\x00path.json"); err == nil {
		t.Error("resolveMergeSourcePath with null-byte path returned nil error")
	}
}

// parseBackupDate: valid and invalid filenames.
func TestParseBackupDate_ValidAndInvalid(t *testing.T) {
	if _, ok := parseBackupDate("backup_2026-05-01_12-00-00.json"); !ok {
		t.Error("expected valid backup filename to parse")
	}
	if _, ok := parseBackupDate("not-a-backup.json"); ok {
		t.Error("expected invalid backup filename to fail parse")
	}
	if _, ok := parseBackupDate("backup_garbage.json"); ok {
		t.Error("expected garbage timestamp to fail parse")
	}
}

// isEmpty on a populated runtime store returns false; on a store whose
// videos table was emptied but actresses remain, also false.
func TestIsEmpty_ActressesPresentVideosEmpty(t *testing.T) {
	store := runtimeTestStore(t)
	if _, err := store.db.Exec("DELETE FROM videos"); err != nil {
		t.Fatalf("delete videos: %v", err)
	}
	empty, err := store.isEmpty()
	if err != nil {
		t.Fatalf("isEmpty: %v", err)
	}
	if empty {
		t.Error("isEmpty = true, want false (actresses still present)")
	}
}
