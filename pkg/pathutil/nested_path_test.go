package pathutil

import (
	"path/filepath"
	"runtime"
	"testing"
)

func TestIsSameOrNestedPath_SamePath(t *testing.T) {
	base := t.TempDir()

	sameOrNested, err := IsSameOrNestedPath(base, base)
	if err != nil {
		t.Fatalf("expected nil error, got %v", err)
	}
	if !sameOrNested {
		t.Fatal("expected identical paths to be treated as same")
	}
}

func TestIsSameOrNestedPath_NestedPath(t *testing.T) {
	base := t.TempDir()
	target := filepath.Join(base, "nested", "child")

	sameOrNested, err := IsSameOrNestedPath(base, target)
	if err != nil {
		t.Fatalf("expected nil error, got %v", err)
	}
	if !sameOrNested {
		t.Fatal("expected nested path to be treated as nested")
	}
}

func TestIsSameOrNestedPath_DifferentVolumes(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("volume-name comparison is Windows-specific")
	}

	sameOrNested, err := IsSameOrNestedPath(`C:\source`, `D:\dest`)
	if err != nil {
		t.Fatalf("expected nil error for different volumes, got %v", err)
	}
	if sameOrNested {
		t.Fatal("expected different volumes to not be treated as same or nested")
	}
}
