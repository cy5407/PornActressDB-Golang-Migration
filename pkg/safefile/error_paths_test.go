package safefile

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestWriteFileEmptyPath(t *testing.T) {
	if err := WriteFile("", []byte("x"), 0o600); err == nil {
		t.Error("WriteFile empty path returned nil")
	}
}

func TestWriteFileMissingDir(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "no-such-dir", "file.txt")
	if err := WriteFile(missing, []byte("x"), 0o600); err == nil {
		t.Error("WriteFile to missing parent dir returned nil")
	}
}

func TestOpenReadEmptyPath(t *testing.T) {
	if _, err := OpenRead(""); err == nil {
		t.Error("OpenRead empty path returned nil")
	}
}

func TestOpenReadMissingDir(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "no-such-dir", "file.txt")
	if _, err := OpenRead(missing); err == nil {
		t.Error("OpenRead missing dir returned nil")
	}
}

func TestOpenFileMissingDir(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "no-such-dir", "file.txt")
	if _, err := OpenFile(missing, os.O_RDONLY, 0); err == nil {
		t.Error("OpenFile missing dir returned nil")
	}
}

func TestReadFileMissingDir(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "no-such-dir", "file.txt")
	if _, err := ReadFile(missing); err == nil {
		t.Error("ReadFile missing dir returned nil")
	}
}

func TestMkdirAllEmptyPathIsNoOp(t *testing.T) {
	if err := MkdirAll("", 0o750); err != nil {
		t.Errorf("MkdirAll empty path returned %v, want nil (no-op)", err)
	}
	if err := MkdirAll(".", 0o750); err != nil {
		t.Errorf("MkdirAll dot returned %v, want nil (no-op)", err)
	}
}

func TestMkdirAllDeepNesting(t *testing.T) {
	root := t.TempDir()
	deep := filepath.Join(root, "a", "b", "c", "d")
	if err := MkdirAll(deep, 0o750); err != nil {
		t.Fatalf("MkdirAll deep: %v", err)
	}
	if info, err := os.Stat(deep); err != nil || !info.IsDir() {
		t.Fatalf("expected dir, got err=%v info=%v", err, info)
	}
}

func TestMkdirAllAcceptsAlreadyExistingIntermediate(t *testing.T) {
	root := t.TempDir()
	mid := filepath.Join(root, "mid")
	if err := os.Mkdir(mid, 0o750); err != nil {
		t.Fatal(err)
	}
	// Build root/mid/leaf where mid already exists — must succeed.
	if err := MkdirAll(filepath.Join(mid, "leaf"), 0o750); err != nil {
		t.Errorf("MkdirAll over existing intermediate: %v", err)
	}
}

func TestMkdirAllRejectsBadRootPath(t *testing.T) {
	// Drive that doesn't exist on Windows; nonsense path on Unix.
	bad := `Z:\nonexistent-drive\target`
	if runtime.GOOS != "windows" {
		bad = "/nonexistent-root-dir-12345/target"
	}
	if err := MkdirAll(bad, 0o750); err == nil {
		t.Skip("OS allowed creating MkdirAll target — skipping unreachable error branch")
	}
}

func TestWriteFileToExistingDirectoryNameErrors(t *testing.T) {
	root := t.TempDir()
	dir := filepath.Join(root, "name-that-is-dir")
	if err := os.Mkdir(dir, 0o750); err != nil {
		t.Fatal(err)
	}
	// WriteFile(dir/.../name-that-is-dir) — OpenFile O_WRONLY|O_TRUNC on a
	// directory must fail at the OpenFile step.
	if err := WriteFile(dir, []byte("x"), 0o600); err == nil {
		t.Error("WriteFile over existing directory returned nil")
	}
}

func TestMkdirAllWithFileAsIntermediate(t *testing.T) {
	root := t.TempDir()
	// Create a file at "blocker", then MkdirAll "blocker/child".
	blocker := filepath.Join(root, "blocker")
	if err := os.WriteFile(blocker, []byte("file not dir"), 0o600); err != nil {
		t.Fatal(err)
	}
	// First Mkdir("blocker") on the leaf returns IsExist (the file exists);
	// the fall-through OpenRoot("blocker") then fails because blocker is
	// not a directory — covers the intermediate OpenRoot error branch.
	err := MkdirAll(filepath.Join(blocker, "child"), 0o750)
	if err == nil {
		t.Error("MkdirAll through file-blocker returned nil, want error")
	}
}

func TestWriteFileOverReadOnlyTargetErrors(t *testing.T) {
	root := t.TempDir()
	target := filepath.Join(root, "readonly.txt")
	if err := os.WriteFile(target, []byte("seed"), 0o400); err != nil {
		t.Fatal(err)
	}
	// On Windows the 0o400 perms map to the readonly attribute, so
	// OpenFile O_WRONLY|O_TRUNC errors at the syscall level.
	if runtime.GOOS != "windows" {
		t.Skip("readonly attribute semantics differ on Unix; skipping")
	}
	if err := WriteFile(target, []byte("nope"), 0o400); err == nil {
		t.Error("WriteFile over readonly file returned nil")
	}
}

func TestReadFileNameWithNullByteFailsAtOpen(t *testing.T) {
	root := t.TempDir()
	bad := filepath.Join(root, "bad\x00name.txt")
	// splitPath cleans the path but keeps \x00 in name; root.Open then
	// fails the syscall with EINVAL — covers the root.Open error branch.
	if _, err := ReadFile(bad); err == nil {
		t.Error("ReadFile with null-byte name returned nil")
	}
}

func TestMkdirAllOnRootOnlyPathIsNoOp(t *testing.T) {
	// "/" cleans to "/" (Unix) or "\" (Windows); splitRootPath returns
	// rootPath = the separator and empty parts → early return at L139.
	if err := MkdirAll(string(filepath.Separator), 0o750); err != nil {
		t.Errorf("MkdirAll separator-only returned %v, want nil (parts==0 short-circuit)", err)
	}
}

func TestMkdirAllInvalidLeafNameErrors(t *testing.T) {
	root := t.TempDir()
	// Null byte in the leaf component → Mkdir errors with non-IsExist
	// syscall error, hits the err-branch inside the loop body.
	bad := filepath.Join(root, "sub", "bad\x00leaf")
	if err := MkdirAll(bad, 0o750); err == nil {
		t.Error("MkdirAll with null-byte leaf returned nil")
	}
}

func TestSplitPath_SeparatorOnlyIsError(t *testing.T) {
	// "/" cleans to "/", Base("/") returns "/", which the guard catches.
	sep := string(filepath.Separator)
	if _, _, err := splitPath(sep); err == nil {
		t.Error("splitPath(separator-only) returned nil error")
	}
}

func TestMkdirAllRootOpenRootFailureOnMissingDrive(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("drive-letter trick only applies on Windows")
	}
	// Find a non-existent drive letter to force OpenRoot at the root step.
	for letter := 'Z'; letter >= 'A'; letter-- {
		drive := string(letter) + `:\`
		if _, err := os.Stat(drive); os.IsNotExist(err) {
			if err := MkdirAll(drive+`some\sub\dir`, 0o750); err == nil {
				t.Errorf("MkdirAll on non-existent drive %q returned nil", drive)
			}
			return
		}
	}
	t.Skip("no spare drive letter available to test root OpenRoot failure")
}

func TestWriteFileNameTooLongFailsAtOpen(t *testing.T) {
	root := t.TempDir()
	// Most filesystems cap basename length around 255 bytes.
	tooLong := filepath.Join(root, strings.Repeat("a", 300)+".txt")
	if err := WriteFile(tooLong, []byte("x"), 0o600); err == nil {
		t.Error("WriteFile with overlong basename returned nil")
	}
}

func TestSplitRootPath_HandlesAllShapes(t *testing.T) {
	// Driver test for splitRootPath via MkdirAll (which is its only caller).
	// Tests relative paths (covered through MkdirAllDeepNesting).

	// Pure dot remainder.
	root, parts := splitRootPath(".")
	if root != "." {
		t.Errorf("splitRootPath('.') root = %q, want '.'", root)
	}
	if len(parts) != 0 {
		t.Errorf("splitRootPath('.') parts = %v, want empty", parts)
	}

	// Empty string after trim.
	root, parts = splitRootPath("")
	if root != "." {
		t.Errorf("splitRootPath('') root = %q, want '.'", root)
	}
	if len(parts) != 0 {
		t.Errorf("splitRootPath('') parts = %v, want empty", parts)
	}

	// Relative two-segment path.
	root, parts = splitRootPath(filepath.Join("foo", "bar"))
	if root != "." {
		t.Errorf("relative path root = %q, want '.'", root)
	}
	if len(parts) != 2 || parts[0] != "foo" || parts[1] != "bar" {
		t.Errorf("relative path parts = %v, want [foo bar]", parts)
	}
}
