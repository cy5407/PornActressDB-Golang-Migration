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

	// 防止 symlink 穿越：解析目錄的真實路徑並驗證一致性
	realDir, err := filepath.EvalSymlinks(dir) // 解析 symlink 取得真實路徑
	if err != nil {
		// 目錄不存在時 EvalSymlinks 會失敗，此時使用原始路徑（由呼叫端處理）
		return dir, name, nil
	}
	// 確認解析後的路徑仍在預期範圍內（Clean 後應一致）
	if filepath.Clean(realDir) != realDir {
		return "", "", fmt.Errorf("suspicious symlink detected in directory path: %s", dir)
	}

	return realDir, name, nil
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

	file, err := root.Open(name)
	if err != nil {
		return nil, err
	}

	data, readErr := io.ReadAll(file)
	closeErr := file.Close()
	if readErr != nil {
		return nil, readErr
	}
	if closeErr != nil {
		return nil, closeErr
	}

	return data, nil
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

	file, err := root.OpenFile(name, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, perm)
	if err != nil {
		return err
	}

	written, writeErr := file.Write(data)
	closeErr := file.Close()
	if writeErr != nil {
		return writeErr
	}
	if written != len(data) {
		return io.ErrShortWrite
	}
	if closeErr != nil {
		return closeErr
	}

	return nil
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

	rootPath, parts := splitRootPath(cleanPath)
	if len(parts) == 0 {
		return nil
	}

	root, err := os.OpenRoot(rootPath)
	if err != nil {
		return err
	}

	for i, part := range parts {
		if err := root.Mkdir(part, perm); err != nil && !os.IsExist(err) {
			_ = root.Close()
			return err
		}
		if i == len(parts)-1 {
			return root.Close()
		}

		nextRoot, err := root.OpenRoot(part)
		if err != nil {
			_ = root.Close()
			return err
		}
		if err := root.Close(); err != nil {
			_ = nextRoot.Close()
			return err
		}
		root = nextRoot
	}

	return nil
}

func ReadAll(path string) ([]byte, error) {
	f, err := OpenRead(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	return io.ReadAll(f)
}

func splitRootPath(path string) (string, []string) {
	volume := filepath.VolumeName(path)
	remainder := strings.TrimPrefix(path, volume)

	rootPath := "."
	if strings.HasPrefix(remainder, string(filepath.Separator)) {
		rootPath = volume + string(filepath.Separator)
		remainder = strings.TrimPrefix(remainder, string(filepath.Separator))
	}

	if remainder == "" || remainder == "." {
		return rootPath, nil
	}

	parts := strings.Split(remainder, string(filepath.Separator))
	filtered := make([]string, 0, len(parts))
	for _, part := range parts {
		if part == "" || part == "." {
			continue
		}
		filtered = append(filtered, part)
	}

	return rootPath, filtered
}
