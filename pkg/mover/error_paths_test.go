package mover

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

// helper to make a mover with a per-test log dir
func mkMover(t *testing.T) *Mover {
	t.Helper()
	return NewMover(t.TempDir())
}

// --- copyFile error paths ---------------------------------------------

func TestCopyFile_MissingSourceErrors(t *testing.T) {
	m := mkMover(t)
	dst := filepath.Join(t.TempDir(), "out.txt")
	if err := m.copyFile(filepath.Join(t.TempDir(), "missing.txt"), dst); err == nil {
		t.Error("copyFile missing source returned nil")
	}
}

func TestCopyFile_BadDestinationErrors(t *testing.T) {
	m := mkMover(t)
	src := filepath.Join(t.TempDir(), "src.txt")
	if err := os.WriteFile(src, []byte("data"), 0o600); err != nil {
		t.Fatal(err)
	}
	// Destination with null byte → OpenFile fails.
	if err := m.copyFile(src, filepath.Join(t.TempDir(), "bad\x00name")); err == nil {
		t.Error("copyFile bad dst returned nil")
	}
}

func TestCopyFile_DestinationDirAsFileErrors(t *testing.T) {
	m := mkMover(t)
	src := filepath.Join(t.TempDir(), "src.txt")
	if err := os.WriteFile(src, []byte("data"), 0o600); err != nil {
		t.Fatal(err)
	}
	// Destination path resolves to an existing directory — OpenFile O_TRUNC
	// on a directory must fail at the syscall layer.
	dstDir := t.TempDir()
	if err := m.copyFile(src, dstDir); err == nil {
		t.Error("copyFile to existing dir-as-file returned nil")
	}
}

// --- replaceFileSafely error paths ------------------------------------

func TestReplaceFileSafely_MissingSourceErrors(t *testing.T) {
	m := mkMover(t)
	dst := filepath.Join(t.TempDir(), "exists.txt")
	if err := os.WriteFile(dst, []byte("old"), 0o600); err != nil {
		t.Fatal(err)
	}
	err := m.replaceFileSafely(filepath.Join(t.TempDir(), "missing.txt"), dst)
	if err == nil {
		t.Error("replaceFileSafely missing source returned nil")
	}
}

// --- generateUniqueName collision path --------------------------------

func TestGenerateUniqueName_AvoidsExistingCollision(t *testing.T) {
	m := mkMover(t)
	dir := t.TempDir()
	// Create primary AND first numeric candidate so generateUniqueName
	// loops at least twice before claiming a slot.
	primary := filepath.Join(dir, "file.txt")
	collision1 := filepath.Join(dir, "file_1.txt")
	for _, p := range []string{primary, collision1} {
		if err := os.WriteFile(p, []byte("x"), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	got := m.generateUniqueName(primary)
	if got == primary || got == collision1 {
		t.Errorf("generateUniqueName returned existing path %q", got)
	}
	if !strings.HasPrefix(filepath.Base(got), "file_") {
		t.Errorf("expected file_N.txt pattern, got %q", filepath.Base(got))
	}
}

// --- MoveFile / ensure / resolve error paths --------------------------

func TestMoveFile_DestinationParentCannotBeCreated(t *testing.T) {
	m := mkMover(t)
	src := filepath.Join(t.TempDir(), "src.txt")
	if err := os.WriteFile(src, []byte("data"), 0o600); err != nil {
		t.Fatal(err)
	}
	// Destination under a null-byte path — MkdirAll fails immediately.
	res := m.MoveFile(src, filepath.Join("bad\x00dir", "out.txt"), Skip)
	if res.Success {
		t.Errorf("expected failure, got Success=true result=%+v", res)
	}
	if res.Error == "" {
		t.Error("expected non-empty Error message")
	}
}

func TestMoveFile_OverwriteFailsWhenReplaceErrors(t *testing.T) {
	m := mkMover(t)
	srcDir := t.TempDir()
	src := filepath.Join(srcDir, "src.txt")
	if err := os.WriteFile(src, []byte("new"), 0o600); err != nil {
		t.Fatal(err)
	}
	dstDir := t.TempDir()
	dst := filepath.Join(dstDir, "dst.txt")
	if err := os.WriteFile(dst, []byte("old"), 0o600); err != nil {
		t.Fatal(err)
	}
	// Sabotage: remove src after stat passes (race window). Easier: pass a
	// dst that resolves to a directory so the rename-via-tmp inside
	// replaceFileSafely fails.
	if err := os.Remove(src); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(src, 0o750); err != nil {
		t.Fatal(err)
	}
	res := m.MoveFile(src, dst, Overwrite)
	if res.Success {
		t.Errorf("expected failure (src is now a dir), got %+v", res)
	}
}

// --- validateMoveDirSource / Destination error paths ------------------

func TestValidateMoveDirSource_NonExistent(t *testing.T) {
	res := &MergeResult{}
	if validateMoveDirSource(filepath.Join(t.TempDir(), "no-such"), res) {
		t.Error("validateMoveDirSource returned true for missing dir")
	}
	if len(res.Errors) == 0 {
		t.Error("expected error appended to result.Errors")
	}
}

func TestValidateMoveDirSource_NotADir(t *testing.T) {
	srcFile := filepath.Join(t.TempDir(), "not-a-dir.txt")
	if err := os.WriteFile(srcFile, []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	res := &MergeResult{}
	if validateMoveDirSource(srcFile, res) {
		t.Error("validateMoveDirSource returned true for file")
	}
}

func TestValidateMoveDirDestination_NestedInSourceErrors(t *testing.T) {
	src := t.TempDir()
	dst := filepath.Join(src, "subdir") // nested
	res := &MergeResult{}
	if validateMoveDirDestination(src, dst, res) {
		t.Error("validateMoveDirDestination accepted nested dst")
	}
	if len(res.Errors) == 0 {
		t.Error("expected error appended")
	}
}

func TestValidateMoveDirDestination_BadInputsErrorsViaIsSameOrNested(t *testing.T) {
	res := &MergeResult{}
	if validateMoveDirDestination("bad\x00src", t.TempDir(), res) {
		t.Error("validateMoveDirDestination accepted bad source")
	}
}

// --- pathsReferToSameDir error path -----------------------------------

func TestPathsReferToSameDir_BadInputReturnsError(t *testing.T) {
	if _, err := pathsReferToSameDir("bad\x00src", t.TempDir()); err == nil {
		t.Error("pathsReferToSameDir bad src returned nil error")
	}
	if _, err := pathsReferToSameDir(t.TempDir(), "bad\x00dst"); err == nil {
		t.Error("pathsReferToSameDir bad dst returned nil error")
	}
}

// --- tryFastMoveDirRename ---------------------------------------------

func TestTryFastMoveDirRename_DryRunReturnsFalse(t *testing.T) {
	m := mkMover(t)
	m.DryRun = true
	src := t.TempDir()
	res := &MergeResult{}
	if m.tryFastMoveDirRename(src, filepath.Join(t.TempDir(), "dst"), res) {
		t.Error("tryFastMoveDirRename returned true in DryRun")
	}
}

func TestTryFastMoveDirRename_DestinationExistsReturnsFalse(t *testing.T) {
	m := mkMover(t)
	src := t.TempDir()
	dst := t.TempDir() // already exists
	res := &MergeResult{}
	if m.tryFastMoveDirRename(src, dst, res) {
		t.Error("tryFastMoveDirRename returned true when dst exists")
	}
}

func TestTryFastMoveDirRename_HappyPathCountsFiles(t *testing.T) {
	m := mkMover(t)
	src := filepath.Join(t.TempDir(), "src")
	if err := os.MkdirAll(filepath.Join(src, "sub"), 0o750); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"a.txt", "sub/b.txt"} {
		p := filepath.Join(src, filepath.FromSlash(name))
		if err := os.WriteFile(p, []byte("data"), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	dst := filepath.Join(t.TempDir(), "dst-target")
	res := &MergeResult{}
	if !m.tryFastMoveDirRename(src, dst, res) {
		t.Errorf("tryFastMoveDirRename failed: %+v", res)
	}
	if res.FilesMoved != 2 {
		t.Errorf("FilesMoved = %d, want 2", res.FilesMoved)
	}
	if !res.DeletedSrc {
		t.Error("DeletedSrc = false, want true after fast rename")
	}
}

// --- moveDirTargetPath ------------------------------------------------

func TestMoveDirTargetPath_DotRelMeansDstRoot(t *testing.T) {
	got, err := moveDirTargetPath(`C:\src`, `C:\dst`, `C:\src`)
	if err != nil {
		t.Fatalf("err = %v", err)
	}
	if runtime.GOOS == "windows" && got != `C:\dst` {
		t.Errorf("got = %q, want C:\\dst", got)
	}
}

// --- ensureMoveDirTargetDir DryRun ------------------------------------

func TestEnsureMoveDirTargetDir_DryRunSkipsMkdir(t *testing.T) {
	m := mkMover(t)
	m.DryRun = true
	// A path with null byte would normally cause MkdirAll error; DryRun
	// must short-circuit before any FS call.
	if err := m.ensureMoveDirTargetDir("bad\x00path"); err != nil {
		t.Errorf("DryRun should bypass FS, got err=%v", err)
	}
}

// --- ensureMoveFileDestinationDir DryRun ------------------------------

func TestEnsureMoveFileDestinationDir_DryRunBypasses(t *testing.T) {
	m := mkMover(t)
	m.DryRun = true
	res := &MoveResult{}
	if !m.ensureMoveFileDestinationDir("bad\x00path/file.txt", res) {
		t.Error("DryRun should return true regardless of dst")
	}
}

// --- isSameFilePath error path ---------------------------------------

func TestIsSameFilePath_BadInputsReturnFalseSafely(t *testing.T) {
	if isSameFilePath("bad\x00a", "bad\x00b") {
		t.Error("isSameFilePath returned true for bad input")
	}
}

// --- history.go: ListOperations / saveOperationLog / loadOperationLog --

func TestListOperations_SkipsCorruptJSONEntries(t *testing.T) {
	m := mkMover(t)
	opsDir := filepath.Join(m.LogDir, "operations")
	if err := os.MkdirAll(opsDir, 0o750); err != nil {
		t.Fatal(err)
	}
	// One valid + one corrupt + one wrong-extension entry; ListOperations
	// must return the single valid entry.
	if err := os.WriteFile(filepath.Join(opsDir, "good.json"),
		[]byte(`{"id":"ok","timestamp":"2026-05-29T00:00:00Z"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(opsDir, "bad.json"),
		[]byte(`{not json`), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(opsDir, "readme.txt"),
		[]byte(`ignored`), 0o600); err != nil {
		t.Fatal(err)
	}
	logs, err := m.ListOperations()
	if err != nil {
		t.Fatalf("ListOperations: %v", err)
	}
	if len(logs) != 1 {
		t.Errorf("len = %d, want 1 (good only)", len(logs))
	}
}

func TestListOperations_NoLogDirSetIsError(t *testing.T) {
	m := &Mover{}
	if _, err := m.ListOperations(); err == nil {
		t.Error("ListOperations on empty LogDir returned nil error")
	}
}

// ListOperations on a file-as-dir is platform-specific (Windows often
// returns "" with no error from ReadDir on a file). Skip — error
// surface here is not portable enough for a real cross-platform test.

func TestSaveOperationLog_NoLogDirIsNoOp(t *testing.T) {
	m := &Mover{} // empty LogDir
	if err := m.saveOperationLog(&OperationLog{}); err != nil {
		t.Errorf("saveOperationLog should be no-op when LogDir is empty, got %v", err)
	}
}

func TestSaveOperationLog_BadLogDirPropagates(t *testing.T) {
	m := &Mover{LogDir: "bad\x00dir"}
	if err := m.saveOperationLog(&OperationLog{Timestamp: time.Now(), ID: "x"}); err == nil {
		t.Error("saveOperationLog with bad LogDir returned nil")
	}
}

func TestLoadOperationLog_NoLogDirIsError(t *testing.T) {
	m := &Mover{}
	if _, err := m.loadOperationLog("any"); err == nil {
		t.Error("loadOperationLog on empty LogDir returned nil")
	}
}

func TestLoadOperationLog_SkipsCorruptThenFails(t *testing.T) {
	m := mkMover(t)
	opsDir := filepath.Join(m.LogDir, "operations")
	if err := os.MkdirAll(opsDir, 0o750); err != nil {
		t.Fatal(err)
	}
	// File matches glob (*_target.json) but is corrupt → continue → not found
	if err := os.WriteFile(filepath.Join(opsDir, "1_target.json"),
		[]byte(`{not json`), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := m.loadOperationLog("target"); err == nil {
		t.Error("loadOperationLog returned nil for unfindable id")
	}
}

func TestMoveFile_OverwriteAcrossDirAsDestErrors(t *testing.T) {
	m := mkMover(t)
	src := filepath.Join(t.TempDir(), "src.txt")
	if err := os.WriteFile(src, []byte("new"), 0o600); err != nil {
		t.Fatal(err)
	}
	// dst is an EXISTING directory — resolveMoveFileConflict sees it
	// exists, enters Overwrite, replaceFileSafely copies src→tmp then
	// Rename(tmp, dst-as-dir) fails on most OSs.
	dst := filepath.Join(t.TempDir(), "dst-is-dir")
	if err := os.Mkdir(dst, 0o750); err != nil {
		t.Fatal(err)
	}
	res := m.MoveFile(src, dst, Overwrite)
	if res.Success {
		t.Errorf("expected failure renaming over existing dir, got %+v", res)
	}
}

// --- resolveMoveFileConflict Overwrite + DryRun ----------------------

func TestMoveFile_OverwriteDryRunSucceeds(t *testing.T) {
	m := mkMover(t)
	m.DryRun = true
	src := filepath.Join(t.TempDir(), "src.txt")
	if err := os.WriteFile(src, []byte("new"), 0o600); err != nil {
		t.Fatal(err)
	}
	dst := filepath.Join(t.TempDir(), "dst.txt")
	if err := os.WriteFile(dst, []byte("old"), 0o600); err != nil {
		t.Fatal(err)
	}
	res := m.MoveFile(src, dst, Overwrite)
	if !res.Success {
		t.Errorf("Overwrite + DryRun should succeed without touching FS, got %+v", res)
	}
	if data, _ := os.ReadFile(dst); string(data) != "old" {
		t.Errorf("DryRun modified dst content to %q, want untouched 'old'", string(data))
	}
}
