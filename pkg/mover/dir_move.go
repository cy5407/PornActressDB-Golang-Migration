package mover

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"actress-classifier/pkg/pathutil"
	"actress-classifier/pkg/safefile"
)

// MoveDir 移動整個目錄
func (m *Mover) MoveDir(src, dst string, strategy ConflictStrategy) MergeResult {
	result := MergeResult{SourceDir: src, DestDir: dst, Success: false}

	if !validateMoveDirSource(src, &result) {
		return result
	}
	if !validateMoveDirDestination(src, dst, &result) {
		return result
	}
	if m.tryFastMoveDirRename(src, dst, &result) {
		return result
	}

	m.walkMoveDirEntries(src, dst, strategy, &result)
	m.finalizeMoveDir(src, &result)
	return result
}

func validateMoveDirSource(src string, result *MergeResult) bool {
	srcInfo, err := os.Stat(src)
	if os.IsNotExist(err) {
		appendMoveDirError(result, src, "", "來源目錄不存在")
		return false
	}
	if err != nil {
		appendMoveDirError(result, src, "", fmt.Sprintf("無法讀取來源目錄: %v", err))
		return false
	}
	if !srcInfo.IsDir() {
		appendMoveDirError(result, src, "", "來源不是目錄")
		return false
	}
	return true
}

func validateMoveDirDestination(src, dst string, result *MergeResult) bool {
	dstInsideSrc, err := pathutil.IsSameOrNestedPath(src, dst)
	if err != nil {
		appendMoveDirError(result, src, "", fmt.Sprintf("無法驗證目標目錄: %v", err))
		return false
	}
	if !dstInsideSrc {
		return true
	}
	if isSameDirPath(src, dst) {
		result.Success = true
		result.DeletedSrc = false
		return false
	}
	appendMoveDirError(result, src, dst, "目標目錄不能位於來源目錄內")
	return false
}

func isSameDirPath(src, dst string) bool {
	absSrc, _ := filepath.Abs(src)
	if absSrc == "" {
		return false
	}
	absDst, _ := filepath.Abs(dst)
	return strings.EqualFold(absSrc, absDst)
}

func (m *Mover) tryFastMoveDirRename(src, dst string, result *MergeResult) bool {
	if m.DryRun {
		return false
	}
	if _, err := os.Stat(dst); !os.IsNotExist(err) {
		return false
	}
	if err := safefile.MkdirAll(filepath.Dir(dst), 0700); err != nil {
		return false
	}
	if err := os.Rename(src, dst); err != nil {
		return false
	}
	countMovedDirFiles(dst, result)
	result.DeletedSrc = true
	result.Success = true
	return true
}

func countMovedDirFiles(dst string, result *MergeResult) {
	_ = filepath.Walk(dst, func(_ string, info os.FileInfo, _ error) error {
		if info != nil && !info.IsDir() {
			result.FilesMoved++
		}
		return nil
	})
}

func (m *Mover) walkMoveDirEntries(src, dst string, strategy ConflictStrategy, result *MergeResult) {
	err := filepath.Walk(src, func(path string, info os.FileInfo, walkErr error) error {
		return m.handleMoveDirEntry(src, dst, path, info, walkErr, strategy, result)
	})
	if err != nil {
		appendMoveDirError(result, src, "", fmt.Sprintf("掃描目錄失敗: %v", err))
	}
}

func (m *Mover) handleMoveDirEntry(srcRoot, dstRoot, path string, info os.FileInfo, walkErr error, strategy ConflictStrategy, result *MergeResult) error {
	if walkErr != nil {
		return walkErr
	}
	targetPath, err := moveDirTargetPath(srcRoot, dstRoot, path)
	if err != nil {
		return err
	}
	if info.IsDir() {
		return m.ensureMoveDirTargetDir(targetPath)
	}
	result.FilesTotal++
	moveResult := m.MoveFile(path, targetPath, strategy)
	if moveResult.Success {
		updateMoveDirCounts(result, moveResult)
		return nil
	}
	result.Errors = append(result.Errors, moveResult)
	return nil
}

func moveDirTargetPath(srcRoot, dstRoot, path string) (string, error) {
	relPath, err := filepath.Rel(srcRoot, path)
	if err != nil {
		return "", err
	}
	if relPath == "." {
		return dstRoot, nil
	}
	return filepath.Join(dstRoot, relPath), nil
}

func (m *Mover) ensureMoveDirTargetDir(targetPath string) error {
	if m.DryRun {
		return nil
	}
	return safefile.MkdirAll(targetPath, 0700)
}

func updateMoveDirCounts(result *MergeResult, moveResult MoveResult) {
	if moveResult.Skipped {
		result.FilesSkipped++
		return
	}
	result.FilesMoved++
}

func (m *Mover) finalizeMoveDir(src string, result *MergeResult) {
	if len(result.Errors) == 0 && result.FilesSkipped == 0 && !m.DryRun {
		if err := os.RemoveAll(src); err != nil {
			appendMoveDirError(result, src, "", fmt.Sprintf("檔案已移動完成，但刪除來源目錄失敗: %v", err))
		} else {
			result.DeletedSrc = true
		}
	}
	result.Success = len(result.Errors) == 0
}

func appendMoveDirError(result *MergeResult, src, dst, message string) {
	result.Errors = append(result.Errors, MoveResult{Source: src, Destination: dst, Error: message})
}
