package mover

import (
	"os"
	"path/filepath"
	"testing"
)

// 測試輔助函式：建立測試環境
func setupTestEnv(t *testing.T) (string, func()) {
	t.Helper()

	// 建立暫時目錄
	tempDir, err := os.MkdirTemp("", "mover_test_*")
	if err != nil {
		t.Fatalf("無法建立暫時目錄: %v", err)
	}

	// 清理函式
	cleanup := func() {
		os.RemoveAll(tempDir)
	}

	return tempDir, cleanup
}

// 測試輔助函式：建立測試檔案
func createTestFile(t *testing.T, path, content string) {
	t.Helper()

	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		t.Fatalf("無法建立目錄 %s: %v", dir, err)
	}

	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("無法建立檔案 %s: %v", path, err)
	}
}

// 測試輔助函式：檢查檔案是否存在
func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// 測試輔助函式：讀取檔案內容
func readFile(t *testing.T, path string) string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("無法讀取檔案 %s: %v", path, err)
	}
	return string(data)
}

// === 單檔移動測試 ===

func TestMoveFile_Basic(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	// 準備測試檔案
	srcFile := filepath.Join(tempDir, "source", "test.txt")
	dstFile := filepath.Join(tempDir, "dest", "test.txt")
	createTestFile(t, srcFile, "Hello World")

	// 執行移動
	m := NewMover("")
	result := m.MoveFile(srcFile, dstFile, Skip)

	// 驗證結果
	if !result.Success {
		t.Errorf("移動應該成功，但失敗了: %s", result.Error)
	}
	if fileExists(srcFile) {
		t.Error("來源檔案應該被刪除")
	}
	if !fileExists(dstFile) {
		t.Error("目標檔案應該存在")
	}
	if content := readFile(t, dstFile); content != "Hello World" {
		t.Errorf("檔案內容不正確，期望 'Hello World'，得到 '%s'", content)
	}
}

func TestMoveFile_SourceNotExists(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcFile := filepath.Join(tempDir, "not_exists.txt")
	dstFile := filepath.Join(tempDir, "dest.txt")

	m := NewMover("")
	result := m.MoveFile(srcFile, dstFile, Skip)

	if result.Success {
		t.Error("來源不存在時應該失敗")
	}
	if result.Error != "來源檔案不存在" {
		t.Errorf("錯誤訊息不正確: %s", result.Error)
	}
}

func TestMoveFile_ConflictSkip(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcFile := filepath.Join(tempDir, "source.txt")
	dstFile := filepath.Join(tempDir, "dest.txt")
	createTestFile(t, srcFile, "Source Content")
	createTestFile(t, dstFile, "Dest Content")

	m := NewMover("")
	result := m.MoveFile(srcFile, dstFile, Skip)

	if !result.Success {
		t.Errorf("Skip 策略應該成功: %s", result.Error)
	}
	if !result.Skipped {
		t.Error("應該標記為 Skipped")
	}
	// 來源應該保持不變
	if !fileExists(srcFile) {
		t.Error("來源檔案應該保留")
	}
	// 目標內容應該不變
	if content := readFile(t, dstFile); content != "Dest Content" {
		t.Errorf("目標內容應該不變，得到 '%s'", content)
	}
}

func TestMoveFile_ConflictOverwrite(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcFile := filepath.Join(tempDir, "source.txt")
	dstFile := filepath.Join(tempDir, "dest.txt")
	createTestFile(t, srcFile, "New Content")
	createTestFile(t, dstFile, "Old Content")

	m := NewMover("")
	result := m.MoveFile(srcFile, dstFile, Overwrite)

	if !result.Success {
		t.Errorf("Overwrite 策略應該成功: %s", result.Error)
	}
	if fileExists(srcFile) {
		t.Error("來源檔案應該被刪除")
	}
	if content := readFile(t, dstFile); content != "New Content" {
		t.Errorf("目標內容應該被覆蓋，得到 '%s'", content)
	}
}

func TestMoveFile_ConflictRename(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcFile := filepath.Join(tempDir, "source.txt")
	dstFile := filepath.Join(tempDir, "dest.txt")
	createTestFile(t, srcFile, "Source Content")
	createTestFile(t, dstFile, "Dest Content")

	m := NewMover("")
	result := m.MoveFile(srcFile, dstFile, Rename)

	if !result.Success {
		t.Errorf("Rename 策略應該成功: %s", result.Error)
	}
	if result.Renamed == "" {
		t.Error("應該有重命名路徑")
	}
	// 檢查重命名後的檔案
	expectedRenamed := filepath.Join(tempDir, "dest_1.txt")
	if result.Renamed != expectedRenamed {
		t.Errorf("重命名路徑不正確，期望 %s，得到 %s", expectedRenamed, result.Renamed)
	}
	if !fileExists(result.Renamed) {
		t.Error("重命名後的檔案應該存在")
	}
}

func TestMoveFile_DryRun(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcFile := filepath.Join(tempDir, "source.txt")
	dstFile := filepath.Join(tempDir, "dest", "test.txt")
	createTestFile(t, srcFile, "Content")

	m := NewMover("")
	m.DryRun = true
	result := m.MoveFile(srcFile, dstFile, Skip)

	if !result.Success {
		t.Errorf("DryRun 應該成功: %s", result.Error)
	}
	// 來源應該保持不變
	if !fileExists(srcFile) {
		t.Error("DryRun 模式下來源檔案應該保留")
	}
	// 目標不應該建立
	if fileExists(dstFile) {
		t.Error("DryRun 模式下目標檔案不應該建立")
	}
}

// === 目錄移動測試 ===

func TestMoveDir_Basic(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	// 建立來源目錄結構
	srcDir := filepath.Join(tempDir, "source")
	createTestFile(t, filepath.Join(srcDir, "file1.txt"), "File 1")
	createTestFile(t, filepath.Join(srcDir, "subdir", "file2.txt"), "File 2")

	dstDir := filepath.Join(tempDir, "dest")

	m := NewMover("")
	result := m.MoveDir(srcDir, dstDir, Skip)

	if !result.Success {
		t.Errorf("目錄移動應該成功: %v", result.Errors)
	}
	if result.FilesMoved != 2 {
		t.Errorf("應該移動 2 個檔案，實際移動 %d", result.FilesMoved)
	}
	if !fileExists(filepath.Join(dstDir, "file1.txt")) {
		t.Error("file1.txt 應該存在於目標")
	}
	if !fileExists(filepath.Join(dstDir, "subdir", "file2.txt")) {
		t.Error("subdir/file2.txt 應該存在於目標")
	}
	if result.DeletedSrc && fileExists(srcDir) {
		t.Error("來源目錄應該被刪除")
	}
}

// === 批次移動測試 ===

func TestBatchMove_Basic(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	// 準備測試檔案
	srcDir := filepath.Join(tempDir, "source")
	dstDir := filepath.Join(tempDir, "dest")

	createTestFile(t, filepath.Join(srcDir, "file1.txt"), "Content 1")
	createTestFile(t, filepath.Join(srcDir, "file2.txt"), "Content 2")
	createTestFile(t, filepath.Join(srcDir, "file3.txt"), "Content 3")

	items := []MoveItem{
		{Source: filepath.Join(srcDir, "file1.txt"), Destination: filepath.Join(dstDir, "file1.txt")},
		{Source: filepath.Join(srcDir, "file2.txt"), Destination: filepath.Join(dstDir, "file2.txt")},
		{Source: filepath.Join(srcDir, "file3.txt"), Destination: filepath.Join(dstDir, "file3.txt")},
	}

	m := NewMover(tempDir)
	result := m.BatchMove(items)

	if result.TotalItems != 3 {
		t.Errorf("總數應該是 3，得到 %d", result.TotalItems)
	}
	if result.SuccessCount != 3 {
		t.Errorf("成功數應該是 3，得到 %d", result.SuccessCount)
	}
	if result.FailedCount != 0 {
		t.Errorf("失敗數應該是 0，得到 %d", result.FailedCount)
	}
}

func TestBatchMove_PartialFailure(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "source")
	dstDir := filepath.Join(tempDir, "dest")

	createTestFile(t, filepath.Join(srcDir, "exists.txt"), "Content")
	// not_exists.txt 不建立

	items := []MoveItem{
		{Source: filepath.Join(srcDir, "exists.txt"), Destination: filepath.Join(dstDir, "exists.txt")},
		{Source: filepath.Join(srcDir, "not_exists.txt"), Destination: filepath.Join(dstDir, "not_exists.txt")},
	}

	m := NewMover(tempDir)
	result := m.BatchMove(items)

	if result.SuccessCount != 1 {
		t.Errorf("成功數應該是 1，得到 %d", result.SuccessCount)
	}
	if result.FailedCount != 1 {
		t.Errorf("失敗數應該是 1，得到 %d", result.FailedCount)
	}
}

// === 操作日誌測試 ===

func TestOperationLog_SaveAndList(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "source")
	dstDir := filepath.Join(tempDir, "dest")
	createTestFile(t, filepath.Join(srcDir, "test.txt"), "Content")

	items := []MoveItem{
		{Source: filepath.Join(srcDir, "test.txt"), Destination: filepath.Join(dstDir, "test.txt")},
	}

	m := NewMover(tempDir)
	m.BatchMove(items)

	// 列出操作日誌
	logs, err := m.ListOperations()
	if err != nil {
		t.Fatalf("列出日誌失敗: %v", err)
	}
	if len(logs) != 1 {
		t.Errorf("應該有 1 筆日誌，得到 %d", len(logs))
	}
	if logs[0].Status != "completed" {
		t.Errorf("日誌狀態應該是 completed，得到 %s", logs[0].Status)
	}
}

// === 回滾測試 ===

func TestRollback_Basic(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "source")
	dstDir := filepath.Join(tempDir, "dest")
	srcFile := filepath.Join(srcDir, "test.txt")
	dstFile := filepath.Join(dstDir, "test.txt")

	createTestFile(t, srcFile, "Content")

	items := []MoveItem{
		{Source: srcFile, Destination: dstFile},
	}

	m := NewMover(tempDir)
	m.BatchMove(items)

	// 確認檔案已移動
	if fileExists(srcFile) {
		t.Error("移動後來源應該不存在")
	}
	if !fileExists(dstFile) {
		t.Error("移動後目標應該存在")
	}

	// 取得操作 ID
	logs, _ := m.ListOperations()
	if len(logs) == 0 {
		t.Fatal("沒有操作日誌")
	}

	// 執行回滾
	_, err := m.Rollback(logs[0].ID)
	if err != nil {
		t.Fatalf("回滾失敗: %v", err)
	}

	// 確認檔案已回滾
	if !fileExists(srcFile) {
		t.Error("回滾後來源應該存在")
	}
	if fileExists(dstFile) {
		t.Error("回滾後目標應該不存在")
	}
}

// === 效能測試 ===

func BenchmarkMoveFile(b *testing.B) {
	tempDir, err := os.MkdirTemp("", "mover_bench_*")
	if err != nil {
		b.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	m := NewMover("")

	for i := 0; i < b.N; i++ {
		srcFile := filepath.Join(tempDir, "src", "bench.txt")
		dstFile := filepath.Join(tempDir, "dst", "bench.txt")

		os.MkdirAll(filepath.Dir(srcFile), 0755)
		os.WriteFile(srcFile, []byte("benchmark content"), 0644)

		m.MoveFile(srcFile, dstFile, Skip)

		// 清理以便下次迭代
		os.RemoveAll(filepath.Join(tempDir, "src"))
		os.RemoveAll(filepath.Join(tempDir, "dst"))
	}
}
