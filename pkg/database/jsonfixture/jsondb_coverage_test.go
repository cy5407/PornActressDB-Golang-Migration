package jsonfixture

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	. "actress-classifier/pkg/database"
)

// loadedJSONDB returns a freshly-loaded JSONDatabase in a temp dir.
func loadedJSONDB(t *testing.T) *JSONDatabase {
	t.Helper()
	db := NewJSONDatabase(t.TempDir())
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load: %v", err)
	}
	return db
}

// --- CompactIfNeeded threshold branches (direct field manipulation) ----

func TestCompactIfNeeded_SizeThresholdTriggersCompaction(t *testing.T) {
	db := loadedJSONDB(t)
	db.mu.Lock()
	db.journalSize = JournalSizeThreshold // hit the size branch exactly
	db.mu.Unlock()

	compacted, err := db.CompactIfNeeded()
	if err != nil {
		t.Fatalf("CompactIfNeeded: %v", err)
	}
	if !compacted {
		t.Error("expected compaction when journalSize >= threshold")
	}
	// After compaction the journal counter resets.
	db.mu.RLock()
	defer db.mu.RUnlock()
	if db.journalSize != 0 {
		t.Errorf("journalSize = %d after compact, want 0", db.journalSize)
	}
}

func TestCompactIfNeeded_AgeThresholdTriggersCompaction(t *testing.T) {
	db := loadedJSONDB(t)
	db.mu.Lock()
	db.journalSize = 0
	db.journalCreatedAt = time.Now().Add(-time.Duration(JournalAgeThreshold+10) * time.Second)
	db.mu.Unlock()

	compacted, err := db.CompactIfNeeded()
	if err != nil {
		t.Fatalf("CompactIfNeeded: %v", err)
	}
	if !compacted {
		t.Error("expected compaction when journal age >= threshold")
	}
}

func TestCompactIfNeeded_BelowBothThresholdsNoCompaction(t *testing.T) {
	db := loadedJSONDB(t)
	compacted, err := db.CompactIfNeeded()
	if err != nil {
		t.Fatalf("CompactIfNeeded: %v", err)
	}
	if compacted {
		t.Error("fresh db should not need compaction")
	}
}

func TestNeedsCompact_TrueWhenSizeExceeded(t *testing.T) {
	db := loadedJSONDB(t)
	db.mu.Lock()
	db.journalSize = JournalSizeThreshold + 1
	db.mu.Unlock()
	if !db.NeedsCompact() {
		t.Error("NeedsCompact should be true past size threshold")
	}
}

// --- saveUnsafe / Save IO error tails via a bad dataFile path ----------

func TestSave_WriteFailureWhenDataFilePathIsBad(t *testing.T) {
	db := loadedJSONDB(t)
	db.mu.Lock()
	db.dataFile = "bad\x00data.json" // null byte → safefile.WriteFile fails
	db.mu.Unlock()
	if err := db.Save(); err == nil {
		t.Error("Save with null-byte dataFile returned nil error")
	}
}

func TestSave_NotLoadedIsError(t *testing.T) {
	db := NewJSONDatabase(t.TempDir()) // never Load'd
	if err := db.Save(); err == nil {
		t.Error("Save on unloaded db returned nil error")
	}
}

// --- CompactJournal error tail when save fails -------------------------

func TestCompactJournal_SaveFailurePropagates(t *testing.T) {
	db := loadedJSONDB(t)
	db.mu.Lock()
	db.dataFile = "bad\x00data.json"
	db.mu.Unlock()
	if err := db.CompactJournal(); err == nil {
		t.Error("CompactJournal with unwritable dataFile returned nil")
	}
}

func TestCompactJournal_NotLoadedIsError(t *testing.T) {
	db := NewJSONDatabase(t.TempDir())
	if err := db.CompactJournal(); err == nil {
		t.Error("CompactJournal on unloaded db returned nil")
	}
}

// --- appendJournalEntry OpenFile error via bad journal path ------------

func TestAppendJournalEntry_BadJournalPathErrors(t *testing.T) {
	db := loadedJSONDB(t)
	db.mu.Lock()
	db.journalFile = "bad\x00journal.jsonl"
	db.mu.Unlock()
	err := db.appendJournalEntry(&JournalEntry{Op: OpUpdate, Type: "video", ID: "X"})
	if err == nil {
		t.Error("appendJournalEntry with null-byte journalFile returned nil")
	}
}

func TestAppendJournalEntry_HappyPathWritesLine(t *testing.T) {
	db := loadedJSONDB(t)
	if err := db.appendJournalEntry(&JournalEntry{Op: OpUpdate, Type: "video", ID: "STARS-707"}); err != nil {
		t.Fatalf("appendJournalEntry: %v", err)
	}
	data, err := os.ReadFile(db.journalFile)
	if err != nil {
		t.Fatalf("read journal: %v", err)
	}
	if len(data) == 0 {
		t.Error("journal file is empty after append")
	}
}

// --- AddVideo + UpdateVideo + DeleteVideo journal growth --------------

func TestAddUpdateDelete_GrowsAndTracksJournal(t *testing.T) {
	db := loadedJSONDB(t)

	if err := db.AddVideo(&Video{Code: "JRN-001", Title: "j", Studio: "S"}); err != nil {
		t.Fatalf("AddVideo: %v", err)
	}
	if err := db.UpdateVideo("JRN-001", &Video{Code: "JRN-001", Title: "j2", Studio: "S"}); err != nil {
		t.Fatalf("UpdateVideo: %v", err)
	}
	if err := db.DeleteVideo("JRN-001"); err != nil {
		t.Fatalf("DeleteVideo: %v", err)
	}
	deleted, err := db.GetDeletedCodes()
	if err != nil {
		t.Fatalf("GetDeletedCodes: %v", err)
	}
	found := false
	for _, c := range deleted {
		if c == "JRN-001" {
			found = true
		}
	}
	if !found {
		t.Errorf("deleted codes = %v, want JRN-001 tracked", deleted)
	}
}

// --- BatchUpdate journal entries + reload ------------------------------

func TestBatchUpdate_AppendsJournalAndReloadReplays(t *testing.T) {
	dir := t.TempDir()
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load: %v", err)
	}
	updates := map[string]*Video{
		"BU-1": {Code: "BU-1", Title: "a", Studio: "S"},
		"BU-2": {Code: "BU-2", Title: "b", Studio: "S"},
		"BU-3": {Code: "BU-3", Title: "c", Studio: "S"},
	}
	if err := db.BatchUpdate(updates); err != nil {
		t.Fatalf("BatchUpdate: %v", err)
	}

	// Reload (replays journal) and confirm all three survive.
	db2 := NewJSONDatabase(dir)
	if err := db2.Load(context.Background()); err != nil {
		t.Fatalf("reload: %v", err)
	}
	for code := range updates {
		if _, err := db2.GetVideo(code); err != nil {
			t.Errorf("GetVideo(%s) after reload: %v", code, err)
		}
	}
}

// --- MergeFromFile JSON-side (mergeVideoRecord / mergeLinkRecords) -----

func TestJSONDatabase_MergeFromFileMergesVideosAndLinks(t *testing.T) {
	dir := t.TempDir()
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load: %v", err)
	}
	if err := db.AddVideo(&Video{Code: "EXIST-1", Title: "orig", Studio: "S"}); err != nil {
		t.Fatalf("seed AddVideo: %v", err)
	}

	src := writeJSONDB(t, &DatabaseData{
		SchemaVersion: SchemaVersion,
		Videos: map[string]*VideoData{
			"EXIST-1": {Code: "EXIST-1", Title: "merged", Studio: "S", UpdatedAt: "2026-07-01T00:00:00Z"},
			"NEW-9":   {Code: "NEW-9", Title: "new", Studio: "S", UpdatedAt: "2026-07-01T00:00:00Z"},
		},
		Actresses: map[string]*ActressData{
			"m1": {ID: "m1", Name: "Merged Actress"},
		},
		Links: []VideoActressLink{
			{VideoCode: "NEW-9", ActressID: "m1", RoleType: "主演", Timestamp: "2026-07-01T00:00:00Z"},
		},
	})

	// overwrite=false: EXIST-1 kept as orig, NEW-9 added.
	stats, err := db.MergeFromFile(src, false)
	if err != nil {
		t.Fatalf("MergeFromFile: %v", err)
	}
	if stats.VideosAdded != 1 {
		t.Errorf("VideosAdded = %d, want 1", stats.VideosAdded)
	}
	if stats.VideosSkipped != 1 {
		t.Errorf("VideosSkipped = %d, want 1 (EXIST-1)", stats.VideosSkipped)
	}
	if v, _ := db.GetVideo("EXIST-1"); v.Title != "orig" {
		t.Errorf("EXIST-1 title = %q, want orig (not overwritten)", v.Title)
	}

	// overwrite=true now updates EXIST-1.
	stats2, err := db.MergeFromFile(src, true)
	if err != nil {
		t.Fatalf("MergeFromFile overwrite: %v", err)
	}
	if stats2.VideosUpdated == 0 {
		t.Errorf("VideosUpdated = %d, want >=1 on overwrite", stats2.VideosUpdated)
	}
}

func TestJSONDatabase_MergeFromFileMissingSourceErrors(t *testing.T) {
	db := loadedJSONDB(t)
	if _, err := db.MergeFromFile(filepath.Join(t.TempDir(), "nope.json"), false); err == nil {
		t.Error("MergeFromFile missing source returned nil error")
	}
}

// --- restoreBackupDataFile sad path: unwritable temp via bad dir -------

func TestRestoreBackupDataFile_BadDataFilePathErrors(t *testing.T) {
	// dataFile under a null-byte path → WriteFile(tempPath) fails.
	if err := restoreBackupDataFile("bad\x00/data.json", []byte("x")); err == nil {
		t.Error("restoreBackupDataFile with bad path returned nil error")
	}
}
