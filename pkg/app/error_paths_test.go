package app

import (
	"context"
	"strings"
	"testing"

	"actress-classifier/pkg/mover"
)

// badLogDir is a logDir path containing a null byte, which makes any
// subsequent filesystem syscall (ReadDir / ReadFile / MkdirAll) fail —
// the standard "force an error from a stdlib helper" trick.
const badLogDir = "bad\x00dir"

func TestListOperations_LogDirErrorPropagates(t *testing.T) {
	if _, err := ListOperations(badLogDir, 0); err == nil {
		t.Error("ListOperations returned nil error for unreadable log dir")
	}
}

func TestShowOperation_LogDirErrorPropagates(t *testing.T) {
	if _, err := ShowOperation(badLogDir, "any-id"); err == nil {
		t.Error("ShowOperation returned nil error for unreadable log dir")
	}
}

func TestRollback_LastWithEmptyHistoryIsError(t *testing.T) {
	logDir := t.TempDir() // empty
	_, err := Rollback(logDir, "", true)
	if err == nil {
		t.Error("Rollback last=true with no history returned nil error")
	}
	if !strings.Contains(err.Error(), "回滾") {
		t.Errorf("unexpected error wording: %v", err)
	}
}

func TestRollback_LastWithBadLogDirPropagates(t *testing.T) {
	if _, err := Rollback(badLogDir, "", true); err == nil {
		t.Error("Rollback last=true on bad logDir returned nil")
	}
}

func TestRollback_UnknownIDIsError(t *testing.T) {
	logDir := t.TempDir()
	_, err := Rollback(logDir, "nonexistent-id", false)
	if err == nil {
		t.Error("Rollback unknown id returned nil, want error from mover")
	}
}

func TestMoveFile_InvalidStrategyIsError(t *testing.T) {
	if _, err := MoveFile("a", "b", "garbage", true, t.TempDir()); err == nil {
		t.Error("MoveFile invalid strategy returned nil")
	}
}

func TestBatchMove_InvalidStrategyIsError(t *testing.T) {
	if _, err := BatchMove(context.Background(), nil, "garbage", true, t.TempDir()); err == nil {
		t.Error("BatchMove invalid strategy returned nil")
	}
}

// TestApplyDefaultConflictStrategy_PerItemOnConflictOverrides 確認 per-item
// OnConflict 不為空時保留原值,為空時 fallback 到傳入的預設策略。
// 取代舊版 TestToMoverItems_PerItemOnConflictOverrides — 收斂 DTO 後不再做
// 跨 type 轉換,但 per-item override 行為必須維持。
func TestApplyDefaultConflictStrategy_PerItemOnConflictOverrides(t *testing.T) {
	items := []mover.MoveItem{
		{Source: "a", Destination: "b", OnConflict: mover.Rename},
		{Source: "c", Destination: "d"}, // empty → falls back to default
	}
	got := applyDefaultConflictStrategy(items, mover.Skip)
	if len(got) != 2 {
		t.Fatalf("len = %d, want 2", len(got))
	}
	if got[0].OnConflict != mover.Rename {
		t.Errorf("item[0].OnConflict = %v, want rename (per-item override)", got[0].OnConflict)
	}
	if got[1].OnConflict != mover.Skip {
		t.Errorf("item[1].OnConflict = %v, want skip (fallback)", got[1].OnConflict)
	}
}
