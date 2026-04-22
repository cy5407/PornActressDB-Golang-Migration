package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"

	"actress-classifier/pkg/app"
	"actress-classifier/pkg/contracts"
	"actress-classifier/pkg/extractor"
	"actress-classifier/pkg/safefile"
)

type moveCommandOptions struct {
	src        string
	dst        string
	batch      string
	batchStdin bool
	kind       string
	strategy   string
	dryRun     bool
	logDir     string
}

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
  db        資料庫操作（get, update, delete, list, stats, merge, compact,
            fix-studios, actress-get/update/delete/list, clean-actresses,
            backup-create/backup-restore/backup-list/backup-cleanup）
  identify  識別番號所屬片商
  cache     快取管理（stats, prune, clear, get, set, delete）

範例:
  classifier.exe scan -dir "D:\Videos"
  classifier.exe move -src "A.mp4" -dst "B/A.mp4"
  classifier.exe move -kind dir -src "A" -dst "B/A"
  classifier.exe move -batch moves.json
  classifier.exe history list
  classifier.exe history rollback abc123
  classifier.exe db get STARS-707
  classifier.exe db update STARS-707 video.json
  classifier.exe db delete STARS-707
  classifier.exe db list
  classifier.exe db stats
  classifier.exe db merge -source dist\data\json_db\data.json
  classifier.exe db compact
  classifier.exe db fix-studios
  classifier.exe db actress-get "Julia"
  classifier.exe db actress-update "Julia" actress.json
  classifier.exe db actress-delete "Julia"
  classifier.exe db actress-list
  classifier.exe db clean-actresses
  classifier.exe db clean-actresses -write
  classifier.exe db backup-create
  classifier.exe db backup-restore backup-2026-01-01.json
  classifier.exe db backup-list
  classifier.exe db backup-cleanup
  classifier.exe identify SONE-123
  classifier.exe identify -batch codes.txt
  classifier.exe cache stats
  classifier.exe cache prune -ttl-days 7
  classifier.exe cache clear -confirm
  classifier.exe cache get "search:STARS-707"
  classifier.exe cache set "key" "value"
  classifier.exe cache delete "search:STARS-707"`)
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
	opts := parseMoveCommandOptions(args)
	if handleBatchMove(opts) {
		return
	}
	runSingleMove(opts)
}

func parseMoveCommandOptions(args []string) moveCommandOptions {
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
	return moveCommandOptions{
		src:        *src,
		dst:        *dst,
		batch:      *batch,
		batchStdin: *batchStdin,
		kind:       *kind,
		strategy:   *strategy,
		dryRun:     *dryRun,
		logDir:     *logDir,
	}
}

func handleBatchMove(opts moveCommandOptions) bool {
	if opts.batch != "" {
		runBatchMoveFile(opts)
		return true
	}
	if opts.batchStdin {
		runBatchMoveStdin(opts)
		return true
	}
	return false
}

func runBatchMoveFile(opts moveCommandOptions) {
	data, err := safefile.ReadFile(opts.batch)
	if err != nil {
		printError(fmt.Sprintf("無法讀取批次檔案: %v", err), "請確認檔案路徑正確")
		os.Exit(1)
	}

	var items []contracts.MoveItem
	unmarshalErr := json.Unmarshal(data, &items)
	if unmarshalErr != nil {
		printError(fmt.Sprintf("JSON 解析錯誤: %v", unmarshalErr), "批次檔案必須是有效的 JSON 陣列格式")
		os.Exit(1)
	}
	result, runErr := app.BatchMove(context.Background(), items, opts.strategy, opts.dryRun, opts.logDir)
	if runErr != nil {
		printError(runErr.Error(), "請確認批次移動輸入與參數格式正確")
		os.Exit(1)
	}
	outputJSON(result)
}

func runBatchMoveStdin(opts moveCommandOptions) {
	result, err := app.BatchMoveStdin(context.Background(), opts.strategy, opts.dryRun, opts.logDir)
	if err != nil {
		printError(err.Error(), "請確認 stdin 為有效的 JSON 陣列")
		os.Exit(1)
	}
	outputJSON(result)
}

func runSingleMove(opts moveCommandOptions) {
	validateSingleMoveOptions(opts)
	switch opts.kind {
	case "dir":
		runDirMove(opts)
	case "file":
		runFileMove(opts)
	default:
		printError(fmt.Sprintf("未知的移動類型: %s", opts.kind), "有效值: file, dir")
		os.Exit(1)
	}
}

func validateSingleMoveOptions(opts moveCommandOptions) {
	if opts.src == "" || opts.dst == "" {
		printError("必須指定 -src 和 -dst，或使用 -batch / -batch-stdin")
		printMoveUsage()
		os.Exit(1)
	}
}

func printMoveUsage() {
	fmt.Fprintln(os.Stderr, "用法: classifier.exe move -src <來源> -dst <目標> [-kind file|dir] [-strategy skip|overwrite|rename]")
}

func runDirMove(opts moveCommandOptions) {
	result, err := app.MoveDir(opts.src, opts.dst, opts.strategy, opts.dryRun, opts.logDir)
	if err != nil {
		printError(err.Error(), "有效值: file, dir；strategy: skip, overwrite, rename")
		os.Exit(1)
	}
	outputJSON(result)
}

func runFileMove(opts moveCommandOptions) {
	result, err := app.MoveFile(opts.src, opts.dst, opts.strategy, opts.dryRun, opts.logDir)
	if err != nil {
		printError(err.Error(), "有效值: file, dir；strategy: skip, overwrite, rename")
		os.Exit(1)
	}
	outputJSON(result)
}

// === History 命令 ===

type historyCommandOptions struct {
	logDir     string
	jsonOutput bool
}

func historyCmd(args []string) {
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe history <list|show|rollback> [選項]")
		os.Exit(1)
	}

	subCmd := args[0]
	opts, remaining := parseHistoryCommandOptions(subCmd, args[1:])

	handler, ok := historyHandlers[subCmd]
	if !ok {
		fmt.Fprintf(os.Stderr, "未知的子命令: %s\n", subCmd)
		os.Exit(1)
	}
	handler(opts, remaining)
}

func parseHistoryCommandOptions(subCmd string, args []string) (historyCommandOptions, []string) {
	// 使用 flag.FlagSet 統一解析 -log-dir 參數
	// 注意：Go flag 遇到非旗標字串就停止解析，因此把旗標和非旗標引數分開處理，
	// 讓 `history rollback <id> -log-dir <path>` 和 `history rollback -log-dir <path> <id>` 都能正常運作。
	fs := flag.NewFlagSet("history "+subCmd, flag.ExitOnError)
	logDir := fs.String("log-dir", "logs", "操作日誌目錄")
	jsonOutput := fs.Bool("json", false, "以 JSON 格式輸出")
	flagArgs, posArgs := splitHistoryArgs(subCmd, args)
	parseFlagsOrExit(fs, flagArgs)
	return historyCommandOptions{
		logDir:     *logDir,
		jsonOutput: *jsonOutput,
	}, posArgs
}

func splitHistoryArgs(subCmd string, rawArgs []string) ([]string, []string) {
	var flagArgs, posArgs []string
	for i := 0; i < len(rawArgs); i++ {
		a := rawArgs[i]
		if subCmd == "rollback" && a == "--last" {
			posArgs = append(posArgs, a)
			continue
		}
		if !strings.HasPrefix(a, "-") {
			posArgs = append(posArgs, a)
			continue
		} else {
			flagArgs = append(flagArgs, a)
			i = consumeHistoryFlagValue(a, rawArgs, i, &flagArgs)
		}
	}
	return flagArgs, posArgs
}

func consumeHistoryFlagValue(flagArg string, rawArgs []string, index int, flagArgs *[]string) int {
	if strings.Contains(flagArg, "=") || !expectsHistoryFlagValue(flagArg) {
		return index
	}
	nextIndex := index + 1
	if nextIndex >= len(rawArgs) || strings.HasPrefix(rawArgs[nextIndex], "-") {
		return index
	}
	*flagArgs = append(*flagArgs, rawArgs[nextIndex])
	return nextIndex
}

func expectsHistoryFlagValue(flagArg string) bool {
	return flagArg == "-log-dir" || flagArg == "--log-dir"
}

var historyHandlers = map[string]func(historyCommandOptions, []string){
	"list":     runHistoryList,
	"show":     runHistoryShow,
	"rollback": runHistoryRollback,
}

func runHistoryList(opts historyCommandOptions, _ []string) {
	logs, err := app.ListOperations(opts.logDir, 0)
	if err != nil {
		printError(fmt.Sprintf("無法列出操作: %v", err))
		os.Exit(1)
	}

	if len(logs) == 0 {
		if opts.jsonOutput {
			outputJSON([]contracts.OperationLog{})
		} else {
			fmt.Println("沒有操作記錄")
		}
		return
	}

	if opts.jsonOutput {
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
}

func runHistoryShow(opts historyCommandOptions, remaining []string) {
	if len(remaining) < 1 {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe history show <操作ID>")
		os.Exit(1)
	}
	log, err := app.ShowOperation(opts.logDir, remaining[0])
	if err != nil {
		printError(err.Error(), "請使用 'history list' 查看有效的操作 ID")
		os.Exit(1)
	}
	outputJSON(log)
}

func runHistoryRollback(opts historyCommandOptions, remaining []string) {
	if len(remaining) < 1 {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe history rollback <操作ID>")
		os.Exit(1)
	}
	result, err := app.Rollback(opts.logDir, remaining[0], remaining[0] == "--last")
	if err != nil {
		printError(fmt.Sprintf("回滾失敗: %v", err))
		os.Exit(1)
	}

	if !opts.jsonOutput {
		printSuccess("回滾完成: 成功 %d, 失敗 %d", result.SuccessCount, result.FailedCount)
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
