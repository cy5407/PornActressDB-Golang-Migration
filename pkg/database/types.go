// Package database 提供增量 JSON 資料庫功能
// 與 Python IncrementalJSONDB 完全相容
package database

import (
	"encoding/json"
	"time"
)

// ============================================================================
// 常數定義（與 Python 完全相容）
// ============================================================================

const (
	// Schema version (compatible with Python SCHEMA_VERSION)
	SchemaVersion = "1.0.0"

	// File names
	DataFileName    = "data.json"
	JournalFileName = "data.journal"
	IndexFileName   = "data.index"
	LockFileName    = "data.journal.lock"

	// Compact thresholds (compatible with Python)
	JournalSizeThreshold = 1000 // 超過 1000 條記錄觸發合併
	JournalAgeThreshold  = 3600 // 超過 1 小時觸發合併（秒）

	// Search statuses (compatible with Python)
	SearchStatusSuccess = "success"
	SearchStatusPartial = "partial"
	SearchStatusFailed  = "failed"

	// Role types (compatible with Python)
	RoleMain       = "主演"
	RoleSupporting = "配角"
	RoleGuest      = "客串"

	// ISO date format (compatible with Python)
	ISODateFormat     = "2006-01-02"
	ISODateTimeFormat = "2006-01-02T15:04:05Z"
)

// Journal 操作類型（與 Python JOURNAL_OP_* 相容）
const (
	OpAdd    = "ADD"
	OpUpdate = "UPDATE"
	OpDelete = "DELETE"
)

// 實體類型
const (
	TypeVideo   = "video"
	TypeActress = "actress"
	TypeLink    = "link"
)

// ============================================================================
// 資料結構定義（與 Python VideoDict, ActressDict 完全相容）
// ============================================================================

// Metadata 影片元資料
type Metadata struct {
	Source     string  `json:"source"`
	Confidence float64 `json:"confidence"`
}

// VideoData 影片資料結構（與 Python VideoDict 完全相容）
// 注意：某些欄位可能有 id 或 code，需要同時支援
type VideoData struct {
	Code             string   `json:"code"`
	ID               string   `json:"id,omitempty"` // 舊版相容欄位
	Title            string   `json:"title"`
	Studio           string   `json:"studio"`
	StudioCode       string   `json:"studio_code,omitempty"`
	ReleaseDate      string   `json:"release_date"`
	URL              string   `json:"url"`
	Actresses        []string `json:"actresses"`
	SearchStatus     string   `json:"search_status"`
	LastSearchDate   string   `json:"last_search_date"`
	CreatedAt        string   `json:"created_at"`
	UpdatedAt        string   `json:"updated_at"`
	Metadata         Metadata `json:"metadata"`
	OriginalFilename string   `json:"original_filename,omitempty"`
	FilePath         string   `json:"file_path,omitempty"`
	SearchMethod     string   `json:"search_method,omitempty"`
}

// GetCode 取得影片番號（優先 code，其次 id）
func (v *VideoData) GetCode() string {
	if v.Code != "" {
		return v.Code
	}
	return v.ID
}

// ActressData 女優資料結構（與 Python ActressDict 完全相容）
type ActressData struct {
	ID         string   `json:"id"`
	Name       string   `json:"name"`
	Aliases    []string `json:"aliases"`
	VideoCount int      `json:"video_count"`
	CreatedAt  string   `json:"created_at"`
	UpdatedAt  string   `json:"updated_at"`
}

// VideoActressLink 影片-女優關聯
type VideoActressLink struct {
	VideoCode string `json:"video_code"`
	ActressID string `json:"actress_id"`
	RoleType  string `json:"role_type"`
	Timestamp string `json:"timestamp"`
}

// DatabaseMetadata 資料庫元資料
type DatabaseMetadata struct {
	Description string `json:"description"`
	Encoding    string `json:"encoding"`
}

// DatabaseData 主資料庫結構（與 Python JSONDatabaseDict 完全相容）
type DatabaseData struct {
	SchemaVersion string                  `json:"schema_version"`
	Metadata      *DatabaseMetadata       `json:"metadata"`
	DataHash      string                  `json:"data_hash"`
	CreatedAt     string                  `json:"created_at"`
	UpdatedAt     string                  `json:"updated_at"`
	Videos        map[string]*VideoData   `json:"videos"`
	Actresses     map[string]*ActressData `json:"actresses"`
	Links         []VideoActressLink      `json:"links"`
	Statistics    map[string]any          `json:"statistics"`
}

// ============================================================================
// Journal 相關結構（與 Python JournalEntry 完全相容）
// ============================================================================

// JournalEntry Journal 記錄項（與 Python 格式完全相容）
// JSON Lines 格式：{"op":"UPDATE","type":"video","id":"STARS-707","data":{...},"ts":"..."}
type JournalEntry struct {
	Op   string          `json:"op"`             // ADD, UPDATE, DELETE
	Type string          `json:"type"`           // video, actress, link
	ID   string          `json:"id"`             // 實體 ID
	Data json.RawMessage `json:"data,omitempty"` // 資料（延遲解析提升效能）
	Ts   string          `json:"ts"`             // 時間戳
}

// NewJournalEntry 建立新的 Journal 記錄
func NewJournalEntry(op, entityType, id string, data any) (*JournalEntry, error) {
	var rawData json.RawMessage
	if data != nil {
		b, err := json.Marshal(data)
		if err != nil {
			return nil, err
		}
		rawData = b
	}

	return &JournalEntry{
		Op:   op,
		Type: entityType,
		ID:   id,
		Data: rawData,
		Ts:   time.Now().UTC().Format(time.RFC3339),
	}, nil
}

// DirtyIndex Dirty keys 索引（與 Python data.index 格式完全相容）
type DirtyIndex struct {
	Videos      []string `json:"videos"`
	Actresses   []string `json:"actresses"`
	Links       []string `json:"links"`
	JournalSize int      `json:"journal_size"`
	CreatedAt   string   `json:"created_at"`
}

// ============================================================================
// 統計資訊結構
// ============================================================================

// Stats 資料庫統計資訊（與 Python get_stats() 返回格式相容）
//
// DirtyVideos 包含所有待 compact 的影片操作（ADD + UPDATE + DELETE）。
// DeletedVideos 是其子集，僅包含本 session 中被刪除的影片（自上次 compact 後）。
// compact 後兩者均會被清空。
type Stats struct {
	JournalSize          int     `json:"journal_size"`
	JournalAgeSeconds    float64 `json:"journal_age_seconds"`
	DirtyVideos          int     `json:"dirty_videos"`   // ADD + UPDATE + DELETE 的合計
	DeletedVideos        int     `json:"deleted_videos"` // 僅 DELETE 操作（DirtyVideos 的子集）
	DirtyActresses       int     `json:"dirty_actresses"`
	DirtyLinks           int     `json:"dirty_links"`
	NeedsCompact         bool    `json:"needs_compact"`
	TotalVideos          int     `json:"total_videos"`
	TotalActresses       int     `json:"total_actresses,omitempty"`
	TotalLinks           int     `json:"total_links,omitempty"`
	DataFileSizeBytes    int64   `json:"data_file_size_bytes,omitempty"`
	JournalFileSizeBytes int64   `json:"journal_file_size_bytes,omitempty"`
}

// MergeStats 資料庫合併結果統計
type MergeStats struct {
	VideosAdded      int `json:"videos_added"`
	VideosUpdated    int `json:"videos_updated"`
	VideosSkipped    int `json:"videos_skipped"`
	ActressesAdded   int `json:"actresses_added"`
	ActressesUpdated int `json:"actresses_updated"`
	LinksAdded       int `json:"links_added"`
}

// ============================================================================
// 錯誤類型
// ============================================================================

// DatabaseError 資料庫操作錯誤
type DatabaseError struct {
	Op  string // 操作名稱
	Err error  // 底層錯誤
}

func (e *DatabaseError) Error() string {
	if e.Err != nil {
		return e.Op + ": " + e.Err.Error()
	}
	return e.Op + ": unknown error"
}

func (e *DatabaseError) Unwrap() error {
	return e.Err
}

// ============================================================================
// 工具函式
// ============================================================================

// GetCurrentTimestamp 取得當前 UTC 時間戳（ISO 8601 格式）
func GetCurrentTimestamp() string {
	return time.Now().UTC().Format(ISODateTimeFormat)
}

// GetCurrentTimestampRFC3339 取得當前 UTC 時間戳（RFC3339 格式，與 Python 相容）
func GetCurrentTimestampRFC3339() string {
	return time.Now().UTC().Format(time.RFC3339)
}

// GetEmptyVideo 建立空的影片資料結構
func GetEmptyVideo() *VideoData {
	now := GetCurrentTimestamp()
	return &VideoData{
		Code:           "",
		Title:          "",
		Studio:         "",
		ReleaseDate:    "",
		URL:            "",
		Actresses:      []string{},
		SearchStatus:   SearchStatusSuccess,
		LastSearchDate: now,
		CreatedAt:      now,
		UpdatedAt:      now,
		Metadata: Metadata{
			Source:     "",
			Confidence: 0.0,
		},
	}
}

// NewVideo 建立新的影片資料結構（測試用）
func NewVideo(code string) *VideoData {
	now := GetCurrentTimestamp()
	return &VideoData{
		Code:           code,
		Title:          "",
		Studio:         "",
		ReleaseDate:    "",
		URL:            "",
		Actresses:      []string{},
		SearchStatus:   SearchStatusSuccess,
		LastSearchDate: now,
		CreatedAt:      now,
		UpdatedAt:      now,
		Metadata: Metadata{
			Source:     "",
			Confidence: 0.0,
		},
	}
}

// GetEmptyActress 建立空的女優資料結構
func GetEmptyActress() *ActressData {
	now := GetCurrentTimestamp()
	return &ActressData{
		ID:         "",
		Name:       "",
		Aliases:    []string{},
		VideoCount: 0,
		CreatedAt:  now,
		UpdatedAt:  now,
	}
}

// NewDatabaseData 建立空的資料庫結構
func NewDatabaseData() *DatabaseData {
	now := GetCurrentTimestamp()
	return &DatabaseData{
		SchemaVersion: SchemaVersion,
		Metadata: &DatabaseMetadata{
			Description: "Python 女優分類系統 JSON 資料庫",
			Encoding:    "UTF-8",
		},
		DataHash:   "",
		CreatedAt:  now,
		UpdatedAt:  now,
		Videos:     make(map[string]*VideoData),
		Actresses:  make(map[string]*ActressData),
		Links:      []VideoActressLink{},
		Statistics: make(map[string]any),
	}
}

// NewEmptyDirtyIndex 建立空的 Dirty Index
func NewEmptyDirtyIndex() *DirtyIndex {
	return &DirtyIndex{
		Videos:      []string{},
		Actresses:   []string{},
		Links:       []string{},
		JournalSize: 0,
		CreatedAt:   GetCurrentTimestampRFC3339(),
	}
}
