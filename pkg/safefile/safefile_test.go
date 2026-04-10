package safefile

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestReadWriteFile(t *testing.T) {
	t.Parallel()

	tempDir := t.TempDir()
	targetDir := filepath.Join(tempDir, "nested", "deep")
	targetFile := filepath.Join(targetDir, "sample.txt")

	if err := MkdirAll(targetDir, 0700); err != nil {
		t.Fatalf("MkdirAll() error = %v", err)
	}

	initial := []byte("first payload")
	if err := WriteFile(targetFile, initial, 0600); err != nil {
		t.Fatalf("WriteFile() initial error = %v", err)
	}

	updated := []byte("next")
	if err := WriteFile(targetFile, updated, 0600); err != nil {
		t.Fatalf("WriteFile() overwrite error = %v", err)
	}

	got, err := ReadFile(targetFile)
	if err != nil {
		t.Fatalf("ReadFile() error = %v", err)
	}
	if !bytes.Equal(got, updated) {
		t.Fatalf("ReadFile() = %q, want %q", got, updated)
	}
}

func TestMkdirAllCreatesNestedDirectories(t *testing.T) {
	t.Parallel()

	targetDir := filepath.Join(t.TempDir(), "a", "b", "c")
	if err := MkdirAll(targetDir, 0700); err != nil {
		t.Fatalf("MkdirAll() error = %v", err)
	}

	info, err := os.Stat(targetDir)
	if err != nil {
		t.Fatalf("Stat() error = %v", err)
	}
	if !info.IsDir() {
		t.Fatalf("Stat() expected directory, got mode %v", info.Mode())
	}
}

// ── splitPath 邊界條件 ──────────────────────────────────────────────────────

func TestSplitPathEmpty(t *testing.T) {
	t.Parallel()
	_, _, err := splitPath("")
	if err == nil {
		t.Fatal("splitPath(\"\") 應回傳 error")
	}
}

func TestSplitPathDot(t *testing.T) {
	t.Parallel()
	_, _, err := splitPath(".")
	if err == nil {
		t.Fatal("splitPath(\".\") 應回傳 error")
	}
}

func TestSplitPathOnlyWhitespace(t *testing.T) {
	t.Parallel()
	_, _, err := splitPath("   ")
	if err == nil {
		t.Fatal("splitPath(空白) 應回傳 error")
	}
}

func TestSplitPathValidFile(t *testing.T) {
	t.Parallel()
	tempDir := t.TempDir()
	filePath := filepath.Join(tempDir, "test.txt")
	// 先建立檔案，讓目錄存在
	if err := os.WriteFile(filePath, []byte("x"), 0600); err != nil {
		t.Fatalf("建立測試檔案失敗: %v", err)
	}

	dir, name, err := splitPath(filePath)
	if err != nil {
		t.Fatalf("splitPath() 不應回傳 error, 得到: %v", err)
	}
	if name != "test.txt" {
		t.Errorf("name = %q, want %q", name, "test.txt")
	}
	_ = dir // dir 是解析後的真實路徑
}

func TestSplitPathNonExistentDir(t *testing.T) {
	t.Parallel()
	// 目錄不存在時 EvalSymlinks 失敗，應回傳原始路徑（不是 error）
	_, name, err := splitPath("/nonexistent/dir/file.txt")
	if err != nil {
		t.Fatalf("非存在目錄的路徑不應回傳 error, 得到: %v", err)
	}
	if name != "file.txt" {
		t.Errorf("name = %q, want %q", name, "file.txt")
	}
}

// ── ReadFile 錯誤路徑 ─────────────────────────────────────────────────────

func TestReadFileNonExistent(t *testing.T) {
	t.Parallel()
	_, err := ReadFile(filepath.Join(t.TempDir(), "no_such_file.txt"))
	if err == nil {
		t.Fatal("ReadFile 不存在的檔案應回傳 error")
	}
}

func TestReadFileEmptyPath(t *testing.T) {
	t.Parallel()
	_, err := ReadFile("")
	if err == nil {
		t.Fatal("ReadFile(\"\") 應回傳 error")
	}
}

// ── WriteFile 錯誤路徑 ────────────────────────────────────────────────────

func TestWriteFileNonExistentDir(t *testing.T) {
	t.Parallel()
	// 目錄不存在，WriteFile 應回傳 error
	err := WriteFile("/nonexistent/dir/file.txt", []byte("data"), 0600)
	if err == nil {
		t.Fatal("WriteFile 到不存在的目錄應回傳 error")
	}
}

// ── OpenRead 錯誤路徑 ─────────────────────────────────────────────────────

func TestOpenReadNonExistent(t *testing.T) {
	t.Parallel()
	_, err := OpenRead(filepath.Join(t.TempDir(), "no_such_file.txt"))
	if err == nil {
		t.Fatal("OpenRead 不存在的檔案應回傳 error")
	}
}

// ── OpenFile ──────────────────────────────────────────────────────────────

func TestOpenFileCreateAndWrite(t *testing.T) {
	t.Parallel()
	tempDir := t.TempDir()
	filePath := filepath.Join(tempDir, "new_file.txt")

	f, err := OpenFile(filePath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0600)
	if err != nil {
		t.Fatalf("OpenFile() error = %v", err)
	}
	_, err = f.Write([]byte("hello"))
	if err != nil {
		t.Fatalf("Write() error = %v", err)
	}
	f.Close()

	// 驗證寫入成功
	got, err := ReadAll(filePath)
	if err != nil {
		t.Fatalf("ReadAll() error = %v", err)
	}
	if string(got) != "hello" {
		t.Errorf("ReadAll() = %q, want %q", got, "hello")
	}
}

func TestOpenFileEmptyPath(t *testing.T) {
	t.Parallel()
	_, err := OpenFile("", os.O_RDONLY, 0)
	if err == nil {
		t.Fatal("OpenFile(\"\") 應回傳 error")
	}
}

// ── ReadAll ───────────────────────────────────────────────────────────────

func TestReadAllSuccess(t *testing.T) {
	t.Parallel()
	tempDir := t.TempDir()
	filePath := filepath.Join(tempDir, "data.txt")

	payload := []byte("test content 123")
	if err := WriteFile(filePath, payload, 0600); err != nil {
		t.Fatalf("WriteFile() error = %v", err)
	}

	got, err := ReadAll(filePath)
	if err != nil {
		t.Fatalf("ReadAll() error = %v", err)
	}
	if !bytes.Equal(got, payload) {
		t.Errorf("ReadAll() = %q, want %q", got, payload)
	}
}

func TestReadAllNonExistent(t *testing.T) {
	t.Parallel()
	_, err := ReadAll(filepath.Join(t.TempDir(), "ghost.txt"))
	if err == nil {
		t.Fatal("ReadAll 不存在的檔案應回傳 error")
	}
}

// ── MkdirAll 邊界條件 ─────────────────────────────────────────────────────

func TestMkdirAllEmptyPath(t *testing.T) {
	t.Parallel()
	// 空字串 → 應靜默成功（已存在或清空）
	err := MkdirAll("", 0700)
	if err != nil {
		t.Fatalf("MkdirAll(\"\") 不應回傳 error, 得到: %v", err)
	}
}

func TestMkdirAllAlreadyExists(t *testing.T) {
	t.Parallel()
	existingDir := t.TempDir()
	// 已存在的目錄不應回傳 error
	err := MkdirAll(existingDir, 0700)
	if err != nil {
		t.Fatalf("MkdirAll(已存在目錄) 不應回傳 error, 得到: %v", err)
	}
}

// ── splitRootPath ──────────────────────────────────────────────────────────

func TestSplitRootPathRelative(t *testing.T) {
	t.Parallel()
	// filepath.Join 使用平台正確的分隔符
	root, parts := splitRootPath(filepath.Join("a", "b", "c"))
	if root != "." {
		t.Errorf("root = %q, want %q", root, ".")
	}
	if len(parts) != 3 {
		t.Errorf("len(parts) = %d, want 3", len(parts))
	}
}

func TestSplitRootPathEmpty(t *testing.T) {
	t.Parallel()
	root, parts := splitRootPath("")
	_ = root
	if len(parts) != 0 {
		t.Errorf("空路徑應回傳空 parts, 得到: %v", parts)
	}
}

func TestSplitRootPathWithDotSegments(t *testing.T) {
	t.Parallel()
	// 使用平台路徑 + 多餘的分隔符（Clean 後再傳入）
	sep := string(filepath.Separator)
	path := "a" + sep + sep + "b" + sep + "." + sep + "c"
	_, parts := splitRootPath(path)
	// 空字串與 "." 應被過濾
	for _, p := range parts {
		if p == "" || p == "." {
			t.Errorf("parts 不應含空字串或 '.', 得到: %v", parts)
		}
	}
}

func TestSplitRootPathAbsolute(t *testing.T) {
	t.Parallel()
	sep := string(filepath.Separator)
	path := sep + "foo" + sep + "bar"
	root, parts := splitRootPath(path)
	if !strings.HasSuffix(root, sep) {
		t.Errorf("絕對路徑的 root 應以 separator 結尾, 得到: %q", root)
	}
	if len(parts) < 2 {
		t.Errorf("parts 長度應 ≥ 2, 得到: %v", parts)
	}
}
