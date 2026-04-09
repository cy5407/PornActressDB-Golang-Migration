package pathutil

import (
	"os"
	"path/filepath"
	"strings"
)

// IsSameOrNestedPath reports whether target is the same path as base,
// or located inside base.
func IsSameOrNestedPath(base, target string) (bool, error) {
	absBase, err := filepath.Abs(base)
	if err != nil {
		return false, err
	}
	absTarget, err := filepath.Abs(target)
	if err != nil {
		return false, err
	}

	absBase = filepath.Clean(absBase)
	absTarget = filepath.Clean(absTarget)

	baseVolume := filepath.VolumeName(absBase)
	targetVolume := filepath.VolumeName(absTarget)
	if baseVolume != "" || targetVolume != "" {
		if !strings.EqualFold(baseVolume, targetVolume) {
			return false, nil
		}
	}

	relPath, err := filepath.Rel(absBase, absTarget)
	if err != nil {
		return false, err
	}
	if relPath == "." {
		return true, nil
	}
	if relPath == ".." || strings.HasPrefix(relPath, ".."+string(os.PathSeparator)) {
		return false, nil
	}
	return true, nil
}
