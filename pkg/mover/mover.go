// Package mover 提供檔案移動和合併功能
package mover

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"

	"github.com/google/uuid"
)

// ConflictStrategy 定義衝突處理策略
type ConflictStrategy string

const (
	Skip      ConflictStrategy = "skip"      // 跳過
	Overwrite ConflictStrategy = "overwrite" // 覆蓋
	Rename    ConflictStrategy = "rename"    // 重命名
	Merge     ConflictStrategy = "merge"     // 合併到子目錄
)

// MoveItem 表示單一移動項目
type MoveItem struct {
	Source      string           `json:"source"`
	Destination string           `json:"destination"`
	OnConflict  ConflictStrategy `json:"on_conflict,omitempty"`
}

// MoveResult 表示移動結果
type MoveResult struct {
	Source      string `json:"source"`
	Destination string `json:"destination"`
	Success     bool   `json:"success"`
	Error       string `json:"error,omitempty"`
	Skipped     bool   `json:"skipped,omitempty"`
	Renamed     string `json:"renamed,omitempty"`
}

// MergeResult 表示資料夾合併結果
type MergeResult struct {
	SourceDir  string       `json:"source_dir"`
	DestDir    string       `json:"dest_dir"`
	FilesMoved int          `json:"files_moved"`
	FilesTotal int          `json:"files_total"`
	Errors     []MoveResult `json:"errors,omitempty"`
	Success    bool         `json:"success"`
	DeletedSrc bool         `json:"deleted_src"`
}

// BatchResult 表示批次移動結果
type BatchResult struct {
	TotalItems   int          `json:"total_items"`
	SuccessCount int          `json:"success_count"`
	FailedCount  int          `json:"failed_count"`
	SkippedCount int          `json:"skipped_count"`
	Results      []MoveResult `json:"results"`
	Duration     string       `json:"duration"`
}

// MoveLog 記錄單一移動操作
type MoveLog struct {
	Source      string `json:"source"`
	Destination string `json:"destination"`
	Status      string `json:"status"` // pending, success, failed, rolled_back
	Error       string `json:"error,omitempty"`
}

// OperationLog 記錄批次操作
type OperationLog struct {
	ID        string    `json:"id"`
	Timestamp time.Time `json:"timestamp"`
	Type      string    `json:"type"` // move_batch, merge
	Items     []MoveLog `json:"items"`
	Status    string    `json:"status"` // started, completed, partial, failed
}

// Mover 檔案移動器
type Mover struct {
	LogDir          string           // 操作日誌目錄
	DefaultStrategy ConflictStrategy // 預設衝突策略
	DryRun          bool             // 模擬執行模式
}

// NewMover 建立新的移動器
func NewMover(logDir string) *Mover {
	return &Mover{
		LogDir:          logDir,
		DefaultStrategy: Skip,
		DryRun:          false,
	}
}

// MoveFile 移動單一檔案
func (m *Mover) MoveFile(src, dst string, strategy ConflictStrategy) MoveResult {
	result := MoveResult{
		Source:      src,
		Destination: dst,
		Success:     false,
	}

	// 檢查來源是否存在
	srcInfo, err := os.Stat(src)
	if os.IsNotExist(err) {
		result.Error = "來源檔案不存在"
		return result
	}
	if err != nil {
		result.Error = fmt.Sprintf("無法讀取來源: %v", err)
		return result
	}

	// 來源必須是檔案
	if srcInfo.IsDir() {
		result.Error = "來源是目錄，請使用 MoveDir"
		return result
	}

	// 確保目標目錄存在
	dstDir := filepath.Dir(dst)
	if !m.DryRun {
		if err := os.MkdirAll(dstDir, 0755); err != nil {
			result.Error = fmt.Sprintf("無法建立目標目錄: %v", err)
			return result
		}
	}

	// 檢查目標是否存在
	if _, err := os.Stat(dst); err == nil {
		// 目標已存在，根據策略處理
		switch strategy {
		case Skip:
			result.Skipped = true
			result.Success = true
			return result

		case Overwrite:
			if !m.DryRun {
				if err := os.Remove(dst); err != nil {
					result.Error = fmt.Sprintf("無法刪除目標檔案: %v", err)
					return result
				}
			}

		case Rename:
			newDst := m.generateUniqueName(dst)
			result.Renamed = newDst
			dst = newDst

		case Merge:
			// Merge 策略只適用於目錄
			result.Error = "Merge 策略不適用於單一檔案"
			return result

		default:
			result.Error = fmt.Sprintf("未知的衝突策略: %s", strategy)
			return result
		}
	}

	// 執行移動
	if m.DryRun {
		result.Success = true
		result.Destination = dst
		return result
	}

	// 嘗試直接重命名（同一磁碟機）
	err = os.Rename(src, dst)
	if err == nil {
		result.Success = true
		result.Destination = dst
		return result
	}

	// 重命名失敗，嘗試複製後刪除（跨磁碟機）
	if err := m.copyFile(src, dst); err != nil {
		result.Error = fmt.Sprintf("複製檔案失敗: %v", err)
		return result
	}

	if err := os.Remove(src); err != nil {
		result.Error = fmt.Sprintf("刪除來源失敗: %v", err)
		// 注意：檔案已複製，但來源未刪除
		return result
	}

	result.Success = true
	result.Destination = dst
	return result
}

// MoveDir 移動整個目錄
func (m *Mover) MoveDir(src, dst string, strategy ConflictStrategy) MergeResult {
	result := MergeResult{
		SourceDir: src,
		DestDir:   dst,
		Success:   false,
	}

	// 檢查來源目錄
	srcInfo, err := os.Stat(src)
	if os.IsNotExist(err) {
		result.Errors = append(result.Errors, MoveResult{
			Source: src,
			Error:  "來源目錄不存在",
		})
		return result
	}
	if !srcInfo.IsDir() {
		result.Errors = append(result.Errors, MoveResult{
			Source: src,
			Error:  "來源不是目錄",
		})
		return result
	}

	// 收集所有檔案
	var files []string
	err = filepath.Walk(src, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if !info.IsDir() {
			files = append(files, path)
		}
		return nil
	})
	if err != nil {
		result.Errors = append(result.Errors, MoveResult{
			Source: src,
			Error:  fmt.Sprintf("掃描目錄失敗: %v", err),
		})
		return result
	}

	result.FilesTotal = len(files)

	// 移動所有檔案
	for _, srcFile := range files {
		relPath, _ := filepath.Rel(src, srcFile)
		dstFile := filepath.Join(dst, relPath)

		moveResult := m.MoveFile(srcFile, dstFile, strategy)
		if moveResult.Success {
			result.FilesMoved++
		} else {
			result.Errors = append(result.Errors, moveResult)
		}
	}

	// 如果所有檔案都移動成功，刪除來源目錄
	if result.FilesMoved == result.FilesTotal && !m.DryRun {
		if err := os.RemoveAll(src); err == nil {
			result.DeletedSrc = true
		}
	}

	result.Success = len(result.Errors) == 0
	return result
}

// BatchMove 批次移動檔案
func (m *Mover) BatchMove(items []MoveItem) BatchResult {
	start := time.Now()
	result := BatchResult{
		TotalItems: len(items),
		Results:    make([]MoveResult, 0, len(items)),
	}

	// 建立操作日誌
	opLog := m.createOperationLog("move_batch", items)

	for i, item := range items {
		strategy := item.OnConflict
		if strategy == "" {
			strategy = m.DefaultStrategy
		}

		moveResult := m.MoveFile(item.Source, item.Destination, strategy)
		result.Results = append(result.Results, moveResult)

		// 更新日誌狀態
		if moveResult.Success {
			if moveResult.Skipped {
				result.SkippedCount++
				opLog.Items[i].Status = "skipped"
			} else {
				result.SuccessCount++
				opLog.Items[i].Status = "success"
			}
		} else {
			result.FailedCount++
			opLog.Items[i].Status = "failed"
			opLog.Items[i].Error = moveResult.Error
		}
	}

	// 更新操作日誌狀態
	if result.FailedCount == 0 {
		opLog.Status = "completed"
	} else if result.SuccessCount > 0 {
		opLog.Status = "partial"
	} else {
		opLog.Status = "failed"
	}

	// 儲存操作日誌
	m.saveOperationLog(opLog)

	result.Duration = time.Since(start).String()
	return result
}

// Rollback 回滾指定的操作
func (m *Mover) Rollback(operationID string) (BatchResult, error) {
	opLog, err := m.loadOperationLog(operationID)
	if err != nil {
		return BatchResult{}, fmt.Errorf("無法載入操作日誌: %v", err)
	}

	// 建立回滾項目（反向）
	var items []MoveItem
	for _, item := range opLog.Items {
		if item.Status == "success" {
			items = append(items, MoveItem{
				Source:      item.Destination,
				Destination: item.Source,
				OnConflict:  Skip,
			})
		}
	}

	// 執行回滾
	result := m.BatchMove(items)

	// 更新原操作日誌
	for i := range opLog.Items {
		if opLog.Items[i].Status == "success" {
			opLog.Items[i].Status = "rolled_back"
		}
	}
	m.saveOperationLog(opLog)

	return result, nil
}

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

	var logs []OperationLog
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			continue
		}

		data, err := os.ReadFile(filepath.Join(logPath, entry.Name()))
		if err != nil {
			continue
		}

		var log OperationLog
		if err := json.Unmarshal(data, &log); err != nil {
			continue
		}
		logs = append(logs, log)
	}

	return logs, nil
}

// === 內部輔助函式 ===

func (m *Mover) generateUniqueName(path string) string {
	dir := filepath.Dir(path)
	ext := filepath.Ext(path)
	base := filepath.Base(path)
	name := base[:len(base)-len(ext)]

	for i := 1; ; i++ {
		newName := fmt.Sprintf("%s_%d%s", name, i, ext)
		newPath := filepath.Join(dir, newName)
		if _, err := os.Stat(newPath); os.IsNotExist(err) {
			return newPath
		}
	}
}

func (m *Mover) copyFile(src, dst string) error {
	srcFile, err := os.Open(src)
	if err != nil {
		return err
	}
	defer srcFile.Close()

	dstFile, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer dstFile.Close()

	_, err = io.Copy(dstFile, srcFile)
	if err != nil {
		return err
	}

	// 保留檔案權限
	srcInfo, err := os.Stat(src)
	if err == nil {
		os.Chmod(dst, srcInfo.Mode())
	}

	return nil
}

func (m *Mover) createOperationLog(opType string, items []MoveItem) *OperationLog {
	log := &OperationLog{
		ID:        uuid.New().String()[:8],
		Timestamp: time.Now(),
		Type:      opType,
		Status:    "started",
		Items:     make([]MoveLog, len(items)),
	}

	for i, item := range items {
		log.Items[i] = MoveLog{
			Source:      item.Source,
			Destination: item.Destination,
			Status:      "pending",
		}
	}

	return log
}

func (m *Mover) saveOperationLog(log *OperationLog) error {
	if m.LogDir == "" {
		return nil // 未設定日誌目錄，跳過
	}

	logPath := filepath.Join(m.LogDir, "operations")
	if err := os.MkdirAll(logPath, 0755); err != nil {
		return err
	}

	filename := fmt.Sprintf("%s_%s.json",
		log.Timestamp.Format("2006-01-02_150405"),
		log.ID,
	)

	data, err := json.MarshalIndent(log, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(filepath.Join(logPath, filename), data, 0644)
}

func (m *Mover) loadOperationLog(id string) (*OperationLog, error) {
	logs, err := m.ListOperations()
	if err != nil {
		return nil, err
	}

	for _, log := range logs {
		if log.ID == id {
			return &log, nil
		}
	}

	return nil, fmt.Errorf("找不到操作 ID: %s", id)
}
