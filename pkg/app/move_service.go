package app

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

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

// applyDefaultConflictStrategy 對 items 中未指定 OnConflict 的項目填入預設策略。
// 取代舊版 toMoverItems(items []contracts.MoveItem, strategy) — 收斂 DTO 之後不必再做 type 轉換,
// 只需處理 per-item override fallback。
func applyDefaultConflictStrategy(items []mover.MoveItem, strategy mover.ConflictStrategy) []mover.MoveItem {
	out := make([]mover.MoveItem, 0, len(items))
	for _, item := range items {
		if item.OnConflict == "" {
			item.OnConflict = strategy
		}
		out = append(out, item)
	}
	return out
}

func MoveFile(src, dst, strategy string, dryRun bool, logDir string) (mover.MoveResult, error) {
	conflictStrategy, err := parseStrategy(strategy)
	if err != nil {
		return mover.MoveResult{}, err
	}
	return newMover(logDir, dryRun).MoveFile(src, dst, conflictStrategy), nil
}

func MoveDir(src, dst, strategy string, dryRun bool, logDir string) (mover.MergeResult, error) {
	conflictStrategy, err := parseStrategy(strategy)
	if err != nil {
		return mover.MergeResult{}, err
	}
	return newMover(logDir, dryRun).MoveDir(src, dst, conflictStrategy), nil
}

func BatchMove(ctx context.Context, items []mover.MoveItem, strategy string, dryRun bool, logDir string) (mover.BatchResult, error) {
	conflictStrategy, err := parseStrategy(strategy)
	if err != nil {
		return mover.BatchResult{}, err
	}
	return newMover(logDir, dryRun).BatchMove(ctx, applyDefaultConflictStrategy(items, conflictStrategy)), nil
}

func BatchMoveStdin(ctx context.Context, strategy string, dryRun bool, logDir string) (mover.BatchResult, error) {
	var items []mover.MoveItem
	if err := json.NewDecoder(os.Stdin).Decode(&items); err != nil {
		return mover.BatchResult{}, fmt.Errorf("JSON 解析錯誤: %v", err)
	}
	return BatchMove(ctx, items, strategy, dryRun, logDir)
}
