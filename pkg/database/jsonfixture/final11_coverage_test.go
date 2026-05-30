package jsonfixture

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
