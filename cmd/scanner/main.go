package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"actress-classifier/pkg/cache"
	"actress-classifier/pkg/database"
	"actress-classifier/pkg/extractor"
	"actress-classifier/pkg/mover"
	"actress-classifier/pkg/studio"
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
	fs.Parse(args)

	// 驗證目錄
	if _, err := os.Stat(*dir); os.IsNotExist(err) {
		printError(fmt.Sprintf("目錄不存在: %s", *dir), "請確認路徑正確並具有讀取權限")
		os.Exit(1)
	}

	ext := extractor.NewCodeExtractor()
	results := make([]ScanResult, 0)
	var mu sync.Mutex
	var wg sync.WaitGroup

	supportedFormats := make(map[string]bool, len(extractor.SupportedFormats))
	for _, f := range extractor.SupportedFormats {
		supportedFormats[f] = true
	}

	jobs := make(chan string, 100)

	// 若啟用進度條，先計算檔案數量
	var pb *ProgressBar
	if *showProgress {
		total := 0
		absDir, _ := filepath.Abs(*dir)
		filepath.WalkDir(*dir, func(path string, d os.DirEntry, err error) error { //nolint:errcheck
			if err != nil || d == nil {
				return nil
			}
			if d.IsDir() {
				if !*recursive {
					absPath, _ := filepath.Abs(path)
					if absPath != absDir {
						return filepath.SkipDir
					}
				}
				return nil
			}
			if supportedFormats[strings.ToLower(filepath.Ext(path))] {
				total++
			}
			return nil
		})
		pb = NewProgressBar(total, "掃描中")
	}

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
				if pb != nil {
					mu.Lock()
					pb.Increment()
					mu.Unlock()
				}
			}
		}()
	}

	absDir, _ := filepath.Abs(*dir)

	err := filepath.WalkDir(*dir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			if !*recursive {
				absPath, _ := filepath.Abs(path)
				if absPath != absDir {
					return filepath.SkipDir
				}
			}
			return nil
		}
		fileExt := strings.ToLower(filepath.Ext(path))
		if !supportedFormats[fileExt] {
			return nil
		}
		jobs <- path
		return nil
	})
	if err != nil {
		printWarning("遍歷目錄時發生錯誤: %v", err)
	}

	close(jobs)
	wg.Wait()

	if pb != nil {
		pb.Finish()
		printSuccess("掃描完成，找到 %d 個番號", len(results))
	}

	output, err := json.MarshalIndent(results, "", "  ")
	if err != nil {
		printError(fmt.Sprintf("JSON 編碼失敗: %v", err))
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
		printError(fmt.Sprintf("未知的衝突策略: %s", *strategy), "有效值: skip, overwrite, rename")
		os.Exit(1)
	}

	// 批次模式
	if *batch != "" {
		data, err := os.ReadFile(*batch)
		if err != nil {
			printError(fmt.Sprintf("無法讀取批次檔案: %v", err), "請確認檔案路徑正確")
			os.Exit(1)
		}

		var items []mover.MoveItem
		if err := json.Unmarshal(data, &items); err != nil {
			printError(fmt.Sprintf("JSON 解析錯誤: %v", err), "批次檔案必須是有效的 JSON 陣列格式")
			os.Exit(1)
		}

		// 設定預設策略
		for i := range items {
			if items[i].OnConflict == "" {
				items[i].OnConflict = conflictStrategy
			}
		}

		result := m.BatchMove(context.Background(), items)
		outputJSON(result)
		return
	}

	// 單檔模式
	if *src == "" || *dst == "" {
		printError("必須指定 -src 和 -dst，或使用 -batch")
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

	// 使用 flag.FlagSet 統一解析 -log-dir 參數
	fs := flag.NewFlagSet("history "+subCmd, flag.ExitOnError)
	logDir := fs.String("log-dir", "logs", "操作日誌目錄")
	jsonOutput := fs.Bool("json", false, "以 JSON 格式輸出")
	fs.Parse(args[1:]) //nolint:errcheck // ExitOnError 模式下不會回傳 error
	remaining := fs.Args()

	m := mover.NewMover(*logDir)

	switch subCmd {
	case "list":
		logs, err := m.ListOperations()
		if err != nil {
			printError(fmt.Sprintf("無法列出操作: %v", err))
			os.Exit(1)
		}

		if len(logs) == 0 {
			if *jsonOutput {
				outputJSON([]mover.OperationLog{})
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
		opID := remaining[0]

		logs, err := m.ListOperations()
		if err != nil {
			printError(fmt.Sprintf("無法讀取操作: %v", err))
			os.Exit(1)
		}

		for _, log := range logs {
			if log.ID == opID {
				outputJSON(log)
				return
			}
		}
		printError(fmt.Sprintf("找不到操作 ID: %s", opID), "請使用 'history list' 查看有效的操作 ID")
		os.Exit(1)

	case "rollback":
		if len(remaining) < 1 {
			fmt.Fprintln(os.Stderr, "用法: classifier.exe history rollback <操作ID>")
			os.Exit(1)
		}
		opID := remaining[0]

		// 特殊處理 --last
		if opID == "--last" {
			logs, err := m.ListOperations()
			if err != nil || len(logs) == 0 {
				printError("沒有可回滾的操作")
				os.Exit(1)
			}
			opID = logs[len(logs)-1].ID
		}

		result, err := m.Rollback(opID)
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

// === DB 命令 ===

func dbCmd(args []string) {
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe db <get|update|delete|list|stats|compact|merge> [選項]")
		os.Exit(1)
	}

	subCmd := args[0]

	// 使用 flag.FlagSet 統一解析 -data-dir 參數
	fs := flag.NewFlagSet("db "+subCmd, flag.ExitOnError)
	dataDir := fs.String("data-dir", "data/json_db", "資料庫目錄")
	fs.Parse(args[1:]) //nolint:errcheck // ExitOnError 模式下不會回傳 error
	remaining := fs.Args()

	db := database.NewJSONDatabase(*dataDir)
	if err := db.Load(context.Background()); err != nil {
		fmt.Fprintf(os.Stderr, "無法載入資料庫: %v\n", err)
		os.Exit(1)
	}

	switch subCmd {
	case "get":
		if len(remaining) < 1 {
			fmt.Fprintln(os.Stderr, "用法: classifier.exe db get <番號>")
			os.Exit(1)
		}
		code := remaining[0]

		video, err := db.GetVideo(code)
		if err != nil {
			fmt.Fprintf(os.Stderr, "取得影片失敗: %v\n", err)
			os.Exit(1)
		}

		outputJSON(video)

	case "update":
		if len(remaining) < 2 {
			fmt.Fprintln(os.Stderr, "用法: classifier.exe db update <番號> <JSON檔案>")
			os.Exit(1)
		}
		code := remaining[0]
		jsonFile := remaining[1]

		data, err := os.ReadFile(jsonFile)
		if err != nil {
			fmt.Fprintf(os.Stderr, "無法讀取 JSON 檔案: %v\n", err)
			os.Exit(1)
		}

		var video database.Video
		if err := json.Unmarshal(data, &video); err != nil {
			fmt.Fprintf(os.Stderr, "JSON 解析錯誤: %v\n", err)
			os.Exit(1)
		}

		if err := db.UpdateVideo(code, &video); err != nil {
			fmt.Fprintf(os.Stderr, "更新影片失敗: %v\n", err)
			os.Exit(1)
		}

		if err := db.Save(); err != nil {
			fmt.Fprintf(os.Stderr, "儲存資料庫失敗: %v\n", err)
			os.Exit(1)
		}

		printSuccess("影片 %s 更新成功", code)

	case "delete":
		if len(remaining) < 1 {
			fmt.Fprintln(os.Stderr, "用法: classifier.exe db delete <番號>")
			os.Exit(1)
		}
		code := remaining[0]

		if err := db.DeleteVideo(code); err != nil {
			fmt.Fprintf(os.Stderr, "刪除影片失敗: %v\n", err)
			os.Exit(1)
		}

		if err := db.Save(); err != nil {
			fmt.Fprintf(os.Stderr, "儲存資料庫失敗: %v\n", err)
			os.Exit(1)
		}

		printSuccess("影片 %s 刪除成功", code)

	case "list":
		codes, err := db.ListVideos()
		if err != nil {
			fmt.Fprintf(os.Stderr, "列出影片失敗: %v\n", err)
			os.Exit(1)
		}

		outputJSON(codes)

	case "stats":
		stats, err := db.GetStats()
		if err != nil {
			fmt.Fprintf(os.Stderr, "取得統計失敗: %v\n", err)
			os.Exit(1)
		}

		outputJSON(stats)

	case "compact":
		if err := db.CompactJournal(); err != nil {
			fmt.Fprintf(os.Stderr, "合併 journal 失敗: %v\n", err)
			os.Exit(1)
		}

		printSuccess("Journal 合併成功")

	case "merge":
		mergeFS := flag.NewFlagSet("db merge", flag.ExitOnError)
		sourceFile := mergeFS.String("source", "", "來源 data.json 檔案路徑")
		overwrite := mergeFS.Bool("overwrite", false, "若番號已存在，是否覆蓋現有資料")
		mergeFS.Parse(args[1:]) //nolint:errcheck // ExitOnError 模式下不會回傳 error

		if strings.TrimSpace(*sourceFile) == "" {
			fmt.Fprintln(os.Stderr, "用法: classifier.exe db merge -source <來源data.json> [-overwrite]")
			os.Exit(1)
		}

		stats, err := db.MergeFromFile(*sourceFile, *overwrite)
		if err != nil {
			fmt.Fprintf(os.Stderr, "合併資料庫失敗: %v\n", err)
			os.Exit(1)
		}

		if err := db.Save(); err != nil {
			fmt.Fprintf(os.Stderr, "儲存資料庫失敗: %v\n", err)
			os.Exit(1)
		}

		outputJSON(stats)

	default:
		fmt.Fprintf(os.Stderr, "未知的子命令: %s\n", subCmd)
		os.Exit(1)
	}
}

// === Identify 命令 ===

func identifyCmd(args []string) {
	fs := flag.NewFlagSet("identify", flag.ExitOnError)
	batchFile := fs.String("batch", "", "批次處理：從檔案讀取番號列表")
	rulesFile := fs.String("rules", "studios.json", "片商規則檔案路徑")
	showPrefixes := fs.Bool("prefixes", false, "顯示指定片商的所有前綴")
	listStudios := fs.Bool("list", false, "列出所有片商")
	checkMajor := fs.Bool("major", false, "檢查是否為大片商")
	fs.Parse(args)

	// 初始化片商識別器
	identifier, err := studio.NewStudioIdentifier(*rulesFile)
	if err != nil {
		printWarning("無法載入片商規則檔案，使用預設規則: %v", err)
	}

	// 列出所有片商
	if *listStudios {
		studios := identifier.GetAllStudios()
		for _, s := range studios {
			isMajor := ""
			if identifier.IsMajorStudio(s) {
				isMajor = " (大片商)"
			}
			fmt.Printf("%s%s\n", s, isMajor)
		}
		return
	}

	// 顯示片商前綴
	if *showPrefixes {
		if len(fs.Args()) == 0 {
			printError("請指定片商名稱", "用法: classifier.exe identify -prefixes <片商名稱>")
			os.Exit(1)
		}
		studioName := fs.Args()[0]
		prefixes := identifier.GetPrefixes(studioName)
		if len(prefixes) == 0 {
			fmt.Printf("片商 %s 沒有註冊的前綴\n", studioName)
		} else {
			fmt.Printf("片商 %s 的前綴: %s\n", studioName, strings.Join(prefixes, ", "))
		}
		return
	}

	// 批次處理
	if *batchFile != "" {
		data, err := os.ReadFile(*batchFile)
		if err != nil {
			fmt.Fprintf(os.Stderr, "錯誤: 無法讀取批次檔案: %v\n", err)
			os.Exit(1)
		}

		codes := strings.Split(string(data), "\n")
		results := make([]map[string]string, 0)

		for _, code := range codes {
			code = strings.TrimSpace(code)
			if code == "" {
				continue
			}

			studioName := identifier.IdentifyStudio(code)
			result := map[string]string{
				"code":   code,
				"studio": studioName,
			}

			if *checkMajor {
				result["is_major"] = fmt.Sprintf("%t", identifier.IsMajorStudio(studioName))
			}

			results = append(results, result)
		}

		outputJSON(results)
		return
	}

	// 單一番號識別
	if len(fs.Args()) == 0 {
		printError("請指定番號", "用法: classifier.exe identify <番號>")
		os.Exit(1)
	}

	code := fs.Args()[0]
	studioName := identifier.IdentifyStudio(code)

	result := map[string]any{
		"code":   code,
		"studio": studioName,
	}

	if *checkMajor {
		result["is_major"] = identifier.IsMajorStudio(studioName)
	}

	outputJSON(result)
}

// === Cache 命令 ===

func cacheCmd(args []string) {
	if len(args) == 0 {
		fmt.Println("cache 子命令:")
		fmt.Println("  stats   顯示快取統計資訊")
		fmt.Println("  prune   清理過期或超大的快取")
		fmt.Println("  clear   清空所有快取")
		os.Exit(1)
	}

	subCommand := args[0]

	switch subCommand {
	case "stats":
		cacheStatsCmd(args[1:])
	case "prune":
		cachePruneCmd(args[1:])
	case "clear":
		cacheClearCmd(args[1:])
	default:
		fmt.Fprintf(os.Stderr, "未知的 cache 子命令: %s\n", subCommand)
		os.Exit(1)
	}
}

func cacheStatsCmd(args []string) {
	fs := flag.NewFlagSet("cache stats", flag.ExitOnError)
	cacheDir := fs.String("cache-dir", "cache", "快取目錄")
	fs.Parse(args)

	cm := cache.NewCacheManager(*cacheDir)
	stats, err := cm.GetStats()
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ 取得快取統計失敗: %v\n", err)
		os.Exit(1)
	}

	outputJSON(stats)
}

func cachePruneCmd(args []string) {
	fs := flag.NewFlagSet("cache prune", flag.ExitOnError)
	cacheDir := fs.String("cache-dir", "cache", "快取目錄")
	ttlDays := fs.Int("ttl-days", 7, "快取保留天數")
	maxSizeMB := fs.Int("max-size", 500, "最大快取大小 (MB)")
	minKeep := fs.Int("min-keep", 100, "最小保留條目數")
	dryRun := fs.Bool("dry-run", false, "模擬執行（不實際刪除）")
	fs.Parse(args)

	cm := cache.NewCacheManager(*cacheDir)
	config := cache.PruneConfig{
		TTLDays:        *ttlDays,
		MaxSizeMB:      *maxSizeMB,
		MinKeepEntries: *minKeep,
		DryRun:         *dryRun,
	}

	result, err := cm.AutoCleanup(context.Background(), config)
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ 清理快取失敗: %v\n", err)
		os.Exit(1)
	}

	if *dryRun {
		fmt.Println("🔍 模擬執行結果:")
	} else {
		fmt.Println("🧹 清理完成:")
	}

	outputJSON(result)
}

func cacheClearCmd(args []string) {
	fs := flag.NewFlagSet("cache clear", flag.ExitOnError)
	cacheDir := fs.String("cache-dir", "cache", "快取目錄")
	confirm := fs.Bool("confirm", false, "確認清空所有快取")
	dryRun := fs.Bool("dry-run", false, "模擬執行（不實際刪除）")
	fs.Parse(args)

	if !*confirm && !*dryRun {
		fmt.Println("⚠️ 清空所有快取需要 -confirm 參數")
		fmt.Println("   使用 -dry-run 可以預覽將被刪除的檔案")
		os.Exit(1)
	}

	cm := cache.NewCacheManager(*cacheDir)
	result, err := cm.ClearAll(*dryRun)
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ 清空快取失敗: %v\n", err)
		os.Exit(1)
	}

	if *dryRun {
		fmt.Println("🔍 模擬執行結果:")
	} else {
		fmt.Println("🗑️ 已清空所有快取:")
	}

	outputJSON(result)
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
