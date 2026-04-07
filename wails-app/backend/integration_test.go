package backend

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

func TestIntegrationBackendSmoke(t *testing.T) {
	app := newTestApp(t)
	app.Startup(context.Background())

	// Smoke test 1: app initialisation should not panic and bindings should be callable.
	if app == nil {
		t.Fatal("expected app to be initialised")
	}

	// Smoke test 2: ScanDirectory binding should be callable and return a slice.
	tmp := t.TempDir()
	if err := os.WriteFile(filepath.Join(tmp, "STARS-707.mp4"), []byte("fake"), 0600); err != nil {
		t.Fatalf("failed to create test video: %v", err)
	}
	results := app.ScanDirectory(tmp, 2, true)
	if results == nil {
		t.Fatal("ScanDirectory returned nil slice")
	}

	// Smoke test 3: GetPreferences should return a valid struct.
	prefs, err := app.GetPreferences()
	if err != nil {
		t.Fatalf("GetPreferences failed: %v", err)
	}
	if prefs.BatchSize == 0 {
		t.Fatal("GetPreferences returned zero-valued preferences unexpectedly")
	}
}
