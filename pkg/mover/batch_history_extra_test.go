package mover

import (
	"strings"
	"testing"
)

func TestResolveBatchMoveStrategyFallsBackToDefault(t *testing.T) {
	m := NewMover("")
	m.DefaultStrategy = Rename

	if got := m.resolveBatchMoveStrategy(""); got != Rename {
		t.Fatalf("expected default strategy, got %q", got)
	}
	if got := m.resolveBatchMoveStrategy(Overwrite); got != Overwrite {
		t.Fatalf("expected explicit strategy, got %q", got)
	}
}

func TestBuildBatchMoveDirOutcomeFailureWithoutErrorsUsesCounts(t *testing.T) {
	m := NewMover("")
	item := MoveItem{Source: "src", Destination: "dst"}
	mr := MergeResult{DestDir: "dst", FilesMoved: 2, FilesTotal: 5, Success: false}

	moveResult, status := m.buildBatchMoveDirOutcome(item, mr)

	if status != "failed" {
		t.Fatalf("expected failed status, got %q", status)
	}
	if !strings.Contains(moveResult.Error, "移動 2/5 個檔案後失敗") {
		t.Fatalf("unexpected synthesized error: %q", moveResult.Error)
	}
}

func TestRecordBatchMoveDirOutcomeFailedRecordsError(t *testing.T) {
	var result BatchResult
	logItem := MoveLog{}
	moveResult := MoveResult{Source: "src", Destination: "dst", Error: "boom"}

	NewMover("").recordBatchMoveDirOutcome(&result, &logItem, moveResult, "failed")

	if result.FailedCount != 1 {
		t.Fatalf("expected failed count to increment, got %d", result.FailedCount)
	}
	if logItem.Status != "failed" || logItem.Error != "boom" {
		t.Fatalf("unexpected log item: %+v", logItem)
	}
	if len(result.Results) != 1 || result.Results[0].Error != "boom" {
		t.Fatalf("unexpected batch results: %+v", result.Results)
	}
}

func TestListOperationsRequiresLogDir(t *testing.T) {
	_, err := NewMover("").ListOperations()
	if err == nil || !strings.Contains(err.Error(), "未設定日誌目錄") {
		t.Fatalf("expected missing log dir error, got %v", err)
	}
}

func TestGetOperationRequiresLogDir(t *testing.T) {
	_, err := NewMover("").GetOperation("missing")
	if err == nil || !strings.Contains(err.Error(), "未設定日誌目錄") {
		t.Fatalf("expected missing log dir error, got %v", err)
	}
}

func TestApplyRollbackResultsHandlesSuccessSkippedFailedAndMissingResult(t *testing.T) {
	opLog := &OperationLog{
		Items: []MoveLog{
			{Status: "success"},
			{Status: "success"},
			{Status: "success"},
			{Status: "success"},
		},
	}
	result := BatchResult{
		Results: []MoveResult{
			{Success: true},
			{Success: true, Skipped: true},
			{Success: false},
		},
	}

	applyRollbackResults(opLog, []int{0, 1, 2, 3}, result)

	if opLog.Items[0].Status != "rolled_back" {
		t.Fatalf("expected rolled_back, got %q", opLog.Items[0].Status)
	}
	if opLog.Items[1].Status != "rollback_skipped" {
		t.Fatalf("expected rollback_skipped, got %q", opLog.Items[1].Status)
	}
	if opLog.Items[2].Status != "rollback_failed" {
		t.Fatalf("expected rollback_failed, got %q", opLog.Items[2].Status)
	}
	if opLog.Items[3].Status != "success" {
		t.Fatalf("expected item without result to remain unchanged, got %q", opLog.Items[3].Status)
	}
}

func TestRunRollbackBatchDirsWithNoItems(t *testing.T) {
	m := NewMover(t.TempDir())

	result := m.runRollbackBatch("batch_move_dirs", nil)

	if result.TotalItems != 0 || result.Status != "completed" {
		t.Fatalf("unexpected rollback result: %+v", result)
	}
}
