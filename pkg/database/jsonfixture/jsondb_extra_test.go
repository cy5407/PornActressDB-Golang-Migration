package jsonfixture

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	. "actress-classifier/pkg/database"
)

// ============================================================
// AddVideo
// ============================================================

func TestAddVideo_Success(t *testing.T) {
	db, _ := setupTestDB(t)

	video := NewVideo("STARS-100")
	video.Title = "新增測試"
	if err := db.AddVideo(video); err != nil {
		t.Fatalf("AddVideo error: %v", err)
	}

	got, err := db.GetVideo("STARS-100")
	if err != nil {
		t.Fatalf("GetVideo after AddVideo error: %v", err)
	}
	if got.Title != "新增測試" {
		t.Errorf("title = %q, want %q", got.Title, "新增測試")
	}
}

func TestAddVideo_EmptyCode(t *testing.T) {
	db, _ := setupTestDB(t)
	if err := db.AddVideo(&VideoData{}); err != ErrInvalidCode {
		t.Errorf("expected ErrInvalidCode, got %v", err)
	}
}

// ============================================================
// ListVideos / GetAllVideos / GetVideoCount
// ============================================================

func TestListVideos(t *testing.T) {
	db, _ := setupTestDB(t)

	for _, code := range []string{"ABC-001", "ABC-002", "ABC-003"} {
		if err := db.UpdateVideo(code, NewVideo(code)); err != nil {
			t.Fatalf("UpdateVideo error: %v", err)
		}
	}

	codes, err := db.ListVideos()
	if err != nil {
		t.Fatalf("ListVideos error: %v", err)
	}
	if len(codes) != 3 {
		t.Errorf("expected 3 codes, got %d", len(codes))
	}
}

func TestGetAllVideos(t *testing.T) {
	db, _ := setupTestDB(t)

	db.UpdateVideo("IPX-001", NewVideo("IPX-001")) //nolint:errcheck
	db.UpdateVideo("IPX-002", NewVideo("IPX-002")) //nolint:errcheck

	videos, err := db.GetAllVideos()
	if err != nil {
		t.Fatalf("GetAllVideos error: %v", err)
	}
	if len(videos) != 2 {
		t.Errorf("expected 2 videos, got %d", len(videos))
	}
}

func TestGetVideoCountExtra(t *testing.T) {
	db, _ := setupTestDB(t)
	db.UpdateVideo("X-001", NewVideo("X-001")) //nolint:errcheck

	count, err := db.GetVideoCount()
	if err != nil {
		t.Fatalf("GetVideoCount error: %v", err)
	}
	if count != 1 {
		t.Errorf("expected count=1, got %d", count)
	}
}

// ============================================================
// Compact / CompactIfNeeded / NeedsCompact
// ============================================================

func TestCompact(t *testing.T) {
	db, _ := setupTestDB(t)
	db.UpdateVideo("SONE-001", NewVideo("SONE-001")) //nolint:errcheck

	if err := db.Compact(); err != nil {
		t.Fatalf("Compact error: %v", err)
	}

	// After compact, journal should be empty
	count, err := db.GetJournalEntryCount()
	if err != nil {
		t.Fatalf("GetJournalEntryCount error: %v", err)
	}
	if count != 0 {
		t.Errorf("expected 0 journal entries after compact, got %d", count)
	}
}

func TestCompactIfNeeded_BelowThreshold(t *testing.T) {
	db, _ := setupTestDB(t)

	compacted, err := db.CompactIfNeeded()
	if err != nil {
		t.Fatalf("CompactIfNeeded error: %v", err)
	}
	if compacted {
		t.Error("expected no compact on empty db")
	}
}

func TestNeedsCompact(t *testing.T) {
	db, _ := setupTestDB(t)
	// Fresh db should not need compact
	if db.NeedsCompact() {
		t.Error("expected NeedsCompact=false for fresh db")
	}
}

// ============================================================
// GetStatsStruct
// ============================================================

func TestGetStatsStruct(t *testing.T) {
	db, _ := setupTestDB(t)
	db.UpdateVideo("STATS-001", NewVideo("STATS-001")) //nolint:errcheck

	stats, err := db.GetStatsStruct()
	if err != nil {
		t.Fatalf("GetStatsStruct error: %v", err)
	}
	if stats.TotalVideos != 1 {
		t.Errorf("TotalVideos = %d, want 1", stats.TotalVideos)
	}
}

// ============================================================
// GetDeletedCodes
// ============================================================

func TestGetDeletedCodes(t *testing.T) {
	db, _ := setupTestDB(t)
	db.UpdateVideo("DEL-001", NewVideo("DEL-001")) //nolint:errcheck
	db.DeleteVideo("DEL-001")                      //nolint:errcheck

	codes, err := db.GetDeletedCodes()
	if err != nil {
		t.Fatalf("GetDeletedCodes error: %v", err)
	}
	if len(codes) != 1 || codes[0] != "DEL-001" {
		t.Errorf("expected [DEL-001], got %v", codes)
	}
}

// ============================================================
// UpsertActress / GetActress / DeleteActress / ListActresses
// ============================================================

func TestUpsertAndGetActress(t *testing.T) {
	db, _ := setupTestDB(t)

	actress := &ActressData{ID: "test-actress-1", Name: "テスト女優"}
	if err := db.UpsertActress(actress); err != nil {
		t.Fatalf("UpsertActress error: %v", err)
	}

	got, err := db.GetActress("test-actress-1")
	if err != nil {
		t.Fatalf("GetActress error: %v", err)
	}
	if got.Name != "テスト女優" {
		t.Errorf("Name = %q, want %q", got.Name, "テスト女優")
	}
}

func TestDeleteActress(t *testing.T) {
	db, _ := setupTestDB(t)

	actress := &ActressData{ID: "to-delete", Name: "削除対象"}
	db.UpsertActress(actress) //nolint:errcheck

	if err := db.DeleteActress("to-delete"); err != nil {
		t.Fatalf("DeleteActress error: %v", err)
	}

	if _, err := db.GetActress("to-delete"); err != ErrNotFound {
		t.Errorf("expected ErrNotFound after delete, got %v", err)
	}
}

func TestDeleteActress_NotFound(t *testing.T) {
	db, _ := setupTestDB(t)
	if err := db.DeleteActress("nonexistent"); err != ErrNotFound {
		t.Errorf("expected ErrNotFound, got %v", err)
	}
}

func TestListActresses(t *testing.T) {
	db, _ := setupTestDB(t)
	db.UpsertActress(&ActressData{ID: "a1", Name: "Actress One"}) //nolint:errcheck
	db.UpsertActress(&ActressData{ID: "a2", Name: "Actress Two"}) //nolint:errcheck

	ids, err := db.ListActresses()
	if err != nil {
		t.Fatalf("ListActresses error: %v", err)
	}
	if len(ids) != 2 {
		t.Errorf("expected 2 actresses, got %d", len(ids))
	}
}

// ============================================================
// GetActressStats / GetStudioStats
// ============================================================

func TestGetActressStats(t *testing.T) {
	db, _ := setupTestDB(t)

	v1 := NewVideo("AAA-001")
	v1.Actresses = []string{"女優A", "女優B"}
	v2 := NewVideo("AAA-002")
	v2.Actresses = []string{"女優A"}
	db.UpdateVideo("AAA-001", v1) //nolint:errcheck
	db.UpdateVideo("AAA-002", v2) //nolint:errcheck

	stats, err := db.GetActressStats()
	if err != nil {
		t.Fatalf("GetActressStats error: %v", err)
	}
	if len(stats) == 0 {
		t.Error("expected non-empty actress stats")
	}
	// First entry should be 女優A (2 videos)
	if stats[0]["actress_name"] != "女優A" {
		t.Errorf("expected 女優A first, got %v", stats[0]["actress_name"])
	}
}

func TestGetStudioStats(t *testing.T) {
	db, _ := setupTestDB(t)

	v1 := NewVideo("S1-001")
	v1.Studio = "SOD"
	v2 := NewVideo("S1-002")
	v2.Studio = "SOD"
	v3 := NewVideo("S1-003")
	v3.Studio = "MOODYZ"
	db.UpdateVideo("S1-001", v1) //nolint:errcheck
	db.UpdateVideo("S1-002", v2) //nolint:errcheck
	db.UpdateVideo("S1-003", v3) //nolint:errcheck

	stats, err := db.GetStudioStats()
	if err != nil {
		t.Fatalf("GetStudioStats error: %v", err)
	}
	if len(stats) == 0 {
		t.Error("expected non-empty studio stats")
	}
	if stats[0]["studio"] != "SOD" {
		t.Errorf("expected SOD first, got %v", stats[0]["studio"])
	}
}

// ============================================================
// BackupCreate / BackupList / BackupRestore / BackupCleanup
// ============================================================

func TestBackupCreate_And_List(t *testing.T) {
	db, _ := setupTestDB(t)
	db.UpdateVideo("BK-001", NewVideo("BK-001")) //nolint:errcheck

	// Compact first so data.json exists
	if err := db.Compact(); err != nil {
		t.Fatalf("Compact error: %v", err)
	}

	path, err := db.BackupCreate()
	if err != nil {
		t.Fatalf("BackupCreate error: %v", err)
	}
	if _, statErr := os.Stat(path); os.IsNotExist(statErr) {
		t.Errorf("backup file %q should exist", path)
	}

	paths, err := db.BackupList()
	if err != nil {
		t.Fatalf("BackupList error: %v", err)
	}
	if len(paths) != 1 {
		t.Errorf("expected 1 backup, got %d", len(paths))
	}
}

func TestBackupList_NoBackupDir(t *testing.T) {
	db, _ := setupTestDB(t)
	paths, err := db.BackupList()
	if err != nil {
		t.Fatalf("BackupList with no backup dir error: %v", err)
	}
	if len(paths) != 0 {
		t.Errorf("expected empty list, got %v", paths)
	}
}

func TestBackupCleanup_NoDir(t *testing.T) {
	db, _ := setupTestDB(t)
	deleted, err := db.BackupCleanup(30, 10)
	if err != nil {
		t.Fatalf("BackupCleanup with no dir error: %v", err)
	}
	if deleted != 0 {
		t.Errorf("expected 0 deleted, got %d", deleted)
	}
}

func TestBackupRestore(t *testing.T) {
	db, dir := setupTestDB(t)
	db.UpdateVideo("R-001", NewVideo("R-001")) //nolint:errcheck
	if err := db.Compact(); err != nil {
		t.Fatalf("Compact error: %v", err)
	}

	backupPath, err := db.BackupCreate()
	if err != nil {
		t.Fatalf("BackupCreate error: %v", err)
	}

	// Delete the video and verify it's gone
	db.DeleteVideo("R-001") //nolint:errcheck
	if err := db.Compact(); err != nil {
		t.Fatalf("Compact after delete error: %v", err)
	}

	if err := db.BackupRestore(backupPath); err != nil {
		t.Fatalf("BackupRestore error: %v", err)
	}

	// After restore, R-001 should be back
	db2 := NewJSONDatabase(dir)
	if err := db2.Load(context.Background()); err != nil {
		t.Fatalf("Load after restore error: %v", err)
	}
	if _, err := db2.GetVideo("R-001"); err != nil {
		t.Errorf("expected R-001 to exist after restore, got %v", err)
	}
}

// ============================================================
// removeOldestBackups helper (indirect via BackupCleanup)
// ============================================================

func TestBackupCleanup_ExceedsMaxCount(t *testing.T) {
	db, dir := setupTestDB(t)
	db.UpdateVideo("CC-001", NewVideo("CC-001")) //nolint:errcheck
	if err := db.Compact(); err != nil {
		t.Fatalf("Compact error: %v", err)
	}

	// Create 3 backups
	backupDir := filepath.Join(dir, "backup")
	os.MkdirAll(backupDir, 0700) //nolint:errcheck
	for _, name := range []string{"backup_2020-01-01_00-00-01.json", "backup_2020-01-02_00-00-02.json", "backup_2020-01-03_00-00-03.json"} {
		os.WriteFile(filepath.Join(backupDir, name), []byte("{}"), 0600) //nolint:errcheck
	}

	// Keep max 2
	deleted, err := db.BackupCleanup(365*10, 2)
	if err != nil {
		t.Fatalf("BackupCleanup error: %v", err)
	}
	if deleted != 1 {
		t.Errorf("expected 1 deleted for maxCount=2 with 3 files, got %d", deleted)
	}
}
