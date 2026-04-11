package mover

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func assertMergeResultState(
	t *testing.T,
	result MergeResult,
	wantSuccess bool,
	wantDeletedSrc bool,
	wantErrorCount int,
) {
	t.Helper()
	if result.Success != wantSuccess {
		t.Fatalf("Success = %v, want %v", result.Success, wantSuccess)
	}
	if result.DeletedSrc != wantDeletedSrc {
		t.Fatalf("DeletedSrc = %v, want %v", result.DeletedSrc, wantDeletedSrc)
	}
	if len(result.Errors) != wantErrorCount {
		t.Fatalf("len(Errors) = %d, want %d", len(result.Errors), wantErrorCount)
	}
}

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
		assertMergeResultState(t, result, true, false, 0)
	})

	t.Run("nested destination is rejected", func(t *testing.T) {
		dstDir := filepath.Join(srcDir, "nested-dest")
		result := MergeResult{SourceDir: srcDir, DestDir: dstDir}

		shouldContinue := validateMoveDirDestination(srcDir, dstDir, &result)

		if shouldContinue {
			t.Fatal("目標位於來源內時不應繼續處理")
		}
		assertMergeResultState(t, result, false, false, 1)
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
		assertMergeResultState(t, result, false, false, 0)
	})
}

func TestPathsReferToSameDir_InvalidPathReturnsError(t *testing.T) {
	if _, err := pathsReferToSameDir("\x00", "\x00"); err == nil {
		t.Fatal("expected invalid path to return error")
	}
}

func TestCountMovedDirFiles_ReturnsWalkError(t *testing.T) {
	result := &MergeResult{}

	err := countMovedDirFiles(filepath.Join(t.TempDir(), "missing"), result)
	if err == nil {
		t.Fatal("expected missing directory to return walk error")
	}
	if !os.IsNotExist(err) {
		t.Fatalf("expected not-exist error, got %v", err)
	}
}
