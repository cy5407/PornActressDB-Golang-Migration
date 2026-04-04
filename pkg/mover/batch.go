package mover

import (
	"context"
	"fmt"
	"os"
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
	opLog.TotalItems, opLog.SuccessCount = result.TotalItems, result.SuccessCount
	opLog.FailedCount, opLog.SkippedCount = result.FailedCount, result.SkippedCount
	return m.finalizeBatchResult(start, &result, opLog, "")
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
