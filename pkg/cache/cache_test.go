package cache

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func createTestIndex(t *testing.T, dir string, entries map[string]IndexEntry) {
	t.Helper()

	index := CacheIndex{
		Metadata: IndexMetadata{
			Version:   "1.0",
			CreatedAt: float64(time.Now().Unix()),
		},
		Entries: entries,
	}

	data, err := json.MarshalIndent(index, "", "  ")
	if err != nil {
		t.Fatalf("序列化索引失敗: %v", err)
	}

	indexPath := filepath.Join(dir, "cache_index.json")
	if err := os.WriteFile(indexPath, data, 0644); err != nil {
		t.Fatalf("寫入索引失敗: %v", err)
	}
}

func TestNew(t *testing.T) {
	const testCacheDir = "/tmp/cache"
	cm := NewCacheManager(testCacheDir)

	if cm.cacheDir != testCacheDir {
		t.Errorf("cacheDir = %s, want %s", cm.cacheDir, testCacheDir)
	}

	// 使用 filepath.Join 確保跨平台路徑比較正確
	wantIndexPath := filepath.Join(testCacheDir, "cache_index.json")
	if cm.indexPath != wantIndexPath {
		t.Errorf("indexPath = %s, want %s", cm.indexPath, wantIndexPath)
	}
}

func TestGetStats_Empty(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	// 不建立索引檔案
	stats, err := cm.GetStats()
	if err != nil {
		t.Fatalf("GetStats 失敗: %v", err)
	}

	if stats.TotalFiles != 0 {
		t.Errorf("TotalFiles = %d, want 0", stats.TotalFiles)
	}
}

func TestGetStats_WithEntries(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	now := float64(time.Now().Unix())
	entries := map[string]IndexEntry{
		"key1": {
			FilePath:     filepath.Join(dir, "a1/b2/key1.cache"),
			CreatedAt:    now - 3600, // 1 小時前
			TTLSeconds:   86400,      // 24 小時
			LastAccessed: now - 1800,
			AccessCount:  5,
			SizeBytes:    1024,
		},
		"key2": {
			FilePath:     filepath.Join(dir, "c3/d4/key2.cache"),
			CreatedAt:    now - 7200, // 2 小時前
			TTLSeconds:   86400,
			LastAccessed: now - 3600,
			AccessCount:  10,
			SizeBytes:    2048,
		},
	}

	createTestIndex(t, dir, entries)

	stats, err := cm.GetStats()
	if err != nil {
		t.Fatalf("GetStats 失敗: %v", err)
	}

	if stats.TotalFiles != 2 {
		t.Errorf("TotalFiles = %d, want 2", stats.TotalFiles)
	}

	expectedSizeMB := float64(1024+2048) / (1024 * 1024)
	if stats.TotalSizeMB != expectedSizeMB {
		t.Errorf("TotalSizeMB = %f, want %f", stats.TotalSizeMB, expectedSizeMB)
	}

	expectedAvgAccess := float64(5+10) / 2
	if stats.AverageAccessCount != expectedAvgAccess {
		t.Errorf("AverageAccessCount = %f, want %f", stats.AverageAccessCount, expectedAvgAccess)
	}

	if stats.ExpiredCount != 0 {
		t.Errorf("ExpiredCount = %d, want 0", stats.ExpiredCount)
	}
}

func TestGetStats_WithExpired(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	now := float64(time.Now().Unix())
	entries := map[string]IndexEntry{
		"expired": {
			FilePath:   filepath.Join(dir, "expired.cache"),
			CreatedAt:  now - 172800, // 2 天前
			TTLSeconds: 86400,        // 1 天 TTL -> 已過期
			SizeBytes:  1024,
		},
		"valid": {
			FilePath:   filepath.Join(dir, "valid.cache"),
			CreatedAt:  now - 3600, // 1 小時前
			TTLSeconds: 86400,      // 未過期
			SizeBytes:  2048,
		},
	}

	createTestIndex(t, dir, entries)

	stats, err := cm.GetStats()
	if err != nil {
		t.Fatalf("GetStats 失敗: %v", err)
	}

	if stats.ExpiredCount != 1 {
		t.Errorf("ExpiredCount = %d, want 1", stats.ExpiredCount)
	}
}

func TestCleanupExpired(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	now := float64(time.Now().Unix())

	// 建立測試快取檔案
	cacheDir := filepath.Join(dir, "a1", "b2")
	os.MkdirAll(cacheDir, 0755)

	expiredFile := filepath.Join(cacheDir, "expired.cache")
	os.WriteFile(expiredFile, []byte("test"), 0644)

	entries := map[string]IndexEntry{
		"expired": {
			FilePath:   expiredFile,
			CreatedAt:  now - 864000, // 10 天前
			TTLSeconds: 86400,        // 1 天 TTL -> 已過期
			SizeBytes:  1024,
		},
		"valid": {
			FilePath:   filepath.Join(dir, "valid.cache"),
			CreatedAt:  now - 3600, // 1 小時前
			TTLSeconds: 86400,      // 未過期
			SizeBytes:  2048,
		},
	}

	createTestIndex(t, dir, entries)

	config := PruneConfig{
		TTLDays:        7,
		MinKeepEntries: 0,
		DryRun:         false,
	}

	result, err := cm.CleanupExpired(config)
	if err != nil {
		t.Fatalf("CleanupExpired 失敗: %v", err)
	}

	if result.DeletedFiles != 1 {
		t.Errorf("DeletedFiles = %d, want 1", result.DeletedFiles)
	}

	if result.RemainingFiles != 1 {
		t.Errorf("RemainingFiles = %d, want 1", result.RemainingFiles)
	}

	// 驗證檔案已刪除
	if _, err := os.Stat(expiredFile); !os.IsNotExist(err) {
		t.Error("過期檔案應該被刪除")
	}
}

func TestCleanupExpired_DryRun(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	now := float64(time.Now().Unix())

	// 建立測試檔案
	cacheDir := filepath.Join(dir, "a1", "b2")
	os.MkdirAll(cacheDir, 0755)

	expiredFile := filepath.Join(cacheDir, "expired.cache")
	os.WriteFile(expiredFile, []byte("test"), 0644)

	entries := map[string]IndexEntry{
		"expired": {
			FilePath:   expiredFile,
			CreatedAt:  now - 864000,
			TTLSeconds: 86400,
			SizeBytes:  1024,
		},
	}

	createTestIndex(t, dir, entries)

	config := PruneConfig{
		TTLDays:        7,
		MinKeepEntries: 0,
		DryRun:         true, // 模擬模式
	}

	result, err := cm.CleanupExpired(config)
	if err != nil {
		t.Fatalf("CleanupExpired 失敗: %v", err)
	}

	if result.DeletedFiles != 1 {
		t.Errorf("DeletedFiles = %d, want 1", result.DeletedFiles)
	}

	// 驗證檔案未被刪除（dry run）
	if _, err := os.Stat(expiredFile); os.IsNotExist(err) {
		t.Error("Dry run 模式下檔案不應該被刪除")
	}
}

func TestCleanupBySize(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	now := float64(time.Now().Unix())

	entries := map[string]IndexEntry{
		"old": {
			FilePath:     filepath.Join(dir, "old.cache"),
			CreatedAt:    now - 7200,
			LastAccessed: now - 7200, // 最舊
			TTLSeconds:   86400,
			SizeBytes:    1024 * 1024, // 1 MB
		},
		"middle": {
			FilePath:     filepath.Join(dir, "middle.cache"),
			CreatedAt:    now - 3600,
			LastAccessed: now - 3600,
			TTLSeconds:   86400,
			SizeBytes:    1024 * 1024, // 1 MB
		},
		"new": {
			FilePath:     filepath.Join(dir, "new.cache"),
			CreatedAt:    now - 1800,
			LastAccessed: now - 1800, // 最新
			TTLSeconds:   86400,
			SizeBytes:    1024 * 1024, // 1 MB
		},
	}

	createTestIndex(t, dir, entries)

	config := PruneConfig{
		MaxSizeMB:      2, // 限制 2 MB，目前 3 MB
		MinKeepEntries: 0,
		DryRun:         true,
	}

	result, err := cm.CleanupBySize(config)
	if err != nil {
		t.Fatalf("CleanupBySize 失敗: %v", err)
	}

	// 應該刪除 1 個（最舊的）
	if result.DeletedFiles != 1 {
		t.Errorf("DeletedFiles = %d, want 1", result.DeletedFiles)
	}

	// 應該釋放 1 MB
	expectedFreedMB := 1.0
	if result.FreedMB != expectedFreedMB {
		t.Errorf("FreedMB = %f, want %f", result.FreedMB, expectedFreedMB)
	}
}

func TestClearAll(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	now := float64(time.Now().Unix())

	entries := map[string]IndexEntry{
		"key1": {
			FilePath:   filepath.Join(dir, "key1.cache"),
			CreatedAt:  now,
			TTLSeconds: 86400,
			SizeBytes:  1024,
		},
		"key2": {
			FilePath:   filepath.Join(dir, "key2.cache"),
			CreatedAt:  now,
			TTLSeconds: 86400,
			SizeBytes:  2048,
		},
	}

	createTestIndex(t, dir, entries)

	result, err := cm.ClearAll(true) // dry run
	if err != nil {
		t.Fatalf("ClearAll 失敗: %v", err)
	}

	if result.DeletedFiles != 2 {
		t.Errorf("DeletedFiles = %d, want 2", result.DeletedFiles)
	}

	expectedFreedBytes := int64(1024 + 2048)
	if result.FreedBytes != expectedFreedBytes {
		t.Errorf("FreedBytes = %d, want %d", result.FreedBytes, expectedFreedBytes)
	}
}

func TestMinKeepEntries(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	now := float64(time.Now().Unix())

	// 建立 5 個過期條目
	entries := make(map[string]IndexEntry)
	for i := 0; i < 5; i++ {
		entries[string(rune('a'+i))] = IndexEntry{
			FilePath:   filepath.Join(dir, string(rune('a'+i))+".cache"),
			CreatedAt:  now - 864000, // 全部過期
			TTLSeconds: 86400,
			SizeBytes:  1024,
		}
	}

	createTestIndex(t, dir, entries)

	config := PruneConfig{
		TTLDays:        7,
		MinKeepEntries: 3, // 保留至少 3 個
		DryRun:         true,
	}

	result, err := cm.CleanupExpired(config)
	if err != nil {
		t.Fatalf("CleanupExpired 失敗: %v", err)
	}

	// 應該只刪除 2 個（5 - 3 = 2）
	if result.DeletedFiles != 2 {
		t.Errorf("DeletedFiles = %d, want 2", result.DeletedFiles)
	}

	if result.RemainingFiles != 3 {
		t.Errorf("RemainingFiles = %d, want 3", result.RemainingFiles)
	}
}

func TestCacheGetSetDelete(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	// Set
	err := cm.Set("test-key", []byte(`{"actress":"蒼井空"}`), 24)
	if err != nil {
		t.Fatalf("Set 失敗: %v", err)
	}

	// Get
	data, found, err := cm.Get("test-key")
	if err != nil {
		t.Fatalf("Get 傳回錯誤: %v", err)
	}
	if !found {
		t.Fatal("Get: 應找到已設定的 key")
	}
	if string(data) != `{"actress":"蒼井空"}` {
		t.Fatalf("Get 回傳值不符: %s", data)
	}

	// Exists
	if !cm.Exists("test-key") {
		t.Fatal("Exists: 應存在")
	}

	// Delete
	err = cm.Delete("test-key")
	if err != nil {
		t.Fatalf("Delete 失敗: %v", err)
	}
	_, found, _ = cm.Get("test-key")
	if found {
		t.Fatal("Delete 後 key 應消失")
	}
	if cm.Exists("test-key") {
		t.Fatal("Delete 後 Exists 應回傳 false")
	}
}

func TestCacheExpiry(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	// ttlHours=0 => TTLSeconds=0 => 立即過期
	err := cm.Set("expiring", []byte(`"value"`), 0)
	if err != nil {
		t.Fatalf("Set 失敗: %v", err)
	}
	_, found, _ := cm.Get("expiring")
	if found {
		t.Fatal("ttlHours=0 的條目不應被返回（立即過期）")
	}
}

func TestCacheGetMissing(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	_, found, err := cm.Get("nonexistent")
	if err != nil {
		t.Fatalf("Get 不存在的 key 不應返回錯誤: %v", err)
	}
	if found {
		t.Fatal("不存在的 key 不應 found=true")
	}
}

func TestCacheIndexUpdatedOnSet(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	err := cm.Set("idx-key", []byte(`123`), 1)
	if err != nil {
		t.Fatalf("Set 失敗: %v", err)
	}

	stats, err := cm.GetStats()
	if err != nil {
		t.Fatalf("GetStats 失敗: %v", err)
	}
	if stats.TotalFiles != 1 {
		t.Errorf("索引應有 1 筆，得 %d", stats.TotalFiles)
	}
}
