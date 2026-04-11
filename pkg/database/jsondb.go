package database

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

	"actress-classifier/pkg/safefile"
)

var (
	// ErrNotFound 資料不存在錯誤
	ErrNotFound = errors.New("video not found")
	// ErrInvalidCode 無效番號錯誤
	ErrInvalidCode = errors.New("invalid video code")
	// ErrDatabaseNotLoaded 資料庫未載入錯誤
	ErrDatabaseNotLoaded = errors.New("database not loaded")
)

const warnSaveIndex = "Warning: failed to save index: %v\n"

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
	//
	// dirtyVideos 記錄所有在 journal 中有待 compact 操作的影片 code，
	// 無論操作類型為 ADD、UPDATE 或 DELETE，均統一標記為 dirty。
	// 這與 Python IncrementalJSONDB 的行為完全一致。
	//
	// 重要語義：
	//   - dirtyVideos 中的 code 不代表影片「存在」，DELETE 後仍會留在其中
	//   - 呼叫方若需區分操作類型，應查閱 journal 檔案或使用 deletedVideos
	//   - compact 後 dirtyVideos 會被清空（journal 已合併到主資料庫）
	dirtyVideos    map[string]bool
	dirtyActresses map[string]bool
	dirtyLinks     map[string]bool

	// deletedVideos 獨立追蹤在本 session（自上次 compact 後）被刪除的影片 code
	// 用途：讓呼叫方無需解析 journal 即可查詢哪些影片已被刪除
	// 注意：compact 後此 set 會被清空
	deletedVideos    map[string]bool
	journalSize      int
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
		db.root = NewDatabaseData()
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
	data, err := safefile.ReadFile(db.indexFile)
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
	db.root.UpdatedAt = time.Now().UTC().Format(ISODateTimeFormat)

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
				fmt.Fprintf(os.Stderr, warnSaveIndex, err)
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
	journalUpdates := copyVideoUpdatesForJournal(updates, video.UpdatedAt)
	entry, err := NewJournalEntry(OpUpdate, TypeVideo, code, journalUpdates)
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
		fmt.Fprintf(os.Stderr, warnSaveIndex, err)
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
			// 更新 dirty tracking：保留 code 在 dirty set 中，
			// 表示 journal 仍有一筆待 compact 的 DELETE 操作，
			// 與 ADD/UPDATE 行為語義一致（compact 前都應視為 dirty）
			db.dirtyVideos[code] = true
			// 同步記錄到 deletedVideos，讓呼叫方可區分「已刪除」與「已修改」
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
func (db *JSONDatabase) GetAllVideos() ([]*VideoData, error) {
	db.mu.RLock()
	defer db.mu.RUnlock()

	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}

	videos := make([]*VideoData, 0, len(db.root.Videos))
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
	db.applyBatchUpdateRecords(updates, now)
	db.appendBatchUpdateJournalEntries(updates)

	// 儲存索引
	if err := db.saveIndex(); err != nil {
		fmt.Fprintf(os.Stderr, warnSaveIndex, err)
	}

	return nil
}

func (db *JSONDatabase) applyBatchUpdateRecords(updates map[string]*Video, now string) {
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

func (db *JSONDatabase) appendBatchUpdateJournalEntries(updates map[string]*Video) {
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

	// 重設 dirty tracking（compact 後 journal 已合併，所有 dirty/deleted 記錄清空）
	db.dirtyVideos = make(map[string]bool)
	db.dirtyActresses = make(map[string]bool)
	db.dirtyLinks = make(map[string]bool)
	db.deletedVideos = make(map[string]bool) // compact 後刪除追蹤也一併清空
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
		DirtyVideos:       len(db.dirtyVideos),   // ADD + UPDATE + DELETE 的合計
		DeletedVideos:     len(db.deletedVideos), // 僅 DELETE 操作
		DirtyActresses:    len(db.dirtyActresses),
		DirtyLinks:        len(db.dirtyLinks),
		NeedsCompact:      needsCompact,
		TotalVideos:       len(db.root.Videos),
		TotalActresses:    len(db.root.Actresses),
		TotalLinks:        len(db.root.Links),
	}, nil
}

// GetDeletedCodes 回傳本 session（自上次 compact 後）被刪除的影片 code 清單
// 讓呼叫方無需解析 journal 即可查詢哪些影片已被刪除
// 注意：compact 後此清單會被清空
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
func (db *JSONDatabase) GetActress(id string) (*ActressData, error) {
	if id == "" {
		return nil, ErrInvalidCode
	}
	db.mu.RLock()
	defer db.mu.RUnlock()
	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}
	actress, exists := db.root.Actresses[id]
	if !exists {
		return nil, ErrNotFound
	}
	copy := *actress
	return &copy, nil
}

// UpsertActress 新增或更新女優資訊（與 Python add_or_update_actress 相容）
func (db *JSONDatabase) UpsertActress(actress *ActressData) error {
	if actress == nil || actress.ID == "" {
		return errors.New("actress id cannot be empty")
	}
	db.mu.Lock()
	defer db.mu.Unlock()
	if !db.loaded {
		return ErrDatabaseNotLoaded
	}
	now := time.Now().UTC().Format(ISODateTimeFormat)
	actress.UpdatedAt = now
	isNew := false
	if _, exists := db.root.Actresses[actress.ID]; !exists {
		actress.CreatedAt = now
		isNew = true
	}
	db.root.Actresses[actress.ID] = actress
	op := OpUpdate
	if isNew {
		op = OpAdd
	}
	entry, err := NewJournalEntry(op, TypeActress, actress.ID, actress)
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
		return ErrInvalidCode
	}
	db.mu.Lock()
	defer db.mu.Unlock()
	if !db.loaded {
		return ErrDatabaseNotLoaded
	}
	if _, exists := db.root.Actresses[id]; !exists {
		return ErrNotFound
	}
	delete(db.root.Actresses, id)
	entry, err := NewJournalEntry(OpDelete, TypeActress, id, nil)
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
func (db *JSONDatabase) MergeFromFile(sourceFile string, overwrite bool) (*MergeStats, error) {
	if strings.TrimSpace(sourceFile) == "" {
		return nil, errors.New("source file path cannot be empty")
	}

	sourceRoot, err := loadMergeSourceData(sourceFile)
	if err != nil {
		return nil, err
	}

	db.mu.Lock()
	defer db.mu.Unlock()

	if !db.loaded {
		return nil, ErrDatabaseNotLoaded
	}

	if sourceRoot.Videos == nil {
		sourceRoot.Videos = make(map[string]*VideoData)
	}
	if sourceRoot.Actresses == nil {
		sourceRoot.Actresses = make(map[string]*ActressData)
	}
	if sourceRoot.Links == nil {
		sourceRoot.Links = []VideoActressLink{}
	}

	stats := &MergeStats{}
	now := time.Now().UTC().Format(ISODateTimeFormat)

	for mapCode, video := range sourceRoot.Videos {
		code, videoCopy, ok := prepareVideoForMerge(mapCode, video, now)
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

func loadMergeSourceData(sourceFile string) (*DatabaseData, error) {
	absPath, err := resolveMergeSourcePath(sourceFile)
	if err != nil {
		return nil, err
	}

	sourceData, err := safefile.ReadFile(absPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read source file: %w", err)
	}

	var sourceRoot DatabaseData
	if err := json.Unmarshal(sourceData, &sourceRoot); err != nil {
		return nil, fmt.Errorf("failed to parse source JSON: %w", err)
	}

	normalizeMergeSourceData(&sourceRoot)
	return &sourceRoot, nil
}

func resolveMergeSourcePath(sourceFile string) (string, error) {
	cleanedPath := filepath.Clean(sourceFile)
	absPath, err := filepath.Abs(cleanedPath)
	if err != nil {
		return "", fmt.Errorf("invalid source file path: %w", err)
	}
	if filepath.Clean(absPath) != absPath {
		return "", fmt.Errorf("suspicious source file path detected: %s", sourceFile)
	}
	return absPath, nil
}

func normalizeMergeSourceData(sourceRoot *DatabaseData) {
	if sourceRoot.Videos == nil {
		sourceRoot.Videos = make(map[string]*VideoData)
	}
	if sourceRoot.Actresses == nil {
		sourceRoot.Actresses = make(map[string]*ActressData)
	}
	if sourceRoot.Links == nil {
		sourceRoot.Links = []VideoActressLink{}
	}
}

func prepareVideoForMerge(mapCode string, video *VideoData, now string) (string, *VideoData, bool) {
	if video == nil {
		return "", nil, false
	}

	code := strings.TrimSpace(video.GetCode())
	if code == "" {
		code = strings.TrimSpace(mapCode)
	}
	if code == "" {
		return "", nil, false
	}

	videoCopy := *video
	videoCopy.Code = code
	if videoCopy.Code == "" && videoCopy.ID != "" {
		videoCopy.Code = videoCopy.ID
	}
	if videoCopy.Code != "" {
		videoCopy.ID = ""
	}
	videoCopy.UpdatedAt = now
	return code, &videoCopy, true
}

func (db *JSONDatabase) mergeVideoRecord(code string, video *VideoData, overwrite bool, now string, stats *MergeStats) {
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

func (db *JSONDatabase) mergeActressRecord(id string, actress *ActressData, overwrite bool, now string, stats *MergeStats) {
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

func (db *JSONDatabase) mergeLinkRecords(links []VideoActressLink, stats *MergeStats) {
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

func mergeLinkKey(link VideoActressLink) string {
	return link.VideoCode + "|" + link.ActressID + "|" + link.RoleType + "|" + link.Timestamp
}

func (db *JSONDatabase) finalizeMerge(now string, stats *MergeStats) {
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
		if !e.IsDir() && isBackupJSONFileName(e.Name()) {
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
	deleted := deleteExpiredBackups(backupDir, entries, cutoff)

	// 重新讀取剩餘備份，若超過 maxCount 則刪除最舊的
	remaining, err := db.BackupList()
	if err != nil {
		return deleted, nil
	}
	deleted += removeOldestBackups(remaining, maxCount)

	return deleted, nil
}

func isBackupJSONFileName(name string) bool {
	return strings.HasPrefix(name, "backup_") && strings.HasSuffix(name, ".json")
}

func deleteExpiredBackups(backupDir string, entries []os.DirEntry, cutoff time.Time) int {
	deleted := 0
	for _, entry := range entries {
		name := entry.Name()
		if entry.IsDir() || !isBackupJSONFileName(name) {
			continue
		}
		backupDate, ok := parseBackupDate(name)
		if !ok || !backupDate.Before(cutoff) {
			continue
		}
		if os.Remove(filepath.Join(backupDir, name)) == nil {
			deleted++
		}
	}
	return deleted
}

func parseBackupDate(name string) (time.Time, bool) {
	stem := strings.TrimSuffix(strings.TrimPrefix(name, "backup_"), ".json")
	parts := strings.SplitN(stem, "_", 2)
	if len(parts) == 0 {
		return time.Time{}, false
	}
	backupDate, err := time.Parse("2006-01-02", parts[0])
	if err != nil {
		return time.Time{}, false
	}
	return backupDate, true
}

func removeOldestBackups(paths []string, maxCount int) int {
	deleted := 0
	for len(paths) > maxCount {
		if os.Remove(paths[0]) == nil {
			deleted++
		}
		paths = paths[1:]
	}
	return deleted
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
	return selectPrimaryStudio(studioCounts)
}

func shouldCountActressStudio(video *VideoData, actressName string) bool {
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

func selectPrimaryStudio(studioCounts map[string]int) string {
	if len(studioCounts) == 0 {
		return ""
	}
	maxStudio, maxCount := "", 0
	for studio, count := range studioCounts {
		if count > maxCount || (count == maxCount && studio < maxStudio) {
			maxStudio, maxCount = studio, count
		}
	}
	return maxStudio
}
