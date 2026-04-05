package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"

	"actress-classifier/pkg/database"
	"actress-classifier/pkg/safefile"
)

func dbCmd(args []string) {
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe db <get|update|delete|list|stats|compact|merge> [選項]")
		os.Exit(1)
	}

	subCmd := args[0]
	fs := flag.NewFlagSet("db "+subCmd, flag.ExitOnError)
	dataDir := fs.String("data-dir", "data/json_db", "資料庫目錄")
	jsonOutput := fs.Bool("json", false, "以 JSON 格式輸出")
	fullOutput := fs.Bool("full", false, "輸出完整影片資料（僅 list 子命令）")
	parseFlagsOrExit(fs, args[1:])
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
		video, err := db.GetVideo(remaining[0])
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
		code, jsonFile := remaining[0], remaining[1]
		data, err := safefile.ReadFile(jsonFile)
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
		if *jsonOutput {
			outputJSON(map[string]any{"success": true, "action": "update", "code": code, "data_dir": *dataDir})
			return
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
		if *jsonOutput {
			outputJSON(map[string]any{"success": true, "action": "delete", "code": code, "data_dir": *dataDir})
			return
		}
		printSuccess("影片 %s 刪除成功", code)
	case "list":
		if *fullOutput {
			videos, err := db.GetAllVideos()
			if err != nil {
				fmt.Fprintf(os.Stderr, "列出影片失敗: %v\n", err)
				os.Exit(1)
			}
			outputJSON(videos)
		} else {
			codes, err := db.ListVideos()
			if err != nil {
				fmt.Fprintf(os.Stderr, "列出影片失敗: %v\n", err)
				os.Exit(1)
			}
			outputJSON(codes)
		}
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
		if *jsonOutput {
			outputJSON(map[string]any{"success": true, "action": "compact", "data_dir": *dataDir})
			return
		}
		printSuccess("Journal 合併成功")
	case "merge":
		mergeFS := flag.NewFlagSet("db merge", flag.ExitOnError)
		sourceFile := mergeFS.String("source", "", "來源 data.json 檔案路徑")
		overwrite := mergeFS.Bool("overwrite", false, "若番號已存在，是否覆蓋現有資料")
		parseFlagsOrExit(mergeFS, args[1:])
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
