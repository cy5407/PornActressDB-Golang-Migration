//go:build !windows

package mover

import "os"

// recycleFile 在非 Windows 平台上直接永久刪除（無垃圾桶概念）。
func recycleFile(path string) error {
	return os.Remove(path)
}
