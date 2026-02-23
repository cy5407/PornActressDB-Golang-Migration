package database

import (
	"context"
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

// Video 是 VideoData 的別名（向後相容）
type Video = VideoData

// JSONDatabaseRoot 是 DatabaseData 的別名（向後相容）
type JSONDatabaseRoot = DatabaseData

// JSONDatabase JSON 資料庫管理器
type JSONDatabase struct {
	mu          sync.RWMutex  // 讀寫鎖
	dataDir     string        // 資料目錄
	dataFile    string        // 資料檔案路徑
	journalFile string        // Journal 檔案路徑
	indexFile   string        // Index 檔案路徑
	root        *DatabaseData // 資料庫根結構
	loaded      bool          // 是否已載入

	// Dirty tracking（與 Python 相容）
	dirtyVideos    map[string]bool
	dirtyActresses map[string]bool
	dirtyLinks     map[string]bool
	journalSize    int
	journalCreatedAt time.Time
}

// NewJSONDatabase 建立新的 JSON 資料庫實例
func NewJSONDatabase(dataDir string) *JSONDatabase {
	return &JSONDatabase{
		dataDir:        dataDir,
		dataFile:       filepath.Join(dataDir, DataFileName),
		journalFile:    filepath.Join(dataDir, JournalFileName),
		indexFile:      filepath.Join(dataDir, IndexFileName),
		root:           nil,
		loaded:         false,
		dirtyVideos:    make(map[string]bool),
		dirtyActresses: make(map[string]bool),
		dirtyLinks:     make(map[string]bool),
		journalSize:    0,
	}
}

// Load 載入資料庫
// ctx 用於支援未來的取消與逾時（目前接受但不使用）
func (db *JSONDatabase) Load(ctx context.Context) error {
	_ = ctx // 預留給未來的取消支援
	db.mu.Lock()
	defer db.mu.Unlock()

	// 確保資料目錄存在
	if err := os.MkdirAll(db.dataDir, 0755); err != nil {
		return fmt.Errorf("failed to create data directory: %w", err)
	}

	// 檢查檔案是否存在
	if _, err := os.Stat(db.dataFile); os.IsNotExist(err) {
		// 檔案不存在，建立新的空資料庫
		db.root = NewDatabaseData()
		db.loaded = true
		db.journalCreatedAt = time.Now().UTC()
		return db.saveUnsafe() // 儲存初始檔案
	}

	// 讀取檔案
	data, err := os.ReadFile(db.dataFile)
	if err != nil {
		return fmt.Errorf("failed to read database file: %w", err)
	}

	// 解析 JSON
	var root DatabaseData
	if err := json.Unmarshal(data, &root); err != nil {
		return fmt.Errorf("failed to parse database JSON: %w", err)
	}

	// 確保 map 已初始化
	if root.Videos == nil {
		root.Videos = make(map[string]*VideoData)
	}
	if root.Actresses == nil {
		root.Actresses = make(map[string]*ActressData)
	}
	if root.Statistics == nil {
		root.Statistics = make(map[string]any)
	}

	db.root = &root
	db.loaded = true

	// 載入 index（如果存在）
	db.loadIndex()

	// 載入 journal (如果存在)
	if err := db.loadJournal(); err != nil {
		// Journal 載入失敗不視為致命錯誤，僅記錄
		fmt.Fprintf(os.Stderr, "Warning: failed to load journal: %v\n", err)
	}

	return nil
}

// loadIndex 載入 dirty index
func (db *JSONDatabase) loadIndex() {
	data, err := os.ReadFile(db.indexFile)
	if err != nil {
		// Index 不存在是正常情況
		db.journalCreatedAt = time.Now().UTC()
		return
	}

	var index DirtyIndex
	if err := json.Unmarshal(data, &index); err != nil {
		db.journalCreatedAt = time.Now().UTC()
		return
	}

	// 載入 dirty keys
	for _, v := range index.Videos {
		db.dirtyVideos[v] = true
	}
	for _, a := range index.Actresses {
		db.dirtyActresses[a] = true
	}
	for _, l := range index.Links {
		db.dirtyLinks[l] = true
	}

	db.journalSize = index.JournalSize

	// 解析建立時間
	if t, err := time.Parse(time.RFC3339, index.CreatedAt); err == nil {
		db.journalCreatedAt = t
	} else {
		db.journalCreatedAt = time.Now().UTC()
	}
}

// saveIndex 儲存 dirty index
func (db *JSONDatabase) saveIndex() error {
	videos := make([]string, 0, len(db.dirtyVideos))
	for v := range db.dirtyVideos {
		videos = append(videos, v)
	}

	actresses := make([]string, 0, len(db.dirtyActresses))
	for a := range db.dirtyActresses {
		actresses = append(actresses, a)
	}

	links := make([]string, 0, len(db.dirtyLinks))
	for l := range db.dirtyLinks {
		links = append(links, l)
	}

	index := DirtyIndex{
		Videos:      videos,
		Actresses:   actresses,
		Links:       links,
		JournalSize: db.journalSize,
		CreatedAt:   db.journalCreatedAt.Format(time.RFC3339),
	}

	data, err := json.MarshalIndent(index, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(db.indexFile, data, 0644)
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

	// 判斷是新增還是更新
	_, exists := db.root.Videos[code]
	var op string
	if !exists {
		video.CreatedAt = video.UpdatedAt
		op = OpAdd
	} else {
		op = OpUpdate
	}

	// 確保 code 欄位正確
	video.Code = code

	// 儲存影片
	db.root.Videos[code] = video

	// 寫入 journal（使用 Python 相容格式）
	entry, err := NewJournalEntry(op, TypeVideo, code, video)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Warning: failed to create journal entry: %v\n", err)
	} else {
		if err := db.appendJournalEntry(entry); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: failed to write journal: %v\n", err)
		} else {
			// 更新 dirty tracking
			db.dirtyVideos[code] = true
			db.journalSize++
			if err := db.saveIndex(); err != nil {
				fmt.Fprintf(os.Stderr, "Warning: failed to save index: %v\n", err)
			}
		}
	}

	return nil
}

// UpdateVideoFields 更新影片的特定欄位（與 Python update_video 相容）
func (db *JSONDatabase) UpdateVideoFields(code string, updates map[string]any) error {
	if code == "" {
		return ErrInvalidCode
	}

	db.mu.Lock()
	defer db.mu.Unlock()

	if !db.loaded {
		return ErrDatabaseNotLoaded
	}

	// 取得現有影片
	video, exists := db.root.Videos[code]
	if !exists {
		return ErrNotFound
	}

	// 套用更新
	db.applyVideoUpdates(video, updates)

	// 寫入 journal（僅記錄更新的欄位，與 Python 相容）
	entry, err := NewJournalEntry(OpUpdate, TypeVideo, code, updates)
	if err != nil {
		return err
	}

	if err := db.appendJournalEntry(entry); err != nil {
		return err
	}

	// 更新 dirty tracking
	db.dirtyVideos[code] = true
	db.journalSize++
	if err := db.saveIndex(); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: failed to save index: %v\n", err)
	}

	return nil
}

// AddVideo 新增影片（與 Python add_video 相容）
func (db *JSONDatabase) AddVideo(video *Video) error {
	code := video.GetCode()
	if code == "" {
		return ErrInvalidCode
	}

	db.mu.Lock()
	defer db.mu.Unlock()

	if !db.loaded {
		return ErrDatabaseNotLoaded
	}

	// 設定時間戳
	now := time.Now().UTC().Format(ISODateTimeFormat)
	video.CreatedAt = now
	video.UpdatedAt = now

	// 儲存影片
	db.root.Videos[code] = video

	// 寫入 journal
	entry, err := NewJournalEntry(OpAdd, TypeVideo, code, video)
	if err != nil {
		return err
	}

	if err := db.appendJournalEntry(entry); err != nil {
		return err
	}

	// 更新 dirty tracking
	db.dirtyVideos[code] = true
	db.journalSize++
	if err := db.saveIndex(); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: failed to save index: %v\n", err)
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

	// 寫入 journal（使用 Python 相容格式）
	entry, err := NewJournalEntry(OpDelete, TypeVideo, code, nil)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Warning: failed to create journal entry: %v\n", err)
	} else {
		if err := db.appendJournalEntry(entry); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: failed to write journal: %v\n", err)
		} else {
			// 更新 dirty tracking
			delete(db.dirtyVideos, code)
			db.journalSize++
			if err := db.saveIndex(); err != nil {
				fmt.Fprintf(os.Stderr, "Warning: failed to save index: %v\n", err)
			}
		}
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

	// 批次寫入 journal，同時更新 dirty tracking
	for code, video := range updates {
		if code == "" || video == nil {
			continue
		}
		if err := db.appendJournal("update", code, video); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: failed to write journal entry: %v\n", err)
		} else {
			db.dirtyVideos[code] = true
			db.journalSize++
		}
	}

	// 儲存索引
	if err := db.saveIndex(); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: failed to save index: %v\n", err)
	}

	return nil
}

// CompactJournal 合併 journal 到主資料庫（與 Python compact() 相容）
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

	// 重建空的 journal
	f, err := os.Create(db.journalFile)
	if err == nil {
		f.Close()
	}

	// 重設 dirty tracking
	db.dirtyVideos = make(map[string]bool)
	db.dirtyActresses = make(map[string]bool)
	db.dirtyLinks = make(map[string]bool)
	db.journalSize = 0
	db.journalCreatedAt = time.Now().UTC()

	// 儲存索引
	if err := db.saveIndex(); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: failed to save index after compact: %v\n", err)
	}

	return nil
}

// Compact 是 CompactJournal 的別名（與 Python 相容）
func (db *JSONDatabase) Compact() error {
	return db.CompactJournal()
}

// CompactIfNeeded 根據閾值自動判斷是否需要合併（與 Python compact_if_needed() 相容）
func (db *JSONDatabase) CompactIfNeeded() (bool, error) {
	db.mu.RLock()
	journalSize := db.journalSize
	journalAge := time.Since(db.journalCreatedAt).Seconds()
	db.mu.RUnlock()

	// 檢查大小閾值
	if journalSize >= JournalSizeThreshold {
		if err := db.CompactJournal(); err != nil {
			return false, err
		}
		return true, nil
	}

	// 檢查時間閾值
	if journalAge >= float64(JournalAgeThreshold) {
		if err := db.CompactJournal(); err != nil {
			return false, err
		}
		return true, nil
	}

	return false, nil
}

// NeedsCompact 檢查是否需要合併
func (db *JSONDatabase) NeedsCompact() bool {
	db.mu.RLock()
	defer db.mu.RUnlock()

	journalAge := time.Since(db.journalCreatedAt).Seconds()
	return db.journalSize >= JournalSizeThreshold || journalAge >= float64(JournalAgeThreshold)
}

// GetStats 取得資料庫統計資訊（與 Python get_stats() 相容）
func (db *JSONDatabase) GetStats() (map[string]any, error) {
	db.mu.RLock()
	defer db.mu.RUnlock()

	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}

	journalAge := time.Since(db.journalCreatedAt).Seconds()
	needsCompact := db.journalSize >= JournalSizeThreshold || journalAge >= float64(JournalAgeThreshold)

	stats := map[string]any{
		"video_count":          len(db.root.Videos),
		"actress_count":        len(db.root.Actresses),
		"link_count":           len(db.root.Links),
		"schema_version":       db.root.SchemaVersion,
		"created_at":           db.root.CreatedAt,
		"updated_at":           db.root.UpdatedAt,
		"journal_size":         db.journalSize,
		"journal_age_seconds":  journalAge,
		"dirty_videos":         len(db.dirtyVideos),
		"dirty_actresses":      len(db.dirtyActresses),
		"dirty_links":          len(db.dirtyLinks),
		"needs_compact":        needsCompact,
		"total_videos":         len(db.root.Videos),
	}

	return stats, nil
}

// GetStatsStruct 取得結構化統計資訊
func (db *JSONDatabase) GetStatsStruct() (*Stats, error) {
	db.mu.RLock()
	defer db.mu.RUnlock()

	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}

	journalAge := time.Since(db.journalCreatedAt).Seconds()
	needsCompact := db.journalSize >= JournalSizeThreshold || journalAge >= float64(JournalAgeThreshold)

	return &Stats{
		JournalSize:       db.journalSize,
		JournalAgeSeconds: journalAge,
		DirtyVideos:       len(db.dirtyVideos),
		DirtyActresses:    len(db.dirtyActresses),
		DirtyLinks:        len(db.dirtyLinks),
		NeedsCompact:      needsCompact,
		TotalVideos:       len(db.root.Videos),
		TotalActresses:    len(db.root.Actresses),
		TotalLinks:        len(db.root.Links),
	}, nil
}
