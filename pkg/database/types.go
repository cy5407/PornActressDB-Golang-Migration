package database

import (
	"encoding/json"
	"time"
)

// ============================================================================
// 資料結構定義（與 Python VideoDict, ActressDict 完全相容）
// ============================================================================

// VideoData represents a video record (compatible with Python VideoDict)
type VideoData struct {
	Code           string   `json:"code"`
	Title          string   `json:"title"`
	Studio         string   `json:"studio"`
	ReleaseDate    string   `json:"release_date"`
	URL            string   `json:"url"`
	Actresses      []string `json:"actresses"`
	SearchStatus   string   `json:"search_status"`
	LastSearchDate string   `json:"last_search_date"`
	CreatedAt      string   `json:"created_at"`
	UpdatedAt      string   `json:"updated_at"`
	Metadata       Metadata `json:"metadata,omitempty"`
}

// Metadata represents video metadata
type Metadata struct {
	Source     string  `json:"source,omitempty"`
	Confidence float64 `json:"confidence,omitempty"`
}

// ActressData represents an actress record (compatible with Python ActressDict)
type ActressData struct {
	ID         string   `json:"id"`
	Name       string   `json:"name"`
	Aliases    []string `json:"aliases,omitempty"`
	VideoCount int      `json:"video_count"`
	CreatedAt  string   `json:"created_at"`
	UpdatedAt  string   `json:"updated_at"`
}

// VideoActressLink represents the relationship between a video and an actress
type VideoActressLink struct {
	VideoCode string `json:"video_code"`
	ActressID string `json:"actress_id"`
	RoleType  string `json:"role_type"` // "主演", "配角", "客串"
	Timestamp string `json:"timestamp"`
}

// DatabaseData represents the complete database structure
type DatabaseData struct {
	SchemaVersion string                     `json:"schema_version"`
	Metadata      map[string]interface{}     `json:"metadata,omitempty"`
	DataHash      string                     `json:"data_hash,omitempty"`
	CreatedAt     string                     `json:"created_at"`
	UpdatedAt     string                     `json:"updated_at"`
	Videos        map[string]*VideoData      `json:"videos"`
	Actresses     map[string]*ActressData    `json:"actresses,omitempty"`
	Links         []*VideoActressLink        `json:"links,omitempty"`
	Statistics    map[string]interface{}     `json:"statistics,omitempty"`
}

// ============================================================================
// Journal 相關結構
// ============================================================================

// JournalOperation types
const (
	OpAdd    = "ADD"
	OpUpdate = "UPDATE"
	OpDelete = "DELETE"
)

// EntityType types
const (
	TypeVideo   = "video"
	TypeActress = "actress"
	TypeLink    = "link"
)

// JournalEntry represents a single journal record (JSON Lines format)
type JournalEntry struct {
	Op        string          `json:"op"`   // ADD, UPDATE, DELETE
	Type      string          `json:"type"` // video, actress, link
	ID        string          `json:"id"`
	Data      json.RawMessage `json:"data,omitempty"` // 延遲解析，提升效能
	Timestamp string          `json:"ts"`
}

// DirtyIndex represents the index of modified entities
type DirtyIndex struct {
	Videos           []string  `json:"videos"`
	Actresses        []string  `json:"actresses"`
	Links            []string  `json:"links"`
	JournalSize      int       `json:"journal_size"`
	JournalCreatedAt time.Time `json:"created_at"`
}

// ============================================================================
// 統計資訊結構
// ============================================================================

// Stats represents database statistics
type Stats struct {
	JournalSize         int     `json:"journal_size"`
	JournalAgeSeconds   float64 `json:"journal_age_seconds"`
	DirtyVideos         int     `json:"dirty_videos"`
	DirtyActresses      int     `json:"dirty_actresses"`
	DirtyLinks          int     `json:"dirty_links"`
	NeedsCompact        bool    `json:"needs_compact"`
	TotalVideos         int     `json:"total_videos"`
	TotalActresses      int     `json:"total_actresses"`
	TotalLinks          int     `json:"total_links"`
	DataFileSizeBytes   int64   `json:"data_file_size_bytes,omitempty"`
	JournalFileSizeBytes int64  `json:"journal_file_size_bytes,omitempty"`
}

// ============================================================================
// 錯誤類型
// ============================================================================

// Error types
type Error struct {
	Op  string // 操作名稱
	Err error  // 底層錯誤
}

func (e *Error) Error() string {
	return e.Op + ": " + e.Err.Error()
}

func (e *Error) Unwrap() error {
	return e.Err
}

// ============================================================================
// 常數定義
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

// ============================================================================
// 工具函式
// ============================================================================

// GetCurrentTimestamp returns current time in ISO 8601 format
func GetCurrentTimestamp() string {
	return time.Now().UTC().Format(ISODateTimeFormat)
}

// GetEmptyVideo creates a new empty VideoData with default values
func GetEmptyVideo() *VideoData {
	now := GetCurrentTimestamp()
	return &VideoData{
		Code:           "",
		Title:          "",
		Studio:         "",
		ReleaseDate:    "",
		URL:            "",
		Actresses:      []string{},
		SearchStatus:   SearchStatusFailed,
		LastSearchDate: "",
		CreatedAt:      now,
		UpdatedAt:      now,
		Metadata:       Metadata{},
	}
}

// GetEmptyActress creates a new empty ActressData with default values
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

// NewDatabaseData creates a new empty DatabaseData structure
func NewDatabaseData() *DatabaseData {
	now := GetCurrentTimestamp()
	return &DatabaseData{
		SchemaVersion: SchemaVersion,
		CreatedAt:     now,
		UpdatedAt:     now,
		Videos:        make(map[string]*VideoData),
		Actresses:     make(map[string]*ActressData),
		Links:         []*VideoActressLink{},
		Metadata:      make(map[string]interface{}),
		Statistics:    make(map[string]interface{}),
	}
}
