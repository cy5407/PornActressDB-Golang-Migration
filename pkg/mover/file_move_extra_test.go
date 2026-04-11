package mover

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// ============================================================
// validateMoveFileSource — 來源是目錄
// ============================================================

func TestMoveFile_SourceIsDirectory(t *testing.T) {
	dir := t.TempDir()
	srcDir := filepath.Join(dir, "aDir")
	os.MkdirAll(srcDir, 0700)
	dst := filepath.Join(dir, "dst.txt")

	m := NewMover("")
	result := m.MoveFile(srcDir, dst, Skip)

	if result.Success {
		t.Error("expected failure when source is a directory")
	}
	if !strings.Contains(result.Error, "目錄") {
		t.Errorf("expected directory error message, got: %s", result.Error)
	}
}

// ============================================================
// MoveFile — src == dst（同路徑保護）
// ============================================================

func TestMoveFile_SamePath(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "same.mp4")
	os.WriteFile(path, []byte("content"), 0600)

	m := NewMover("")
	result := m.MoveFile(path, path, Skip)

	if !result.Success {
		t.Errorf("expected success for same-path, got: %s", result.Error)
	}
	if !result.Skipped {
		t.Error("expected Skipped=true for same-path")
	}
}

// ============================================================
// resolveMoveFileConflict — Rename 策略
// ============================================================

func TestMoveFile_ConflictRenameExtra(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src.txt")
	dst := filepath.Join(dir, "dst.txt")
	os.WriteFile(src, []byte("src content"), 0600)
	os.WriteFile(dst, []byte("original dst"), 0600) // 目標已存在

	m := NewMover("")
	result := m.MoveFile(src, dst, Rename)

	if !result.Success {
		t.Errorf("Rename strategy should succeed: %s", result.Error)
	}
	if result.Renamed == "" {
		t.Error("expected Renamed path to be set")
	}
	// 原始目標應保持不變
	data, _ := os.ReadFile(dst)
	if string(data) != "original dst" {
		t.Errorf("original dst should be untouched, got: %s", data)
	}
	// 重命名後的檔案應存在
	if _, err := os.Stat(result.Renamed); os.IsNotExist(err) {
		t.Errorf("renamed file %q should exist", result.Renamed)
	}
}

// ============================================================
// resolveMoveFileConflict — Overwrite 策略
// ============================================================

func TestMoveFile_ConflictOverwriteExtra(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src.txt")
	dst := filepath.Join(dir, "dst.txt")
	os.WriteFile(src, []byte("new content"), 0600)
	os.WriteFile(dst, []byte("old content"), 0600)

	m := NewMover("")
	result := m.MoveFile(src, dst, Overwrite)

	if !result.Success {
		t.Errorf("Overwrite strategy should succeed: %s", result.Error)
	}
	// 目標應被新內容取代
	data, _ := os.ReadFile(dst)
	if string(data) != "new content" {
		t.Errorf("dst content should be 'new content', got: %s", data)
	}
	// 來源應消失
	if _, err := os.Stat(src); !os.IsNotExist(err) {
		t.Error("source should be removed after overwrite")
	}
}

// ============================================================
// resolveMoveFileConflict — Merge 策略（對單檔案回傳錯誤）
// ============================================================

func TestMoveFile_ConflictMerge(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src.txt")
	dst := filepath.Join(dir, "dst.txt")
	os.WriteFile(src, []byte("src"), 0600)
	os.WriteFile(dst, []byte("dst"), 0600) // 目標存在以觸發衝突分支

	m := NewMover("")
	result := m.MoveFile(src, dst, Merge)

	if result.Success {
		t.Error("Merge strategy on single file should not succeed")
	}
	if !strings.Contains(result.Error, "Merge") {
		t.Errorf("expected Merge error, got: %s", result.Error)
	}
}

// ============================================================
// resolveMoveFileConflict — 未知策略
// ============================================================

func TestMoveFile_ConflictUnknown(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src.txt")
	dst := filepath.Join(dir, "dst.txt")
	os.WriteFile(src, []byte("src"), 0600)
	os.WriteFile(dst, []byte("dst"), 0600)

	m := NewMover("")
	result := m.MoveFile(src, dst, ConflictStrategy("unknown"))

	if result.Success {
		t.Error("unknown strategy should not succeed")
	}
}

// ============================================================
// replaceFileSafely — 直接測試
// ============================================================

func TestReplaceFileSafely(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "src.txt")
	dst := filepath.Join(dir, "dst.txt")
	os.WriteFile(src, []byte("new"), 0600)
	os.WriteFile(dst, []byte("old"), 0600)

	m := NewMover("")
	err := m.replaceFileSafely(src, dst)
	if err != nil {
		t.Fatalf("replaceFileSafely error: %v", err)
	}

	data, _ := os.ReadFile(dst)
	if string(data) != "new" {
		t.Errorf("dst content should be 'new', got: %s", data)
	}
	if _, statErr := os.Stat(src); !os.IsNotExist(statErr) {
		t.Error("source should be removed after replace")
	}
}

// ============================================================
// GetOperation — 直接透過 mover
// ============================================================

func TestGetOperation_Found(t *testing.T) {
	dir := t.TempDir()
	logDir := filepath.Join(dir, "logs")
	src := filepath.Join(dir, "STARS-001.mp4")
	dst := filepath.Join(dir, "out", "STARS-001.mp4")
	os.WriteFile(src, []byte("content"), 0600)

	m := NewMover(logDir)
	items := []MoveItem{{Source: src, Destination: dst, OnConflict: Skip}}
	result := m.BatchMove(context.Background(), items)

	op, err := m.GetOperation(result.OperationID)
	if err != nil {
		t.Fatalf("GetOperation error: %v", err)
	}
	if op.ID != result.OperationID {
		t.Errorf("got ID %q, want %q", op.ID, result.OperationID)
	}
}

func TestGetOperation_NotFound(t *testing.T) {
	dir := t.TempDir()
	m := NewMover(filepath.Join(dir, "logs"))
	_, err := m.GetOperation("nonexistent-id")
	if err == nil {
		t.Error("expected error for nonexistent ID")
	}
}
