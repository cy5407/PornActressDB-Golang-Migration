package mover

import (
	"os"
	"path/filepath"
	"testing"
)

func TestApplyFileMode_ReturnsErrorForMissingTarget(t *testing.T) {
	err := applyFileMode(filepath.Join(t.TempDir(), "missing.txt"), 0600)
	if err == nil {
		t.Fatal("expected missing target to return error")
	}
	if !os.IsNotExist(err) {
		t.Fatalf("expected not-exist error, got %v", err)
	}
}
