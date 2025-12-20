package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sync"

	"actress-classifier/pkg/extractor"
	"actress-classifier/pkg/mover"
)

type ScanResult struct {
	Path string `json:"path"`
	Code string `json:"code"`
}

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	command := os.Args[1]

	switch command {
	case "scan":
		scanCmd(os.Args[2:])
	case "move":
		moveCmd(os.Args[2:])
	case "history":
		historyCmd(os.Args[2:])
	case "help", "-h", "--help":
		printUsage()
	default:
		// 向後相容：如果第一個參數是 -dir，使用舊的 scan 模式
		if len(os.Args) > 1 && (os.Args[1] == "-dir" || os.Args[1] == "-workers") {
			scanCmd(os.Args[1:])
		} else {
			fmt.Fprintf(os.Stderr, "未知命令: %s\n", command)
			printUsage()
			os.Exit(1)
		}
	}
}

func printUsage() {
	fmt.Println(`番號分類器 - classifier.exe

用法:
  classifier.exe <命令> [選項]

命令:
  scan      掃描目錄中的影片檔案，提取番號
  move      移動檔案（單檔或批次）
  history   查看操作歷史或回滾

範例:
  classifier.exe scan -dir "D:\Videos"
  classifier.exe move -src "A.mp4" -dst "B/A.mp4"
  classifier.exe move -batch moves.json
  classifier.exe history list
  classifier.exe history rollback abc123`)
}

// === Scan 命令 ===

func scanCmd(args []string) {
	fs := flag.NewFlagSet("scan", flag.ExitOnError)
	dir := fs.String("dir", ".", "要掃描的目錄")
	workers := fs.Int("workers", 10, "並行工作數")
	fs.Parse(args)

	// 驗證目錄
	if _, err := os.Stat(*dir); os.IsNotExist(err) {
		fmt.Fprintf(os.Stderr, "錯誤: 目錄不存在: %s\n", *dir)
		os.Exit(1)
	}

	ext := extractor.NewCodeExtractor()
	results := make([]ScanResult, 0)
	var mu sync.Mutex
	var wg sync.WaitGroup

	// 建立任務通道
	jobs := make(chan string, 100)

	// 啟動工作者
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

	// 遍歷目錄
	err := filepath.WalkDir(*dir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			return nil
		}
		jobs <- path
		return nil
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "遍歷目錄錯誤: %v\n", err)
	}

	close(jobs)
	wg.Wait()

	// 輸出 JSON
	output, err := json.MarshalIndent(results, "", "  ")
	if err != nil {
		fmt.Fprintf(os.Stderr, "JSON 編碼錯誤: %v\n", err)
		return
	}
	fmt.Println(string(output))
}

// === Move 命令 ===

func moveCmd(args []string) {
	fs := flag.NewFlagSet("move", flag.ExitOnError)
	src := fs.String("src", "", "來源路徑")
	dst := fs.String("dst", "", "目標路徑")
	batch := fs.String("batch", "", "批次移動 JSON 檔案")
	strategy := fs.String("strategy", "skip", "衝突策略: skip, overwrite, rename")
	dryRun := fs.Bool("dry-run", false, "模擬執行模式")
	logDir := fs.String("log-dir", "logs", "操作日誌目錄")
	fs.Parse(args)

	m := mover.NewMover(*logDir)
	m.DryRun = *dryRun

	// 解析衝突策略
	var conflictStrategy mover.ConflictStrategy
	switch *strategy {
	case "skip":
		conflictStrategy = mover.Skip
	case "overwrite":
		conflictStrategy = mover.Overwrite
	case "rename":
		conflictStrategy = mover.Rename
	default:
		fmt.Fprintf(os.Stderr, "未知的衝突策略: %s\n", *strategy)
		os.Exit(1)
	}

	// 批次模式
	if *batch != "" {
		data, err := os.ReadFile(*batch)
		if err != nil {
			fmt.Fprintf(os.Stderr, "無法讀取批次檔案: %v\n", err)
			os.Exit(1)
		}

		var items []mover.MoveItem
		if err := json.Unmarshal(data, &items); err != nil {
			fmt.Fprintf(os.Stderr, "JSON 解析錯誤: %v\n", err)
			os.Exit(1)
		}

		// 設定預設策略
		for i := range items {
			if items[i].OnConflict == "" {
				items[i].OnConflict = conflictStrategy
			}
		}

		result := m.BatchMove(items)
		outputJSON(result)
		return
	}

	// 單檔模式
	if *src == "" || *dst == "" {
		fmt.Fprintln(os.Stderr, "錯誤: 必須指定 -src 和 -dst，或使用 -batch")
		fs.Usage()
		os.Exit(1)
	}

	result := m.MoveFile(*src, *dst, conflictStrategy)
	outputJSON(result)
}

// === History 命令 ===

func historyCmd(args []string) {
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe history <list|show|rollback> [選項]")
		os.Exit(1)
	}

	subCmd := args[0]
	logDir := "logs"

	// 檢查是否有 -log-dir 參數
	for i, arg := range args {
		if arg == "-log-dir" && i+1 < len(args) {
			logDir = args[i+1]
		}
	}

	m := mover.NewMover(logDir)

	switch subCmd {
	case "list":
		logs, err := m.ListOperations()
		if err != nil {
			fmt.Fprintf(os.Stderr, "無法列出操作: %v\n", err)
			os.Exit(1)
		}

		if len(logs) == 0 {
			fmt.Println("沒有操作記錄")
			return
		}

		fmt.Printf("%-10s %-20s %-12s %-10s\n", "ID", "時間", "類型", "狀態")
		fmt.Println("------------------------------------------------------")
		for _, log := range logs {
			fmt.Printf("%-10s %-20s %-12s %-10s\n",
				log.ID,
				log.Timestamp.Format("2006-01-02 15:04:05"),
				log.Type,
				log.Status,
			)
		}

	case "show":
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "用法: classifier.exe history show <操作ID>")
			os.Exit(1)
		}
		opID := args[1]

		logs, err := m.ListOperations()
		if err != nil {
			fmt.Fprintf(os.Stderr, "無法讀取操作: %v\n", err)
			os.Exit(1)
		}

		for _, log := range logs {
			if log.ID == opID {
				outputJSON(log)
				return
			}
		}
		fmt.Fprintf(os.Stderr, "找不到操作 ID: %s\n", opID)
		os.Exit(1)

	case "rollback":
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "用法: classifier.exe history rollback <操作ID>")
			os.Exit(1)
		}
		opID := args[1]

		// 特殊處理 --last
		if opID == "--last" {
			logs, err := m.ListOperations()
			if err != nil || len(logs) == 0 {
				fmt.Fprintln(os.Stderr, "沒有可回滾的操作")
				os.Exit(1)
			}
			opID = logs[len(logs)-1].ID
		}

		result, err := m.Rollback(opID)
		if err != nil {
			fmt.Fprintf(os.Stderr, "回滾失敗: %v\n", err)
			os.Exit(1)
		}

		fmt.Printf("✅ 回滾完成: 成功 %d, 失敗 %d\n", result.SuccessCount, result.FailedCount)
		outputJSON(result)

	default:
		fmt.Fprintf(os.Stderr, "未知的子命令: %s\n", subCmd)
		os.Exit(1)
	}
}

// === 輔助函式 ===

func outputJSON(v interface{}) {
	output, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		fmt.Fprintf(os.Stderr, "JSON 編碼錯誤: %v\n", err)
		return
	}
	fmt.Println(string(output))
}
