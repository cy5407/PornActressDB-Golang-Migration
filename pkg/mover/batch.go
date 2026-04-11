package mover

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// BatchMove 批次移動檔案
func (m *Mover) BatchMove(ctx context.Context, items []MoveItem) BatchResult {
	return m.batchMoveWithType(ctx, items, "batch_move")
}

func (m *Mover) batchMoveWithType(ctx context.Context, items []MoveItem, opType string) BatchResult {
	start := time.Now()
	result := BatchResult{TotalItems: len(items), Results: make([]MoveResult, 0, len(items))}
	opLog := m.createOperationLog(opType, items)

	for i, item := range items {
		select {
		case <-ctx.Done():
			opLog.Status = "cancelled"
			return m.finalizeBatchResult(start, &result, opLog, "批次移動已取消")
		default:
		}

		strategy := item.OnConflict
		if strategy == "" {
			strategy = m.DefaultStrategy
		}
		moveResult := m.MoveFile(item.Source, item.Destination, strategy)
		result.Results = append(result.Results, moveResult)
		opLog.Items[i].Destination = moveResult.Destination
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
			opLog.Items[i].Status, opLog.Items[i].Error = "failed", moveResult.Error
		}
	}

	if result.FailedCount == 0 {
		opLog.Status = "completed"
	} else if result.SuccessCount > 0 {
		opLog.Status = "partial"
	} else {
		opLog.Status = "failed"
	}
	return m.finalizeBatchResult(start, &result, opLog, "")
}

// BatchMoveDirs 批次移動目錄，每個 item 的 Source 為來源目錄，Destination 為目標目錄。
// 操作記錄以 "batch_move_dirs" 類型寫入 opLog，支援 RollbackOperation。
// 判斷完整成功（dirFullyMoved）的條件：mr.Success && mr.FilesSkipped == 0 && mr.DeletedSrc。
// 只要來源目錄仍存在（例如有 skipped 檔案，或刪除來源目錄失敗），
// 整個目錄即視為未完整移走，計入 SkippedCount。
// 注意：directory batch 的 MoveResult.Destination 代表實際落點；若發生 rename，
// MoveResult.Renamed 也會填入同一個實際路徑，供前端顯示實際改名結果。
func (m *Mover) BatchMoveDirs(ctx context.Context, items []MoveItem) BatchResult {
	return m.batchMoveDirsWithType(ctx, items, "batch_move_dirs")
}

func (m *Mover) batchMoveDirsWithType(ctx context.Context, items []MoveItem, opType string) BatchResult {
	start := time.Now()
	result := BatchResult{TotalItems: len(items), Results: make([]MoveResult, 0, len(items))}
	opLog := m.createOperationLog(opType, items)

	for i, item := range items {
		if ctx.Err() != nil {
			opLog.Status = "cancelled"
			return m.finalizeBatchResult(start, &result, opLog, "批次目錄移動已取消")
		}

		mr := m.MoveDir(item.Source, item.Destination, m.resolveBatchMoveStrategy(item.OnConflict))
		moveResult, status := m.buildBatchMoveDirOutcome(item, mr)
		m.recordBatchMoveDirOutcome(&result, &opLog.Items[i], moveResult, status)
	}

	if result.FailedCount == 0 && result.SkippedCount == 0 {
		opLog.Status = "completed"
	} else if result.FailedCount == 0 && result.SuccessCount == 0 {
		opLog.Status = "skipped"
	} else if result.FailedCount == 0 || result.SuccessCount > 0 {
		opLog.Status = "partial"
	} else {
		opLog.Status = "failed"
	}
	return m.finalizeBatchResult(start, &result, opLog, "")
}

func (m *Mover) resolveBatchMoveStrategy(strategy ConflictStrategy) ConflictStrategy {
	if strategy != "" {
		return strategy
	}
	return m.DefaultStrategy
}

func (m *Mover) buildBatchMoveDirOutcome(item MoveItem, mr MergeResult) (MoveResult, string) {
	moveResult := MoveResult{
		Source:      item.Source,
		Destination: mr.DestDir,
		Success:     mr.Success,
		// Renamed 維持零值：合併語意下整個目錄不更名，衝突由內部檔案層級 Rename 處理
	}

	if !mr.Success {
		if len(mr.Errors) > 0 {
			moveResult.Error = mr.Errors[0].Error
		} else {
			moveResult.Error = fmt.Sprintf("移動 %d/%d 個檔案後失敗", mr.FilesMoved, mr.FilesTotal)
		}
		return moveResult, "failed"
	}

	if sameSourceAndDestination(item.Source, item.Destination) || mr.FilesSkipped == 0 && mr.DeletedSrc {
		return moveResult, "success"
	}

	moveResult.Skipped = true
	return moveResult, "skipped"
}

func (m *Mover) recordBatchMoveDirOutcome(result *BatchResult, logItem *MoveLog, moveResult MoveResult, status string) {
	result.Results = append(result.Results, moveResult)
	logItem.Destination = moveResult.Destination
	logItem.Status = status

	switch status {
	case "success":
		result.SuccessCount++
	case "skipped":
		result.SkippedCount++
	case "failed":
		result.FailedCount++
		logItem.Error = moveResult.Error
	}
}

func formatBatchSummary(result BatchResult) string {
	return fmt.Sprintf("總計 %d，成功 %d，跳過 %d，失敗 %d", result.TotalItems, result.SuccessCount, result.SkippedCount, result.FailedCount)
}

func (m *Mover) finalizeBatchResult(start time.Time, result *BatchResult, opLog *OperationLog, summaryOverride string) BatchResult {
	opLog.TotalItems, opLog.SuccessCount = result.TotalItems, result.SuccessCount
	opLog.FailedCount, opLog.SkippedCount = result.FailedCount, result.SkippedCount
	if err := m.saveOperationLog(opLog); err != nil {
		fmt.Fprintf(os.Stderr, "[WARNING] 儲存操作日誌失敗: %v\n", err)
	}
	result.OperationID, result.Status = opLog.ID, opLog.Status
	if summaryOverride != "" {
		result.Summary = summaryOverride
	} else {
		result.Summary = formatBatchSummary(*result)
	}
	result.Duration = time.Since(start).String()
	return *result
}

func sameSourceAndDestination(src, dst string) bool {
	absSrc, errSrc := filepath.Abs(src)
	absDst, errDst := filepath.Abs(dst)
	return errSrc == nil && errDst == nil && strings.EqualFold(absSrc, absDst)
}
