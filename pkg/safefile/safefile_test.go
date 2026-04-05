package safefile

import (
	"bytes"
	"os"
	"path/filepath"
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
