package app

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"actress-classifier/pkg/contracts"
)

// ============================================================
// ScanFiles
// ============================================================

func TestShouldSkipScanDirectory(t *testing.T) {
	dir := t.TempDir()
	sub := filepath.Join(dir, "sub")
	if err := os.Mkdir(sub, 0700); err != nil {
		t.Fatal(err)
	}

	absDir, err := filepath.Abs(dir)
	if err != nil {
		t.Fatal(err)
	}

	skip, err := shouldSkipScanDirectory(dir, false, absDir)
	if err != nil {
		t.Fatalf("unexpected error for root dir: %v", err)
	}
	if skip {
		t.Fatal("root directory should not be skipped")
	}

	skip, err = shouldSkipScanDirectory(sub, false, absDir)
	if err != nil {
		t.Fatalf("unexpected error for subdir: %v", err)
	}
	if !skip {
		t.Fatal("nested directory should be skipped when recursive is false")
	}

	skip, err = shouldSkipScanDirectory(sub, true, absDir)
	if err != nil {
		t.Fatalf("unexpected error for recursive scan: %v", err)
	}
	if skip {
		t.Fatal("nested directory should not be skipped when recursive is true")
	}
}

func TestScanFiles_NonExistentDir(t *testing.T) {
	_, err := ScanFiles(ScanRequest{Dir: "/nonexistent/path", Workers: 1})
	if err == nil {
		t.Fatal("expected error for non-existent directory")
	}
}

func TestScanFiles_EmptyDir(t *testing.T) {
	dir := t.TempDir()
	results, err := ScanFiles(ScanRequest{Dir: dir, Workers: 2})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(results) != 0 {
		t.Errorf("expected 0 results, got %d", len(results))
	}
}

func TestScanFiles_DetectsCodes(t *testing.T) {
	dir := t.TempDir()
	files := []string{"STARS-707.mp4", "ABW-001.mkv", "not-a-code.txt"}
	for _, f := range files {
		if err := os.WriteFile(filepath.Join(dir, f), []byte{}, 0600); err != nil {
			t.Fatal(err)
		}
	}

	results, err := ScanFiles(ScanRequest{Dir: dir, Workers: 2})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(results) != 2 {
		t.Errorf("expected 2 results (mp4+mkv), got %d", len(results))
	}
	codes := make(map[string]bool)
	for _, r := range results {
		codes[r.Code] = true
	}
	if !codes["STARS-707"] {
		t.Error("expected STARS-707 in results")
	}
	if !codes["ABW-001"] {
		t.Error("expected ABW-001 in results")
	}
}

func TestScanFiles_Recursive(t *testing.T) {
	dir := t.TempDir()
	sub := filepath.Join(dir, "sub")
	if err := os.Mkdir(sub, 0700); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(filepath.Join(dir, "SSIS-001.mp4"), []byte{}, 0600)
	os.WriteFile(filepath.Join(sub, "MIAA-002.mp4"), []byte{}, 0600)

	// 非遞迴：只找到 1 筆
	results, err := ScanFiles(ScanRequest{Dir: dir, Workers: 2, Recursive: false})
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 1 {
		t.Errorf("non-recursive: expected 1 result, got %d", len(results))
	}

	// 遞迴：找到 2 筆
	results, err = ScanFiles(ScanRequest{Dir: dir, Workers: 2, Recursive: true})
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 2 {
		t.Errorf("recursive: expected 2 results, got %d", len(results))
	}
}

func TestScanFiles_Workers(t *testing.T) {
	dir := t.TempDir()
	for i := 0; i < 10; i++ {
		name := filepath.Join(dir, "IPX-"+string(rune('0'+i))+"00.mp4")
		os.WriteFile(name, []byte{}, 0600)
	}
	// workers=1 和 workers=4 結果數量應相同
	r1, _ := ScanFiles(ScanRequest{Dir: dir, Workers: 1})
	r4, _ := ScanFiles(ScanRequest{Dir: dir, Workers: 4})
	if len(r1) != len(r4) {
		t.Errorf("workers=1 got %d, workers=4 got %d, should be equal", len(r1), len(r4))
	}
}

// ============================================================
// MoveFile / BatchMove
// ============================================================

func TestMoveFile_Success(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src.mp4")
	dst := filepath.Join(dir, "sub", "dst.mp4")
	os.WriteFile(src, []byte("test"), 0600)

	result, err := MoveFile(src, dst, "skip", false, "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !result.Success {
		t.Errorf("expected success, got error: %s", result.Error)
	}
	if _, err := os.Stat(dst); os.IsNotExist(err) {
		t.Error("destination file does not exist after move")
	}
}

func TestMoveFile_DryRun(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src.mp4")
	dst := filepath.Join(dir, "dst.mp4")
	os.WriteFile(src, []byte("test"), 0600)

	result, err := MoveFile(src, dst, "skip", true, "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !result.Success {
		t.Errorf("expected dry-run success")
	}
	// dry-run 不應搬動檔案
	if _, err := os.Stat(src); os.IsNotExist(err) {
		t.Error("source should still exist after dry-run")
	}
}

func TestBatchMove_MultipleFiles(t *testing.T) {
	dir := t.TempDir()
	items := []contracts.MoveItem{}
	for _, code := range []string{"STARS-001", "ABW-002", "IPX-003"} {
		src := filepath.Join(dir, code+".mp4")
		dst := filepath.Join(dir, "out", code+".mp4")
		os.WriteFile(src, []byte(code), 0600)
		items = append(items, contracts.MoveItem{Source: src, Destination: dst})
	}

	logDir := filepath.Join(dir, "logs")
	result, err := BatchMove(context.Background(), items, "skip", false, logDir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.SuccessCount != 3 {
		t.Errorf("expected 3 successes, got %d", result.SuccessCount)
	}
	if result.FailedCount != 0 {
		t.Errorf("expected 0 failures, got %d", result.FailedCount)
	}
}

// ============================================================
// ListOperations / Rollback
// ============================================================

func TestListOperations_EmptyLogDir(t *testing.T) {
	dir := t.TempDir()
	logs, err := ListOperations(filepath.Join(dir, "logs"), 0)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(logs) != 0 {
		t.Errorf("expected 0 logs, got %d", len(logs))
	}
}

func TestRollbackLast_NoHistory(t *testing.T) {
	dir := t.TempDir()
	_, err := Rollback(filepath.Join(dir, "logs"), "", true)
	if err == nil {
		t.Error("expected error when no history exists")
	}
}

func TestBatchAndRollback_RoundTrip(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src", "STARS-707.mp4")
	dst := filepath.Join(dir, "dst", "SOD", "STARS-707.mp4")
	os.MkdirAll(filepath.Dir(src), 0700)
	os.WriteFile(src, []byte("content"), 0600)

	logDir := filepath.Join(dir, "logs")
	items := []contracts.MoveItem{{Source: src, Destination: dst}}

	// 搬移
	batchResult, err := BatchMove(context.Background(), items, "skip", false, logDir)
	if err != nil || batchResult.SuccessCount != 1 {
		t.Fatalf("batch move failed: %v, result: %+v", err, batchResult)
	}

	// 確認目的地有檔案
	if _, statErr := os.Stat(dst); os.IsNotExist(statErr) {
		t.Fatal("destination file missing after batch move")
	}

	// 回滾
	rollback, err := Rollback(logDir, "", true)
	if err != nil {
		t.Fatalf("rollback failed: %v", err)
	}
	if rollback.SuccessCount != 1 {
		t.Errorf("expected 1 rollback success, got %d", rollback.SuccessCount)
	}

	// 確認來源回來了
	if _, err := os.Stat(src); os.IsNotExist(err) {
		t.Error("source file should be restored after rollback")
	}
}
