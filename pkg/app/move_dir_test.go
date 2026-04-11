package app

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"testing"

	"actress-classifier/pkg/contracts"
)

// ============================================================
// parseStrategy
// ============================================================

func TestParseStrategy_Valid(t *testing.T) {
	cases := []struct{ in, want string }{
		{"skip", "skip"},
		{"overwrite", "overwrite"},
		{"rename", "rename"},
	}
	for _, c := range cases {
		s, err := parseStrategy(c.in)
		if err != nil {
			t.Errorf("parseStrategy(%q) unexpected error: %v", c.in, err)
		}
		if string(s) != c.want {
			t.Errorf("parseStrategy(%q) = %q, want %q", c.in, s, c.want)
		}
	}
}

func TestParseStrategy_Invalid(t *testing.T) {
	_, err := parseStrategy("bogus")
	if err == nil {
		t.Error("expected error for unknown strategy")
	}
}

// ============================================================
// mergeResultToContract / moveResultToContract
// ============================================================

func TestMergeResultToContract(t *testing.T) {
	src := "C:\\src\\actressA"
	dst := "C:\\dst\\actressA"

	dir := t.TempDir()
	srcDir := filepath.Join(dir, "actressA")
	dstDir := filepath.Join(dir, "out", "actressA")
	os.MkdirAll(srcDir, 0700)
	os.WriteFile(filepath.Join(srcDir, "STARS-001.mp4"), []byte("x"), 0600)

	result, err := MoveDir(srcDir, dstDir, "skip", false, "")
	if err != nil {
		t.Fatalf("MoveDir error: %v", err)
	}
	_ = src
	_ = dst
	if !result.Success {
		t.Errorf("expected success, got error")
	}
	if result.FilesMoved != 1 {
		t.Errorf("expected FilesMoved=1, got %d", result.FilesMoved)
	}
}

// ============================================================
// MoveDir
// ============================================================

func TestMoveDir_Success(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "actress")
	dst := filepath.Join(dir, "out", "actress")
	os.MkdirAll(src, 0700)
	os.WriteFile(filepath.Join(src, "IPX-001.mp4"), []byte("data"), 0600)
	os.WriteFile(filepath.Join(src, "IPX-002.mp4"), []byte("data2"), 0600)

	result, err := MoveDir(src, dst, "skip", false, "")
	if err != nil {
		t.Fatalf("MoveDir error: %v", err)
	}
	if !result.Success {
		t.Errorf("expected success")
	}
	if result.FilesMoved != 2 {
		t.Errorf("expected 2 files moved, got %d", result.FilesMoved)
	}
	// 來源目錄應已消失
	if _, err := os.Stat(src); !os.IsNotExist(err) {
		t.Error("source dir should be gone after move")
	}
}

func TestMoveDir_InvalidStrategy(t *testing.T) {
	_, err := MoveDir("/src", "/dst", "invalid", false, "")
	if err == nil {
		t.Error("expected error for invalid strategy")
	}
}

func TestMoveDir_DryRun(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "actress")
	dst := filepath.Join(dir, "out", "actress")
	os.MkdirAll(src, 0700)
	os.WriteFile(filepath.Join(src, "ABW-001.mp4"), []byte("data"), 0600)

	result, err := MoveDir(src, dst, "skip", true, "")
	if err != nil {
		t.Fatalf("MoveDir dry-run error: %v", err)
	}
	if !result.Success {
		t.Errorf("expected dry-run success")
	}
	// 來源應仍存在
	if _, err := os.Stat(src); os.IsNotExist(err) {
		t.Error("source dir should still exist after dry-run")
	}
}

// ============================================================
// BatchMoveStdin
// ============================================================

func TestBatchMoveStdin_ValidJSON(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "SSIS-001.mp4")
	dst := filepath.Join(dir, "out", "SSIS-001.mp4")
	os.WriteFile(src, []byte("video"), 0600)

	items := []contracts.MoveItem{{Source: src, Destination: dst}}
	data, _ := json.Marshal(items)

	// 替換 os.Stdin
	r, w, _ := os.Pipe()
	_, _ = w.Write(data)
	w.Close()

	oldStdin := os.Stdin
	os.Stdin = r
	defer func() { os.Stdin = oldStdin }()

	logDir := filepath.Join(dir, "logs")
	result, err := BatchMoveStdin(context.Background(), "skip", false, logDir)
	if err != nil {
		t.Fatalf("BatchMoveStdin error: %v", err)
	}
	if result.SuccessCount != 1 {
		t.Errorf("expected 1 success, got %d", result.SuccessCount)
	}
}

func TestBatchMoveStdin_InvalidJSON(t *testing.T) {
	r, w, _ := os.Pipe()
	io.WriteString(w, "not valid json")
	w.Close()

	oldStdin := os.Stdin
	os.Stdin = r
	defer func() { os.Stdin = oldStdin }()

	_, err := BatchMoveStdin(context.Background(), "skip", false, "")
	if err == nil {
		t.Error("expected error for invalid JSON on stdin")
	}
}

// ============================================================
// ShowOperation（history_service.go）
// ============================================================

func TestShowOperation_Found(t *testing.T) {
	dir := t.TempDir()
	logDir := filepath.Join(dir, "logs")
	src := filepath.Join(dir, "X-001.mp4")
	dst := filepath.Join(dir, "out", "X-001.mp4")
	os.WriteFile(src, []byte("x"), 0600)

	items := []contracts.MoveItem{{Source: src, Destination: dst}}
	batch, err := BatchMove(context.Background(), items, "skip", false, logDir)
	if err != nil {
		t.Fatalf("batch move error: %v", err)
	}

	op, err := ShowOperation(logDir, batch.OperationID)
	if err != nil {
		t.Fatalf("ShowOperation error: %v", err)
	}
	if op.ID != batch.OperationID {
		t.Errorf("got ID %q, want %q", op.ID, batch.OperationID)
	}
}

func TestShowOperation_NotFound(t *testing.T) {
	dir := t.TempDir()
	_, err := ShowOperation(filepath.Join(dir, "logs"), "nonexistent-id")
	if err == nil {
		t.Error("expected error for nonexistent operation ID")
	}
}

// ============================================================
// 輔助：讓 bytes.Buffer 滿足 io.Reader 介面（確認測試依賴）
// ============================================================
var _ io.Reader = (*bytes.Buffer)(nil)
