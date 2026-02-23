package database

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
)

// appendJournalEntry 附加 journal 記錄（與 Python IncrementalJSONDB 格式相容）
// 格式: {"op":"UPDATE","type":"video","id":"STARS-707","data":{...},"ts":"..."}
func (db *JSONDatabase) appendJournalEntry(entry *JournalEntry) error {
	// 序列化為 JSON Lines 格式
	data, err := json.Marshal(entry)
	if err != nil {
		return fmt.Errorf("failed to marshal journal entry: %w", err)
	}

	// 附加到 journal 檔案
	f, err := os.OpenFile(db.journalFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
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

	f, err := os.Open(db.journalFile)
	if err != nil {
		return fmt.Errorf("failed to open journal: %w", err)
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
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
		// 未來擴展
	case TypeLink:
		// 未來擴展
	}
}

// applyVideoJournalEntry 套用影片 journal 記錄
func (db *JSONDatabase) applyVideoJournalEntry(entry *JournalEntry) {
	switch entry.Op {
	case OpAdd:
		if entry.Data != nil {
			var video VideoData
			if err := json.Unmarshal(entry.Data, &video); err == nil {
				// 確保 code 正確
				if video.Code == "" {
					video.Code = entry.ID
				}
				db.root.Videos[entry.ID] = &video
			}
		}
	case OpUpdate:
		if entry.Data != nil {
			// 取得現有影片或建立新的
			existing, exists := db.root.Videos[entry.ID]
			if !exists {
				existing = GetEmptyVideo()
				existing.Code = entry.ID
			}

			// 解析更新欄位
			var updates map[string]any
			if err := json.Unmarshal(entry.Data, &updates); err == nil {
				db.applyVideoUpdates(existing, updates)
			}
			db.root.Videos[entry.ID] = existing
		}
	case OpDelete:
		delete(db.root.Videos, entry.ID)
	}
}

// applyVideoUpdates 將更新套用到影片
func (db *JSONDatabase) applyVideoUpdates(video *VideoData, updates map[string]any) {
	for key, value := range updates {
		switch key {
		case "title":
			if v, ok := value.(string); ok {
				video.Title = v
			}
		case "studio":
			if v, ok := value.(string); ok {
				video.Studio = v
			}
		case "studio_code":
			if v, ok := value.(string); ok {
				video.StudioCode = v
			}
		case "release_date":
			if v, ok := value.(string); ok {
				video.ReleaseDate = v
			}
		case "url":
			if v, ok := value.(string); ok {
				video.URL = v
			}
		case "actresses":
			if v, ok := value.([]any); ok {
				actresses := make([]string, 0, len(v))
				for _, a := range v {
					if s, ok := a.(string); ok {
						actresses = append(actresses, s)
					}
				}
				video.Actresses = actresses
			}
		case "search_status":
			if v, ok := value.(string); ok {
				video.SearchStatus = v
			}
		case "last_search_date":
			if v, ok := value.(string); ok {
				video.LastSearchDate = v
			}
		case "original_filename":
			if v, ok := value.(string); ok {
				video.OriginalFilename = v
			}
		case "file_path":
			if v, ok := value.(string); ok {
				video.FilePath = v
			}
		case "search_method":
			if v, ok := value.(string); ok {
				video.SearchMethod = v
			}
		case "test_field":
			if v, ok := value.(string); ok {
				video.TestField = v
			}
		}
	}
	video.UpdatedAt = GetCurrentTimestamp()
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

	f, err := os.Open(db.journalFile)
	if err != nil {
		return 0, err
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
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
