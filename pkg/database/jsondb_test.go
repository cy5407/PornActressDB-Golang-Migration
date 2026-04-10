package database

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func setupTestDB(t *testing.T) (*JSONDatabase, string) {
	// 建立暫存測試目錄
	tmpDir := t.TempDir()

	db := NewJSONDatabase(tmpDir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Failed to load database: %v", err)
	}

	return db, tmpDir
}

func TestNewJSONDatabase(t *testing.T) {
	db, _ := setupTestDB(t)

	if db == nil {
		t.Fatal("Expected database to be created")
	}

	if !db.loaded {
		t.Error("Expected database to be loaded")
	}
}

func TestGetVideo_NotFound(t *testing.T) {
	db, _ := setupTestDB(t)

	_, err := db.GetVideo("NONEXISTENT-001")
	if err != ErrNotFound {
		t.Errorf("Expected ErrNotFound, got %v", err)
	}
}

func TestUpdateVideo(t *testing.T) {
	db, _ := setupTestDB(t)

	video := NewVideo("STARS-707")
	video.Title = "測試影片"
	video.Studio = "SOD Create"
	video.Actresses = []string{"女優A", "女優B"}

	// 更新影片
	if err := db.UpdateVideo("STARS-707", video); err != nil {
		t.Fatalf("Failed to update video: %v", err)
	}

	// 驗證取得
	retrieved, err := db.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("Failed to get video: %v", err)
	}

	if retrieved.Title != "測試影片" {
		t.Errorf("Expected title '測試影片', got '%s'", retrieved.Title)
	}

	if retrieved.Studio != "SOD Create" {
		t.Errorf("Expected studio 'SOD Create', got '%s'", retrieved.Studio)
	}

	if len(retrieved.Actresses) != 2 {
		t.Errorf("Expected 2 actresses, got %d", len(retrieved.Actresses))
	}
}

func TestDeleteVideo(t *testing.T) {
	db, _ := setupTestDB(t)

	// 先新增影片
	video := NewVideo("TEST-001")
	if err := db.UpdateVideo("TEST-001", video); err != nil {
		t.Fatalf("Failed to update video: %v", err)
	}

	// 刪除影片
	if err := db.DeleteVideo("TEST-001"); err != nil {
		t.Fatalf("Failed to delete video: %v", err)
	}

	// 驗證已刪除
	_, err := db.GetVideo("TEST-001")
	if err != ErrNotFound {
		t.Errorf("Expected ErrNotFound after deletion, got %v", err)
	}
}

func TestBatchUpdate(t *testing.T) {
	db, _ := setupTestDB(t)

	updates := map[string]*Video{
		"BATCH-001": NewVideo("BATCH-001"),
		"BATCH-002": NewVideo("BATCH-002"),
		"BATCH-003": NewVideo("BATCH-003"),
	}

	updates["BATCH-001"].Title = "批次測試 1"
	updates["BATCH-002"].Title = "批次測試 2"
	updates["BATCH-003"].Title = "批次測試 3"

	// 批次更新
	if err := db.BatchUpdate(updates); err != nil {
		t.Fatalf("Failed to batch update: %v", err)
	}

	// 驗證
	for code, expected := range updates {
		retrieved, err := db.GetVideo(code)
		if err != nil {
			t.Errorf("Failed to get video %s: %v", code, err)
			continue
		}

		if retrieved.Title != expected.Title {
			t.Errorf("Expected title '%s', got '%s'", expected.Title, retrieved.Title)
		}
	}
}

func TestSaveAndLoad(t *testing.T) {
	tmpDir := t.TempDir()

	// 建立第一個資料庫實例
	db1 := NewJSONDatabase(tmpDir)
	if err := db1.Load(context.Background()); err != nil {
		t.Fatalf("Failed to load db1: %v", err)
	}

	// 新增資料
	video := NewVideo("SAVE-001")
	video.Title = "儲存測試"
	if err := db1.UpdateVideo("SAVE-001", video); err != nil {
		t.Fatalf("Failed to update video: %v", err)
	}

	// 儲存
	if err := db1.Save(); err != nil {
		t.Fatalf("Failed to save db1: %v", err)
	}

	// 建立第二個資料庫實例並載入
	db2 := NewJSONDatabase(tmpDir)
	if err := db2.Load(context.Background()); err != nil {
		t.Fatalf("Failed to load db2: %v", err)
	}

	// 驗證資料已持久化
	retrieved, err := db2.GetVideo("SAVE-001")
	if err != nil {
		t.Fatalf("Failed to get video from db2: %v", err)
	}

	if retrieved.Title != "儲存測試" {
		t.Errorf("Expected title '儲存測試', got '%s'", retrieved.Title)
	}
}

func TestJournal(t *testing.T) {
	tmpDir := t.TempDir()

	db := NewJSONDatabase(tmpDir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Failed to load database: %v", err)
	}

	// 新增多筆資料 (會寫入 journal)
	for i := 1; i <= 5; i++ {
		code := fmt.Sprintf("JOURNAL-%03d", i)
		video := NewVideo(code)
		if err := db.UpdateVideo(code, video); err != nil {
			t.Errorf("Failed to update video %s: %v", code, err)
		}
	}

	// 檢查 journal 記錄數
	count, err := db.GetJournalEntryCount()
	if err != nil {
		t.Fatalf("Failed to get journal count: %v", err)
	}

	if count != 5 {
		t.Errorf("Expected 5 journal entries, got %d", count)
	}

	// 合併 journal
	if err := db.CompactJournal(); err != nil {
		t.Fatalf("Failed to compact journal: %v", err)
	}

	// 驗證 journal 已清空
	count, err = db.GetJournalEntryCount()
	if err != nil {
		t.Fatalf("Failed to get journal count after compact: %v", err)
	}

	if count != 0 {
		t.Errorf("Expected 0 journal entries after compact, got %d", count)
	}
}

func TestApplyVideoUpdates_HandlesMixedFieldTypes(t *testing.T) {
	video := GetEmptyVideo()
	video.UpdatedAt = "2024-01-01T00:00:00Z"

	updates := map[string]any{
		"id":            "LEGACY-001",
		"code":          "VIDEO-001",
		"title":         "混合欄位測試",
		"metadata":      map[string]any{"source": "AV-WIKI", "confidence": 0.88},
		"actresses":     []any{"女優A", 123, "女優B"},
		"updated_at":    "2025-05-05T05:05:05Z",
		"studio_code":   "ST-001",
		"search_method": "manual",
	}

	db := &JSONDatabase{}
	db.applyVideoFieldUpdates(video, updates)

	if video.ID != "LEGACY-001" {
		t.Fatalf("Expected ID to be updated, got %q", video.ID)
	}
	if video.Code != "VIDEO-001" {
		t.Fatalf("Expected Code to be updated, got %q", video.Code)
	}
	if video.Title != "混合欄位測試" {
		t.Fatalf("Expected Title to be updated, got %q", video.Title)
	}
	if video.Metadata.Source != "AV-WIKI" || video.Metadata.Confidence != 0.88 {
		t.Fatalf("Expected metadata to be updated, got %+v", video.Metadata)
	}
	if len(video.Actresses) != 2 || video.Actresses[0] != "女優A" || video.Actresses[1] != "女優B" {
		t.Fatalf("Expected actresses to keep only strings, got %#v", video.Actresses)
	}
	if video.UpdatedAt != "2025-05-05T05:05:05Z" {
		t.Fatalf("Expected UpdatedAt to remain explicit, got %q", video.UpdatedAt)
	}
	if video.StudioCode != "ST-001" {
		t.Fatalf("Expected StudioCode to be updated, got %q", video.StudioCode)
	}
	if video.SearchMethod != "manual" {
		t.Fatalf("Expected SearchMethod to be updated, got %q", video.SearchMethod)
	}
}

func TestApplyVideoUpdates_HandlesSourceSpecificSearchFields(t *testing.T) {
	video := GetEmptyVideo()
	video.UpdatedAt = "2024-01-01T00:00:00Z"

	updates := map[string]any{
		"avwiki_actress_status":   "searched_found",
		"avwiki_last_search_date": "2026-04-10T10:00:00Z",
		"javdb_actress_status":    "searched_not_found",
		"javdb_last_search_date":  "2026-04-10T11:00:00Z",
		"updated_at":              "2026-04-10T12:00:00Z",
	}

	db := &JSONDatabase{}
	db.applyVideoFieldUpdates(video, updates)

	if video.AVWikiActressStatus != "searched_found" {
		t.Fatalf("Expected AVWikiActressStatus to be updated, got %q", video.AVWikiActressStatus)
	}
	if video.AVWikiLastSearchDate != "2026-04-10T10:00:00Z" {
		t.Fatalf("Expected AVWikiLastSearchDate to be updated, got %q", video.AVWikiLastSearchDate)
	}
	if video.JAVDBActressStatus != "searched_not_found" {
		t.Fatalf("Expected JAVDBActressStatus to be updated, got %q", video.JAVDBActressStatus)
	}
	if video.JAVDBLastSearchDate != "2026-04-10T11:00:00Z" {
		t.Fatalf("Expected JAVDBLastSearchDate to be updated, got %q", video.JAVDBLastSearchDate)
	}
}

func TestGetVideoCount(t *testing.T) {
	db, _ := setupTestDB(t)

	// 初始應該為 0
	count, err := db.GetVideoCount()
	if err != nil {
		t.Fatalf("Failed to get video count: %v", err)
	}
	if count != 0 {
		t.Errorf("Expected 0 videos, got %d", count)
	}

	// 新增 3 部影片
	for i := 1; i <= 3; i++ {
		code := fmt.Sprintf("COUNT-%03d", i)
		video := NewVideo(code)
		if err := db.UpdateVideo(code, video); err != nil {
			t.Fatalf("Failed to update video: %v", err)
		}
	}

	// 驗證數量
	count, err = db.GetVideoCount()
	if err != nil {
		t.Fatalf("Failed to get video count: %v", err)
	}
	if count != 3 {
		t.Errorf("Expected 3 videos, got %d", count)
	}
}

func TestGetStats(t *testing.T) {
	db, _ := setupTestDB(t)

	// 新增一些資料
	video := NewVideo("STATS-001")
	if err := db.UpdateVideo("STATS-001", video); err != nil {
		t.Fatalf("Failed to update video: %v", err)
	}

	// 取得統計
	stats, err := db.GetStats()
	if err != nil {
		t.Fatalf("Failed to get stats: %v", err)
	}

	videoCount, ok := stats["video_count"].(int)
	if !ok || videoCount != 1 {
		t.Errorf("Expected video_count to be 1, got %v", stats["video_count"])
	}

	schemaVersion, ok := stats["schema_version"].(string)
	if !ok || schemaVersion != SchemaVersion {
		t.Errorf("Expected schema_version to be %s, got %v", SchemaVersion, stats["schema_version"])
	}
}

// Benchmark 測試
func BenchmarkGetVideo(b *testing.B) {
	tmpDir := b.TempDir()
	db := NewJSONDatabase(tmpDir)
	if err := db.Load(context.Background()); err != nil {
		b.Fatal(err)
	}

	// 預先建立測試資料
	video := NewVideo("BENCH-001")
	if err := db.UpdateVideo("BENCH-001", video); err != nil {
		b.Fatal(err)
	}

	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		_, err := db.GetVideo("BENCH-001")
		if err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkUpdateVideo(b *testing.B) {
	tmpDir := b.TempDir()
	db := NewJSONDatabase(tmpDir)
	if err := db.Load(context.Background()); err != nil {
		b.Fatal(err)
	}

	video := NewVideo("BENCH-UPDATE")
	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		if err := db.UpdateVideo("BENCH-UPDATE", video); err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkBatchUpdate(b *testing.B) {
	tmpDir := b.TempDir()
	db := NewJSONDatabase(tmpDir)
	if err := db.Load(context.Background()); err != nil {
		b.Fatal(err)
	}

	// 準備 100 筆更新
	updates := make(map[string]*Video)
	for i := 0; i < 100; i++ {
		code := fmt.Sprintf("BATCH-%03d", i)
		updates[code] = NewVideo(code)
	}

	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		if err := db.BatchUpdate(updates); err != nil {
			b.Fatal(err)
		}
	}
}

func TestMergeFromFile_NoOverwrite(t *testing.T) {
	db, tmpDir := setupTestDB(t)

	existing := NewVideo("CODE-001")
	existing.Title = "old-title"
	if err := db.UpdateVideo("CODE-001", existing); err != nil {
		t.Fatalf("Failed to seed existing video: %v", err)
	}

	source := NewDatabaseData()
	source.Videos["CODE-001"] = &VideoData{Code: "CODE-001", Title: "new-title"}
	source.Videos["CODE-002"] = &VideoData{Code: "CODE-002", Title: "added-title"}
	source.Actresses["act-1"] = &ActressData{ID: "act-1", Name: "Actress 1"}
	source.Links = []VideoActressLink{
		{VideoCode: "CODE-002", ActressID: "act-1", RoleType: RoleMain, Timestamp: "2026-01-01T00:00:00Z"},
	}

	sourcePath := filepath.Join(tmpDir, "source.json")
	raw, err := json.Marshal(source)
	if err != nil {
		t.Fatalf("Failed to marshal source: %v", err)
	}
	if err := os.WriteFile(sourcePath, raw, 0644); err != nil {
		t.Fatalf("Failed to write source file: %v", err)
	}

	stats, err := db.MergeFromFile(sourcePath, false)
	if err != nil {
		t.Fatalf("MergeFromFile failed: %v", err)
	}

	if stats.VideosAdded != 1 || stats.VideosSkipped != 1 || stats.VideosUpdated != 0 {
		t.Fatalf("Unexpected video stats: %+v", stats)
	}

	v1, err := db.GetVideo("CODE-001")
	if err != nil {
		t.Fatalf("Failed to get CODE-001: %v", err)
	}
	if v1.Title != "old-title" {
		t.Fatalf("Expected CODE-001 title to remain old-title, got %s", v1.Title)
	}

	v2, err := db.GetVideo("CODE-002")
	if err != nil {
		t.Fatalf("Failed to get CODE-002: %v", err)
	}
	if v2.Title != "added-title" {
		t.Fatalf("Expected CODE-002 added-title, got %s", v2.Title)
	}
}

func TestMergeFromFile_WithOverwrite(t *testing.T) {
	db, tmpDir := setupTestDB(t)

	existing := NewVideo("CODE-003")
	existing.Title = "old-title"
	if err := db.UpdateVideo("CODE-003", existing); err != nil {
		t.Fatalf("Failed to seed existing video: %v", err)
	}

	source := NewDatabaseData()
	source.Videos["CODE-003"] = &VideoData{Code: "CODE-003", Title: "new-title"}

	sourcePath := filepath.Join(tmpDir, "source-overwrite.json")
	raw, err := json.Marshal(source)
	if err != nil {
		t.Fatalf("Failed to marshal source: %v", err)
	}
	if err := os.WriteFile(sourcePath, raw, 0644); err != nil {
		t.Fatalf("Failed to write source file: %v", err)
	}

	stats, err := db.MergeFromFile(sourcePath, true)
	if err != nil {
		t.Fatalf("MergeFromFile failed: %v", err)
	}

	if stats.VideosUpdated != 1 || stats.VideosAdded != 0 || stats.VideosSkipped != 0 {
		t.Fatalf("Unexpected video stats: %+v", stats)
	}

	v, err := db.GetVideo("CODE-003")
	if err != nil {
		t.Fatalf("Failed to get CODE-003: %v", err)
	}
	if v.Title != "new-title" {
		t.Fatalf("Expected CODE-003 title to be overwritten to new-title, got %s", v.Title)
	}
}

func TestPrepareVideoForMerge_UsesLegacyIDAndClearsID(t *testing.T) {
	original := &VideoData{
		ID:        "LEGACY-001",
		Title:     "legacy-title",
		CreatedAt: "2024-01-01T00:00:00Z",
	}

	code, prepared, ok := prepareVideoForMerge(" MAP-IGNORED ", original, "2025-01-01T00:00:00Z")
	if !ok {
		t.Fatal("Expected video to be prepared")
	}
	if code != "LEGACY-001" {
		t.Fatalf("Expected legacy ID to be used as code, got %q", code)
	}
	if prepared == nil {
		t.Fatal("Expected prepared video copy")
	}
	if prepared.Code != "LEGACY-001" {
		t.Fatalf("Expected prepared code LEGACY-001, got %q", prepared.Code)
	}
	if prepared.ID != "" {
		t.Fatalf("Expected legacy ID field to be cleared, got %q", prepared.ID)
	}
	if prepared.UpdatedAt != "2025-01-01T00:00:00Z" {
		t.Fatalf("Expected updated time to be refreshed, got %q", prepared.UpdatedAt)
	}
	if original.ID != "LEGACY-001" {
		t.Fatalf("Expected original video data to remain unchanged, got %q", original.ID)
	}
}

func TestDeleteExpiredBackups_RemovesOnlyExpiredBackupFiles(t *testing.T) {
	backupDir := t.TempDir()
	oldName := fmt.Sprintf("backup_%s_00-00-00.json", time.Now().AddDate(0, 0, -10).Format("2006-01-02"))
	newName := fmt.Sprintf("backup_%s_00-00-00.json", time.Now().Format("2006-01-02"))
	otherName := "notes.txt"

	for _, name := range []string{oldName, newName, otherName} {
		path := filepath.Join(backupDir, name)
		if err := os.WriteFile(path, []byte("{}"), 0600); err != nil {
			t.Fatalf("WriteFile failed for %s: %v", name, err)
		}
	}

	entries, err := os.ReadDir(backupDir)
	if err != nil {
		t.Fatalf("ReadDir failed: %v", err)
	}

	deleted := deleteExpiredBackups(backupDir, entries, time.Now().AddDate(0, 0, -3))
	if deleted != 1 {
		t.Fatalf("Expected 1 deleted backup, got %d", deleted)
	}

	if _, err := os.Stat(filepath.Join(backupDir, oldName)); !os.IsNotExist(err) {
		t.Fatalf("Expected expired backup to be removed, stat err=%v", err)
	}
	if _, err := os.Stat(filepath.Join(backupDir, newName)); err != nil {
		t.Fatalf("Expected recent backup to remain, stat err=%v", err)
	}
	if _, err := os.Stat(filepath.Join(backupDir, otherName)); err != nil {
		t.Fatalf("Expected non-backup file to remain, stat err=%v", err)
	}
}

func TestLoad_RestoresActressAndDeletedCodesFromJournal(t *testing.T) {
	db, tempDir := setupTestDB(t)

	actress := &ActressData{ID: "actress-001", Name: "測試女優"}
	if err := db.UpsertActress(actress); err != nil {
		t.Fatalf("UpsertActress failed: %v", err)
	}

	video := NewVideo("DELETE-001")
	if err := db.UpdateVideo("DELETE-001", video); err != nil {
		t.Fatalf("UpdateVideo failed: %v", err)
	}
	if err := db.DeleteVideo("DELETE-001"); err != nil {
		t.Fatalf("DeleteVideo failed: %v", err)
	}

	reloaded := NewJSONDatabase(tempDir)
	if err := reloaded.Load(context.Background()); err != nil {
		t.Fatalf("Reload failed: %v", err)
	}

	gotActress, err := reloaded.GetActress("actress-001")
	if err != nil {
		t.Fatalf("GetActress after reload failed: %v", err)
	}
	if gotActress.Name != "測試女優" {
		t.Fatalf("Actress name after reload = %q, want %q", gotActress.Name, "測試女優")
	}

	deletedCodes, err := reloaded.GetDeletedCodes()
	if err != nil {
		t.Fatalf("GetDeletedCodes after reload failed: %v", err)
	}
	if len(deletedCodes) != 1 || deletedCodes[0] != "DELETE-001" {
		t.Fatalf("deleted codes after reload = %v, want [DELETE-001]", deletedCodes)
	}
}

func TestLoad_RestoresLargeJournalEntry(t *testing.T) {
	db, tempDir := setupTestDB(t)

	video := NewVideo("LARGE-001")
	video.Title = strings.Repeat("A", 70*1024)
	if err := db.UpdateVideo("LARGE-001", video); err != nil {
		t.Fatalf("UpdateVideo failed: %v", err)
	}

	reloaded := NewJSONDatabase(tempDir)
	if err := reloaded.Load(context.Background()); err != nil {
		t.Fatalf("Reload failed: %v", err)
	}

	got, err := reloaded.GetVideo("LARGE-001")
	if err != nil {
		t.Fatalf("GetVideo after reload failed: %v", err)
	}
	if got.Title != video.Title {
		t.Fatalf("reloaded title length = %d, want %d", len(got.Title), len(video.Title))
	}
}

func TestBackupRestore_IgnoresLaterJournalState(t *testing.T) {
	db, _ := setupTestDB(t)

	baseVideo := NewVideo("BASE-001")
	if err := db.UpdateVideo("BASE-001", baseVideo); err != nil {
		t.Fatalf("UpdateVideo failed: %v", err)
	}
	if err := db.CompactJournal(); err != nil {
		t.Fatalf("CompactJournal failed: %v", err)
	}

	backupPath, err := db.BackupCreate()
	if err != nil {
		t.Fatalf("BackupCreate failed: %v", err)
	}

	laterVideo := NewVideo("LATE-001")
	if err := db.UpdateVideo("LATE-001", laterVideo); err != nil {
		t.Fatalf("late UpdateVideo failed: %v", err)
	}

	if err := db.BackupRestore(backupPath); err != nil {
		t.Fatalf("BackupRestore failed: %v", err)
	}

	if _, err := db.GetVideo("BASE-001"); err != nil {
		t.Fatalf("expected base video after restore, got err=%v", err)
	}
	if _, err := db.GetVideo("LATE-001"); err != ErrNotFound {
		t.Fatalf("expected late video to be absent after restore, got err=%v", err)
	}
}

func TestUpdateVideoFields_ReloadPreservesUpdatedAt(t *testing.T) {
	db, tempDir := setupTestDB(t)

	video := NewVideo("UPDATE-001")
	if err := db.UpdateVideo("UPDATE-001", video); err != nil {
		t.Fatalf("UpdateVideo failed: %v", err)
	}
	if err := db.UpdateVideoFields("UPDATE-001", map[string]any{"title": "changed"}); err != nil {
		t.Fatalf("UpdateVideoFields failed: %v", err)
	}

	updated, err := db.GetVideo("UPDATE-001")
	if err != nil {
		t.Fatalf("GetVideo failed: %v", err)
	}
	expectedUpdatedAt := updated.UpdatedAt

	time.Sleep(1100 * time.Millisecond)

	reloaded := NewJSONDatabase(tempDir)
	if err := reloaded.Load(context.Background()); err != nil {
		t.Fatalf("Reload failed: %v", err)
	}

	got, err := reloaded.GetVideo("UPDATE-001")
	if err != nil {
		t.Fatalf("GetVideo after reload failed: %v", err)
	}
	if got.UpdatedAt != expectedUpdatedAt {
		t.Fatalf("reloaded updated_at = %q, want %q", got.UpdatedAt, expectedUpdatedAt)
	}
}

func TestUpdateVideoFields_ReloadPreservesSourceSpecificSearchFields(t *testing.T) {
	db, tempDir := setupTestDB(t)

	video := NewVideo("SOURCE-001")
	if err := db.UpdateVideo("SOURCE-001", video); err != nil {
		t.Fatalf("UpdateVideo failed: %v", err)
	}
	if err := db.UpdateVideoFields("SOURCE-001", map[string]any{
		"avwiki_actress_status":   "searched_found",
		"avwiki_last_search_date": "2026-04-10T08:00:00Z",
		"javdb_actress_status":    "searched_not_found",
		"javdb_last_search_date":  "2026-04-10T09:00:00Z",
	}); err != nil {
		t.Fatalf("UpdateVideoFields failed: %v", err)
	}

	reloaded := NewJSONDatabase(tempDir)
	if err := reloaded.Load(context.Background()); err != nil {
		t.Fatalf("Reload failed: %v", err)
	}

	got, err := reloaded.GetVideo("SOURCE-001")
	if err != nil {
		t.Fatalf("GetVideo after reload failed: %v", err)
	}
	if got.AVWikiActressStatus != "searched_found" {
		t.Fatalf("AVWikiActressStatus = %q, want searched_found", got.AVWikiActressStatus)
	}
	if got.AVWikiLastSearchDate != "2026-04-10T08:00:00Z" {
		t.Fatalf("AVWikiLastSearchDate = %q, want 2026-04-10T08:00:00Z", got.AVWikiLastSearchDate)
	}
	if got.JAVDBActressStatus != "searched_not_found" {
		t.Fatalf("JAVDBActressStatus = %q, want searched_not_found", got.JAVDBActressStatus)
	}
	if got.JAVDBLastSearchDate != "2026-04-10T09:00:00Z" {
		t.Fatalf("JAVDBLastSearchDate = %q, want 2026-04-10T09:00:00Z", got.JAVDBLastSearchDate)
	}
}

// ─── GetActressPrimaryStudio 測試 ────────────────────────────────────────────

func TestGetActressPrimaryStudio_SingleStudio(t *testing.T) {
	db, _ := setupTestDB(t)
	for _, code := range []string{"STARS-001", "STARS-002", "STARS-003"} {
		v := NewVideo(code)
		v.Actresses = []string{"花蓮夏目"}
		v.Studio = "S1"
		if err := db.UpdateVideo(code, v); err != nil {
			t.Fatalf("UpdateVideo failed: %v", err)
		}
	}
	got := db.GetActressPrimaryStudio("花蓮夏目")
	if got != "S1" {
		t.Errorf("expected S1, got %q", got)
	}
}

func TestGetActressPrimaryStudio_MostFrequentWins(t *testing.T) {
	db, _ := setupTestDB(t)
	for code, studio := range map[string]string{
		"MIAB-001":  "MOODYZ",
		"MIAB-002":  "MOODYZ",
		"STARS-099": "S1",
	} {
		v := NewVideo(code)
		v.Actresses = []string{"某女優"}
		v.Studio = studio
		if err := db.UpdateVideo(code, v); err != nil {
			t.Fatalf("UpdateVideo failed: %v", err)
		}
	}
	got := db.GetActressPrimaryStudio("某女優")
	if got != "MOODYZ" {
		t.Errorf("expected MOODYZ, got %q", got)
	}
}

func TestGetActressPrimaryStudio_NoStudio(t *testing.T) {
	db, _ := setupTestDB(t)
	v := NewVideo("GANA-001")
	v.Actresses = []string{"素人女優"}
	v.Studio = ""
	if err := db.UpdateVideo("GANA-001", v); err != nil {
		t.Fatalf("UpdateVideo failed: %v", err)
	}
	got := db.GetActressPrimaryStudio("素人女優")
	if got != "" {
		t.Errorf("expected empty string, got %q", got)
	}
}

func TestGetActressPrimaryStudio_EmptyName(t *testing.T) {
	db, _ := setupTestDB(t)
	got := db.GetActressPrimaryStudio("")
	if got != "" {
		t.Errorf("expected empty string, got %q", got)
	}
}
