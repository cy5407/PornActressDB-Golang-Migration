package mover

import (
	"context"
	"os"
	"path/filepath"
	"strings" // 用於 Summary 訊息的字串比對測試
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
	if !result.DeletedSrc {
		t.Error("來源目錄應該被刪除 (DeletedSrc = false)")
	}
	if fileExists(srcDir) {
		t.Error("來源目錄應該被刪除（檔案系統上仍存在）")
	}
}

func TestMoveDir_PartialSkipKeepsSource(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "source")
	dstDir := filepath.Join(tempDir, "dest")

	createTestFile(t, filepath.Join(srcDir, "a.txt"), "A")
	createTestFile(t, filepath.Join(srcDir, "b.txt"), "B-src")
	createTestFile(t, filepath.Join(dstDir, "b.txt"), "B-dst")

	m := NewMover("")
	result := m.MoveDir(srcDir, dstDir, Skip)

	if !result.Success {
		t.Fatalf("MoveDir 應成功，errors=%v", result.Errors)
	}
	if result.FilesMoved != 1 {
		t.Fatalf("FilesMoved = %d, want 1", result.FilesMoved)
	}
	if result.FilesSkipped != 1 {
		t.Fatalf("FilesSkipped = %d, want 1", result.FilesSkipped)
	}
	if result.DeletedSrc {
		t.Fatal("來源目錄不應被刪除，因為仍有 skipped 檔案留在來源")
	}
	if !fileExists(filepath.Join(srcDir, "b.txt")) {
		t.Fatal("skipped 的來源檔案必須保留")
	}
}

func TestMoveDir_PreservesEmptySubdirs(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "source")
	dstDir := filepath.Join(tempDir, "dest")

	if err := os.MkdirAll(filepath.Join(srcDir, "empty", "nested"), 0755); err != nil {
		t.Fatal(err)
	}
	createTestFile(t, filepath.Join(srcDir, "has-file", "video.txt"), "ok")

	m := NewMover("")
	result := m.MoveDir(srcDir, dstDir, Skip)

	if !result.Success {
		t.Fatalf("MoveDir 應成功，errors=%v", result.Errors)
	}
	if _, err := os.Stat(filepath.Join(dstDir, "empty", "nested")); err != nil {
		t.Fatalf("空子目錄應該被保留到目標: %v", err)
	}
}

func TestMoveDir_ConflictRenameMergesIntoExistingDirectory(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "Julia")
	dstDir := filepath.Join(tempDir, "studio", "Julia")

	createTestFile(t, filepath.Join(srcDir, "same.txt"), "src")
	createTestFile(t, filepath.Join(srcDir, "nested", "keep.txt"), "nested-src")
	if err := os.MkdirAll(filepath.Join(srcDir, "empty", "nested"), 0755); err != nil {
		t.Fatal(err)
	}
	createTestFile(t, filepath.Join(dstDir, "same.txt"), "dst")
	createTestFile(t, filepath.Join(dstDir, "existing.txt"), "dst")

	m := NewMover("")
	result := m.MoveDir(srcDir, dstDir, Rename)

	if !result.Success {
		t.Fatalf("Rename 應成功，errors=%v", result.Errors)
	}
	if result.DestDir != dstDir {
		t.Fatalf("DestDir = %s, want %s", result.DestDir, dstDir)
	}
	if !fileExists(filepath.Join(dstDir, "same_1.txt")) {
		t.Fatal("同名衝突檔案應在既有目標資料夾內重新命名")
	}
	if content := readFile(t, filepath.Join(dstDir, "same_1.txt")); content != "src" {
		t.Fatalf("same_1.txt 內容錯誤，got %q", content)
	}
	if !fileExists(filepath.Join(dstDir, "same.txt")) {
		t.Fatal("原本目標中的 same.txt 應保留不變")
	}
	if content := readFile(t, filepath.Join(dstDir, "same.txt")); content != "dst" {
		t.Fatalf("原本目標 same.txt 內容錯誤，got %q", content)
	}
	if !fileExists(filepath.Join(dstDir, "existing.txt")) {
		t.Fatal("原本已存在的目標檔案應保留不變")
	}
	if !fileExists(filepath.Join(dstDir, "nested", "keep.txt")) {
		t.Fatal("非衝突檔案應直接 merge 到既有目標資料夾")
	}
	if _, err := os.Stat(filepath.Join(dstDir, "empty", "nested")); err != nil {
		t.Fatalf("空子目錄應保留在 merge 後的目標資料夾: %v", err)
	}
	if fileExists(filepath.Join(tempDir, "studio", "Julia_1")) {
		t.Fatal("不應把整個目標資料夾改名成 Julia_1")
	}
}

func TestMoveDir_DestinationInsideSource(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "source")
	dstDir := filepath.Join(srcDir, "nested-dest")

	createTestFile(t, filepath.Join(srcDir, "video.txt"), "source-video")
	createTestFile(t, filepath.Join(dstDir, "keep.txt"), "keep")

	m := NewMover("")
	m.DryRun = true
	result := m.MoveDir(srcDir, dstDir, Skip)

	if result.Success {
		t.Fatal("當目標位於來源目錄內時應安全失敗")
	}
	if result.DeletedSrc {
		t.Fatal("拒絕危險路徑時不應刪除來源目錄")
	}
	if len(result.Errors) == 0 {
		t.Fatal("應回傳明確錯誤")
	}
	if !strings.Contains(result.Errors[0].Error, "目標目錄不能位於來源目錄內") {
		t.Fatalf("錯誤訊息應說明目標在來源內，got %q", result.Errors[0].Error)
	}
	if !fileExists(srcDir) {
		t.Fatal("來源目錄應保持存在")
	}
	if !fileExists(filepath.Join(srcDir, "video.txt")) {
		t.Fatal("來源檔案不應被搬移")
	}
	if !fileExists(dstDir) {
		t.Fatal("既有目標子目錄不應被刪除")
	}
	if content := readFile(t, filepath.Join(dstDir, "keep.txt")); content != "keep" {
		t.Fatalf("既有目標子目錄內容應保持不變，got %q", content)
	}
}

// === 批次移動測試 ===

func TestBatchMoveDirs_PartialDirectoryMarkedSkipped(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "Julia")
	dstDir := filepath.Join(tempDir, "studio", "Julia")

	createTestFile(t, filepath.Join(srcDir, "a.txt"), "A")
	createTestFile(t, filepath.Join(srcDir, "b.txt"), "B-src")
	createTestFile(t, filepath.Join(dstDir, "b.txt"), "B-dst")

	m := NewMover(tempDir)
	result := m.BatchMoveDirs(context.Background(), []MoveItem{
		{Source: srcDir, Destination: dstDir, OnConflict: Skip},
	})

	if result.SuccessCount != 0 {
		t.Fatalf("SuccessCount = %d, want 0", result.SuccessCount)
	}
	if result.SkippedCount != 1 {
		t.Fatalf("SkippedCount = %d, want 1", result.SkippedCount)
	}
	if len(result.Results) != 1 || !result.Results[0].Skipped {
		t.Fatalf("目錄項目應標記為 skipped/incomplete")
	}
	if result.Status != "partial" {
		t.Fatalf("Status = %s, want partial", result.Status)
	}
}

func TestBatchMoveDirs_RenameStoresMergedDestination(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "Julia")
	dstDir := filepath.Join(tempDir, "studio", "Julia")

	createTestFile(t, filepath.Join(srcDir, "same.txt"), "src")
	createTestFile(t, filepath.Join(dstDir, "existing.txt"), "dst")
	createTestFile(t, filepath.Join(dstDir, "same.txt"), "dst-same")

	m := NewMover(tempDir)
	result := m.BatchMoveDirs(context.Background(), []MoveItem{
		{Source: srcDir, Destination: dstDir, OnConflict: Rename},
	})

	if len(result.Results) != 1 {
		t.Fatalf("len(results) = %d, want 1", len(result.Results))
	}
	if result.Results[0].Destination != dstDir {
		t.Fatalf("Destination = %s, want %s", result.Results[0].Destination, dstDir)
	}
	if result.Results[0].Renamed != "" {
		t.Fatalf("整個資料夾不應標記為 renamed，got %s", result.Results[0].Renamed)
	}
	if !fileExists(filepath.Join(dstDir, "same_1.txt")) {
		t.Fatal("批次目錄移動應在 merge 目標內對衝突檔案重新命名")
	}
	if fileExists(filepath.Join(tempDir, "studio", "Julia_1")) {
		t.Fatal("批次目錄移動不應建立 Julia_1 目錄")
	}
}

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
	result := m.BatchMove(context.Background(), items)

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
	result := m.BatchMove(context.Background(), items)

	if result.SuccessCount != 1 {
		t.Errorf("成功數應該是 1，得到 %d", result.SuccessCount)
	}
	if result.FailedCount != 1 {
		t.Errorf("失敗數應該是 1，得到 %d", result.FailedCount)
	}
}

func TestBatchMove_CancelledContextReturnsPartialResult(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "source")
	dstDir := filepath.Join(tempDir, "dest")
	createTestFile(t, filepath.Join(srcDir, "file1.txt"), "Content 1")
	createTestFile(t, filepath.Join(srcDir, "file2.txt"), "Content 2")

	items := []MoveItem{
		{Source: filepath.Join(srcDir, "file1.txt"), Destination: filepath.Join(dstDir, "file1.txt")},
		{Source: filepath.Join(srcDir, "file2.txt"), Destination: filepath.Join(dstDir, "file2.txt")},
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	m := NewMover(tempDir)
	result := m.BatchMove(ctx, items)

	if result.Status != "cancelled" {
		t.Fatalf("狀態應該是 cancelled，得到 %s", result.Status)
	}
	if result.OperationID == "" {
		t.Fatal("取消時仍應產生 operation ID")
	}
	if result.Duration == "" {
		t.Fatal("取消時仍應填入 duration")
	}
	if result.Summary != "批次移動已取消" {
		t.Fatalf("Summary 不正確，得到 %s", result.Summary)
	}
	if len(result.Results) != 0 {
		t.Fatalf("取消前未處理任何項目時，結果應為空，得到 %d", len(result.Results))
	}

	logs, err := m.ListOperations()
	if err != nil {
		t.Fatalf("列出日誌失敗: %v", err)
	}
	if len(logs) != 1 {
		t.Fatalf("應該有 1 筆日誌，得到 %d", len(logs))
	}
	if logs[0].Status != "cancelled" {
		t.Fatalf("日誌狀態應該是 cancelled，得到 %s", logs[0].Status)
	}
	if logs[0].SuccessCount != 0 || logs[0].FailedCount != 0 || logs[0].SkippedCount != 0 {
		t.Fatalf("取消前未處理任何項目時，計數應全部為 0，得到 success=%d failed=%d skipped=%d", logs[0].SuccessCount, logs[0].FailedCount, logs[0].SkippedCount)
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
	m.BatchMove(context.Background(), items)

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
	m.BatchMove(context.Background(), items)

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

// TestRollback_SummaryAllSuccess 測試全部回滾成功時的 Summary 訊息
func TestRollback_SummaryAllSuccess(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcFile := filepath.Join(tempDir, "source", "file.txt") // 來源路徑
	dstFile := filepath.Join(tempDir, "dest", "file.txt")   // 目標路徑

	createTestFile(t, srcFile, "Content")

	m := NewMover(tempDir)
	m.BatchMove(context.Background(), []MoveItem{
		{Source: srcFile, Destination: dstFile},
	})

	logs, _ := m.ListOperations()
	if len(logs) == 0 {
		t.Fatal("沒有操作日誌")
	}

	result, err := m.Rollback(logs[0].ID)
	if err != nil {
		t.Fatalf("回滾失敗: %v", err)
	}

	// 全部成功：Summary 應包含「回滾完成」關鍵字
	if !strings.Contains(result.Summary, "回滾完成") {
		t.Errorf("全部成功時 Summary 應包含「回滾完成」，實際為：%s", result.Summary)
	}
	if result.Status == "partial" {
		t.Errorf("全部成功時 Status 不應為 partial，實際為：%s", result.Status)
	}
}

// TestRollback_SummarySkippedItems 測試部分因衝突跳過時的 Summary 訊息
func TestRollback_SummarySkippedItems(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcFile := filepath.Join(tempDir, "source", "file.txt") // 來源路徑
	dstFile := filepath.Join(tempDir, "dest", "file.txt")   // 目標路徑

	createTestFile(t, srcFile, "Content")

	m := NewMover(tempDir)
	m.BatchMove(context.Background(), []MoveItem{
		{Source: srcFile, Destination: dstFile},
	})

	// 在原來源路徑預先放一個檔案，造成回滾時衝突（Skip 策略）
	createTestFile(t, srcFile, "Blocker")

	logs, _ := m.ListOperations()
	if len(logs) == 0 {
		t.Fatal("沒有操作日誌")
	}

	result, err := m.Rollback(logs[0].ID)
	if err != nil {
		t.Fatalf("回滾執行出錯: %v", err)
	}

	// 有衝突跳過：Summary 應包含「跳過」或「部分」關鍵字
	if !strings.Contains(result.Summary, "跳過") {
		t.Errorf("有衝突跳過時 Summary 應包含「跳過」，實際為：%s", result.Summary)
	}
	// Status 應設為 partial
	if result.Status != "partial" {
		t.Errorf("有衝突跳過時 Status 應為 partial，實際為：%s", result.Status)
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
