package app

import (
	"fmt"

	"actress-classifier/pkg/mover"
)

func ListOperations(logDir string, limit int) ([]mover.OperationLog, error) {
	logs, err := mover.NewMover(logDir).ListOperations()
	if err != nil {
		return nil, err
	}
	if limit > 0 && len(logs) > limit {
		return logs[:limit], nil
	}
	return logs, nil
}

func ShowOperation(logDir, id string) (mover.OperationLog, error) {
	logs, err := ListOperations(logDir, 0)
	if err != nil {
		return mover.OperationLog{}, err
	}
	for _, log := range logs {
		if log.ID == id {
			return log, nil
		}
	}
	return mover.OperationLog{}, fmt.Errorf("找不到操作 ID: %s", id)
}

func Rollback(logDir, id string, last bool) (mover.BatchResult, error) {
	targetID := id
	if last {
		logs, err := ListOperations(logDir, 0)
		if err != nil {
			return mover.BatchResult{}, err
		}
		if len(logs) == 0 {
			return mover.BatchResult{}, fmt.Errorf("沒有可回滾的操作")
		}
		targetID = logs[0].ID
	}
	return mover.NewMover(logDir).Rollback(targetID)
}
