package mover

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"actress-classifier/pkg/safefile"
)

func isSameOrNestedPath(base, target string) (bool, error) {
	absBase, err := filepath.Abs(base)
	if err != nil {
		return false, err
	}
	absTarget, err := filepath.Abs(target)
	if err != nil {
		return false, err
	}

	rel, err := filepath.Rel(absBase, absTarget)
	if err != nil {
		return false, nil
	}
	rel = filepath.Clean(rel)

	return rel == "." || (rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator))), nil
}

// MoveDir 移動整個目錄
func (m *Mover) MoveDir(src, dst string, strategy ConflictStrategy) MergeResult {
	result := MergeResult{SourceDir: src, DestDir: dst, Success: false}

	srcInfo, err := os.Stat(src)
	if os.IsNotExist(err) {
		result.Errors = append(result.Errors, MoveResult{Source: src, Error: "來源目錄不存在"})
		return result
	}
	if err != nil {
		result.Errors = append(result.Errors, MoveResult{Source: src, Error: fmt.Sprintf("無法讀取來源目錄: %v", err)})
		return result
	}
	if !srcInfo.IsDir() {
		result.Errors = append(result.Errors, MoveResult{Source: src, Error: "來源不是目錄"})
		return result
	}
	dstInsideSrc, err := isSameOrNestedPath(src, dst)
	if err != nil {
		result.Errors = append(result.Errors, MoveResult{Source: src, Error: fmt.Sprintf("無法驗證目標目錄: %v", err)})
		return result
	}
	if dstInsideSrc {
		result.Errors = append(result.Errors, MoveResult{Source: src, Destination: dst, Error: "目標目錄不能位於來源目錄內或與來源相同"})
		return result
	}

	actualDst := dst

	err = filepath.Walk(src, func(path string, info os.FileInfo, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		relPath, relErr := filepath.Rel(src, path)
		if relErr != nil {
			return relErr
		}

		targetPath := actualDst
		if relPath != "." {
			targetPath = filepath.Join(actualDst, relPath)
		}

		if info.IsDir() {
			if m.DryRun {
				return nil
			}
			return safefile.MkdirAll(targetPath, 0700)
		}

		result.FilesTotal++
		moveResult := m.MoveFile(path, targetPath, strategy)
		if moveResult.Success {
			if moveResult.Skipped {
				result.FilesSkipped++
			} else {
				result.FilesMoved++
			}
			return nil
		}
		result.Errors = append(result.Errors, moveResult)
		return nil
	})
	if err != nil {
		result.Errors = append(result.Errors, MoveResult{Source: src, Error: fmt.Sprintf("掃描目錄失敗: %v", err)})
	}

	if len(result.Errors) == 0 && result.FilesSkipped == 0 && !m.DryRun {
		if err := os.RemoveAll(src); err != nil {
			result.Errors = append(result.Errors, MoveResult{
				Source: src,
				Error:  fmt.Sprintf("檔案已移動完成，但刪除來源目錄失敗: %v", err),
			})
		} else {
			result.DeletedSrc = true
		}
	}
	result.Success = len(result.Errors) == 0
	return result
}
