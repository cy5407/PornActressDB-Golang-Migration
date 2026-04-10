package mover

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"

	"actress-classifier/pkg/safefile"
)

// generateUniqueNameMaxAttempts 是 generateUniqueName 的最大遞增編號嘗試次數
// 超過上限後改用時間戳確保唯一性
const generateUniqueNameMaxAttempts = 10000

// MoveFile 移動單一檔案
func (m *Mover) MoveFile(src, dst string, strategy ConflictStrategy) MoveResult {
	result := MoveResult{Source: src, Destination: dst, Success: false}

	// 同路徑保護：source == destination 視為已完成（skip），避免覆蓋策略觸發時刪除自身
	if isSameFilePath(src, dst) {
		result.Skipped, result.Success = true, true
		return result
	}

	if !validateMoveFileSource(src, &result) {
		return result
	}

	if !m.ensureMoveFileDestinationDir(dst, &result) {
		return result
	}

	dst, handled := m.resolveMoveFileConflict(src, dst, strategy, &result)
	if handled {
		return result
	}

	if m.DryRun {
		result.Success, result.Destination = true, dst
		return result
	}
	if err := os.Rename(src, dst); err == nil {
		result.Success, result.Destination = true, dst
		return result
	}
	if err := m.copyFile(src, dst); err != nil {
		result.Error = fmt.Sprintf("複製檔案失敗: %v", err)
		return result
	}
	// 複製成功後刪除來源：送入資源回收筒（Windows），非 Windows 則永久刪除
	if err := recycleFile(src); err != nil {
		result.Error = fmt.Sprintf("刪除來源失敗: %v", err)
		return result
	}

	result.Success, result.Destination = true, dst
	return result
}

func isSameFilePath(src, dst string) bool {
	absSrc, errSrc := filepath.Abs(src)
	absDst, errDst := filepath.Abs(dst)
	return errSrc == nil && errDst == nil && absSrc == absDst
}

func validateMoveFileSource(src string, result *MoveResult) bool {
	srcInfo, err := os.Stat(src)
	if os.IsNotExist(err) {
		result.Error = "來源檔案不存在"
		return false
	}
	if err != nil {
		result.Error = fmt.Sprintf("無法讀取來源: %v", err)
		return false
	}
	if srcInfo.IsDir() {
		result.Error = "來源是目錄，請使用 MoveDir"
		return false
	}
	return true
}

func (m *Mover) ensureMoveFileDestinationDir(dst string, result *MoveResult) bool {
	if m.DryRun {
		return true
	}
	if err := safefile.MkdirAll(filepath.Dir(dst), 0700); err != nil {
		result.Error = fmt.Sprintf("無法建立目標目錄: %v", err)
		return false
	}
	return true
}

func (m *Mover) resolveMoveFileConflict(src, dst string, strategy ConflictStrategy, result *MoveResult) (string, bool) {
	if _, err := os.Stat(dst); err != nil {
		return dst, false
	}

	switch strategy {
	case Skip:
		result.Skipped, result.Success = true, true
		return dst, true
	case Overwrite:
		if !m.DryRun {
			if err := m.replaceFileSafely(src, dst); err != nil {
				result.Error = fmt.Sprintf("覆蓋目標檔案失敗: %v", err)
				return dst, true
			}
			result.Success, result.Destination = true, dst
			return dst, true
		}
	case Rename:
		newDst := m.generateUniqueName(dst)
		result.Renamed, dst = newDst, newDst
	case Merge:
		result.Error = "Merge 策略不適用於單一檔案"
		return dst, true
	default:
		result.Error = fmt.Sprintf("未知的衝突策略: %s", strategy)
		return dst, true
	}

	return dst, false
}

// generateUniqueName 在指定路徑已存在時，產生不衝突的唯一路徑
func (m *Mover) generateUniqueName(path string) string {
	dir, fileExt, base := filepath.Dir(path), filepath.Ext(path), filepath.Base(path)
	name := base[:len(base)-len(fileExt)]
	for i := 1; i <= generateUniqueNameMaxAttempts; i++ {
		candidatePath := filepath.Join(dir, fmt.Sprintf("%s_%d%s", name, i, fileExt))
		f, err := os.OpenFile(candidatePath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600) // #nosec G304 -- path is program-constructed via filepath.Join, not from user input
		if err == nil {
			_ = f.Close()
			// 保留佔位檔，以原子方式鎖定路徑，避免 TOCTOU。
			// 後續 copyFile（O_TRUNC）或 os.Rename（Linux atomic replace）會覆寫此佔位檔。
			return candidatePath
		}
		if !os.IsExist(err) {
			continue
		}
	}
	result := filepath.Join(dir, fmt.Sprintf("%s_%s%s", name, time.Now().Format("20060102150405"), fileExt))
	fmt.Fprintf(os.Stderr, "[WARNING] generateUniqueName: 達到最大嘗試次數 (%d)，改用時間戳後備名稱：%s\n", generateUniqueNameMaxAttempts, result)
	return result
}

func (m *Mover) copyFile(src, dst string) error {
	srcFile, err := safefile.OpenRead(src)
	if err != nil {
		return err
	}
	defer srcFile.Close()

	dstFile, err := safefile.OpenFile(dst, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0600)
	if err != nil {
		return err
	}
	if _, err = io.Copy(dstFile, srcFile); err != nil {
		_ = dstFile.Close()
		_ = os.Remove(dst)
		return fmt.Errorf("failed to copy file contents: %w", err)
	}
	if err := dstFile.Sync(); err != nil {
		_ = dstFile.Close()
		_ = os.Remove(dst)
		return fmt.Errorf("failed to sync destination file: %w", err)
	}
	if err := dstFile.Close(); err != nil {
		_ = os.Remove(dst)
		return fmt.Errorf("failed to close destination file: %w", err)
	}
	if srcInfo, err := os.Stat(src); err == nil {
		_ = os.Chmod(dst, srcInfo.Mode())
	}
	return nil
}

// replaceFileSafely 使用暫存檔原子替換目標，確保中途失敗時目標檔案仍保持完整
func (m *Mover) replaceFileSafely(src, dst string) error {
	tmpDst := fmt.Sprintf("%s.tmp-%d", dst, time.Now().UnixNano())
	if err := m.copyFile(src, tmpDst); err != nil {
		return fmt.Errorf("無法複製到暫存檔: %w", err)
	}
	if err := os.Rename(tmpDst, dst); err != nil {
		_ = os.Remove(tmpDst)
		return fmt.Errorf("無法以暫存檔替換目標: %w", err)
	}
	// 覆蓋完成後刪除來源：送入資源回收筒（Windows），非 Windows 則永久刪除
	if err := recycleFile(src); err != nil {
		return fmt.Errorf("目標已替換但刪除來源失敗: %w", err)
	}
	return nil
}
