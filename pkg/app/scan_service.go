package app

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"actress-classifier/pkg/contracts"
	"actress-classifier/pkg/extractor"
)

type ScanRequest struct {
	Dir       string
	Workers   int
	Recursive bool
}

func buildSupportedScanFormats() map[string]bool {
	supportedFormats := make(map[string]bool, len(extractor.SupportedFormats))
	for _, format := range extractor.SupportedFormats {
		supportedFormats[format] = true
	}
	return supportedFormats
}

func shouldSkipScanDirectory(path string, recursive bool, absDir string) (bool, error) {
	if recursive {
		return false, nil
	}

	absPath, err := filepath.Abs(path)
	if err != nil {
		return false, nil
	}

	return absPath != absDir, nil
}

func isSupportedScanFile(path string, supportedFormats map[string]bool) bool {
	return supportedFormats[strings.ToLower(filepath.Ext(path))]
}

func startScanWorkers(workers int, jobs <-chan string, ext *extractor.CodeExtractor, results *[]contracts.ScanResult, mu *sync.Mutex, wg *sync.WaitGroup) {
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for path := range jobs {
				if code := ext.ExtractCode(path); code != "" {
					mu.Lock()
					*results = append(*results, contracts.ScanResult{Path: path, Code: code})
					mu.Unlock()
				}
			}
		}()
	}
}

func walkScanFiles(root string, recursive bool, absDir string, supportedFormats map[string]bool, jobs chan<- string) error {
	return filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil || d == nil {
			return nil
		}

		if d.IsDir() {
			skip, skipErr := shouldSkipScanDirectory(path, recursive, absDir)
			if skipErr != nil {
				return skipErr
			}
			if skip {
				return filepath.SkipDir
			}
			return nil
		}

		if !isSupportedScanFile(path, supportedFormats) {
			return nil
		}

		jobs <- path
		return nil
	})
}

func ScanFiles(req ScanRequest) ([]contracts.ScanResult, error) {
	if _, err := os.Stat(req.Dir); os.IsNotExist(err) {
		return nil, fmt.Errorf("目錄不存在: %s", req.Dir)
	}

	ext := extractor.NewCodeExtractor()
	results := make([]contracts.ScanResult, 0)
	jobs := make(chan string, 100)
	var mu sync.Mutex
	var wg sync.WaitGroup

	startScanWorkers(req.Workers, jobs, ext, &results, &mu, &wg)

	absDir, absErr := filepath.Abs(req.Dir)
	if absErr != nil {
		return nil, fmt.Errorf("無法取得目錄絕對路徑: %v", absErr)
	}

	err := walkScanFiles(req.Dir, req.Recursive, absDir, buildSupportedScanFormats(), jobs)
	close(jobs)
	wg.Wait()
	if err != nil {
		return results, fmt.Errorf("遍歷目錄時發生錯誤: %v", err)
	}
	return results, nil
}
