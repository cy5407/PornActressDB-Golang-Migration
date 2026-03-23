// Package mover 提供檔案移動和合併功能
package mover

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
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
	OperationID  string       `json:"operation_id,omitempty"`
	TotalItems   int          `json:"total_items"`
	SuccessCount int          `json:"success_count"`
	FailedCount  int          `json:"failed_count"`
	SkippedCount int          `json:"skipped_count"`
	Results      []MoveResult `json:"results"`
	Status       string       `json:"status,omitempty"`
	Summary      string       `json:"summary,omitempty"`
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
	ID           string    `json:"id"`
	Timestamp    time.Time `json:"timestamp"`
	Type         string    `json:"type"` // batch_move, rollback, merge
	Items        []MoveLog `json:"items"`
	TotalItems   int       `json:"total_items"`
	SuccessCount int       `json:"success_count"`
	FailedCount  int       `json:"failed_count"`
	SkippedCount int       `json:"skipped_count"`
	Status       string    `json:"status"` // started, completed, partial, failed
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
				// 使用暫存檔原子替換，避免先 Remove 後 Rename 失敗時目標消失
				if err := m.replaceFileSafely(src, dst); err != nil {
					result.Error = fmt.Sprintf("覆蓋目標檔案失敗: %v", err)
					return result
				}
				// replaceFileSafely 已完整搬移 src→dst，直接回傳成功
				result.Success = true
				result.Destination = dst
				return result
			}
			// DryRun 模式：不執行實際替換，繼續到下方 DryRun 判斷區段

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
// ctx 用於支援未來的取消與逾時（目前接受但不使用）
func (m *Mover) BatchMove(ctx context.Context, items []MoveItem) BatchResult {
	return m.batchMoveWithType(ctx, items, "batch_move")
}

func (m *Mover) batchMoveWithType(ctx context.Context, items []MoveItem, opType string) BatchResult {
	_ = ctx // 預留給未來的取消支援
	start := time.Now()
	result := BatchResult{
		TotalItems: len(items),
		Results:    make([]MoveResult, 0, len(items)),
	}

	// 建立操作日誌
	opLog := m.createOperationLog(opType, items)

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
	opLog.TotalItems = result.TotalItems
	opLog.SuccessCount = result.SuccessCount
	opLog.FailedCount = result.FailedCount
	opLog.SkippedCount = result.SkippedCount

	// 儲存操作日誌
	m.saveOperationLog(opLog)

	result.OperationID = opLog.ID
	result.Status = opLog.Status
	result.Summary = formatBatchSummary(result)
	result.Duration = time.Since(start).String()
	return result
}

// Rollback 回滾指定的操作
func (m *Mover) Rollback(operationID string) (BatchResult, error) {
	opLog, err := m.loadOperationLog(operationID)
	if err != nil {
		return BatchResult{}, fmt.Errorf("無法載入操作日誌: %v", err)
	}

	// 建立回滾項目（反向），並記錄每個回滾項目對應的原始 opLog.Items 索引
	var items []MoveItem
	var originalIndices []int // 回滾項目索引 → 原始 opLog.Items 索引的映射
	for i, item := range opLog.Items {
		if item.Status == "success" {
			items = append(items, MoveItem{
				Source:      item.Destination, // 回滾來源為原操作的目標
				Destination: item.Source,      // 回滾目標為原操作的來源
				OnConflict:  Skip,
			})
			originalIndices = append(originalIndices, i)
		}
	}

	// 執行回滾
	result := m.batchMoveWithType(context.Background(), items, "rollback")

	// 根據實際回滾結果更新原操作日誌各項目狀態（區分回滾成功、衝突跳過、失敗）
	for ri, origIdx := range originalIndices {
		if ri < len(result.Results) {
			r := result.Results[ri]
			if r.Success && !r.Skipped {
				opLog.Items[origIdx].Status = "rolled_back"
			} else if r.Skipped {
				opLog.Items[origIdx].Status = "rollback_skipped" // 目標位置已有檔案，跳過
			} else {
				opLog.Items[origIdx].Status = "rollback_failed"
			}
		}
	}

	// 更新整體操作日誌狀態
	if result.SkippedCount > 0 || result.FailedCount > 0 {
		opLog.Status = "rollback_partial" // 部分回滾：有衝突跳過或失敗
	} else if len(items) > 0 {
		opLog.Status = "rolled_back"
	}
	m.saveOperationLog(opLog)

	// 根據回滾結果設定明確的 Summary 訊息，讓呼叫方清楚知道回滾是否完整
	switch {
	case result.SkippedCount > 0 && result.FailedCount > 0:
		// 同時有衝突跳過和執行失敗
		result.Status = "partial"
		result.Summary = fmt.Sprintf(
			"回滾未完整：%d 項成功，%d 項因衝突跳過，%d 項失敗（共 %d 項）",
			result.SuccessCount, result.SkippedCount, result.FailedCount, result.TotalItems,
		)
	case result.SkippedCount > 0:
		// 有衝突跳過（目標路徑已有檔案）
		result.Status = "partial"
		result.Summary = fmt.Sprintf(
			"回滾部分完成：%d 項成功，%d 項因衝突跳過（共 %d 項）",
			result.SuccessCount, result.SkippedCount, result.TotalItems,
		)
	case result.FailedCount > 0:
		// 有執行失敗（非衝突原因）
		result.Status = "partial"
		result.Summary = fmt.Sprintf(
			"回滾部分完成：%d 項成功，%d 項失敗（共 %d 項）",
			result.SuccessCount, result.FailedCount, result.TotalItems,
		)
	default:
		// 全部成功（或沒有可回滾項目）
		result.Summary = fmt.Sprintf("回滾完成：共 %d 項成功", result.SuccessCount)
	}

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

	sort.Slice(logs, func(i, j int) bool {
		return logs[i].Timestamp.After(logs[j].Timestamp)
	})

	return logs, nil
}

// === 內部輔助函式 ===

// generateUniqueNameMaxAttempts 是 generateUniqueName 的最大遞增編號嘗試次數
// 超過上限後改用時間戳確保唯一性
const generateUniqueNameMaxAttempts = 10000

// generateUniqueName 在指定路徑已存在時，產生不衝突的唯一路徑
//
// 策略：
//  1. 嘗試 file_1.ext、file_2.ext ... 直到找到不存在的名稱
//  2. 若嘗試次數超過 generateUniqueNameMaxAttempts，
//     改以「file_YYYYMMDDHHMMSS.ext」格式（可讀時間戳）作為後備
//     並記錄 warning 到 stderr，告知開發者出現了極端的命名衝突
func (m *Mover) generateUniqueName(path string) string {
	dir := filepath.Dir(path)
	fileExt := filepath.Ext(path)
	base := filepath.Base(path)
	name := base[:len(base)-len(fileExt)]

	for i := 1; i <= generateUniqueNameMaxAttempts; i++ {
		candidate := fmt.Sprintf("%s_%d%s", name, i, fileExt)
		candidatePath := filepath.Join(dir, candidate)
		if _, err := os.Stat(candidatePath); os.IsNotExist(err) {
			return candidatePath
		}
	}

	// Fallback：以可讀時間戳確保唯一性（格式：YYYYMMDDHHMMSS）
	// 記錄 warning：正常情況下不應到達此處，可能目錄下有大量同名衝突檔案
	timestamp := time.Now().Format("20060102150405")
	result := filepath.Join(dir, fmt.Sprintf("%s_%s%s", name, timestamp, fileExt))
	fmt.Fprintf(os.Stderr,
		"[WARNING] generateUniqueName: 達到最大嘗試次數 (%d)，改用時間戳後備名稱：%s\n",
		generateUniqueNameMaxAttempts, result,
	)
	return result
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

	if _, err = io.Copy(dstFile, srcFile); err != nil {
		dstFile.Close()
		os.Remove(dst) // 清理複製失敗的不完整目標檔案
		return fmt.Errorf("failed to copy file contents: %w", err)
	}

	// 確保資料寫入磁碟
	if err := dstFile.Sync(); err != nil {
		dstFile.Close()
		os.Remove(dst)
		return fmt.Errorf("failed to sync destination file: %w", err)
	}

	// 明確處理 Close() 的 error
	if err := dstFile.Close(); err != nil {
		os.Remove(dst)
		return fmt.Errorf("failed to close destination file: %w", err)
	}

	// 保留檔案權限
	srcInfo, err := os.Stat(src)
	if err == nil {
		os.Chmod(dst, srcInfo.Mode())
	}

	return nil
}

// replaceFileSafely 使用暫存檔原子替換目標，確保中途失敗時目標檔案仍保持完整
// 步驟：複製 src 到同目錄暫存檔 → Rename 覆蓋 dst → 刪除 src
func (m *Mover) replaceFileSafely(src, dst string) error { // src: 來源路徑，dst: 目標路徑
	// 暫存檔放在與目標相同目錄，以時間戳結尾確保唯一性
	tmpDst := fmt.Sprintf("%s.tmp-%d", dst, time.Now().UnixNano()) // 暫存檔路徑

	// 第一步：將 src 完整複製到暫存位置（此時原 dst 仍完整）
	if err := m.copyFile(src, tmpDst); err != nil {
		return fmt.Errorf("無法複製到暫存檔: %w", err)
	}

	// 第二步：原子 Rename 替換目標（即使 dst 存在也會覆蓋，原 dst 在此步驟前仍完整）
	if err := os.Rename(tmpDst, dst); err != nil {
		os.Remove(tmpDst) // 清理暫存檔，確保原 dst 不受影響
		return fmt.Errorf("無法以暫存檔替換目標: %w", err)
	}

	// 第三步：刪除來源（目標已成功替換，來源不再需要）
	if err := os.Remove(src); err != nil {
		// 目標已替換成功，但來源未能刪除；回傳錯誤讓呼叫方決定處理方式
		return fmt.Errorf("目標已替換但刪除來源失敗: %w", err)
	}

	return nil
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
		log.Items[i] = MoveLog{
			Source:      item.Source,
			Destination: item.Destination,
			Status:      "pending",
		}
	}

	return log
}

func formatBatchSummary(result BatchResult) string {
	return fmt.Sprintf(
		"總計 %d，成功 %d，跳過 %d，失敗 %d",
		result.TotalItems,
		result.SuccessCount,
		result.SkippedCount,
		result.FailedCount,
	)
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
	if m.LogDir == "" {
		return nil, fmt.Errorf("未設定日誌目錄")
	}

	logPath := filepath.Join(m.LogDir, "operations")

	// 使用 glob 直接定位日誌檔案，避免載入全部日誌線性搜尋
	pattern := filepath.Join(logPath, "*_"+id+".json")
	matches, err := filepath.Glob(pattern)
	if err != nil {
		return nil, fmt.Errorf("搜尋日誌檔案失敗: %w", err)
	}

	for _, match := range matches {
		data, err := os.ReadFile(match)
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
