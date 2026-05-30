package cache

import (
	"context"
	"crypto/sha256"
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

type cacheEntryCandidate struct {
	key        string
	entry      IndexEntry
	orderValue float64
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
		expired := limitCleanupCandidates(collectExpiredCandidates(index.Entries, now, ttlSeconds), len(index.Entries), config.MinKeepEntries)
		cm.applyCleanupCandidates(index, expired, config.DryRun, result)
	}

	// 第二步：清理超大條目（LRU，共用同一份 index）
	totalSize := totalIndexSize(index.Entries)
	maxSizeBytes := int64(config.MaxSizeMB) * 1024 * 1024
	if totalSize > maxSizeBytes {
		bytesToFree := totalSize - maxSizeBytes
		candidates := selectSizeCleanupCandidates(collectLRUCandidates(index.Entries), bytesToFree, len(index.Entries), config.MinKeepEntries)
		cm.applyCleanupCandidates(index, candidates, config.DryRun, result)
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

func collectExpiredCandidates(entries map[string]IndexEntry, now, ttlSeconds float64) []cacheEntryCandidate {
	candidates := make([]cacheEntryCandidate, 0)
	for key, entry := range entries {
		if now-entry.CreatedAt > ttlSeconds {
			candidates = append(candidates, cacheEntryCandidate{
				key:        key,
				entry:      entry,
				orderValue: entry.CreatedAt,
			})
		}
	}
	sortCacheCandidates(candidates)
	return candidates
}

func collectLRUCandidates(entries map[string]IndexEntry) []cacheEntryCandidate {
	candidates := make([]cacheEntryCandidate, 0, len(entries))
	for key, entry := range entries {
		orderValue := entry.LastAccessed
		if orderValue == 0 {
			orderValue = entry.CreatedAt
		}
		candidates = append(candidates, cacheEntryCandidate{
			key:        key,
			entry:      entry,
			orderValue: orderValue,
		})
	}
	sortCacheCandidates(candidates)
	return candidates
}

func sortCacheCandidates(candidates []cacheEntryCandidate) {
	sort.Slice(candidates, func(i, j int) bool {
		return candidates[i].orderValue < candidates[j].orderValue
	})
}

func limitCleanupCandidates(candidates []cacheEntryCandidate, totalEntries, minKeepEntries int) []cacheEntryCandidate {
	maxDeletable := totalEntries - minKeepEntries
	if maxDeletable <= 0 {
		return nil
	}
	if len(candidates) <= maxDeletable {
		return candidates
	}
	return candidates[:maxDeletable]
}

func selectSizeCleanupCandidates(candidates []cacheEntryCandidate, bytesToFree int64, totalEntries, minKeepEntries int) []cacheEntryCandidate {
	limited := limitCleanupCandidates(candidates, totalEntries, minKeepEntries)
	selected := make([]cacheEntryCandidate, 0, len(limited))
	var freedBytes int64
	for _, candidate := range limited {
		if freedBytes >= bytesToFree {
			break
		}
		selected = append(selected, candidate)
		freedBytes += int64(candidate.entry.SizeBytes)
	}
	return selected
}

func (cm *CacheManager) applyCleanupCandidates(index *CacheIndex, candidates []cacheEntryCandidate, dryRun bool, result *CleanupResult) {
	for _, candidate := range candidates {
		if !dryRun {
			if candidate.entry.FilePath != "" {
				if err := cm.safeRemoveCacheFile(candidate.entry.FilePath); err != nil && !os.IsNotExist(err) {
					result.Errors++
					continue
				}
			}
			delete(index.Entries, candidate.key)
		}
		result.DeletedFiles++
		result.FreedBytes += int64(candidate.entry.SizeBytes)
	}
}

func totalIndexSize(entries map[string]IndexEntry) int64 {
	var totalSize int64
	for _, entry := range entries {
		totalSize += int64(entry.SizeBytes)
	}
	return totalSize
}

// hashKey 以 SHA256 雜湊 key（與 Python _generate_cache_key 相容）
func hashKey(key string) string {
	sum := sha256.Sum256([]byte(key))
	return fmt.Sprintf("%x", sum[:])
}

// cacheFilePath 回傳快取檔案路徑（前兩字元作為子目錄，.json 副檔名）
func (cm *CacheManager) cacheFilePath(cacheKey string) string {
	subDir := cacheKey[:2]
	return filepath.Join(cm.cacheDir, subDir, cacheKey+".json")
}

// Set 寫入快取值。ttlHours <= 0 視為立即過期（讀取時永遠不返回）。
func (cm *CacheManager) Set(key string, value []byte, ttlHours int) error {
	cacheKey := hashKey(key)
	filePath := cm.cacheFilePath(cacheKey)

	if err := os.MkdirAll(filepath.Dir(filePath), 0750); err != nil {
		return fmt.Errorf("建立快取子目錄失敗: %w", err)
	}

	payload := CachePayload{
		Version:    1,
		CreatedAt:  float64(time.Now().Unix()),
		TTLSeconds: ttlHours * 3600,
		Compressed: false,
		Data:       value,
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("序列化快取載荷失敗: %w", err)
	}
	if err := safefile.WriteFile(filePath, data, 0600); err != nil {
		return fmt.Errorf("寫入快取檔案失敗: %w", err)
	}

	// 更新索引（best-effort，索引失敗不影響主要快取寫入）
	index, _ := cm.loadIndex() //nolint:errcheck
	if index == nil {
		index = &CacheIndex{
			Metadata: IndexMetadata{Version: "1.0", CreatedAt: payload.CreatedAt},
			Entries:  make(map[string]IndexEntry),
		}
	}
	index.Entries[cacheKey] = IndexEntry{
		FilePath:     filePath,
		CreatedAt:    payload.CreatedAt,
		TTLSeconds:   payload.TTLSeconds,
		LastAccessed: payload.CreatedAt,
		AccessCount:  0,
		Compressed:   false,
		SizeBytes:    len(data),
	}
	return cm.saveIndex(index)
}

// Get 讀取快取值。found=false 表示 key 不存在或已過期。
func (cm *CacheManager) Get(key string) (value []byte, found bool, err error) {
	cacheKey := hashKey(key)
	filePath := cm.cacheFilePath(cacheKey)

	data, readErr := safefile.ReadFile(filePath)
	if readErr != nil {
		return nil, false, nil // 不存在
	}

	var payload CachePayload
	if unmarshalErr := json.Unmarshal(data, &payload); unmarshalErr != nil {
		return nil, false, nil // 損毀，視為不存在
	}

	// ttlSeconds <= 0 視為立即過期
	if payload.TTLSeconds <= 0 {
		return nil, false, nil
	}
	age := float64(time.Now().Unix()) - payload.CreatedAt
	if age > float64(payload.TTLSeconds) {
		return nil, false, nil // 已過期
	}

	// 更新存取統計（best-effort，忽略錯誤）
	index, _ := cm.loadIndex() //nolint:errcheck
	if index != nil {
		if entry, ok := index.Entries[cacheKey]; ok {
			entry.LastAccessed = float64(time.Now().Unix())
			entry.AccessCount++
			index.Entries[cacheKey] = entry
			_ = cm.saveIndex(index) //nolint:errcheck
		}
	}

	return payload.Data, true, nil
}

// Delete 刪除快取條目及其索引記錄。
func (cm *CacheManager) Delete(key string) error {
	cacheKey := hashKey(key)
	filePath := cm.cacheFilePath(cacheKey)

	if !cm.validateCachePath(filePath) {
		return fmt.Errorf("路徑安全驗證失敗: %s", filePath)
	}
	_ = os.Remove(filePath)

	index, _ := cm.loadIndex() //nolint:errcheck
	if index != nil {
		delete(index.Entries, cacheKey)
		return cm.saveIndex(index)
	}
	return nil
}
