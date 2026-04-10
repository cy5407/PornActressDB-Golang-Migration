package mover

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestValidateMoveDirDestination(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "source")
	createTestFile(t, filepath.Join(srcDir, "video.txt"), "source-video")

	t.Run("same path succeeds without moving", func(t *testing.T) {
		result := MergeResult{SourceDir: srcDir, DestDir: srcDir}

		shouldContinue := validateMoveDirDestination(srcDir, srcDir, &result)

		if shouldContinue {
			t.Fatal("source == destination 時不應繼續處理")
		}
		if !result.Success {
			t.Fatal("source == destination 時應視為成功")
		}
		if result.DeletedSrc {
			t.Fatal("source == destination 時不應刪除來源")
		}
		if len(result.Errors) != 0 {
			t.Fatalf("source == destination 時不應回傳錯誤: %+v", result.Errors)
		}
	})

	t.Run("nested destination is rejected", func(t *testing.T) {
		dstDir := filepath.Join(srcDir, "nested-dest")
		result := MergeResult{SourceDir: srcDir, DestDir: dstDir}

		shouldContinue := validateMoveDirDestination(srcDir, dstDir, &result)

		if shouldContinue {
			t.Fatal("目標位於來源內時不應繼續處理")
		}
		if result.Success {
			t.Fatal("目標位於來源內時應回報失敗")
		}
		if len(result.Errors) != 1 {
			t.Fatalf("應回傳 1 個錯誤，got %d", len(result.Errors))
		}
		if !strings.Contains(result.Errors[0].Error, "目標目錄不能位於來源目錄內") {
			t.Fatalf("錯誤訊息不正確: %q", result.Errors[0].Error)
		}
	})

	t.Run("separate destination continues", func(t *testing.T) {
		dstDir := filepath.Join(tempDir, "dest")
		result := MergeResult{SourceDir: srcDir, DestDir: dstDir}

		shouldContinue := validateMoveDirDestination(srcDir, dstDir, &result)

		if !shouldContinue {
			t.Fatal("一般目標路徑應繼續後續處理")
		}
		if result.Success {
			t.Fatal("尚未完成移動前不應提前標記成功")
		}
		if len(result.Errors) != 0 {
			t.Fatalf("一般目標路徑不應預先產生錯誤: %+v", result.Errors)
		}
	})
}
