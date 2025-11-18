package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sync"

	"actress-classifier/pkg/extractor"
)

type ScanResult struct {
	Path string `json:"path"`
	Code string `json:"code"`
}

func main() {
	dir := flag.String("dir", ".", "Directory to scan")
	workers := flag.Int("workers", 10, "Number of worker goroutines")
	flag.Parse()

	// Validate directory
	if _, err := os.Stat(*dir); os.IsNotExist(err) {
		fmt.Fprintf(os.Stderr, "Error: Directory does not exist: %s\n", *dir)
		os.Exit(1)
	}

	ext := extractor.NewCodeExtractor()
	results := make([]ScanResult, 0)
	var mu sync.Mutex
	var wg sync.WaitGroup

	// Create job channel
	jobs := make(chan string, 100)

	// Start workers
	for i := 0; i < *workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for path := range jobs {
				if code := ext.ExtractCode(path); code != "" {
					mu.Lock()
					results = append(results, ScanResult{Path: path, Code: code})
					mu.Unlock()
				}
			}
		}()
	}

	// Walk directory
	filepath.WalkDir(*dir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			return nil
		}
		jobs <- path
		return nil
	})

	close(jobs)
	wg.Wait()

	// Output JSON
	output, _ := json.MarshalIndent(results, "", "  ")
	fmt.Println(string(output))
}
