package jsonfixture

import (
	"errors"
	"os"
	"path/filepath"
	"testing"

	. "actress-classifier/pkg/database"
)

// --- JSON-side write error tails via a corrupted journal path ----------

func corruptedJournalDB(t *testing.T) *JSONDatabase {
	t.Helper()
	db := loadedJSONDB(t)
	// Seed a video so Update/Delete have something to act on.
	if err := db.AddVideo(&Video{Code: "SEED-1", Title: "s", Studio: "S"}); err != nil {
		t.Fatalf("seed AddVideo: %v", err)
	}
	db.mu.Lock()
	db.journalFile = "bad\x00journal.jsonl"
	db.mu.Unlock()
	return db
}

func TestAddVideo_JournalWriteFailurePropagates(t *testing.T) {
	db := corruptedJournalDB(t)
	if err := db.AddVideo(&Video{Code: "NEW-1", Title: "n"}); err == nil {
		t.Error("AddVideo with bad journal path returned nil error")
	}
}

func TestUpdateVideo_JournalWriteFailureWarnsButSucceeds(t *testing.T) {
	// UpdateVideo only warns on journal-write failure (does not fail the
	// op). The bad journal path still drives the warn branch; the
	// in-memory update applies.
	db := corruptedJournalDB(t)
	if err := db.UpdateVideo("SEED-1", &Video{Code: "SEED-1", Title: "u"}); err != nil {
		t.Errorf("UpdateVideo returned %v, want nil (journal failure only warns)", err)
	}
	got, err := db.GetVideo("SEED-1")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	if got.Title != "u" {
		t.Errorf("title = %q, want u (in-memory update applied)", got.Title)
	}
}

func TestUpdateVideoFields_JournalWriteFailurePropagates(t *testing.T) {
	db := corruptedJournalDB(t)
	if err := db.UpdateVideoFields("SEED-1", map[string]any{"title": "x"}); err == nil {
		t.Error("UpdateVideoFields with bad journal path returned nil error")
	}
}

func TestBatchUpdate_JournalWriteFailureWarnsButSucceeds(t *testing.T) {
	db := corruptedJournalDB(t)
	// BatchUpdate warns on journal failure but applies the in-memory batch.
	if err := db.BatchUpdate(map[string]*Video{"B-1": {Code: "B-1", Title: "b"}}); err != nil {
		t.Errorf("BatchUpdate returned %v, want nil (journal failure only warns)", err)
	}
	if _, err := db.GetVideo("B-1"); err != nil {
		t.Errorf("B-1 not applied in-memory: %v", err)
	}
}

func TestJSONDeleteVideo_NotFoundAndEmptyCode(t *testing.T) {
	db := loadedJSONDB(t)
	if err := db.DeleteVideo(""); !errors.Is(err, ErrInvalidCode) {
		t.Errorf("DeleteVideo empty code = %v, want ErrInvalidCode", err)
	}
	if err := db.DeleteVideo("ghost"); !errors.Is(err, ErrNotFound) {
		t.Errorf("DeleteVideo missing = %v, want ErrNotFound", err)
	}
}

func TestJSONUpdateVideo_EmptyCodeAndNotLoaded(t *testing.T) {
	db := loadedJSONDB(t)
	if err := db.UpdateVideo("", &Video{}); !errors.Is(err, ErrInvalidCode) {
		t.Errorf("UpdateVideo empty code = %v, want ErrInvalidCode", err)
	}
	unloaded := NewJSONDatabase(t.TempDir())
	if err := unloaded.UpdateVideo("X", &Video{}); err == nil {
		t.Error("UpdateVideo on unloaded db returned nil")
	}
}

func TestJSONUpdateVideoFields_NotFoundAndNotLoaded(t *testing.T) {
	db := loadedJSONDB(t)
	if err := db.UpdateVideoFields("ghost", map[string]any{"title": "x"}); !errors.Is(err, ErrNotFound) {
		t.Errorf("UpdateVideoFields missing = %v, want ErrNotFound", err)
	}
	unloaded := NewJSONDatabase(t.TempDir())
	if err := unloaded.UpdateVideoFields("X", nil); err == nil {
		t.Error("UpdateVideoFields on unloaded db returned nil")
	}
}

// --- restoreBackupDataFile rollback branch (sidecar clear failure) -----

func TestRestoreBackupDataFile_SidecarClearFailureRollsBack(t *testing.T) {
	dir := t.TempDir()
	dataFile := filepath.Join(dir, "data.json")
	if err := os.WriteFile(dataFile, []byte("original"), 0o600); err != nil {
		t.Fatal(err)
	}
	// A sidecar path containing a null byte makes clearBackupRestoreSidecars
	// fail AFTER the data file was swapped, triggering the rollback branch.
	err := restoreBackupDataFile(dataFile, []byte("new-content"), "bad\x00sidecar")
	if err == nil {
		t.Error("expected error when sidecar clear fails")
	}
	// Rollback should have restored the original content.
	got, readErr := os.ReadFile(dataFile)
	if readErr != nil {
		t.Fatalf("read data file after rollback: %v", readErr)
	}
	if string(got) != "original" {
		t.Errorf("after rollback content = %q, want original", got)
	}
}
