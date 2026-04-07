package backend

import (
	"context"
	"os"
	"path/filepath"

	"actress-classifier/pkg/extractor"
)

// App is the main application struct exposed as Wails bindings.
type App struct {
	ctx       context.Context
	extractor *extractor.CodeExtractor
}

// NewApp creates a new App instance.
func NewApp() *App {
	return &App{
		extractor: extractor.NewCodeExtractor(),
	}
}

// Startup is called when the app starts.
func (a *App) Startup(ctx context.Context) {
	a.ctx = ctx
}

// ScanResult represents a single scanned video file.
type ScanResult struct {
	Path string `json:"path"`
	Code string `json:"code"`
}

// ScanDirectory scans the given directory for video files and extracts their codes.
// Returns a slice of ScanResult (path + extracted code).
func (a *App) ScanDirectory(dir string) []ScanResult {
	var results []ScanResult

	_ = filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() {
			return nil
		}
		code := a.extractor.ExtractCode(filepath.Base(path))
		if code != "" {
			results = append(results, ScanResult{Path: path, Code: code})
		}
		return nil
	})

	return results
}
