//go:build windows

package mover

import (
	"fmt"
	"syscall"
	"unsafe"
)

var (
	shell32          = syscall.NewLazyDLL("shell32.dll")
	shFileOperationW = shell32.NewProc("SHFileOperationW")
)

const (
	foDelete          = uint32(0x0003)
	fofAllowUndo      = uint16(0x0040)
	fofNoConfirmation = uint16(0x0010)
	fofSilent         = uint16(0x0004)
	fofNoErrorUI      = uint16(0x0400)
)

// shFileOpStructW mirrors Windows SHFILEOPSTRUCTW.
type shFileOpStructW struct {
	hwnd                  uintptr
	wFunc                 uint32
	pFrom                 uintptr
	pTo                   uintptr
	fFlags                uint16
	fAnyOperationsAborted int32
	hNameMappings         uintptr
	lpszProgressTitle     uintptr
}

// recycleFile 將指定路徑的檔案送入 Windows 資源回收筒。
// 若送入失敗（例如路徑在網路磁碟），回傳 error，呼叫方可降級為 os.Remove。
func recycleFile(path string) error {
	// SHFileOperationW 的 pFrom 需要雙 null 結尾的 UTF-16 字串
	encoded, err := syscall.UTF16FromString(path)
	if err != nil {
		return fmt.Errorf("無法將路徑轉成 UTF-16: %w", err)
	}
	// 確保雙 null 結尾（StringToUTF16 已加一個 null，再補一個）
	buf := append(encoded, 0)

	op := shFileOpStructW{
		wFunc:  foDelete,
		pFrom:  uintptr(unsafe.Pointer(&buf[0])),
		fFlags: fofAllowUndo | fofNoConfirmation | fofSilent | fofNoErrorUI,
	}

	ret, _, callErr := shFileOperationW.Call(uintptr(unsafe.Pointer(&op)))
	if callErr != syscall.Errno(0) {
		return fmt.Errorf("呼叫 SHFileOperationW 失敗: %w", callErr)
	}
	if ret != 0 {
		return fmt.Errorf("SHFileOperationW 回傳錯誤碼 %d（路徑: %s）", ret, path)
	}
	return nil
}
