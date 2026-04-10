package mover

import (
	"context"
	"fmt"
	"os"
)

// Rollback 回滾指定的操作
func (m *Mover) Rollback(operationID string) (BatchResult, error) {
	opLog, err := m.loadOperationLog(operationID)
	if err != nil {
		return BatchResult{}, fmt.Errorf("無法載入操作日誌: %v", err)
	}

	items, originalIndices := rollbackItemsForLog(opLog)
	result := m.runRollbackBatch(opLog.Type, items)
	applyRollbackResults(opLog, originalIndices, result)
	rollbackSummary, rollbackStatus := buildRollbackSummary(result)
	result.Summary = rollbackSummary
	result.Status = rollbackStatus

	if rollbackStatus == "partial" {
		opLog.Status = "partial"
	} else if len(items) > 0 {
		opLog.Status = "rolled_back"
	}
	if err := m.saveOperationLog(opLog); err != nil {
		fmt.Fprintf(os.Stderr, "[WARNING] 儲存回滾日誌失敗: %v\n", err)
	}

	return result, nil
}

func rollbackItemsForLog(opLog *OperationLog) ([]MoveItem, []int) {
	items := make([]MoveItem, 0, len(opLog.Items))
	originalIndices := make([]int, 0, len(opLog.Items))
	for i, item := range opLog.Items {
		if item.Status != "success" {
			continue
		}
		items = append(items, MoveItem{
			Source:      item.Destination,
			Destination: item.Source,
			OnConflict:  Skip,
		})
		originalIndices = append(originalIndices, i)
	}
	return items, originalIndices
}

func (m *Mover) runRollbackBatch(opType string, items []MoveItem) BatchResult {
	if opType == "batch_move_dirs" {
		// 目錄級回滾：反向移動整個目錄
		return m.batchMoveDirsWithType(context.Background(), items, "rollback")
	}
	return m.batchMoveWithType(context.Background(), items, "rollback")
}

func applyRollbackResults(opLog *OperationLog, originalIndices []int, result BatchResult) {
	for ri, origIdx := range originalIndices {
		if ri >= len(result.Results) {
			continue
		}
		r := result.Results[ri]
		switch {
		case r.Success && !r.Skipped:
			opLog.Items[origIdx].Status = "rolled_back"
		case r.Skipped:
			opLog.Items[origIdx].Status = "rollback_skipped"
		default:
			opLog.Items[origIdx].Status = "rollback_failed"
		}
	}
}

func buildRollbackSummary(result BatchResult) (string, string) {
	switch {
	case result.SkippedCount > 0 && result.FailedCount > 0:
		return fmt.Sprintf("回滾未完整：%d 項成功，%d 項因衝突跳過，%d 項失敗（共 %d 項）", result.SuccessCount, result.SkippedCount, result.FailedCount, result.TotalItems), "partial"
	case result.SkippedCount > 0:
		return fmt.Sprintf("回滾部分完成：%d 項成功，%d 項因衝突跳過（共 %d 項）", result.SuccessCount, result.SkippedCount, result.TotalItems), "partial"
	case result.FailedCount > 0:
		return fmt.Sprintf("回滾部分完成：%d 項成功，%d 項失敗（共 %d 項）", result.SuccessCount, result.FailedCount, result.TotalItems), "partial"
	default:
		return fmt.Sprintf("回滾完成：共 %d 項成功", result.SuccessCount), "completed"
	}
}
