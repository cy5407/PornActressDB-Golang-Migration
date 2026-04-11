// Package cache 提供快取管理功能
//
// 此套件專注於快取索引操作（stats, prune, clear），
// 與 Python cache_manager.py 完全相容。
// 讀寫快取值仍由 Python 處理（目前為 JSON 載荷格式）。
package cache

// IndexEntry 索引條目
type IndexEntry struct {
	FilePath     string  `json:"file_path"`
	CreatedAt    float64 `json:"created_at"`
	TTLSeconds   int     `json:"ttl_seconds"`
	LastAccessed float64 `json:"last_accessed"`
	AccessCount  int     `json:"access_count"`
	Compressed   bool    `json:"compressed"`
	SizeBytes    int     `json:"size_bytes"`
}

// IndexMetadata 索引元數據
type IndexMetadata struct {
	Version   string  `json:"version"`
	CreatedAt float64 `json:"created_at"`
}

// CacheIndex 快取索引結構
type CacheIndex struct {
	Metadata IndexMetadata         `json:"_metadata"`
	Entries  map[string]IndexEntry `json:"entries"`
}

// CacheStats 快取統計資訊
type CacheStats struct {
	TotalFiles         int     `json:"total_files"`
	TotalSizeMB        float64 `json:"total_size_mb"`
	OldestEntry        string  `json:"oldest_entry,omitempty"`
	NewestEntry        string  `json:"newest_entry,omitempty"`
	IndexEntries       int     `json:"index_entries"`
	AverageAccessCount float64 `json:"average_access_count"`
	ExpiredCount       int     `json:"expired_count"`
}

// CleanupResult 清理結果
type CleanupResult struct {
	DeletedFiles   int     `json:"deleted_files"`
	FreedBytes     int64   `json:"freed_bytes"`
	FreedMB        float64 `json:"freed_mb"`
	RemainingFiles int     `json:"remaining_files"`
	Errors         int     `json:"errors"`
}

// PruneConfig 清理配置
type PruneConfig struct {
	TTLDays        int  `json:"ttl_days"`
	MaxSizeMB      int  `json:"max_size_mb"`
	MinKeepEntries int  `json:"min_keep_entries"`
	DryRun         bool `json:"dry_run"`
}

// DefaultPruneConfig 預設清理配置
func DefaultPruneConfig() PruneConfig {
	return PruneConfig{
		TTLDays:        7,
		MaxSizeMB:      500,
		MinKeepEntries: 100,
		DryRun:         false,
	}
}

// CachePayload 快取讀寫載荷格式（與 Python cache_manager.py 磁碟格式相容）
type CachePayload struct {
	Version    int     `json:"version"`
	CreatedAt  float64 `json:"created_at"`
	TTLSeconds int     `json:"ttl_seconds"`
	Compressed bool    `json:"compressed"`
	Data       []byte  `json:"data"`
}
