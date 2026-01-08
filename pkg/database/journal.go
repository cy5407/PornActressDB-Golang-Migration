package database

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"time"
)

// JournalEntry Journal 記錄項目
type JournalEntry struct {
	Timestamp string  `json:"timestamp"` // 時間戳
	Operation string  `json:"operation"` // 操作類型 (update, delete)
	Code      string  `json:"code"`      // 影片番號
	Video     *Video  `json:"video,omitempty"` // 影片資料 (delete 時為 nil)
}

// appendJournal 附加 journal 記錄
func (db *JSONDatabase) appendJournal(operation, code string, video *Video) error {
	entry := JournalEntry{
		Timestamp: time.Now().UTC().Format(ISODateTimeFormat),
		Operation: operation,
		Code:      code,
		Video:     video,
	}

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

	return nil
}

// loadJournal 載入 journal 並套用變更
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

		var entry JournalEntry
		if err := json.Unmarshal([]byte(line), &entry); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: failed to parse journal line %d: %v\n", lineNum, err)
			continue
		}

		// 套用變更
		switch entry.Operation {
		case "update":
			if entry.Video != nil {
				db.root.Videos[entry.Code] = entry.Video
			}
		case "delete":
			delete(db.root.Videos, entry.Code)
		default:
			fmt.Fprintf(os.Stderr, "Warning: unknown journal operation: %s\n", entry.Operation)
		}
	}

	if err := scanner.Err(); err != nil {
		return fmt.Errorf("failed to read journal: %w", err)
	}

	return nil
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
