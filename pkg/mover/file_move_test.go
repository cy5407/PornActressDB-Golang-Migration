package mover

import (
	"os"
	"path/filepath"
	"testing"
)

func TestApplyFileMode_ReturnsErrorForMissingTarget(t *testing.T) {
	err := applyFileMode(filepath.Join(t.TempDir(), "missing.txt"), 0600)
	if err == nil {
		t.Fatal("expected missing target to return error")
	}
	if !os.IsNotExist(err) {
		t.Fatalf("expected not-exist error, got %v", err)
	}
}

// TestCopyFile_DirectorySourceTriggersCopyError exercises copyFile's
// io.Copy-error branch: a directory opens for read but reading its bytes
// fails, so the partial destination is closed + removed and the error is
// wrapped. Real filesystem, no mocks.
func TestCopyFile_DirectorySourceTriggersCopyError(t *testing.T) {
	m := NewMover(t.TempDir())
	srcDir := t.TempDir() // a directory, not a regular file
	dst := filepath.Join(t.TempDir(), "out.bin")
	if err := m.copyFile(srcDir, dst); err == nil {
		t.Fatal("copyFile with directory source returned nil, want io.Copy error")
	}
	if _, err := os.Stat(dst); !os.IsNotExist(err) {
		t.Error("partial destination should be removed after copy failure")
	}
}

// TestIsSameFilePath_OneResolvableOneBad covers the errSrc||errDst guard
// when exactly one side fails to normalise (null byte in dst).
func TestIsSameFilePath_OneResolvableOneBad(t *testing.T) {
	good := filepath.Join(t.TempDir(), "real.txt")
	if err := os.WriteFile(good, []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	if isSameFilePath(good, "bad\x00path") {
		t.Error("isSameFilePath with one bad path should return false")
	}
}
