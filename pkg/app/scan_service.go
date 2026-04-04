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

func ScanFiles(req ScanRequest) ([]contracts.ScanResult, error) {
	if _, err := os.Stat(req.Dir); os.IsNotExist(err) {
		return nil, fmt.Errorf("目錄不存在: %s", req.Dir)
	}

	ext := extractor.NewCodeExtractor()
	results := make([]contracts.ScanResult, 0)
	supportedFormats := make(map[string]bool, len(extractor.SupportedFormats))
	for _, f := range extractor.SupportedFormats {
		supportedFormats[f] = true
	}

	jobs := make(chan string, 100)
	var mu sync.Mutex
	var wg sync.WaitGroup

	for i := 0; i < req.Workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for path := range jobs {
				if code := ext.ExtractCode(path); code != "" {
					mu.Lock()
					results = append(results, contracts.ScanResult{Path: path, Code: code})
					mu.Unlock()
				}
			}
		}()
	}

	absDir, absErr := filepath.Abs(req.Dir)
	if absErr != nil {
		return nil, fmt.Errorf("無法取得目錄絕對路徑: %v", absErr)
	}

	err := filepath.WalkDir(req.Dir, func(path string, d os.DirEntry, err error) error {
		if err != nil || d == nil {
			return nil
		}
		if d.IsDir() {
			if req.Recursive {
				return nil
			}
			absPath, absPathErr := filepath.Abs(path)
			if absPathErr != nil || absPath == absDir {
				return nil
			}
			return filepath.SkipDir
		}
		if !supportedFormats[strings.ToLower(filepath.Ext(path))] {
			return nil
		}
		jobs <- path
		return nil
	})
	close(jobs)
	wg.Wait()
	if err != nil {
		return results, fmt.Errorf("遍歷目錄時發生錯誤: %v", err)
	}
	return results, nil
}
