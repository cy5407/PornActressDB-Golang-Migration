package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"

	"actress-classifier/pkg/app"
	"actress-classifier/pkg/contracts"
	"actress-classifier/pkg/extractor"
	"actress-classifier/pkg/safefile"
)

func parseFlagsOrExit(fs *flag.FlagSet, args []string) {
	if err := fs.Parse(args); err != nil {
		os.Exit(2)
	}
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
	case "db":
		dbCmd(os.Args[2:])
	case "identify":
		identifyCmd(os.Args[2:])
	case "cache":
		cacheCmd(os.Args[2:])
	case "help", "-h", "--help":
		printUsage()
	default:
		// 向後相容：如果第一個參數是 -dir，使用舊的 scan 模式
		if len(os.Args) > 1 && (os.Args[1] == "-dir" || os.Args[1] == "-workers") {
			scanCmd(os.Args[1:])
		} else {
			printError(fmt.Sprintf("未知命令: %s", command), "使用 'help' 查看所有可用命令")
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
  db        資料庫操作（get, update, delete, list, stats, merge）
  identify  識別番號所屬片商
  cache     快取管理（stats, prune, clear）

範例:
  classifier.exe scan -dir "D:\Videos"
  classifier.exe move -src "A.mp4" -dst "B/A.mp4"
  classifier.exe move -kind dir -src "A" -dst "B/A"
  classifier.exe move -batch moves.json
  classifier.exe history list
  classifier.exe history rollback abc123
  classifier.exe db get STARS-707
  classifier.exe db update STARS-707 video.json
  classifier.exe db list
  classifier.exe db stats
  classifier.exe db merge -source dist\data\json_db\data.json
  classifier.exe identify SONE-123
  classifier.exe identify -batch codes.txt
  classifier.exe cache stats
  classifier.exe cache prune -ttl-days 7
  classifier.exe cache clear -confirm`)
}

// === Scan 命令 ===

func scanCmd(args []string) {
	fs := flag.NewFlagSet("scan", flag.ExitOnError)
	dir := fs.String("dir", ".", "要掃描的目錄")
	workers := fs.Int("workers", 10, "並行工作數")
	recursive := fs.Bool("recursive", true, "是否遞迴掃描子目錄")
	showProgress := fs.Bool("progress", false, "顯示掃描進度條（輸出至 stderr）")
	extractFile := fs.String("extract", "", "從單一檔案名稱提取番號")
	parseFlagsOrExit(fs, args)

	if *extractFile != "" {
		e := extractor.NewCodeExtractor()
		code := e.ExtractCode(*extractFile)
		outputJSON(map[string]string{"filename": *extractFile, "code": code})
		return
	}

	if *showProgress {
		fmt.Fprintln(os.Stderr, "[WARNING] -progress 目前未接入 app service，將以一般模式掃描")
	}
	results, err := app.ScanFiles(app.ScanRequest{Dir: *dir, Workers: *workers, Recursive: *recursive})
	if err != nil {
		printError(err.Error(), "請確認路徑正確並具有讀取權限")
		os.Exit(1)
	}
	outputJSON(results)
}

// === Move 命令 ===

func moveCmd(args []string) {
	fs := flag.NewFlagSet("move", flag.ExitOnError)
	src := fs.String("src", "", "來源路徑")
	dst := fs.String("dst", "", "目標路徑")
	batch := fs.String("batch", "", "批次移動 JSON 檔案")
	batchStdin := fs.Bool("batch-stdin", false, "從 stdin 讀取批次移動 JSON")
	kind := fs.String("kind", "file", "移動類型: file, dir")
	strategy := fs.String("strategy", "skip", "衝突策略: skip, overwrite, rename")
	dryRun := fs.Bool("dry-run", false, "模擬執行模式")
	logDir := fs.String("log-dir", "logs", "操作日誌目錄")
	parseFlagsOrExit(fs, args)

	// 批次模式
	if *batch != "" {
		data, err := safefile.ReadFile(*batch)
		if err != nil {
			printError(fmt.Sprintf("無法讀取批次檔案: %v", err), "請確認檔案路徑正確")
			os.Exit(1)
		}

		var items []contracts.MoveItem
		if err := json.Unmarshal(data, &items); err != nil {
			printError(fmt.Sprintf("JSON 解析錯誤: %v", err), "批次檔案必須是有效的 JSON 陣列格式")
			os.Exit(1)
		}
		result, err := app.BatchMove(context.Background(), items, *strategy, *dryRun, *logDir)
		if err != nil {
			printError(err.Error(), "請確認批次移動輸入與參數格式正確")
			os.Exit(1)
		}
		outputJSON(result)
		return
	}
	if *batchStdin {
		result, err := app.BatchMoveStdin(context.Background(), *strategy, *dryRun, *logDir)
		if err != nil {
			printError(err.Error(), "請確認 stdin 為有效的 JSON 陣列")
			os.Exit(1)
		}
		outputJSON(result)
		return
	}

	// 單檔模式
	if *src == "" || *dst == "" {
		printError("必須指定 -src 和 -dst，或使用 -batch / -batch-stdin")
		fs.Usage()
		os.Exit(1)
	}

	if *kind == "dir" {
		result, err := app.MoveDir(*src, *dst, *strategy, *dryRun, *logDir)
		if err != nil {
			printError(err.Error(), "有效值: file, dir；strategy: skip, overwrite, rename")
			os.Exit(1)
		}
		outputJSON(result)
		return
	}

	if *kind != "file" {
		printError(fmt.Sprintf("未知的移動類型: %s", *kind), "有效值: file, dir")
		os.Exit(1)
	}

	result, err := app.MoveFile(*src, *dst, *strategy, *dryRun, *logDir)
	if err != nil {
		printError(err.Error(), "有效值: file, dir；strategy: skip, overwrite, rename")
		os.Exit(1)
	}
	outputJSON(result)
}

// === History 命令 ===

func historyCmd(args []string) {
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe history <list|show|rollback> [選項]")
		os.Exit(1)
	}

	subCmd := args[0]

	// 使用 flag.FlagSet 統一解析 -log-dir 參數
	fs := flag.NewFlagSet("history "+subCmd, flag.ExitOnError)
	logDir := fs.String("log-dir", "logs", "操作日誌目錄")
	jsonOutput := fs.Bool("json", false, "以 JSON 格式輸出")
	parseFlagsOrExit(fs, args[1:])
	remaining := fs.Args()

	switch subCmd {
	case "list":
		logs, err := app.ListOperations(*logDir, 0)
		if err != nil {
			printError(fmt.Sprintf("無法列出操作: %v", err))
			os.Exit(1)
		}

		if len(logs) == 0 {
			if *jsonOutput {
				outputJSON([]contracts.OperationLog{})
			} else {
				fmt.Println("沒有操作記錄")
			}
			return
		}

		if *jsonOutput {
			outputJSON(logs)
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
		if len(remaining) < 1 {
			fmt.Fprintln(os.Stderr, "用法: classifier.exe history show <操作ID>")
			os.Exit(1)
		}
		log, err := app.ShowOperation(*logDir, remaining[0])
		if err != nil {
			printError(err.Error(), "請使用 'history list' 查看有效的操作 ID")
			os.Exit(1)
		}
		outputJSON(log)

	case "rollback":
		if len(remaining) < 1 {
			fmt.Fprintln(os.Stderr, "用法: classifier.exe history rollback <操作ID>")
			os.Exit(1)
		}
		result, err := app.Rollback(*logDir, remaining[0], remaining[0] == "--last")
		if err != nil {
			printError(fmt.Sprintf("回滾失敗: %v", err))
			os.Exit(1)
		}

		if !*jsonOutput {
			printSuccess("回滾完成: 成功 %d, 失敗 %d", result.SuccessCount, result.FailedCount)
		}
		outputJSON(result)

	default:
		fmt.Fprintf(os.Stderr, "未知的子命令: %s\n", subCmd)
		os.Exit(1)
	}
}

// === 輔助函式 ===

func outputJSON(v any) {
	output, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		fmt.Fprintf(os.Stderr, "JSON 編碼錯誤: %v\n", err)
		return
	}
	fmt.Println(string(output))
}
