package database

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"testing"
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
