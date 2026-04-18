package backend

import (
	"os/exec"
	"syscall"
)

// hideWindow sets the subprocess creation flags so no console window appears on Windows.
func hideWindow(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{
		HideWindow:    true,
		CreationFlags: 0x08000000, // CREATE_NO_WINDOW
	}
}
