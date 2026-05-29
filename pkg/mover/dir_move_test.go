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

func TestPathsReferToSameDir(t *testing.T) {
	root := t.TempDir()

	same, err := pathsReferToSameDir(root, filepath.Join(root, "."))
	if err != nil {
		t.Fatalf("same-path comparison returned error: %v", err)
	}
	if !same {
		t.Fatal("expected equivalent paths to be treated as the same directory")
	}

	different, err := pathsReferToSameDir(root, filepath.Join(root, "child"))
	if err != nil {
		t.Fatalf("different-path comparison returned error: %v", err)
	}
	if different {
		t.Fatal("expected different directories to compare as different")
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

// TestMoveDirTargetPath_RelErrorOnMismatchedRoots covers the
// filepath.Rel error branch: an absolute srcRoot with a relative path
// (or vice versa) cannot be made relative.
func TestMoveDirTargetPath_RelErrorOnMismatchedRoots(t *testing.T) {
	absRoot := t.TempDir() // absolute
	if _, err := moveDirTargetPath(absRoot, "dstRoot", "relative/path"); err == nil {
		t.Fatal("moveDirTargetPath with relative path under absolute root returned nil error")
	}
}

// TestMoveDirTargetPath_DotReturnsDstRoot covers the relPath=="." branch
// (path equals srcRoot → target is dstRoot itself).
func TestMoveDirTargetPath_DotReturnsDstRoot(t *testing.T) {
	root := t.TempDir()
	got, err := moveDirTargetPath(root, "DST", root)
	if err != nil {
		t.Fatalf("moveDirTargetPath: %v", err)
	}
	if got != "DST" {
		t.Errorf("got %q, want DST (relPath==\".\")", got)
	}
}

// TestHandleMoveDirEntry_WalkErrorPropagates covers the walkErr!=nil
// early-return branch of handleMoveDirEntry.
func TestHandleMoveDirEntry_WalkErrorPropagates(t *testing.T) {
	m := NewMover(t.TempDir())
	result := &MergeResult{}
	sentinel := os.ErrPermission
	err := m.handleMoveDirEntry("src", "dst", "src/x", nil, sentinel, Skip, result)
	if err != sentinel {
		t.Fatalf("handleMoveDirEntry returned %v, want the walk error %v", err, sentinel)
	}
}

// TestHandleMoveDirEntry_TargetPathErrorPropagates covers the
// moveDirTargetPath-error branch: an absolute srcRoot with a relative
// path makes Rel fail inside handleMoveDirEntry.
func TestHandleMoveDirEntry_TargetPathErrorPropagates(t *testing.T) {
	m := NewMover(t.TempDir())
	// Need a real FileInfo for the path argument; stat any existing file.
	f := filepath.Join(t.TempDir(), "f.txt")
	if err := os.WriteFile(f, []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(f)
	if err != nil {
		t.Fatal(err)
	}
	result := &MergeResult{}
	absRoot := t.TempDir()
	// path is relative while srcRoot is absolute → Rel error.
	err = m.handleMoveDirEntry(absRoot, "dst", "relative/path", info, nil, Skip, result)
	if err == nil {
		t.Fatal("handleMoveDirEntry with un-relativisable path returned nil error")
	}
}

// TestHandleMoveDirEntry_DirEntryEnsuresTargetDir covers the info.IsDir()
// branch (creates the mirrored target directory).
func TestHandleMoveDirEntry_DirEntryEnsuresTargetDir(t *testing.T) {
	m := NewMover(t.TempDir())
	srcRoot := t.TempDir()
	sub := filepath.Join(srcRoot, "subdir")
	if err := os.Mkdir(sub, 0o750); err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(sub)
	if err != nil {
		t.Fatal(err)
	}
	dstRoot := filepath.Join(t.TempDir(), "dst")
	result := &MergeResult{}
	if err := m.handleMoveDirEntry(srcRoot, dstRoot, sub, info, nil, Skip, result); err != nil {
		t.Fatalf("handleMoveDirEntry dir entry: %v", err)
	}
	// The mirrored subdir should now exist under dstRoot.
	if st, err := os.Stat(filepath.Join(dstRoot, "subdir")); err != nil || !st.IsDir() {
		t.Errorf("expected mirrored subdir created, err=%v", err)
	}
}
