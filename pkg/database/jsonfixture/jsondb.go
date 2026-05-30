// Package jsonfixture hosts the JSON-backed JSONDatabase implementation
// kept around as a fixture / import / export / legacy-tools helper.
//
// Runtime callers must use the SQLite-backed *database.SQLiteStore (see
// pkg/database/store_factory.go). This package only exists so the test
// fixtures, db migrate-from-json import path, and db export-json paths
// have a JSON-aware reference implementation to compare against.
//
// All shared types (VideoData / ActressData / JournalEntry / ...) live
// in pkg/database; this package imports them as `database.Foo`.
package jsonfixture

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"actress-classifier/pkg/database"
	"actress-classifier/pkg/safefile"
)

// ErrDatabaseNotLoaded is the jsonfixture-internal sentinel returned
// when a method is called before Load. Runtime callers should never see
// this — it only surfaces from the JSONDatabase fixture path.
var ErrDatabaseNotLoaded = errors.New("database not loaded")

const warnSaveIndex = "Warning: failed to save index: %v\n"

// JSONDatabaseRoot is an alias for database.DatabaseData kept for
// fixture callers that historically referenced the root type by name.
type JSONDatabaseRoot = database.DatabaseData

// JSONDatabase is the JSON-backed reference implementation. Fields stay
// unexported so the contract stays narrow; jsonfixture-internal tests
// can still drive corner cases because they live in the same package.
type JSONDatabase struct {
	mu          sync.RWMutex           // 讀寫鎖
	dataDir     string                 // 資料目錄
	dataFile    string                 // 資料檔案路徑
	journalFile string                 // Journal 檔案路徑
	indexFile   string                 // Index 檔案路徑
	root        *database.DatabaseData // 資料庫根結構
	loaded      bool                   // 是否已載入

	// Dirty tracking（與 Python 相容）
	dirtyVideos    map[string]bool
	dirtyActresses map[string]bool
	dirtyLinks     map[string]bool

	// deletedVideos 獨立追蹤在本 session（自上次 compact 後）被刪除的影片 code
	deletedVideos    map[string]bool
	journalSize      int
	journalCreatedAt time.Time
}

// NewJSONDatabase 建立新的 JSON 資料庫實例
func NewJSONDatabase(dataDir string) *JSONDatabase {
	return &JSONDatabase{
		dataDir:        dataDir,
		dataFile:       filepath.Join(dataDir, database.DataFileName),
		journalFile:    filepath.Join(dataDir, database.JournalFileName),
		indexFile:      filepath.Join(dataDir, database.IndexFileName),
		root:           nil,
		loaded:         false,
		dirtyVideos:    make(map[string]bool),
		dirtyActresses: make(map[string]bool),
		dirtyLinks:     make(map[string]bool),
		deletedVideos:  make(map[string]bool),
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
	if err := safefile.MkdirAll(db.dataDir, 0700); err != nil {
		return fmt.Errorf("failed to create data directory: %w", err)
	}

	// 檢查檔案是否存在
	if _, err := os.Stat(db.dataFile); os.IsNotExist(err) {
		// 檔案不存在，建立新的空資料庫
		db.root = database.NewDatabaseData()
		db.loaded = true
		db.journalCreatedAt = time.Now().UTC()
		return db.saveUnsafe() // 儲存初始檔案
	}

	// 讀取檔案
	data, err := safefile.ReadFile(db.dataFile)
	if err != nil {
		return fmt.Errorf("failed to read database file: %w", err)
	}

	// 解析 JSON
	var root database.DatabaseData
	if err := json.Unmarshal(data, &root); err != nil {
		return fmt.Errorf("failed to parse database JSON: %w", err)
	}

	// 確保 map 已初始化
	if root.Videos == nil {
		root.Videos = make(map[string]*database.VideoData)
	}
	if root.Actresses == nil {
		root.Actresses = make(map[string]*database.ActressData)
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
	data, err := safefile.ReadFile(db.indexFile)
	if err != nil {
		// Index 不存在是正常情況
		db.journalCreatedAt = time.Now().UTC()
		return
	}

	var index database.DirtyIndex
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

	index := database.DirtyIndex{
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

	return safefile.WriteFile(db.indexFile, data, 0600)
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
	db.root.UpdatedAt = time.Now().UTC().Format(database.ISODateTimeFormat)

	// 序列化 JSON
	data, err := json.MarshalIndent(db.root, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal database: %w", err)
	}

	// 寫入暫存檔
	tmpFile := db.dataFile + ".tmp"
	if err := safefile.WriteFile(tmpFile, data, 0600); err != nil {
		return fmt.Errorf("failed to write temp file: %w", err)
	}

	// 原子性替換
	if err := os.Rename(tmpFile, db.dataFile); err != nil {
		_ = os.Remove(tmpFile) // 清理暫存檔
		return fmt.Errorf("failed to replace database file: %w", err)
	}

	return nil
}

// GetVideo 取得影片資訊
func (db *JSONDatabase) GetVideo(code string) (*database.VideoData, error) {
	if code == "" {
		return nil, database.ErrInvalidCode
	}

	db.mu.RLock()
	defer db.mu.RUnlock()

	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}

	video, exists := db.root.Videos[code]
	if !exists {
		return nil, database.ErrNotFound
	}

	// 返回複本避免外部修改
	videoCopy := *video
	return &videoCopy, nil
}

// UpdateVideo 更新影片資訊
func (db *JSONDatabase) UpdateVideo(code string, video *database.VideoData) error {
	if code == "" {
		return database.ErrInvalidCode
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
	video.UpdatedAt = time.Now().UTC().Format(database.ISODateTimeFormat)

	// 判斷是新增還是更新
	_, exists := db.root.Videos[code]
	var op string
	if !exists {
		video.CreatedAt = video.UpdatedAt
		op = database.OpAdd
	} else {
		op = database.OpUpdate
	}

	// 確保 code 欄位正確
	video.Code = code

	// 儲存影片
	db.root.Videos[code] = video

	// 寫入 journal（使用 Python 相容格式）
	entry, err := database.NewJournalEntry(op, database.TypeVideo, code, video)
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
				fmt.Fprintf(os.Stderr, warnSaveIndex, err)
			}
		}
	}

	return nil
}

// UpdateVideoFields 更新影片的特定欄位（與 Python update_video 相容）
func (db *JSONDatabase) UpdateVideoFields(code string, updates map[string]any) error {
	if code == "" {
		return database.ErrInvalidCode
	}

	db.mu.Lock()
	defer db.mu.Unlock()

	if !db.loaded {
		return ErrDatabaseNotLoaded
	}

	// 取得現有影片
	video, exists := db.root.Videos[code]
	if !exists {
		return database.ErrNotFound
	}

	// 套用更新
	db.applyVideoUpdates(video, updates)

	// 寫入 journal（僅記錄更新的欄位，與 Python 相容）
	journalUpdates := copyVideoUpdatesForJournal(updates, video.UpdatedAt)
	entry, err := database.NewJournalEntry(database.OpUpdate, database.TypeVideo, code, journalUpdates)
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
		fmt.Fprintf(os.Stderr, warnSaveIndex, err)
	}

	return nil
}

func copyVideoUpdatesForJournal(updates map[string]any, updatedAt string) map[string]any {
	journalUpdates := make(map[string]any, len(updates)+1)
	for key, value := range updates {
		journalUpdates[key] = value
	}
	if _, exists := journalUpdates["updated_at"]; !exists {
		journalUpdates["updated_at"] = updatedAt
	}
	return journalUpdates
}

// AddVideo 新增影片（與 Python add_video 相容）
func (db *JSONDatabase) AddVideo(video *database.VideoData) error {
	code := video.GetCode()
	if code == "" {
		return database.ErrInvalidCode
	}

	db.mu.Lock()
	defer db.mu.Unlock()

	if !db.loaded {
		return ErrDatabaseNotLoaded
	}

	// 設定時間戳
	now := time.Now().UTC().Format(database.ISODateTimeFormat)
	video.CreatedAt = now
	video.UpdatedAt = now

	// 儲存影片
	db.root.Videos[code] = video

	// 寫入 journal
	entry, err := database.NewJournalEntry(database.OpAdd, database.TypeVideo, code, video)
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
		fmt.Fprintf(os.Stderr, warnSaveIndex, err)
	}

	return nil
}

// DeleteVideo 刪除影片
func (db *JSONDatabase) DeleteVideo(code string) error {
	if code == "" {
		return database.ErrInvalidCode
	}

	db.mu.Lock()
	defer db.mu.Unlock()

	if !db.loaded {
		return ErrDatabaseNotLoaded
	}

	if _, exists := db.root.Videos[code]; !exists {
		return database.ErrNotFound
	}

	delete(db.root.Videos, code)

	// 寫入 journal（使用 Python 相容格式）
	entry, err := database.NewJournalEntry(database.OpDelete, database.TypeVideo, code, nil)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Warning: failed to create journal entry: %v\n", err)
	} else {
		if err := db.appendJournalEntry(entry); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: failed to write journal: %v\n", err)
		} else {
			db.dirtyVideos[code] = true
			db.deletedVideos[code] = true
			db.journalSize++
			if err := db.saveIndex(); err != nil {
				fmt.Fprintf(os.Stderr, warnSaveIndex, err)
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

// GetAllVideos 取得所有影片的完整資料（RLock，journal 已於 Load 時合併）
func (db *JSONDatabase) GetAllVideos() ([]*database.VideoData, error) {
	db.mu.RLock()
	defer db.mu.RUnlock()

	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}

	videos := make([]*database.VideoData, 0, len(db.root.Videos))
	for _, v := range db.root.Videos {
		videos = append(videos, v)
	}
	return videos, nil
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
func (db *JSONDatabase) BatchUpdate(updates map[string]*database.VideoData) error {
	if len(updates) == 0 {
		return nil
	}

	db.mu.Lock()
	defer db.mu.Unlock()

	if !db.loaded {
		return ErrDatabaseNotLoaded
	}

	now := time.Now().UTC().Format(database.ISODateTimeFormat)
	db.applyBatchUpdateRecords(updates, now)
	db.appendBatchUpdateJournalEntries(updates)

	// 儲存索引
	if err := db.saveIndex(); err != nil {
		fmt.Fprintf(os.Stderr, warnSaveIndex, err)
	}

	return nil
}

func (db *JSONDatabase) applyBatchUpdateRecords(updates map[string]*database.VideoData, now string) {
	for code, video := range updates {
		if code == "" || video == nil {
			continue
		}

		video.UpdatedAt = now
		if _, exists := db.root.Videos[code]; !exists {
			video.CreatedAt = now
		}

		db.root.Videos[code] = video
	}
}

func (db *JSONDatabase) appendBatchUpdateJournalEntries(updates map[string]*database.VideoData) {
	for code, video := range updates {
		if code == "" || video == nil {
			continue
		}
		if err := db.appendJournal("update", code, video); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: failed to write journal entry: %v\n", err)
			continue
		}
		db.dirtyVideos[code] = true
		db.journalSize++
	}
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
	f, err := safefile.OpenFile(db.journalFile, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0600)
	if err == nil {
		_ = f.Close()
	}

	// 重設 dirty tracking
	db.dirtyVideos = make(map[string]bool)
	db.dirtyActresses = make(map[string]bool)
	db.dirtyLinks = make(map[string]bool)
	db.deletedVideos = make(map[string]bool)
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
	if journalSize >= database.JournalSizeThreshold {
		if err := db.CompactJournal(); err != nil {
			return false, err
		}
		return true, nil
	}

	// 檢查時間閾值
	if journalAge >= float64(database.JournalAgeThreshold) {
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
	return db.journalSize >= database.JournalSizeThreshold || journalAge >= float64(database.JournalAgeThreshold)
}

// GetStats 取得資料庫統計資訊（與 Python get_stats() 相容）
func (db *JSONDatabase) GetStats() (map[string]any, error) {
	db.mu.RLock()
	defer db.mu.RUnlock()

	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}

	journalAge := time.Since(db.journalCreatedAt).Seconds()
	needsCompact := db.journalSize >= database.JournalSizeThreshold || journalAge >= float64(database.JournalAgeThreshold)

	stats := map[string]any{
		"video_count":         len(db.root.Videos),
		"actress_count":       len(db.root.Actresses),
		"link_count":          len(db.root.Links),
		"schema_version":      db.root.SchemaVersion,
		"created_at":          db.root.CreatedAt,
		"updated_at":          db.root.UpdatedAt,
		"journal_size":        db.journalSize,
		"journal_age_seconds": journalAge,
		"dirty_videos":        len(db.dirtyVideos),
		"dirty_actresses":     len(db.dirtyActresses),
		"dirty_links":         len(db.dirtyLinks),
		"needs_compact":       needsCompact,
		"total_videos":        len(db.root.Videos),
	}

	return stats, nil
}

// GetStatsStruct 取得結構化統計資訊
func (db *JSONDatabase) GetStatsStruct() (*database.Stats, error) {
	db.mu.RLock()
	defer db.mu.RUnlock()

	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}

	journalAge := time.Since(db.journalCreatedAt).Seconds()
	needsCompact := db.journalSize >= database.JournalSizeThreshold || journalAge >= float64(database.JournalAgeThreshold)

	return &database.Stats{
		JournalSize:       db.journalSize,
		JournalAgeSeconds: journalAge,
		DirtyVideos:       len(db.dirtyVideos),
		DeletedVideos:     len(db.deletedVideos),
		DirtyActresses:    len(db.dirtyActresses),
		DirtyLinks:        len(db.dirtyLinks),
		NeedsCompact:      needsCompact,
		TotalVideos:       len(db.root.Videos),
		TotalActresses:    len(db.root.Actresses),
		TotalLinks:        len(db.root.Links),
	}, nil
}

// GetDeletedCodes 回傳本 session（自上次 compact 後）被刪除的影片 code 清單
func (db *JSONDatabase) GetDeletedCodes() ([]string, error) {
	db.mu.RLock()
	defer db.mu.RUnlock()

	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}

	codes := make([]string, 0, len(db.deletedVideos))
	for code := range db.deletedVideos {
		codes = append(codes, code)
	}
	return codes, nil
}

// GetActress 取得女優資訊
func (db *JSONDatabase) GetActress(id string) (*database.ActressData, error) {
	if id == "" {
		return nil, database.ErrInvalidCode
	}
	db.mu.RLock()
	defer db.mu.RUnlock()
	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}
	actress, exists := db.root.Actresses[id]
	if !exists {
		return nil, database.ErrNotFound
	}
	c := *actress
	return &c, nil
}

// UpsertActress 新增或更新女優資訊（與 Python add_or_update_actress 相容）
func (db *JSONDatabase) UpsertActress(actress *database.ActressData) error {
	if actress == nil || actress.ID == "" {
		return errors.New("actress id cannot be empty")
	}
	db.mu.Lock()
	defer db.mu.Unlock()
	if !db.loaded {
		return ErrDatabaseNotLoaded
	}
	now := time.Now().UTC().Format(database.ISODateTimeFormat)
	actress.UpdatedAt = now
	isNew := false
	if _, exists := db.root.Actresses[actress.ID]; !exists {
		actress.CreatedAt = now
		isNew = true
	}
	db.root.Actresses[actress.ID] = actress
	op := database.OpUpdate
	if isNew {
		op = database.OpAdd
	}
	entry, err := database.NewJournalEntry(op, database.TypeActress, actress.ID, actress)
	if err == nil {
		if db.appendJournalEntry(entry) == nil {
			db.dirtyActresses[actress.ID] = true
			db.journalSize++
			_ = db.saveIndex() //nolint:errcheck
		}
	}
	return nil
}

// DeleteActress 刪除女優
func (db *JSONDatabase) DeleteActress(id string) error {
	if id == "" {
		return database.ErrInvalidCode
	}
	db.mu.Lock()
	defer db.mu.Unlock()
	if !db.loaded {
		return ErrDatabaseNotLoaded
	}
	if _, exists := db.root.Actresses[id]; !exists {
		return database.ErrNotFound
	}
	delete(db.root.Actresses, id)
	entry, err := database.NewJournalEntry(database.OpDelete, database.TypeActress, id, nil)
	if err == nil {
		if db.appendJournalEntry(entry) == nil {
			db.dirtyActresses[id] = true
			db.journalSize++
			_ = db.saveIndex() //nolint:errcheck
		}
	}
	return nil
}

// ListActresses 列出所有女優 ID
func (db *JSONDatabase) ListActresses() ([]string, error) {
	db.mu.RLock()
	defer db.mu.RUnlock()
	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}
	ids := make([]string, 0, len(db.root.Actresses))
	for id := range db.root.Actresses {
		ids = append(ids, id)
	}
	return ids, nil
}

// MergeFromFile 從 JSON 檔案合併資料到目前資料庫
func (db *JSONDatabase) MergeFromFile(sourceFile string, overwrite bool) (*database.MergeStats, error) {
	if strings.TrimSpace(sourceFile) == "" {
		return nil, errors.New("source file path cannot be empty")
	}

	sourceRoot, err := database.LoadMergeSourceData(sourceFile)
	if err != nil {
		return nil, err
	}

	db.mu.Lock()
	defer db.mu.Unlock()

	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}

	if sourceRoot.Videos == nil {
		sourceRoot.Videos = make(map[string]*database.VideoData)
	}
	if sourceRoot.Actresses == nil {
		sourceRoot.Actresses = make(map[string]*database.ActressData)
	}
	if sourceRoot.Links == nil {
		sourceRoot.Links = []database.VideoActressLink{}
	}

	stats := &database.MergeStats{}
	now := time.Now().UTC().Format(database.ISODateTimeFormat)

	for mapCode, video := range sourceRoot.Videos {
		code, videoCopy, ok := database.PrepareVideoForMerge(mapCode, video, now)
		if !ok {
			continue
		}
		db.mergeVideoRecord(code, videoCopy, overwrite, now, stats)
	}

	for id, actress := range sourceRoot.Actresses {
		db.mergeActressRecord(id, actress, overwrite, now, stats)
	}

	db.mergeLinkRecords(sourceRoot.Links, stats)
	db.finalizeMerge(now, stats)

	if err := db.saveIndex(); err != nil {
		fmt.Fprintf(os.Stderr, warnSaveIndex, err)
	}

	return stats, nil
}

func (db *JSONDatabase) mergeVideoRecord(code string, video *database.VideoData, overwrite bool, now string, stats *database.MergeStats) {
	if existing, exists := db.root.Videos[code]; exists {
		if !overwrite {
			stats.VideosSkipped++
			return
		}
		video.CreatedAt = existing.CreatedAt
		db.root.Videos[code] = video
		stats.VideosUpdated++
	} else {
		if video.CreatedAt == "" {
			video.CreatedAt = now
		}
		db.root.Videos[code] = video
		stats.VideosAdded++
	}

	db.dirtyVideos[code] = true
}

func (db *JSONDatabase) mergeActressRecord(id string, actress *database.ActressData, overwrite bool, now string, stats *database.MergeStats) {
	if actress == nil {
		return
	}

	id = strings.TrimSpace(id)
	if id == "" {
		return
	}

	actressCopy := *actress
	actressCopy.ID = id
	actressCopy.UpdatedAt = now

	if existing, exists := db.root.Actresses[id]; exists {
		if !overwrite {
			return
		}
		actressCopy.CreatedAt = existing.CreatedAt
		db.root.Actresses[id] = &actressCopy
		stats.ActressesUpdated++
	} else {
		if actressCopy.CreatedAt == "" {
			actressCopy.CreatedAt = now
		}
		db.root.Actresses[id] = &actressCopy
		stats.ActressesAdded++
	}

	db.dirtyActresses[id] = true
}

func (db *JSONDatabase) mergeLinkRecords(links []database.VideoActressLink, stats *database.MergeStats) {
	linkSet := make(map[string]bool, len(db.root.Links)+len(links))
	for _, link := range db.root.Links {
		linkSet[mergeLinkKey(link)] = true
	}

	for _, link := range links {
		key := mergeLinkKey(link)
		if linkSet[key] {
			continue
		}
		db.root.Links = append(db.root.Links, link)
		linkSet[key] = true
		stats.LinksAdded++
	}
}

func mergeLinkKey(link database.VideoActressLink) string {
	return link.VideoCode + "|" + link.ActressID + "|" + link.RoleType + "|" + link.Timestamp
}

func (db *JSONDatabase) finalizeMerge(now string, stats *database.MergeStats) {
	db.root.UpdatedAt = now
	db.journalSize += stats.VideosAdded + stats.VideosUpdated + stats.ActressesAdded + stats.ActressesUpdated + stats.LinksAdded
}

// GetActressStats 取得女優統計資訊（影片數排序）
func (db *JSONDatabase) GetActressStats() ([]map[string]any, error) {
	db.mu.RLock()
	defer db.mu.RUnlock()
	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}

	actressCounts := make(map[string]int)
	for _, video := range db.root.Videos {
		if video == nil {
			continue
		}
		for _, actressName := range video.Actresses {
			actressCounts[actressName]++
		}
	}

	results := make([]map[string]any, 0, len(actressCounts))
	for name, count := range actressCounts {
		results = append(results, map[string]any{
			"actress_name": name,
			"video_count":  count,
		})
	}

	sort.Slice(results, func(i, j int) bool {
		vi, _ := results[i]["video_count"].(int) //nolint:errcheck
		vj, _ := results[j]["video_count"].(int) //nolint:errcheck
		return vi > vj
	})

	return results, nil
}

// BackupCreate 建立備份，回傳備份檔案路徑
func (db *JSONDatabase) BackupCreate() (string, error) {
	backupDir := filepath.Join(db.dataDir, "backup")
	if err := safefile.MkdirAll(backupDir, 0700); err != nil {
		return "", fmt.Errorf("無法建立備份目錄: %w", err)
	}

	timestamp := time.Now().Format("2006-01-02_15-04-05")
	backupPath := filepath.Join(backupDir, "backup_"+timestamp+".json")

	content, err := safefile.ReadFile(db.dataFile)
	if err != nil {
		return "", fmt.Errorf("無法讀取資料檔案: %w", err)
	}

	if err := safefile.WriteFile(backupPath, content, 0600); err != nil {
		return "", fmt.Errorf("無法寫入備份檔案: %w", err)
	}

	return backupPath, nil
}

// BackupRestore 從備份還原資料庫
func (db *JSONDatabase) BackupRestore(backupPath string) error {
	content, err := safefile.ReadFile(backupPath)
	if err != nil {
		return fmt.Errorf("備份檔案不存在或無法讀取: %w", err)
	}

	// 驗證 JSON 格式
	var temp any
	if err := json.Unmarshal(content, &temp); err != nil {
		return fmt.Errorf("備份檔案 JSON 格式無效: %w", err)
	}

	// 在寫鎖下覆寫 data.json
	db.mu.Lock()
	if err := restoreBackupDataFile(db.dataFile, content, db.journalFile, db.indexFile); err != nil {
		db.mu.Unlock()
		return err
	}
	db.dirtyVideos = make(map[string]bool)
	db.dirtyActresses = make(map[string]bool)
	db.dirtyLinks = make(map[string]bool)
	db.deletedVideos = make(map[string]bool)
	db.journalSize = 0
	db.loaded = false
	db.mu.Unlock()

	// 重新載入（Load 自行取鎖）
	return db.Load(context.Background())
}

func restoreBackupDataFile(dataFile string, content []byte, sidecarPaths ...string) error {
	tempPath := dataFile + ".restore.tmp"
	backupPath := dataFile + ".restore.bak"

	if err := os.Remove(tempPath); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("清理暫存還原檔案失敗: %w", err)
	}
	if err := os.Remove(backupPath); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("清理舊還原備份檔案失敗: %w", err)
	}

	if err := safefile.WriteFile(tempPath, content, 0600); err != nil {
		return fmt.Errorf("寫入還原暫存檔失敗: %w", err)
	}
	if err := os.Rename(dataFile, backupPath); err != nil {
		_ = os.Remove(tempPath)
		return fmt.Errorf("備份現有資料檔失敗: %w", err)
	}
	if err := os.Rename(tempPath, dataFile); err != nil {
		_ = os.Remove(tempPath)
		_ = os.Rename(backupPath, dataFile) //nolint:errcheck
		return fmt.Errorf("切換還原資料檔失敗: %w", err)
	}
	if err := clearBackupRestoreSidecars(sidecarPaths...); err != nil {
		if rollbackErr := rollbackRestoredDataFile(dataFile, backupPath); rollbackErr != nil {
			return fmt.Errorf("清理還原附屬檔案失敗: %w；回復原資料檔也失敗: %v", err, rollbackErr)
		}
		return err
	}
	if err := os.Remove(backupPath); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("清理舊資料備份失敗: %w", err)
	}
	return nil
}

func rollbackRestoredDataFile(dataFile, backupPath string) error {
	if err := os.Remove(dataFile); err != nil && !os.IsNotExist(err) {
		return err
	}
	return os.Rename(backupPath, dataFile)
}

func clearBackupRestoreSidecars(paths ...string) error {
	for _, path := range paths {
		if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
			return fmt.Errorf("清理還原附屬檔案失敗: %w", err)
		}
	}
	return nil
}

// BackupList 列出備份檔案路徑（按名稱排序）
func (db *JSONDatabase) BackupList() ([]string, error) {
	backupDir := filepath.Join(db.dataDir, "backup")
	entries, err := os.ReadDir(backupDir)
	if err != nil {
		if os.IsNotExist(err) {
			return []string{}, nil
		}
		return nil, fmt.Errorf("無法讀取備份目錄: %w", err)
	}

	var paths []string
	for _, e := range entries {
		if !e.IsDir() && database.IsBackupJSONFileName(e.Name()) {
			paths = append(paths, filepath.Join(backupDir, e.Name()))
		}
	}
	sort.Strings(paths)
	return paths, nil
}

// BackupCleanup 清理過期與超量備份，回傳刪除數量
func (db *JSONDatabase) BackupCleanup(days, maxCount int) (int, error) {
	backupDir := filepath.Join(db.dataDir, "backup")
	entries, err := os.ReadDir(backupDir)
	if err != nil {
		if os.IsNotExist(err) {
			return 0, nil
		}
		return 0, fmt.Errorf("無法讀取備份目錄: %w", err)
	}

	cutoff := time.Now().AddDate(0, 0, -days)
	deleted := database.DeleteExpiredBackups(backupDir, entries, cutoff)

	// 重新讀取剩餘備份，若超過 maxCount 則刪除最舊的
	remaining, err := db.BackupList()
	if err != nil {
		return deleted, nil //nolint:nilerr // best-effort tail trim
	}
	deleted += database.RemoveOldestBackups(remaining, maxCount)

	return deleted, nil
}

// GetStudioStats 取得片商統計資訊（影片數排序）
func (db *JSONDatabase) GetStudioStats() ([]map[string]any, error) {
	db.mu.RLock()
	defer db.mu.RUnlock()
	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}

	studioCounts := make(map[string]int)
	for _, video := range db.root.Videos {
		if video == nil {
			continue
		}
		studio := video.Studio
		if studio == "" {
			studio = "UNKNOWN"
		}
		studioCounts[studio]++
	}

	results := make([]map[string]any, 0, len(studioCounts))
	for studio, count := range studioCounts {
		results = append(results, map[string]any{
			"studio":      studio,
			"video_count": count,
		})
	}

	sort.Slice(results, func(i, j int) bool {
		vi, _ := results[i]["video_count"].(int) //nolint:errcheck
		vj, _ := results[j]["video_count"].(int) //nolint:errcheck
		return vi > vj
	})

	return results, nil
}

// GetActressPrimaryStudio 統計 DB 中女優出現最多的片商名稱。
// actressName 為空或無任何有效 studio 記錄時返回空字串。
// 同票數時取字典序較小的片商名。
func (db *JSONDatabase) GetActressPrimaryStudio(actressName string) string {
	if actressName == "" {
		return ""
	}
	db.mu.RLock()
	defer db.mu.RUnlock()
	if !db.loaded {
		return ""
	}

	studioCounts := map[string]int{}
	for _, video := range db.root.Videos {
		if shouldCountActressStudio(video, actressName) {
			studioCounts[video.Studio]++
		}
	}
	return database.SelectPrimaryStudio(studioCounts)
}

func shouldCountActressStudio(video *database.VideoData, actressName string) bool {
	if video == nil || video.Studio == "" || video.Studio == "UNKNOWN" {
		return false
	}
	for _, actress := range video.Actresses {
		if actress == actressName {
			return true
		}
	}
	return false
}
