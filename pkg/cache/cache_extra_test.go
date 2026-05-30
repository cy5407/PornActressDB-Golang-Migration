package cache

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// ============================================================
// validateCachePath
// ============================================================

func TestValidateCachePath_Inside(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)
	inside := filepath.Join(dir, "ab", "abcdef.json")
	if !cm.validateCachePath(inside) {
		t.Errorf("expected path inside cache dir to be valid: %s", inside)
	}
}

func TestValidateCachePath_Outside(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)
	// 路徑遍歷到上一層
	outside := filepath.Join(dir, "..", "evil.txt")
	if cm.validateCachePath(outside) {
		t.Errorf("expected path outside cache dir to be rejected: %s", outside)
	}
}

func TestValidateCachePath_SameAsCache(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)
	if !cm.validateCachePath(dir) {
		t.Errorf("expected cacheDir itself to be valid")
	}
}

// ============================================================
// safeRemoveCacheFile
// ============================================================

func TestSafeRemoveCacheFile_OutsideCache(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(filepath.Join(dir, "cache"))
	outside := filepath.Join(dir, "should_not_delete.txt")
	os.WriteFile(outside, []byte("keep"), 0644)

	err := cm.safeRemoveCacheFile(outside)
	if err == nil {
		t.Error("expected error when removing file outside cache dir")
	}
	// 檔案應未被刪除
	if _, statErr := os.Stat(outside); os.IsNotExist(statErr) {
		t.Error("file outside cache should NOT have been deleted")
	}
}

// ============================================================
// ClearAll（non-dry-run）
// ============================================================

func TestClearAll_NonDryRun(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	// 放入一筆真實快取
	if err := cm.Set("clearall-key", []byte(`"value"`), 24); err != nil {
		t.Fatalf("Set failed: %v", err)
	}

	stats, _ := cm.GetStats()
	if stats.TotalFiles != 1 {
		t.Fatalf("expected 1 entry before ClearAll, got %d", stats.TotalFiles)
	}

	result, err := cm.ClearAll(false)
	if err != nil {
		t.Fatalf("ClearAll error: %v", err)
	}
	if result.DeletedFiles != 1 {
		t.Errorf("DeletedFiles = %d, want 1", result.DeletedFiles)
	}

	// 索引應已清空
	stats, _ = cm.GetStats()
	if stats.TotalFiles != 0 {
		t.Errorf("expected 0 entries after ClearAll, got %d", stats.TotalFiles)
	}
}

// ============================================================
// AutoCleanup — 過期清理
// ============================================================

func TestAutoCleanup_ExpiredEntries(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	now := float64(time.Now().Unix())
	cacheSubDir := filepath.Join(dir, "ab")
	os.MkdirAll(cacheSubDir, 0755)
	expiredFile := filepath.Join(cacheSubDir, "expired.cache")
	os.WriteFile(expiredFile, []byte("old"), 0644)

	entries := map[string]IndexEntry{
		"expired": {
			FilePath:   expiredFile,
			CreatedAt:  now - 864000, // 10 天前
			TTLSeconds: 86400,
			SizeBytes:  512,
		},
		"valid": {
			FilePath:   filepath.Join(dir, "ab", "valid.cache"),
			CreatedAt:  now - 3600,
			TTLSeconds: 86400,
			SizeBytes:  256,
		},
	}
	createTestIndex(t, dir, entries)

	cfg := PruneConfig{
		TTLDays:        7,
		MaxSizeMB:      500,
		MinKeepEntries: 0,
		DryRun:         false,
	}

	result, err := cm.AutoCleanup(context.Background(), cfg)
	if err != nil {
		t.Fatalf("AutoCleanup error: %v", err)
	}
	if result.DeletedFiles != 1 {
		t.Errorf("DeletedFiles = %d, want 1", result.DeletedFiles)
	}
	if _, statErr := os.Stat(expiredFile); !os.IsNotExist(statErr) {
		t.Error("expired file should be deleted")
	}
}

// ============================================================
// AutoCleanup — 大小清理（LRU）
// ============================================================

func TestAutoCleanup_SizeLimit(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	// 寫入 3 筆各 1 MB 的快取（總 3 MB），限 2 MB
	now := float64(time.Now().Unix())
	entries := map[string]IndexEntry{
		"oldest": {
			FilePath:     filepath.Join(dir, "ab", "oldest.cache"),
			CreatedAt:    now - 7200,
			LastAccessed: now - 7200,
			TTLSeconds:   86400 * 30,
			SizeBytes:    1024 * 1024,
		},
		"middle": {
			FilePath:     filepath.Join(dir, "ab", "middle.cache"),
			CreatedAt:    now - 3600,
			LastAccessed: now - 3600,
			TTLSeconds:   86400 * 30,
			SizeBytes:    1024 * 1024,
		},
		"newest": {
			FilePath:     filepath.Join(dir, "ab", "newest.cache"),
			CreatedAt:    now - 600,
			LastAccessed: now - 600,
			TTLSeconds:   86400 * 30,
			SizeBytes:    1024 * 1024,
		},
	}
	createTestIndex(t, dir, entries)

	cfg := PruneConfig{
		TTLDays:        30,
		MaxSizeMB:      2,
		MinKeepEntries: 0,
		DryRun:         true,
	}

	result, err := cm.AutoCleanup(context.Background(), cfg)
	if err != nil {
		t.Fatalf("AutoCleanup error: %v", err)
	}
	if result.DeletedFiles != 1 {
		t.Errorf("DeletedFiles = %d, want 1 (oldest LRU)", result.DeletedFiles)
	}
}

// ============================================================
// AutoCleanup — 空快取（無操作）
// ============================================================

func TestAutoCleanup_Empty(t *testing.T) {
	dir := t.TempDir()
	cm := NewCacheManager(dir)

	result, err := cm.AutoCleanup(context.Background(), PruneConfig{TTLDays: 7, MaxSizeMB: 500, MinKeepEntries: 100, DryRun: false})
	if err != nil {
		t.Fatalf("AutoCleanup on empty cache error: %v", err)
	}
	if result.DeletedFiles != 0 {
		t.Errorf("expected 0 deletions on empty cache, got %d", result.DeletedFiles)
	}
}
