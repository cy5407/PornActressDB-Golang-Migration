package database

import (
	"path/filepath"
	"testing"
)

// JSONDatabase.BackupCreate error tails: bad backup dir, missing data file.
func TestJSONBackupCreate_BadBackupDirErrors(t *testing.T) {
	db := loadedJSONDB(t)
	db.mu.Lock()
	db.dataDir = "bad\x00dir"
	db.mu.Unlock()
	if _, err := db.BackupCreate(); err == nil {
		t.Error("BackupCreate with bad data dir returned nil error")
	}
}

func TestJSONBackupCreate_MissingDataFileErrors(t *testing.T) {
	db := loadedJSONDB(t)
	db.mu.Lock()
	// backup dir is fine, but data file path points nowhere readable.
	db.dataFile = filepath.Join(t.TempDir(), "no-such-data.json")
	db.mu.Unlock()
	if _, err := db.BackupCreate(); err == nil {
		t.Error("BackupCreate with missing data file returned nil error")
	}
}

// resolveMergeSourcePath rejects a path that does not survive Clean
// round-trip (defensive branch) — exercised via a path with a null byte
// which makes filepath.Abs fail.
func TestResolveMergeSourcePath_BadPathErrors(t *testing.T) {
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

// GetStats JSON-side full key surface on a populated db.
func TestJSONGetStats_PopulatedKeys(t *testing.T) {
	db := seededJSONDB(t)
	stats, err := db.GetStats()
	if err != nil {
		t.Fatalf("GetStats: %v", err)
	}
	for _, k := range []string{"video_count", "actress_count", "journal_size", "needs_compact"} {
		if _, ok := stats[k]; !ok {
			t.Errorf("stats missing key %q", k)
		}
	}
}

// GetDeletedCodes after a delete returns the tracked code.
func TestJSONGetDeletedCodes_AfterDelete(t *testing.T) {
	db := seededJSONDB(t)
	if err := db.DeleteVideo("BK-001"); err != nil {
		t.Fatalf("DeleteVideo: %v", err)
	}
	codes, err := db.GetDeletedCodes()
	if err != nil {
		t.Fatalf("GetDeletedCodes: %v", err)
	}
	found := false
	for _, c := range codes {
		if c == "BK-001" {
			found = true
		}
	}
	if !found {
		t.Errorf("deleted codes = %v, want BK-001", codes)
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
