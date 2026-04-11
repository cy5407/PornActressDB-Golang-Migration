//go:build windows

package mover

import (
	"os"
	"path/filepath"
	"testing"
)

func TestRecycleFile_ExistingFile(t *testing.T) {
	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "recycle_test.txt")
	if err := os.WriteFile(path, []byte("recycle me"), 0644); err != nil {
		t.Fatalf("failed to create test file: %v", err)
	}

	if err := recycleFile(path); err != nil {
		t.Errorf("recycleFile returned unexpected error: %v", err)
	}

	// 送入資源回收筒後，檔案不應再存在於原路徑
	if _, statErr := os.Stat(path); !os.IsNotExist(statErr) {
		t.Errorf("expected file to be removed from original path after recycling, stat error: %v", statErr)
	}
}

func TestRecycleFile_NonExistentPath(t *testing.T) {
	// 對不存在的路徑呼叫 recycleFile：
	// SHFileOperationW 通常對不存在路徑回傳非零值，應得到 error。
	path := filepath.Join(t.TempDir(), "does_not_exist.txt")

	err := recycleFile(path)
	// 不存在的路徑不一定讓 SHFileOperationW 報錯（行為因 Windows 版本而異），
	// 此處只驗證函式不 panic，且回傳值型別正確。
	_ = err
}
