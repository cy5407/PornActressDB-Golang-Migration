package mover

import (
	"fmt"
	"os"
	"path/filepath"
)

// MoveDir 移動整個目錄
func (m *Mover) MoveDir(src, dst string, strategy ConflictStrategy) MergeResult {
	result := MergeResult{SourceDir: src, DestDir: dst, Success: false}

	srcInfo, err := os.Stat(src)
	if os.IsNotExist(err) {
		result.Errors = append(result.Errors, MoveResult{Source: src, Error: "來源目錄不存在"})
		return result
	}
	if !srcInfo.IsDir() {
		result.Errors = append(result.Errors, MoveResult{Source: src, Error: "來源不是目錄"})
		return result
	}

	var files []string
	err = filepath.Walk(src, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if !info.IsDir() {
			files = append(files, path)
		}
		return nil
	})
	if err != nil {
		result.Errors = append(result.Errors, MoveResult{Source: src, Error: fmt.Sprintf("掃描目錄失敗: %v", err)})
		return result
	}

	result.FilesTotal = len(files)
	for _, srcFile := range files {
		relPath, _ := filepath.Rel(src, srcFile)
		moveResult := m.MoveFile(srcFile, filepath.Join(dst, relPath), strategy)
		if moveResult.Success {
			result.FilesMoved++
		} else {
			result.Errors = append(result.Errors, moveResult)
		}
	}
	if result.FilesMoved == result.FilesTotal && !m.DryRun {
		if err := os.RemoveAll(src); err == nil {
			result.DeletedSrc = true
		}
	}
	result.Success = len(result.Errors) == 0
	return result
}
