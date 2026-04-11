package app

import (
	"fmt"

	"actress-classifier/pkg/contracts"
	"actress-classifier/pkg/mover"
)

func moveLogToContract(item mover.MoveLog) contracts.MoveLog {
	return contracts.MoveLog{
		Source:      item.Source,
		Destination: item.Destination,
		Status:      item.Status,
		Error:       item.Error,
	}
}

func operationLogToContract(log mover.OperationLog) contracts.OperationLog {
	items := make([]contracts.MoveLog, 0, len(log.Items))
	for _, item := range log.Items {
		items = append(items, moveLogToContract(item))
	}
	return contracts.OperationLog{
		ID:           log.ID,
		Timestamp:    log.Timestamp,
		Type:         log.Type,
		Items:        items,
		TotalItems:   log.TotalItems,
		SuccessCount: log.SuccessCount,
		FailedCount:  log.FailedCount,
		SkippedCount: log.SkippedCount,
		Status:       log.Status,
	}
}

func ListOperations(logDir string, limit int) ([]contracts.OperationLog, error) {
	logs, err := mover.NewMover(logDir).ListOperations()
	if err != nil {
		return nil, err
	}
	results := make([]contracts.OperationLog, 0, len(logs))
	for _, log := range logs {
		results = append(results, operationLogToContract(log))
	}
	if limit > 0 && len(results) > limit {
		return results[:limit], nil
	}
	return results, nil
}

func ShowOperation(logDir, id string) (contracts.OperationLog, error) {
	logs, err := ListOperations(logDir, 0)
	if err != nil {
		return contracts.OperationLog{}, err
	}
	for _, log := range logs {
		if log.ID == id {
			return log, nil
		}
	}
	return contracts.OperationLog{}, fmt.Errorf("找不到操作 ID: %s", id)
}

func Rollback(logDir, id string, last bool) (contracts.BatchResult, error) {
	targetID := id
	if last {
		logs, err := ListOperations(logDir, 0)
		if err != nil {
			return contracts.BatchResult{}, err
		}
		if len(logs) == 0 {
			return contracts.BatchResult{}, fmt.Errorf("沒有可回滾的操作")
		}
		targetID = logs[0].ID
	}
	result, err := mover.NewMover(logDir).Rollback(targetID)
	if err != nil {
		return contracts.BatchResult{}, err
	}
	return batchResultToContract(result), nil
}
