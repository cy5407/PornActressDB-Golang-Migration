// Package database 提供 JSON 資料庫的核心功能
package database

import "time"

// Metadata 額外資訊
type Metadata struct {
	Source     string  `json:"source"`               // 資料來源
	Confidence float64 `json:"confidence,omitempty"` // 資訊置信度 (0.0-1.0)
}

// Video 影片資料結構
type Video struct {
	Code           string   `json:"code"`                       // 影片番號
	Title          string   `json:"title"`                      // 片名
	Studio         string   `json:"studio"`                     // 片商名稱
	ReleaseDate    string   `json:"release_date"`               // 發行日期 (ISO 8601: YYYY-MM-DD)
	URL            string   `json:"url"`                        // 線上連結
	Actresses      []string `json:"actresses"`                  // 女優名稱清單
	SearchStatus   string   `json:"search_status"`              // "success" | "partial" | "failed"
	LastSearchDate string   `json:"last_search_date,omitempty"` // 最後搜尋日期 (ISO 8601)
	CreatedAt      string   `json:"created_at"`                 // 建立時間 (ISO 8601)
	UpdatedAt      string   `json:"updated_at"`                 // 更新時間 (ISO 8601)
	Metadata       Metadata `json:"metadata"`                   // 額外資訊
}

// Actress 女優資料結構
type Actress struct {
	ID         string   `json:"id"`          // 唯一識別符
	Name       string   `json:"name"`        // 名字
	Aliases    []string `json:"aliases"`     // 別名清單
	VideoCount int      `json:"video_count"` // 出演部數
	CreatedAt  string   `json:"created_at"`  // 建立時間 (ISO 8601)
	UpdatedAt  string   `json:"updated_at"`  // 更新時間 (ISO 8601)
}

// VideoActressLink 影片-女優關聯資料
type VideoActressLink struct {
	VideoCode  string `json:"video_code"`  // 影片番號
	ActressID  string `json:"actress_id"`  // 女優 ID
	RoleType   string `json:"role_type"`   // 角色類型
	Timestamp  string `json:"timestamp"`   // 關聯建立時間
}

// ActressStatistics 女優統計
type ActressStatistics struct {
	ActressID       string   `json:"actress_id"`         // 女優 ID
	TotalVideos     int      `json:"total_videos"`       // 總出演部數
	Studios         []string `json:"studios"`            // 片商清單
	LatestVideoDate string   `json:"latest_video_date"`  // 最新出演日期
}

// StudioStatistics 片商統計
type StudioStatistics struct {
	StudioName   string            `json:"studio_name"`   // 片商名稱
	TotalVideos  int               `json:"total_videos"`  // 總影片數
	ActressCount int               `json:"actress_count"` // 女優數
	DateRange    map[string]string `json:"date_range"`    // 日期範圍
}

// CrossStatistics 交叉統計
type CrossStatistics struct {
	ActressID string `json:"actress_id"` // 女優 ID
	Studio    string `json:"studio"`     // 片商名稱
	Count     int    `json:"count"`      // 出演部數
}

// Statistics 統計快取結構
type Statistics struct {
	ActressStats []ActressStatistics `json:"actress_stats"`   // 女優統計
	StudioStats  []StudioStatistics  `json:"studio_stats"`    // 片商統計
	CrossStats   []CrossStatistics   `json:"cross_stats"`     // 交叉統計
	LastComputed string              `json:"last_computed"`   // 最後計算時間
}

// JSONDatabaseRoot JSON 資料庫根層結構
type JSONDatabaseRoot struct {
	SchemaVersion string                `json:"schema_version"` // Schema 版本
	Metadata      map[string]interface{} `json:"metadata"`       // 元數據
	DataHash      string                `json:"data_hash"`      // 資料 SHA256 雜湊
	CreatedAt     string                `json:"created_at"`     // 建立時間
	UpdatedAt     string                `json:"updated_at"`     // 更新時間
	Videos        map[string]*Video     `json:"videos"`         // 影片資料
	Actresses     map[string]*Actress   `json:"actresses"`      // 女優資料
	Links         []VideoActressLink    `json:"links"`          // 影片-女優關聯
	Statistics    Statistics            `json:"statistics"`     // 統計快取
}

// 常數定義
const (
	SchemaVersion = "1.0.0"

	// 搜尋狀態
	SearchStatusSuccess = "success"
	SearchStatusPartial = "partial"
	SearchStatusFailed  = "failed"

	// 角色類型
	RoleTypeMain       = "主演"
	RoleTypeSupporting = "配角"
	RoleTypeGuest      = "客串"

	// 日期格式
	ISODateFormat     = "2006-01-02"
	ISODateTimeFormat = "2006-01-02T15:04:05Z"
)

// NewVideo 建立新的影片資料
func NewVideo(code string) *Video {
	now := time.Now().UTC().Format(ISODateTimeFormat)
	return &Video{
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

// NewActress 建立新的女優資料
func NewActress(id, name string) *Actress {
	now := time.Now().UTC().Format(ISODateTimeFormat)
	return &Actress{
		ID:         id,
		Name:       name,
		Aliases:    []string{},
		VideoCount: 0,
		CreatedAt:  now,
		UpdatedAt:  now,
	}
}

// NewJSONDatabaseRoot 建立空的資料庫根結構
func NewJSONDatabaseRoot() *JSONDatabaseRoot {
	now := time.Now().UTC().Format(ISODateTimeFormat)
	return &JSONDatabaseRoot{
		SchemaVersion: SchemaVersion,
		Metadata: map[string]interface{}{
			"description": "Go 女優分類系統 JSON 資料庫",
			"encoding":    "UTF-8",
		},
		DataHash:  "",
		CreatedAt: now,
		UpdatedAt: now,
		Videos:    make(map[string]*Video),
		Actresses: make(map[string]*Actress),
		Links:     []VideoActressLink{},
		Statistics: Statistics{
			ActressStats: []ActressStatistics{},
			StudioStats:  []StudioStatistics{},
			CrossStats:   []CrossStatistics{},
			LastComputed: now,
		},
	}
}
