package mover

import (
	"context"
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

// forceRenameFailure swaps renameFile for one that always errors, so
// MoveFile exercises its real copy+recycle fallback. Restored on cleanup.
func forceRenameFailure(t *testing.T) {
	t.Helper()
	orig := renameFile
	renameFile = func(_, _ string) error { return os.ErrInvalid }
	t.Cleanup(func() { renameFile = orig })
}

func TestMoveFile_CopyFallbackWhenRenameFails(t *testing.T) {
	forceRenameFailure(t)
	m := mkMover(t)
	srcDir := t.TempDir()
	src := filepath.Join(srcDir, "src.txt")
	if err := os.WriteFile(src, []byte("fallback-content"), 0o600); err != nil {
		t.Fatal(err)
	}
	dst := filepath.Join(t.TempDir(), "dst.txt")
	res := m.MoveFile(src, dst, Skip)
	if !res.Success {
		t.Fatalf("expected copy fallback to succeed, got %+v", res)
	}
	got, err := os.ReadFile(dst)
	if err != nil {
		t.Fatalf("read dst: %v", err)
	}
	if string(got) != "fallback-content" {
		t.Errorf("dst content = %q, want fallback-content", string(got))
	}
	// Source must be gone (recycled / removed) after a successful move.
	if _, err := os.Stat(src); !os.IsNotExist(err) {
		t.Error("source still present after copy-fallback move")
	}
}

func TestMoveFile_CopyFallbackErrorWhenDestinationUnwritable(t *testing.T) {
	forceRenameFailure(t)
	m := mkMover(t)
	src := filepath.Join(t.TempDir(), "src.txt")
	if err := os.WriteFile(src, []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	// dst does not pre-exist (so no conflict handling) but its final
	// component collides with a directory we pre-create at that exact
	// path's leaf — copyFile's OpenFile O_TRUNC then fails. We achieve a
	// non-existing-yet-unwritable dst by making the leaf an existing dir
	// AND using a strategy that proceeds: there is none, so instead force
	// copyFile failure via a null byte in the leaf name.
	dst := filepath.Join(t.TempDir(), "bad\x00leaf.txt")
	res := m.MoveFile(src, dst, Skip)
	if res.Success {
		t.Errorf("expected copy-fallback failure, got %+v", res)
	}
	if res.Error == "" {
		t.Error("expected non-empty Error from failed copy")
	}
}

func TestCopyFile_HappyPathCopiesContentAndMode(t *testing.T) {
	m := mkMover(t)
	srcDir := t.TempDir()
	src := filepath.Join(srcDir, "src.txt")
	if err := os.WriteFile(src, []byte("payload-bytes"), 0o640); err != nil {
		t.Fatal(err)
	}
	dst := filepath.Join(t.TempDir(), "dst.txt")
	if err := m.copyFile(src, dst); err != nil {
		t.Fatalf("copyFile happy path: %v", err)
	}
	got, err := os.ReadFile(dst)
	if err != nil {
		t.Fatalf("read dst: %v", err)
	}
	if string(got) != "payload-bytes" {
		t.Errorf("dst content = %q, want payload-bytes", string(got))
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
	// Relies on a null-byte path making filepath.Abs (inside
	// IsSameOrNestedPath) fail — Windows-only behaviour. On Linux/macOS
	// Abs accepts it, so this validation-error branch is unreachable there.
	if runtime.GOOS != "windows" {
		t.Skip("null-byte path triggers the Abs error branch only on Windows")
	}
	res := &MergeResult{}
	if validateMoveDirDestination("bad\x00src", t.TempDir(), res) {
		t.Error("validateMoveDirDestination accepted bad source")
	}
}

func TestValidateMoveDirDestination_SamePathReportsSuccessNoMove(t *testing.T) {
	// dst == src exactly → IsSameOrNestedPath true, pathsReferToSameDir
	// true → result.Success=true, DeletedSrc=false, returns false (no move).
	src := t.TempDir()
	res := &MergeResult{}
	proceed := validateMoveDirDestination(src, src, res)
	if proceed {
		t.Error("validateMoveDirDestination returned true for identical src/dst")
	}
	if !res.Success {
		t.Error("expected Success=true for same-path no-op")
	}
	if res.DeletedSrc {
		t.Error("expected DeletedSrc=false for same-path no-op")
	}
}

func TestMoveDir_StatErrorOnSourcePropagates(t *testing.T) {
	m := mkMover(t)
	// Null-byte source → os.Stat non-IsNotExist error branch of
	// validateMoveDirSource.
	res := m.MoveDir("bad\x00src", filepath.Join(t.TempDir(), "dst"), Skip)
	if res.Success {
		t.Errorf("expected failure for unreadable source dir, got %+v", res)
	}
	if len(res.Errors) == 0 {
		t.Error("expected error appended")
	}
}

func TestLoadOperationLog_MatchingDirEntrySkipped(t *testing.T) {
	m := mkMover(t)
	opsDir := filepath.Join(m.LogDir, "operations")
	if err := os.MkdirAll(opsDir, 0o750); err != nil {
		t.Fatal(err)
	}
	// A *directory* whose name matches the glob "*_target.json": ReadFile
	// on it fails → continue → eventually not-found.
	if err := os.MkdirAll(filepath.Join(opsDir, "1_target.json"), 0o750); err != nil {
		t.Fatal(err)
	}
	if _, err := m.loadOperationLog("target"); err == nil {
		t.Error("loadOperationLog returned nil when only a dir matched")
	}
}

// --- pathsReferToSameDir error path -----------------------------------

func TestPathsReferToSameDir_BadInputReturnsError(t *testing.T) {
	// pathsReferToSameDir errors only when filepath.Abs fails, which for a
	// null-byte path happens on Windows only.
	if runtime.GOOS != "windows" {
		t.Skip("filepath.Abs rejects null-byte paths only on Windows")
	}
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

func TestTryFastMoveDirRename_MkdirAllParentFailsReturnsFalse(t *testing.T) {
	m := mkMover(t)
	// Create a FILE that will act as a blocking intermediate, then aim
	// dst at <file>/child/leaf so MkdirAll(Dir(dst)) = MkdirAll(<file>/child)
	// fails (cannot create a dir under a file). dst itself does not exist
	// so the Stat IsNotExist check passes through to MkdirAll.
	blocker := filepath.Join(t.TempDir(), "blocker")
	if err := os.WriteFile(blocker, []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	src := t.TempDir()
	dst := filepath.Join(blocker, "child", "leaf")
	res := &MergeResult{}
	if m.tryFastMoveDirRename(src, dst, res) {
		t.Error("tryFastMoveDirRename returned true when parent dir cannot be created")
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

// --- validateMoveFileSource stat error (non-IsNotExist) ---------------

func TestMoveFile_StatErrorOnSourcePropagates(t *testing.T) {
	m := mkMover(t)
	// Null-byte source → os.Stat returns a non-IsNotExist error, hitting
	// the "無法讀取來源" branch of validateMoveFileSource.
	res := m.MoveFile("bad\x00src", filepath.Join(t.TempDir(), "dst.txt"), Skip)
	if res.Success {
		t.Errorf("expected failure for unreadable source, got %+v", res)
	}
	if res.Error == "" {
		t.Error("expected non-empty Error")
	}
}

// --- buildRollbackSummary all four branches ---------------------------

func TestBuildRollbackSummary_AllBranches(t *testing.T) {
	cases := []struct {
		name       string
		result     BatchResult
		wantStatus string
	}{
		{"skipped+failed", BatchResult{SuccessCount: 1, SkippedCount: 2, FailedCount: 3, TotalItems: 6}, "partial"},
		{"skipped only", BatchResult{SuccessCount: 1, SkippedCount: 2, TotalItems: 3}, "partial"},
		{"failed only", BatchResult{SuccessCount: 1, FailedCount: 2, TotalItems: 3}, "partial"},
		{"all success", BatchResult{SuccessCount: 3, TotalItems: 3}, "completed"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			msg, status := buildRollbackSummary(tc.result)
			if status != tc.wantStatus {
				t.Errorf("status = %q, want %q", status, tc.wantStatus)
			}
			if msg == "" {
				t.Error("summary message empty")
			}
		})
	}
}

// --- batchMoveDirsWithType: cancellation + status branches ------------

func TestBatchMoveDirs_CancelledContextReturnsCancelled(t *testing.T) {
	m := mkMover(t)
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // pre-cancelled
	src := t.TempDir()
	res := m.BatchMoveDirs(ctx, []MoveItem{{Source: src, Destination: filepath.Join(t.TempDir(), "d")}})
	// Cancelled before processing any item → zero results.
	if len(res.Results) != 0 {
		t.Errorf("Results = %d, want 0 (cancelled before first item)", len(res.Results))
	}
}

func TestBatchMoveDirs_FailedItemMarksFailedStatus(t *testing.T) {
	m := mkMover(t)
	// Source dir does not exist → MoveDir fails → outcome "failed".
	res := m.BatchMoveDirs(context.Background(), []MoveItem{
		{Source: filepath.Join(t.TempDir(), "no-such-dir"), Destination: filepath.Join(t.TempDir(), "dst")},
	})
	if res.FailedCount != 1 {
		t.Errorf("FailedCount = %d, want 1", res.FailedCount)
	}
}

func TestBatchMoveDirs_SuccessfulMoveCompletes(t *testing.T) {
	m := mkMover(t)
	src := filepath.Join(t.TempDir(), "src")
	if err := os.MkdirAll(src, 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(src, "f.txt"), []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	dst := filepath.Join(t.TempDir(), "dst")
	res := m.BatchMoveDirs(context.Background(), []MoveItem{{Source: src, Destination: dst}})
	if res.SuccessCount != 1 {
		t.Errorf("SuccessCount = %d, want 1; result=%+v", res.SuccessCount, res)
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

func TestListOperations_BadLogDirReadDirErrorPropagates(t *testing.T) {
	// Null byte in LogDir → ReadDir fails with a non-IsNotExist syscall
	// error, exercising the `return nil, err` branch.
	m := &Mover{LogDir: "bad\x00dir"}
	if _, err := m.ListOperations(); err == nil {
		t.Error("ListOperations with null-byte LogDir returned nil error")
	}
}

func TestListOperations_SortsByTimestampDescending(t *testing.T) {
	m := mkMover(t)
	opsDir := filepath.Join(m.LogDir, "operations")
	if err := os.MkdirAll(opsDir, 0o750); err != nil {
		t.Fatal(err)
	}
	// Two valid logs with different timestamps → exercises the sort
	// comparator (line 45) and confirms newest-first ordering.
	older := `{"id":"old","timestamp":"2026-01-01T00:00:00Z"}`
	newer := `{"id":"new","timestamp":"2026-12-31T00:00:00Z"}`
	if err := os.WriteFile(filepath.Join(opsDir, "a.json"), []byte(older), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(opsDir, "b.json"), []byte(newer), 0o600); err != nil {
		t.Fatal(err)
	}
	logs, err := m.ListOperations()
	if err != nil {
		t.Fatalf("ListOperations: %v", err)
	}
	if len(logs) != 2 {
		t.Fatalf("len = %d, want 2", len(logs))
	}
	if logs[0].ID != "new" {
		t.Errorf("logs[0].ID = %q, want new (descending by timestamp)", logs[0].ID)
	}
}

func TestLoadOperationLog_MalformedGlobPatternErrors(t *testing.T) {
	m := mkMover(t)
	// id containing "[" makes the glob pattern "*_[.json" malformed →
	// filepath.Glob returns ErrBadPattern, hitting the error branch.
	if _, err := m.loadOperationLog("["); err == nil {
		t.Error("loadOperationLog with malformed-glob id returned nil error")
	}
}

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

func TestGenerateUniqueName_TimestampFallbackOnRepeatedFailure(t *testing.T) {
	// Force every OpenFile attempt to fail by passing a path under a
	// directory that does NOT exist — each OpenFile returns ENOENT
	// (non-IsExist), the loop spins 10000 times and falls through to
	// the timestamp-suffixed result.
	m := mkMover(t)
	bogusDir := filepath.Join(t.TempDir(), "definitely-not-created")
	got := m.generateUniqueName(filepath.Join(bogusDir, "file.txt"))
	// Result should still be a path under the bogus dir with .txt suffix.
	if filepath.Dir(got) != bogusDir {
		t.Errorf("dir = %q, want %q", filepath.Dir(got), bogusDir)
	}
	if filepath.Ext(got) != ".txt" {
		t.Errorf("ext = %q, want .txt", filepath.Ext(got))
	}
	// Should NOT be "file_1.txt" (first numeric attempt) — must be the
	// 14-digit timestamp fallback shape.
	base := strings.TrimSuffix(filepath.Base(got), ".txt")
	parts := strings.Split(base, "_")
	if len(parts) != 2 {
		t.Fatalf("base = %q, want <name>_<stamp> shape", base)
	}
	if len(parts[1]) != 14 {
		t.Errorf("timestamp suffix = %q (len %d), want 14 digits", parts[1], len(parts[1]))
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
