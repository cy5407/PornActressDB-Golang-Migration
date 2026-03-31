package safefile

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

func splitPath(path string) (string, string, error) {
	cleanPath := filepath.Clean(strings.TrimSpace(path))
	if cleanPath == "" || cleanPath == "." {
		return "", "", fmt.Errorf("path cannot be empty")
	}

	dir := filepath.Dir(cleanPath)
	name := filepath.Base(cleanPath)
	if name == "." || name == string(filepath.Separator) {
		return "", "", fmt.Errorf("invalid path: %s", path)
	}
	if dir == "" {
		dir = "."
	}

	return dir, name, nil
}

func ReadFile(path string) ([]byte, error) {
	dir, name, err := splitPath(path)
	if err != nil {
		return nil, err
	}

	root, err := os.OpenRoot(dir)
	if err != nil {
		return nil, err
	}
	defer root.Close()

	return root.ReadFile(name)
}

func WriteFile(path string, data []byte, perm os.FileMode) error {
	dir, name, err := splitPath(path)
	if err != nil {
		return err
	}

	root, err := os.OpenRoot(dir)
	if err != nil {
		return err
	}
	defer root.Close()

	return root.WriteFile(name, data, perm)
}

func OpenRead(path string) (*os.File, error) {
	dir, name, err := splitPath(path)
	if err != nil {
		return nil, err
	}

	root, err := os.OpenRoot(dir)
	if err != nil {
		return nil, err
	}
	defer root.Close()

	return root.Open(name)
}

func OpenFile(path string, flag int, perm os.FileMode) (*os.File, error) {
	dir, name, err := splitPath(path)
	if err != nil {
		return nil, err
	}

	root, err := os.OpenRoot(dir)
	if err != nil {
		return nil, err
	}
	defer root.Close()

	return root.OpenFile(name, flag, perm)
}

func MkdirAll(path string, perm os.FileMode) error {
	cleanPath := filepath.Clean(strings.TrimSpace(path))
	if cleanPath == "" || cleanPath == "." {
		return nil
	}

	parent := filepath.Dir(cleanPath)
	name := filepath.Base(cleanPath)
	if parent == "" {
		parent = "."
	}

	root, err := os.OpenRoot(parent)
	if err != nil {
		return err
	}
	defer root.Close()

	return root.MkdirAll(name, perm)
}

func ReadAll(path string) ([]byte, error) {
	f, err := OpenRead(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	return io.ReadAll(f)
}
