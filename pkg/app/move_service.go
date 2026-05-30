package app

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

	"actress-classifier/pkg/contracts"
	"actress-classifier/pkg/mover"
)

func parseStrategy(strategy string) (mover.ConflictStrategy, error) {
	switch strategy {
	case "skip":
		return mover.Skip, nil
	case "overwrite":
		return mover.Overwrite, nil
	case "rename":
		return mover.Rename, nil
	default:
		return "", fmt.Errorf("未知的衝突策略: %s", strategy)
	}
}

func newMover(logDir string, dryRun bool) *mover.Mover {
	m := mover.NewMover(logDir)
	m.DryRun = dryRun
	return m
}

func moveResultToContract(result mover.MoveResult) contracts.MoveResult {
	return contracts.MoveResult{
		Source:      result.Source,
		Destination: result.Destination,
		Success:     result.Success,
		Error:       result.Error,
		Skipped:     result.Skipped,
		Renamed:     result.Renamed,
	}
}

func mergeResultToContract(result mover.MergeResult) contracts.MergeResult {
	errors := make([]contracts.MoveResult, 0, len(result.Errors))
	for _, item := range result.Errors {
		errors = append(errors, moveResultToContract(item))
	}
	return contracts.MergeResult{
		SourceDir:    result.SourceDir,
		DestDir:      result.DestDir,
		FilesMoved:   result.FilesMoved,
		FilesSkipped: result.FilesSkipped,
		FilesTotal:   result.FilesTotal,
		Errors:       errors,
		Success:      result.Success,
		DeletedSrc:   result.DeletedSrc,
	}
}

func batchResultToContract(result mover.BatchResult) contracts.BatchResult {
	items := make([]contracts.MoveResult, 0, len(result.Results))
	for _, item := range result.Results {
		items = append(items, moveResultToContract(item))
	}
	return contracts.BatchResult{
		OperationID:  result.OperationID,
		TotalItems:   result.TotalItems,
		SuccessCount: result.SuccessCount,
		FailedCount:  result.FailedCount,
		SkippedCount: result.SkippedCount,
		Results:      items,
		Status:       result.Status,
		Summary:      result.Summary,
		Duration:     result.Duration,
	}
}

func toMoverItems(items []contracts.MoveItem, strategy mover.ConflictStrategy) []mover.MoveItem {
	out := make([]mover.MoveItem, 0, len(items))
	for _, item := range items {
		conflict := strategy
		if item.OnConflict != "" {
			conflict = mover.ConflictStrategy(item.OnConflict)
		}
		out = append(out, mover.MoveItem{
			Source:      item.Source,
			Destination: item.Destination,
			OnConflict:  conflict,
		})
	}
	return out
}

func MoveFile(src, dst, strategy string, dryRun bool, logDir string) (contracts.MoveResult, error) {
	conflictStrategy, err := parseStrategy(strategy)
	if err != nil {
		return contracts.MoveResult{}, err
	}
	return moveResultToContract(newMover(logDir, dryRun).MoveFile(src, dst, conflictStrategy)), nil
}

func MoveDir(src, dst, strategy string, dryRun bool, logDir string) (contracts.MergeResult, error) {
	conflictStrategy, err := parseStrategy(strategy)
	if err != nil {
		return contracts.MergeResult{}, err
	}
	return mergeResultToContract(newMover(logDir, dryRun).MoveDir(src, dst, conflictStrategy)), nil
}

func BatchMove(ctx context.Context, items []contracts.MoveItem, strategy string, dryRun bool, logDir string) (contracts.BatchResult, error) {
	conflictStrategy, err := parseStrategy(strategy)
	if err != nil {
		return contracts.BatchResult{}, err
	}
	result := newMover(logDir, dryRun).BatchMove(ctx, toMoverItems(items, conflictStrategy))
	return batchResultToContract(result), nil
}

func BatchMoveStdin(ctx context.Context, strategy string, dryRun bool, logDir string) (contracts.BatchResult, error) {
	var items []contracts.MoveItem
	if err := json.NewDecoder(os.Stdin).Decode(&items); err != nil {
		return contracts.BatchResult{}, fmt.Errorf("JSON 解析錯誤: %v", err)
	}
	return BatchMove(ctx, items, strategy, dryRun, logDir)
}
