package database

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"

	"actress-classifier/pkg/safefile"
)

const maxJournalLineSize = 1024 * 1024

// appendJournalEntry 附加 journal 記錄（與 Python IncrementalJSONDB 格式相容）
// 格式: {"op":"UPDATE","type":"video","id":"STARS-707","data":{...},"ts":"..."}
func (db *JSONDatabase) appendJournalEntry(entry *JournalEntry) error {
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
func (db *JSONDatabase) appendJournal(operation, code string, video *Video) error {
	// 轉換為新格式
	var op string
	switch operation {
	case "update":
		op = OpUpdate
	case "delete":
		op = OpDelete
	case "add":
		op = OpAdd
	default:
		op = OpUpdate
	}

	entry, err := NewJournalEntry(op, TypeVideo, code, video)
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
		var entry JournalEntry
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
func (db *JSONDatabase) applyJournalEntry(entry *JournalEntry) {
	switch entry.Type {
	case TypeVideo:
		db.applyVideoJournalEntry(entry)
	case TypeActress:
		db.applyActressJournalEntry(entry)
	case TypeLink:
		// 未來擴展
	}
}

// applyVideoJournalEntry 套用影片 journal 記錄
func (db *JSONDatabase) applyVideoJournalEntry(entry *JournalEntry) {
	switch entry.Op {
	case OpAdd:
		db.applyVideoJournalAdd(entry)
	case OpUpdate:
		db.applyVideoJournalUpdate(entry)
	case OpDelete:
		db.applyVideoJournalDelete(entry.ID)
	}
}

// applyVideoUpdates 將更新套用到影片
// updates 可以是完整 VideoData 的 JSON 物件或部分欄位的 map
func (db *JSONDatabase) applyVideoUpdates(video *VideoData, updates map[string]any) {
	db.applyVideoFieldUpdates(video, updates)
}

func (db *JSONDatabase) applyVideoFieldUpdates(video *VideoData, updates map[string]any) {
	hasUpdatedAt := false // 追蹤是否有明確提供 updated_at，避免不必要的時間覆蓋

	for key, value := range updates {
		if key == "updated_at" {
			if v, ok := value.(string); ok {
				video.UpdatedAt = v
				hasUpdatedAt = true // 已明確提供，稍後不再覆蓋
			}
			continue
		}

		if handler, ok := videoFieldUpdateHandlers[key]; ok {
			handler(video, value)
		}
	}

	// 若更新資料中未明確提供 updated_at（例如部分欄位更新），才以目前時間填入
	if !hasUpdatedAt {
		video.UpdatedAt = GetCurrentTimestamp()
	}
}

var videoFieldUpdateHandlers = map[string]func(*VideoData, any){
	"id": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.ID = v
		}
	},
	"code": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.Code = v
		}
	},
	"created_at": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.CreatedAt = v
		}
	},
	"metadata": func(video *VideoData, value any) {
		if m, ok := value.(map[string]any); ok {
			if src, ok := m["source"].(string); ok {
				video.Metadata.Source = src
			}
			if conf, ok := m["confidence"].(float64); ok {
				video.Metadata.Confidence = conf
			}
		}
	},
	"title": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.Title = v
		}
	},
	"studio": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.Studio = v
		}
	},
	"studio_code": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.StudioCode = v
		}
	},
	"release_date": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.ReleaseDate = v
		}
	},
	"url": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.URL = v
		}
	},
	"actresses": func(video *VideoData, value any) {
		if v, ok := value.([]any); ok {
			actresses := make([]string, 0, len(v))
			for _, a := range v {
				if s, ok := a.(string); ok {
					actresses = append(actresses, s)
				}
			}
			video.Actresses = actresses
		}
	},
	"search_status": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.SearchStatus = v
		}
	},
	"last_search_date": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.LastSearchDate = v
		}
	},
	"avwiki_actress_status": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.AVWikiActressStatus = v
		}
	},
	"avwiki_last_search_date": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.AVWikiLastSearchDate = v
		}
	},
	"javdb_actress_status": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.JAVDBActressStatus = v
		}
	},
	"javdb_last_search_date": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.JAVDBLastSearchDate = v
		}
	},
	"original_filename": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.OriginalFilename = v
		}
	},
	"file_path": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.FilePath = v
		}
	},
	"search_method": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.SearchMethod = v
		}
	},
	"error": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.Error = v
		}
	},
	"error_kind": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.ErrorKind = v
		}
	},
}

func (db *JSONDatabase) applyVideoJournalAdd(entry *JournalEntry) {
	if entry.Data == nil {
		return
	}

	var video VideoData
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

func (db *JSONDatabase) applyVideoJournalUpdate(entry *JournalEntry) {
	if entry.Data == nil {
		return
	}

	// 取得現有影片或建立新的
	existing, exists := db.root.Videos[entry.ID]
	if !exists {
		existing = GetEmptyVideo()
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

func (db *JSONDatabase) applyActressJournalEntry(entry *JournalEntry) {
	switch entry.Op {
	case OpAdd, OpUpdate:
		db.applyActressJournalUpsert(entry)
	case OpDelete:
		db.applyActressJournalDelete(entry.ID)
	}
}

func (db *JSONDatabase) applyActressJournalUpsert(entry *JournalEntry) {
	if entry.Data == nil {
		return
	}

	var actress ActressData
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
	Timestamp string     `json:"timestamp"`
	Operation string     `json:"operation"`
	Code      string     `json:"code"`
	Video     *VideoData `json:"video,omitempty"`
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
