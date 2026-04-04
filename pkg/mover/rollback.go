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

	var items []MoveItem
	var originalIndices []int
	for i, item := range opLog.Items {
		if item.Status == "success" {
			items = append(items, MoveItem{Source: item.Destination, Destination: item.Source, OnConflict: Skip})
			originalIndices = append(originalIndices, i)
		}
	}

	result := m.batchMoveWithType(context.Background(), items, "rollback")
	for ri, origIdx := range originalIndices {
		if ri >= len(result.Results) {
			continue
		}
		r := result.Results[ri]
		if r.Success && !r.Skipped {
			opLog.Items[origIdx].Status = "rolled_back"
		} else if r.Skipped {
			opLog.Items[origIdx].Status = "rollback_skipped"
		} else {
			opLog.Items[origIdx].Status = "rollback_failed"
		}
	}

	if result.SkippedCount > 0 || result.FailedCount > 0 {
		opLog.Status = "rollback_partial"
	} else if len(items) > 0 {
		opLog.Status = "rolled_back"
	}
	if err := m.saveOperationLog(opLog); err != nil {
		fmt.Fprintf(os.Stderr, "[WARNING] 儲存回滾日誌失敗: %v\n", err)
	}

	switch {
	case result.SkippedCount > 0 && result.FailedCount > 0:
		result.Status = "partial"
		result.Summary = fmt.Sprintf("回滾未完整：%d 項成功，%d 項因衝突跳過，%d 項失敗（共 %d 項）", result.SuccessCount, result.SkippedCount, result.FailedCount, result.TotalItems)
	case result.SkippedCount > 0:
		result.Status = "partial"
		result.Summary = fmt.Sprintf("回滾部分完成：%d 項成功，%d 項因衝突跳過（共 %d 項）", result.SuccessCount, result.SkippedCount, result.TotalItems)
	case result.FailedCount > 0:
		result.Status = "partial"
		result.Summary = fmt.Sprintf("回滾部分完成：%d 項成功，%d 項失敗（共 %d 項）", result.SuccessCount, result.FailedCount, result.TotalItems)
	default:
		result.Summary = fmt.Sprintf("回滾完成：共 %d 項成功", result.SuccessCount)
	}

	return result, nil
}
