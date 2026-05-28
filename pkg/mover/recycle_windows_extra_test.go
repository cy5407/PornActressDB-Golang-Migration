//go:build windows

package mover

import "testing"

func TestRecycleFile_NullBytePathFailsUTF16Conversion(t *testing.T) {
	// syscall.UTF16FromString rejects a string containing a NUL byte,
	// exercising recycleFile's early conversion-error return.
	if err := recycleFile("bad\x00path"); err == nil {
		t.Error("recycleFile with null-byte path returned nil, want UTF-16 conversion error")
	}
}
