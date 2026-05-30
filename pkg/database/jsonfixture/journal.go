package jsonfixture

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"

	"actress-classifier/pkg/database"
	"actress-classifier/pkg/safefile"
)

const maxJournalLineSize = 1024 * 1024

// appendJournalEntry 附加 journal 記錄（與 Python IncrementalJSONDb 格式相容）
// 格式: {"op":"UPDATE","type":"video","id":"STARS-707","data":{...},"ts":"..."}
func (db *JSONDatabase) appendJournalEntry(entry *database.JournalEntry) error {
	// 序列化為 JSON Lines 格式
	data, err := json.Marshal(entry)
	if err != nil {
		return fmt.Errorf("failed to marshal journal entry: %w", err)
	}

	// 附加到 journal 檔案
	f, err := safefile.OpenFile(db.journalFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0600)
	if err != nil {
		return fmt.Errorf("failed to open journal file: %w", err)
	}
	defer f.Close()

	// 寫入一行 (JSON Lines 格式)
	if _, err := f.Write(data); err != nil {
		return fmt.Errorf("failed to write journal entry: %w", err)
	}
	if _, err := f.WriteString("\n"); err != nil {
		return fmt.Errorf("failed to write newline: %w", err)
	}

	// 確保資料寫入磁碟（防止斷電遺失 journal 記錄）
	if err := f.Sync(); err != nil {
		return fmt.Errorf("failed to sync journal file: %w", err)
	}

	return nil
}

// appendJournal 附加 journal 記錄（舊版相容介面）
func (db *JSONDatabase) appendJournal(operation, code string, video *database.VideoData) error {
	// 轉換為新格式
	var op string
	switch operation {
	case "update":
		op = database.OpUpdate
	case "delete":
		op = database.OpDelete
	case "add":
		op = database.OpAdd
	default:
		op = database.OpUpdate
	}

	entry, err := database.NewJournalEntry(op, database.TypeVideo, code, video)
	if err != nil {
		return err
	}

	return db.appendJournalEntry(entry)
}

// loadJournal 載入 journal 並套用變更
// 同時支援舊格式和新格式（Python 相容）
func (db *JSONDatabase) loadJournal() error {
	// 檢查 journal 是否存在
	if _, err := os.Stat(db.journalFile); os.IsNotExist(err) {
		return nil // journal 不存在，正常情況
	}

	f, err := safefile.OpenRead(db.journalFile)
	if err != nil {
		return fmt.Errorf("failed to open journal: %w", err)
	}
	defer f.Close()

	scanner := newJournalScanner(f)
	lineNum := 0

	for scanner.Scan() {
		lineNum++
		line := scanner.Text()

		if line == "" {
			continue // 跳過空行
		}

		// 嘗試解析為新格式（Python 相容）
		var entry database.JournalEntry
		if err := json.Unmarshal([]byte(line), &entry); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: failed to parse journal line %d: %v\n", lineNum, err)
			continue
		}

		// 根據格式套用變更
		if entry.Op != "" {
			// 新格式（Python 相容）
			db.applyJournalEntry(&entry)
		} else {
			// 嘗試舊格式
			db.applyLegacyJournalEntry([]byte(line))
		}
	}

	if err := scanner.Err(); err != nil {
		return fmt.Errorf("failed to read journal: %w", err)
	}

	return nil
}

// applyJournalEntry 套用新格式 journal 記錄
func (db *JSONDatabase) applyJournalEntry(entry *database.JournalEntry) {
	switch entry.Type {
	case database.TypeVideo:
		db.applyVideoJournalEntry(entry)
	case database.TypeActress:
		db.applyActressJournalEntry(entry)
	case database.TypeLink:
		// 未來擴展
	}
}

// applyVideoJournalEntry 套用影片 journal 記錄
func (db *JSONDatabase) applyVideoJournalEntry(entry *database.JournalEntry) {
	switch entry.Op {
	case database.OpAdd:
		db.applyVideoJournalAdd(entry)
	case database.OpUpdate:
		db.applyVideoJournalUpdate(entry)
	case database.OpDelete:
		db.applyVideoJournalDelete(entry.ID)
	}
}

// applyVideoUpdates 將更新套用到影片
// updates 可以是完整 VideoData 的 JSON 物件或部分欄位的 map
func (db *JSONDatabase) applyVideoUpdates(video *database.VideoData, updates map[string]any) {
	db.applyVideoFieldUpdates(video, updates)
}

// applyVideoFieldUpdates 委派給 pkg/database 內共用的 ApplyVideoFieldUpdates。
// 既存的 fixture 測試會直接呼叫此方法以驅動 handler map 各個 case。
func (db *JSONDatabase) applyVideoFieldUpdates(video *database.VideoData, updates map[string]any) {
	database.ApplyVideoFieldUpdates(video, updates)
}

func (db *JSONDatabase) applyVideoJournalAdd(entry *database.JournalEntry) {
	if entry.Data == nil {
		return
	}

	var video database.VideoData
	if err := json.Unmarshal(entry.Data, &video); err != nil {
		return
	}

	// 確保 code 正確
	if video.Code == "" {
		video.Code = entry.ID
	}
	db.root.Videos[entry.ID] = &video
	delete(db.deletedVideos, entry.ID)
}

func (db *JSONDatabase) applyVideoJournalUpdate(entry *database.JournalEntry) {
	if entry.Data == nil {
		return
	}

	// 取得現有影片或建立新的
	existing, exists := db.root.Videos[entry.ID]
	if !exists {
		existing = database.GetEmptyVideo()
		existing.Code = entry.ID
	}

	// 解析更新欄位
	var updates map[string]any
	if err := json.Unmarshal(entry.Data, &updates); err == nil {
		db.applyVideoFieldUpdates(existing, updates)
	}
	db.root.Videos[entry.ID] = existing
	delete(db.deletedVideos, entry.ID)
}

func (db *JSONDatabase) applyVideoJournalDelete(id string) {
	delete(db.root.Videos, id)
	db.deletedVideos[id] = true
}

func (db *JSONDatabase) applyActressJournalEntry(entry *database.JournalEntry) {
	switch entry.Op {
	case database.OpAdd, database.OpUpdate:
		db.applyActressJournalUpsert(entry)
	case database.OpDelete:
		db.applyActressJournalDelete(entry.ID)
	}
}

func (db *JSONDatabase) applyActressJournalUpsert(entry *database.JournalEntry) {
	if entry.Data == nil {
		return
	}

	var actress database.ActressData
	if err := json.Unmarshal(entry.Data, &actress); err != nil {
		return
	}
	if actress.ID == "" {
		actress.ID = entry.ID
	}
	db.root.Actresses[entry.ID] = &actress
}

func (db *JSONDatabase) applyActressJournalDelete(id string) {
	delete(db.root.Actresses, id)
}

// legacyJournalEntry 舊格式 journal 記錄
type legacyJournalEntry struct {
	Timestamp string              `json:"timestamp"`
	Operation string              `json:"operation"`
	Code      string              `json:"code"`
	Video     *database.VideoData `json:"video,omitempty"`
}

// applyLegacyJournalEntry 套用舊格式 journal 記錄
func (db *JSONDatabase) applyLegacyJournalEntry(data []byte) {
	var entry legacyJournalEntry
	if err := json.Unmarshal(data, &entry); err != nil {
		return
	}

	switch entry.Operation {
	case "update":
		if entry.Video != nil {
			db.root.Videos[entry.Code] = entry.Video
		}
	case "delete":
		delete(db.root.Videos, entry.Code)
	}
}

// GetJournalSize 取得 journal 檔案大小
func (db *JSONDatabase) GetJournalSize() (int64, error) {
	info, err := os.Stat(db.journalFile)
	if os.IsNotExist(err) {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}
	return info.Size(), nil
}

// GetJournalEntryCount 取得 journal 記錄數量
func (db *JSONDatabase) GetJournalEntryCount() (int, error) {
	if _, err := os.Stat(db.journalFile); os.IsNotExist(err) {
		return 0, nil
	}

	f, err := safefile.OpenRead(db.journalFile)
	if err != nil {
		return 0, err
	}
	defer f.Close()

	scanner := newJournalScanner(f)
	count := 0

	for scanner.Scan() {
		if scanner.Text() != "" {
			count++
		}
	}

	if err := scanner.Err(); err != nil {
		return 0, err
	}

	return count, nil
}

func newJournalScanner(r io.Reader) *bufio.Scanner {
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 64*1024), maxJournalLineSize)
	return scanner
}
