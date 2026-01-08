package database

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"
)

var (
	// ErrNotFound 資料不存在錯誤
	ErrNotFound = errors.New("video not found")
	// ErrInvalidCode 無效番號錯誤
	ErrInvalidCode = errors.New("invalid video code")
	// ErrDatabaseNotLoaded 資料庫未載入錯誤
	ErrDatabaseNotLoaded = errors.New("database not loaded")
)

// JSONDatabase JSON 資料庫管理器
type JSONDatabase struct {
	mu          sync.RWMutex       // 讀寫鎖
	dataFile    string             // 資料檔案路徑
	journalFile string             // Journal 檔案路徑
	root        *JSONDatabaseRoot  // 資料庫根結構
	loaded      bool               // 是否已載入
}

// NewJSONDatabase 建立新的 JSON 資料庫實例
func NewJSONDatabase(dataDir string) *JSONDatabase {
	dataFile := filepath.Join(dataDir, "data.json")
	journalFile := filepath.Join(dataDir, "data.journal")

	return &JSONDatabase{
		dataFile:    dataFile,
		journalFile: journalFile,
		root:        nil,
		loaded:      false,
	}
}

// Load 載入資料庫
func (db *JSONDatabase) Load() error {
	db.mu.Lock()
	defer db.mu.Unlock()

	// 檢查檔案是否存在
	if _, err := os.Stat(db.dataFile); os.IsNotExist(err) {
		// 檔案不存在，建立新的空資料庫
		db.root = NewJSONDatabaseRoot()
		db.loaded = true
		return db.saveUnsafe() // 儲存初始檔案
	}

	// 讀取檔案
	data, err := os.ReadFile(db.dataFile)
	if err != nil {
		return fmt.Errorf("failed to read database file: %w", err)
	}

	// 解析 JSON
	var root JSONDatabaseRoot
	if err := json.Unmarshal(data, &root); err != nil {
		return fmt.Errorf("failed to parse database JSON: %w", err)
	}

	db.root = &root
	db.loaded = true

	// 載入 journal (如果存在)
	if err := db.loadJournal(); err != nil {
		// Journal 載入失敗不視為致命錯誤，僅記錄
		fmt.Fprintf(os.Stderr, "Warning: failed to load journal: %v\n", err)
	}

	return nil
}

// Save 儲存資料庫
func (db *JSONDatabase) Save() error {
	db.mu.Lock()
	defer db.mu.Unlock()

	return db.saveUnsafe()
}

// saveUnsafe 儲存資料庫 (不加鎖，內部使用)
func (db *JSONDatabase) saveUnsafe() error {
	if !db.loaded {
		return ErrDatabaseNotLoaded
	}

	// 更新時間戳
	db.root.UpdatedAt = time.Now().UTC().Format(ISODateTimeFormat)

	// 序列化 JSON
	data, err := json.MarshalIndent(db.root, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal database: %w", err)
	}

	// 寫入暫存檔
	tmpFile := db.dataFile + ".tmp"
	if err := os.WriteFile(tmpFile, data, 0644); err != nil {
		return fmt.Errorf("failed to write temp file: %w", err)
	}

	// 原子性替換
	if err := os.Rename(tmpFile, db.dataFile); err != nil {
		os.Remove(tmpFile) // 清理暫存檔
		return fmt.Errorf("failed to replace database file: %w", err)
	}

	return nil
}

// GetVideo 取得影片資訊
func (db *JSONDatabase) GetVideo(code string) (*Video, error) {
	if code == "" {
		return nil, ErrInvalidCode
	}

	db.mu.RLock()
	defer db.mu.RUnlock()

	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}

	video, exists := db.root.Videos[code]
	if !exists {
		return nil, ErrNotFound
	}

	// 返回複本避免外部修改
	videoCopy := *video
	return &videoCopy, nil
}

// UpdateVideo 更新影片資訊
func (db *JSONDatabase) UpdateVideo(code string, video *Video) error {
	if code == "" {
		return ErrInvalidCode
	}
	if video == nil {
		return errors.New("video cannot be nil")
	}

	db.mu.Lock()
	defer db.mu.Unlock()

	if !db.loaded {
		return ErrDatabaseNotLoaded
	}

	// 更新時間戳
	video.UpdatedAt = time.Now().UTC().Format(ISODateTimeFormat)

	// 如果是新影片，設定 CreatedAt
	if _, exists := db.root.Videos[code]; !exists {
		video.CreatedAt = video.UpdatedAt
	}

	// 儲存影片
	db.root.Videos[code] = video

	// 寫入 journal
	if err := db.appendJournal("update", code, video); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: failed to write journal: %v\n", err)
	}

	return nil
}

// DeleteVideo 刪除影片
func (db *JSONDatabase) DeleteVideo(code string) error {
	if code == "" {
		return ErrInvalidCode
	}

	db.mu.Lock()
	defer db.mu.Unlock()

	if !db.loaded {
		return ErrDatabaseNotLoaded
	}

	if _, exists := db.root.Videos[code]; !exists {
		return ErrNotFound
	}

	delete(db.root.Videos, code)

	// 寫入 journal
	if err := db.appendJournal("delete", code, nil); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: failed to write journal: %v\n", err)
	}

	return nil
}

// ListVideos 列出所有影片番號
func (db *JSONDatabase) ListVideos() ([]string, error) {
	db.mu.RLock()
	defer db.mu.RUnlock()

	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}

	codes := make([]string, 0, len(db.root.Videos))
	for code := range db.root.Videos {
		codes = append(codes, code)
	}

	return codes, nil
}

// GetVideoCount 取得影片總數
func (db *JSONDatabase) GetVideoCount() (int, error) {
	db.mu.RLock()
	defer db.mu.RUnlock()

	if !db.loaded {
		return 0, ErrDatabaseNotLoaded
	}

	return len(db.root.Videos), nil
}

// BatchUpdate 批次更新影片
func (db *JSONDatabase) BatchUpdate(updates map[string]*Video) error {
	if len(updates) == 0 {
		return nil
	}

	db.mu.Lock()
	defer db.mu.Unlock()

	if !db.loaded {
		return ErrDatabaseNotLoaded
	}

	now := time.Now().UTC().Format(ISODateTimeFormat)

	for code, video := range updates {
		if code == "" || video == nil {
			continue
		}

		// 更新時間戳
		video.UpdatedAt = now
		if _, exists := db.root.Videos[code]; !exists {
			video.CreatedAt = now
		}

		db.root.Videos[code] = video
	}

	// 批次寫入 journal
	for code, video := range updates {
		if err := db.appendJournal("update", code, video); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: failed to write journal entry: %v\n", err)
		}
	}

	return nil
}

// CompactJournal 合併 journal 到主資料庫
func (db *JSONDatabase) CompactJournal() error {
	db.mu.Lock()
	defer db.mu.Unlock()

	if !db.loaded {
		return ErrDatabaseNotLoaded
	}

	// 儲存主資料庫
	if err := db.saveUnsafe(); err != nil {
		return fmt.Errorf("failed to save database: %w", err)
	}

	// 清空 journal
	if err := os.Remove(db.journalFile); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("failed to remove journal: %w", err)
	}

	return nil
}

// GetStats 取得資料庫統計資訊
func (db *JSONDatabase) GetStats() (map[string]interface{}, error) {
	db.mu.RLock()
	defer db.mu.RUnlock()

	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}

	stats := map[string]interface{}{
		"video_count":   len(db.root.Videos),
		"actress_count": len(db.root.Actresses),
		"link_count":    len(db.root.Links),
		"schema_version": db.root.SchemaVersion,
		"created_at":    db.root.CreatedAt,
		"updated_at":    db.root.UpdatedAt,
	}

	return stats, nil
}
