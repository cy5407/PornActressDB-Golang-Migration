package mover

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"time"

	"actress-classifier/pkg/safefile"

	"github.com/google/uuid"
)

// ListOperations 列出所有操作日誌
func (m *Mover) ListOperations() ([]OperationLog, error) {
	if m.LogDir == "" {
		return nil, fmt.Errorf("未設定日誌目錄")
	}
	logPath := filepath.Join(m.LogDir, "operations")
	entries, err := os.ReadDir(logPath)
	if err != nil {
		if os.IsNotExist(err) {
			return []OperationLog{}, nil
		}
		return nil, err
	}

	logs := make([]OperationLog, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		data, err := safefile.ReadFile(filepath.Join(logPath, entry.Name()))
		if err != nil {
			continue
		}
		var log OperationLog
		if err := json.Unmarshal(data, &log); err != nil {
			continue
		}
		logs = append(logs, log)
	}
	sort.Slice(logs, func(i, j int) bool { return logs[i].Timestamp.After(logs[j].Timestamp) })
	return logs, nil
}

func (m *Mover) saveOperationLog(log *OperationLog) error {
	if m.LogDir == "" {
		return nil
	}
	logPath := filepath.Join(m.LogDir, "operations")
	if err := safefile.MkdirAll(logPath, 0700); err != nil {
		return err
	}
	filename := fmt.Sprintf("%s_%s.json", log.Timestamp.Format("2006-01-02_150405"), log.ID)
	data, err := json.MarshalIndent(log, "", "  ")
	if err != nil {
		return err
	}
	return safefile.WriteFile(filepath.Join(logPath, filename), data, 0600)
}

func (m *Mover) loadOperationLog(id string) (*OperationLog, error) {
	if m.LogDir == "" {
		return nil, fmt.Errorf("未設定日誌目錄")
	}
	matches, err := filepath.Glob(filepath.Join(m.LogDir, "operations", "*_"+id+".json"))
	if err != nil {
		return nil, fmt.Errorf("搜尋日誌檔案失敗: %w", err)
	}
	for _, match := range matches {
		data, err := safefile.ReadFile(match)
		if err != nil {
			continue
		}
		var log OperationLog
		if err := json.Unmarshal(data, &log); err != nil {
			continue
		}
		if log.ID == id {
			return &log, nil
		}
	}
	return nil, fmt.Errorf("找不到操作 ID: %s", id)
}

// GetOperation 取得指定 ID 的操作日誌（公開版 loadOperationLog）
func (m *Mover) GetOperation(id string) (*OperationLog, error) {
	return m.loadOperationLog(id)
}

func (m *Mover) createOperationLog(opType string, items []MoveItem) *OperationLog {
	log := &OperationLog{
		ID:         uuid.New().String()[:8],
		Timestamp:  time.Now(),
		Type:       opType,
		Status:     "started",
		TotalItems: len(items),
		Items:      make([]MoveLog, len(items)),
	}
	for i, item := range items {
		log.Items[i] = MoveLog{Source: item.Source, Destination: item.Destination, Status: "pending"}
	}
	return log
}
