package cache

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"actress-classifier/pkg/safefile"
)

// CacheManager 快取管理器
type CacheManager struct {
	cacheDir  string
	indexPath string
}

// NewCacheManager 建立快取管理器（符合 Go 命名慣例）
func NewCacheManager(cacheDir string) *CacheManager {
	return &CacheManager{
		cacheDir:  cacheDir,
		indexPath: filepath.Join(cacheDir, "cache_index.json"),
	}
}

// validateCachePath 驗證檔案路徑是否在快取目錄範圍內，防止路徑穿越攻擊
func (cm *CacheManager) validateCachePath(filePath string) bool {
	absCache, err := filepath.Abs(cm.cacheDir) // 取得快取目錄絕對路徑
	if err != nil {
		return false
	}
	absFile, err := filepath.Abs(filePath) // 取得檔案絕對路徑
	if err != nil {
		return false
	}
	// 確認檔案路徑以快取目錄為前綴
	return strings.HasPrefix(absFile, absCache+string(filepath.Separator)) || absFile == absCache
}

// safeRemoveCacheFile 安全刪除快取檔案，先驗證路徑是否在快取目錄內
func (cm *CacheManager) safeRemoveCacheFile(filePath string) error {
	if !cm.validateCachePath(filePath) {
		return fmt.Errorf("refusing to delete file outside cache directory: %s", filePath)
	}
	return os.Remove(filePath)
}

// New 建立快取管理器（向後相容別名，建議改用 NewCacheManager）
//
// Deprecated: 請改用 NewCacheManager
func New(cacheDir string) *CacheManager {
	return NewCacheManager(cacheDir)
}

// loadIndex 載入索引檔案
func (cm *CacheManager) loadIndex() (*CacheIndex, error) {
	data, err := safefile.ReadFile(cm.indexPath)
	if err != nil {
		if os.IsNotExist(err) {
			// 返回空索引
			return &CacheIndex{
				Metadata: IndexMetadata{
					Version:   "1.0",
					CreatedAt: float64(time.Now().Unix()),
				},
				Entries: make(map[string]IndexEntry),
			}, nil
		}
		return nil, fmt.Errorf("讀取索引失敗: %w", err)
	}

	var index CacheIndex
	if err := json.Unmarshal(data, &index); err != nil {
		return nil, fmt.Errorf("解析索引失敗: %w", err)
	}

	if index.Entries == nil {
		index.Entries = make(map[string]IndexEntry)
	}

	return &index, nil
}

// saveIndex 儲存索引檔案（使用 tmp+rename 確保原子寫入，避免中途中斷留下損壞的索引）
func (cm *CacheManager) saveIndex(index *CacheIndex) error {
	data, err := json.MarshalIndent(index, "", "  ") // 序列化索引為縮排 JSON
	if err != nil {
		return fmt.Errorf("序列化索引失敗: %w", err)
	}

	// 先寫入暫存檔（與正式檔案同目錄，確保 rename 為同一掛載點上的原子操作）
	tmpPath := cm.indexPath + ".tmp" // 暫存檔路徑，與正式檔案同目錄
	if err := safefile.WriteFile(tmpPath, data, 0600); err != nil {
		return fmt.Errorf("寫入暫存索引失敗: %w", err)
	}

	// 原子性替換正式檔案（rename 在同一檔案系統內保證原子性）
	if err := os.Rename(tmpPath, cm.indexPath); err != nil {
		_ = os.Remove(tmpPath) // rename 失敗時清理暫存檔，避免殘留
		return fmt.Errorf("替換索引檔案失敗: %w", err)
	}

	return nil
}

// GetStats 取得快取統計資訊
func (cm *CacheManager) GetStats() (*CacheStats, error) {
	index, err := cm.loadIndex()
	if err != nil {
		return nil, err
	}

	stats := &CacheStats{
		TotalFiles:   len(index.Entries),
		IndexEntries: len(index.Entries),
	}

	if len(index.Entries) == 0 {
		return stats, nil
	}

	var totalSize int64
	var totalAccessCount int
	var oldestTime, newestTime float64
	now := float64(time.Now().Unix())

	for _, entry := range index.Entries {
		totalSize += int64(entry.SizeBytes)
		totalAccessCount += entry.AccessCount

		// 追蹤最舊和最新
		if oldestTime == 0 || entry.CreatedAt < oldestTime {
			oldestTime = entry.CreatedAt
		}
		if entry.CreatedAt > newestTime {
			newestTime = entry.CreatedAt
		}

		// 檢查過期
		if now-entry.CreatedAt > float64(entry.TTLSeconds) {
			stats.ExpiredCount++
		}
	}

	stats.TotalSizeMB = float64(totalSize) / (1024 * 1024)
	stats.AverageAccessCount = float64(totalAccessCount) / float64(len(index.Entries))

	if oldestTime > 0 {
		t := time.Unix(int64(oldestTime), 0)
		stats.OldestEntry = t.Format(time.RFC3339)
	}
	if newestTime > 0 {
		t := time.Unix(int64(newestTime), 0)
		stats.NewestEntry = t.Format(time.RFC3339)
	}

	return stats, nil
}

// CleanupExpired 清理過期快取
func (cm *CacheManager) CleanupExpired(config PruneConfig) (*CleanupResult, error) {
	index, err := cm.loadIndex()
	if err != nil {
		return nil, err
	}

	result := &CleanupResult{
		RemainingFiles: len(index.Entries),
	}

	// 檢查最小保留數
	if len(index.Entries) <= config.MinKeepEntries {
		return result, nil
	}

	now := float64(time.Now().Unix())
	ttlSeconds := float64(config.TTLDays * 24 * 3600)

	// 收集過期條目
	type expiredEntry struct {
		key       string
		entry     IndexEntry
		createdAt float64
	}
	var expired []expiredEntry

	for key, entry := range index.Entries {
		if now-entry.CreatedAt > ttlSeconds {
			expired = append(expired, expiredEntry{key, entry, entry.CreatedAt})
		}
	}

	// 確保不會刪除太多
	maxDeletable := len(index.Entries) - config.MinKeepEntries
	if len(expired) > maxDeletable {
		// 按建立時間排序，刪除最舊的
		sort.Slice(expired, func(i, j int) bool {
			return expired[i].createdAt < expired[j].createdAt
		})
		expired = expired[:maxDeletable]
	}

	// 執行刪除
	for _, e := range expired {
		if !config.DryRun {
			// 刪除檔案（驗證路徑在快取目錄內）
			if e.entry.FilePath != "" {
				if err := cm.safeRemoveCacheFile(e.entry.FilePath); err != nil && !os.IsNotExist(err) {
					result.Errors++
					continue
				}
			}
			// 從索引移除
			delete(index.Entries, e.key)
		}
		result.DeletedFiles++
		result.FreedBytes += int64(e.entry.SizeBytes)
	}

	result.FreedMB = float64(result.FreedBytes) / (1024 * 1024)
	// 計算剩餘檔案數（考慮 dry run）
	if config.DryRun {
		result.RemainingFiles = len(index.Entries) - result.DeletedFiles
	} else {
		result.RemainingFiles = len(index.Entries)
	}

	// 儲存更新的索引
	if !config.DryRun && result.DeletedFiles > 0 {
		if err := cm.saveIndex(index); err != nil {
			return result, fmt.Errorf("儲存索引失敗: %w", err)
		}
	}

	return result, nil
}

// CleanupBySize 根據大小清理快取 (LRU 策略)
func (cm *CacheManager) CleanupBySize(config PruneConfig) (*CleanupResult, error) {
	index, err := cm.loadIndex()
	if err != nil {
		return nil, err
	}

	result := &CleanupResult{
		RemainingFiles: len(index.Entries),
	}

	// 計算當前總大小
	var totalSize int64
	for _, entry := range index.Entries {
		totalSize += int64(entry.SizeBytes)
	}

	maxSizeBytes := int64(config.MaxSizeMB) * 1024 * 1024

	// 不需要清理
	if totalSize <= maxSizeBytes {
		return result, nil
	}

	bytesToFree := totalSize - maxSizeBytes

	// 按最後存取時間排序 (LRU)
	type entryWithKey struct {
		key          string
		entry        IndexEntry
		lastAccessed float64
	}
	var entries []entryWithKey
	for key, entry := range index.Entries {
		lastAccessed := entry.LastAccessed
		if lastAccessed == 0 {
			lastAccessed = entry.CreatedAt
		}
		entries = append(entries, entryWithKey{key, entry, lastAccessed})
	}

	sort.Slice(entries, func(i, j int) bool {
		return entries[i].lastAccessed < entries[j].lastAccessed
	})

	// 計算可刪除的最大數量
	maxDeletable := len(index.Entries) - config.MinKeepEntries

	// 刪除直到釋放足夠空間
	var freedBytes int64
	for i, e := range entries {
		if freedBytes >= bytesToFree || i >= maxDeletable {
			break
		}

		if !config.DryRun {
			// 刪除檔案（驗證路徑在快取目錄內）
			if e.entry.FilePath != "" {
				if err := cm.safeRemoveCacheFile(e.entry.FilePath); err != nil && !os.IsNotExist(err) {
					result.Errors++
					continue
				}
			}
			// 從索引移除
			delete(index.Entries, e.key)
		}

		freedBytes += int64(e.entry.SizeBytes)
		result.DeletedFiles++
	}

	result.FreedBytes = freedBytes
	result.FreedMB = float64(freedBytes) / (1024 * 1024)
	result.RemainingFiles = len(index.Entries)

	// 儲存更新的索引
	if !config.DryRun && result.DeletedFiles > 0 {
		if err := cm.saveIndex(index); err != nil {
			return result, fmt.Errorf("儲存索引失敗: %w", err)
		}
	}

	return result, nil
}

// ClearAll 清空所有快取
func (cm *CacheManager) ClearAll(dryRun bool) (*CleanupResult, error) {
	index, err := cm.loadIndex()
	if err != nil {
		return nil, err
	}

	result := &CleanupResult{}

	// 刪除所有快取檔案（驗證路徑在快取目錄內）
	for key, entry := range index.Entries {
		if !dryRun {
			if entry.FilePath != "" {
				if err := cm.safeRemoveCacheFile(entry.FilePath); err != nil && !os.IsNotExist(err) {
					result.Errors++
					continue
				}
			}
			delete(index.Entries, key)
		}
		result.DeletedFiles++
		result.FreedBytes += int64(entry.SizeBytes)
	}

	result.FreedMB = float64(result.FreedBytes) / (1024 * 1024)

	// 重置索引
	if !dryRun {
		newIndex := &CacheIndex{
			Metadata: IndexMetadata{
				Version:   "1.0",
				CreatedAt: float64(time.Now().Unix()),
			},
			Entries: make(map[string]IndexEntry),
		}
		if err := cm.saveIndex(newIndex); err != nil {
			return result, fmt.Errorf("儲存索引失敗: %w", err)
		}
	}

	return result, nil
}

// AutoCleanup 自動清理（結合過期和大小清理）
// 一次 index 讀取 + 一次寫入，解決原本兩次讀寫的 TOCTOU 問題
// ctx 用於支援未來的取消與逾時（目前接受但不使用）
func (cm *CacheManager) AutoCleanup(ctx context.Context, config PruneConfig) (*CleanupResult, error) {
	_ = ctx // 預留給未來的取消支援

	// 一次性讀取索引
	index, err := cm.loadIndex()
	if err != nil {
		return nil, err
	}

	result := &CleanupResult{
		RemainingFiles: len(index.Entries),
	}

	now := float64(time.Now().Unix())
	ttlSeconds := float64(config.TTLDays * 24 * 3600)

	// 第一步：清理過期條目（共用同一份 index，無 TOCTOU 問題）
	if len(index.Entries) > config.MinKeepEntries {
		type expiredEntry struct {
			key       string
			entry     IndexEntry
			createdAt float64
		}
		var expired []expiredEntry
		for key, entry := range index.Entries {
			if now-entry.CreatedAt > ttlSeconds {
				expired = append(expired, expiredEntry{key, entry, entry.CreatedAt})
			}
		}

		maxDeletable := len(index.Entries) - config.MinKeepEntries
		if len(expired) > maxDeletable {
			sort.Slice(expired, func(i, j int) bool {
				return expired[i].createdAt < expired[j].createdAt
			})
			expired = expired[:maxDeletable]
		}

		for _, e := range expired {
			if !config.DryRun {
				if e.entry.FilePath != "" {
					if rmErr := cm.safeRemoveCacheFile(e.entry.FilePath); rmErr != nil && !os.IsNotExist(rmErr) {
						result.Errors++
						continue
					}
				}
				delete(index.Entries, e.key)
			}
			result.DeletedFiles++
			result.FreedBytes += int64(e.entry.SizeBytes)
		}
	}

	// 第二步：清理超大條目（LRU，共用同一份 index）
	var totalSize int64
	for _, entry := range index.Entries {
		totalSize += int64(entry.SizeBytes)
	}

	maxSizeBytes := int64(config.MaxSizeMB) * 1024 * 1024
	if totalSize > maxSizeBytes {
		bytesToFree := totalSize - maxSizeBytes

		type entryWithKey struct {
			key          string
			entry        IndexEntry
			lastAccessed float64
		}
		var entries []entryWithKey
		for key, entry := range index.Entries {
			lastAccessed := entry.LastAccessed
			if lastAccessed == 0 {
				lastAccessed = entry.CreatedAt
			}
			entries = append(entries, entryWithKey{key, entry, lastAccessed})
		}

		sort.Slice(entries, func(i, j int) bool {
			return entries[i].lastAccessed < entries[j].lastAccessed
		})

		maxDeletable := len(index.Entries) - config.MinKeepEntries
		var freedBytes int64

		for i, e := range entries {
			if freedBytes >= bytesToFree || i >= maxDeletable {
				break
			}
			if !config.DryRun {
				if e.entry.FilePath != "" {
					if rmErr := cm.safeRemoveCacheFile(e.entry.FilePath); rmErr != nil && !os.IsNotExist(rmErr) {
						result.Errors++
						continue
					}
				}
				delete(index.Entries, e.key)
			}
			freedBytes += int64(e.entry.SizeBytes)
			result.DeletedFiles++
			result.FreedBytes += int64(e.entry.SizeBytes)
		}
	}

	result.FreedMB = float64(result.FreedBytes) / (1024 * 1024)
	result.RemainingFiles = len(index.Entries)

	// 一次性寫入索引（避免 TOCTOU 問題）
	if !config.DryRun && result.DeletedFiles > 0 {
		if err := cm.saveIndex(index); err != nil {
			return result, fmt.Errorf("儲存索引失敗: %w", err)
		}
	}

	return result, nil
}
