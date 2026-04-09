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
	"actress-classifier/pkg/studio"
)

func dbCmd(args []string) {
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe db <get|update|delete|list|stats|compact|merge|fix-studios|actress-get|actress-update|actress-delete|actress-list|backup-create|backup-restore|backup-list|backup-cleanup> [選項]")
		os.Exit(1)
	}

	subCmd := args[0]

	// fix-studios 有獨立的 flag 集合，提前處理
	if subCmd == "fix-studios" {
		dbFixStudiosCmd(args[1:])
		return
	}
	if subCmd == "merge" {
		dbMergeCmd(args[1:])
		return
	}
	fs := flag.NewFlagSet("db "+subCmd, flag.ExitOnError)
	dataDir := fs.String("data-dir", "data/json_db", "資料庫目錄")
	jsonOutput := fs.Bool("json", false, "以 JSON 格式輸出")
	fullOutput := fs.Bool("full", false, "輸出完整影片資料（僅 list 子命令）")
	actressStats := fs.Bool("actress", false, "顯示女優統計")
	studioStats := fs.Bool("studio", false, "顯示片商統計")
	backupPath := fs.String("backup-path", "", "備份檔案路徑（用於 backup-restore）")
	backupDays := fs.Int("days", 30, "備份保留天數（用於 backup-cleanup）")
	backupMaxCount := fs.Int("max-count", 50, "最大備份數量（用於 backup-cleanup）")
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
		if *actressStats {
			stats, err := db.GetActressStats()
			if err != nil {
				fmt.Fprintf(os.Stderr, "取得女優統計失敗: %v\n", err)
				os.Exit(1)
			}
			outputJSON(stats)
		} else if *studioStats {
			stats, err := db.GetStudioStats()
			if err != nil {
				fmt.Fprintf(os.Stderr, "取得片商統計失敗: %v\n", err)
				os.Exit(1)
			}
			outputJSON(stats)
		} else {
			stats, err := db.GetStats()
			if err != nil {
				fmt.Fprintf(os.Stderr, "取得統計失敗: %v\n", err)
				os.Exit(1)
			}
			outputJSON(stats)
		}
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
	case "actress-get":
		if len(remaining) < 1 {
			fmt.Fprintln(os.Stderr, "用法: classifier.exe db actress-get <女優ID>")
			os.Exit(1)
		}
		actress, err := db.GetActress(remaining[0])
		if err != nil {
			fmt.Fprintf(os.Stderr, "取得女優失敗: %v\n", err)
			os.Exit(1)
		}
		outputJSON(actress)

	case "actress-update":
		if len(remaining) < 2 {
			fmt.Fprintln(os.Stderr, "用法: classifier.exe db actress-update <女優ID> <JSON檔案>")
			os.Exit(1)
		}
		actressID, jsonFile := remaining[0], remaining[1]
		data, err := safefile.ReadFile(jsonFile)
		if err != nil {
			fmt.Fprintf(os.Stderr, "無法讀取 JSON 檔案: %v\n", err)
			os.Exit(1)
		}
		var actress database.ActressData
		if err := json.Unmarshal(data, &actress); err != nil {
			fmt.Fprintf(os.Stderr, "JSON 解析錯誤: %v\n", err)
			os.Exit(1)
		}
		actress.ID = actressID
		if err := db.UpsertActress(&actress); err != nil {
			fmt.Fprintf(os.Stderr, "更新女優失敗: %v\n", err)
			os.Exit(1)
		}
		if err := db.Save(); err != nil {
			fmt.Fprintf(os.Stderr, "儲存資料庫失敗: %v\n", err)
			os.Exit(1)
		}
		if *jsonOutput {
			outputJSON(map[string]any{"success": true, "action": "actress-update", "id": actressID})
			return
		}
		printSuccess("女優 %s 更新成功", actressID)

	case "actress-delete":
		if len(remaining) < 1 {
			fmt.Fprintln(os.Stderr, "用法: classifier.exe db actress-delete <女優ID>")
			os.Exit(1)
		}
		actressID := remaining[0]
		if err := db.DeleteActress(actressID); err != nil {
			fmt.Fprintf(os.Stderr, "刪除女優失敗: %v\n", err)
			os.Exit(1)
		}
		if err := db.Save(); err != nil {
			fmt.Fprintf(os.Stderr, "儲存資料庫失敗: %v\n", err)
			os.Exit(1)
		}
		if *jsonOutput {
			outputJSON(map[string]any{"success": true, "action": "actress-delete", "id": actressID})
			return
		}
		printSuccess("女優 %s 刪除成功", actressID)

	case "actress-list":
		ids, err := db.ListActresses()
		if err != nil {
			fmt.Fprintf(os.Stderr, "列出女優失敗: %v\n", err)
			os.Exit(1)
		}
		outputJSON(ids)

	case "backup-create":
		path, err := db.BackupCreate()
		if err != nil {
			fmt.Fprintf(os.Stderr, "建立備份失敗: %v\n", err)
			os.Exit(1)
		}
		outputJSON(map[string]any{"path": path, "success": true})

	case "backup-restore":
		if strings.TrimSpace(*backupPath) == "" {
			fmt.Fprintln(os.Stderr, "用法: classifier.exe db backup-restore -backup-path <備份路徑> [-data-dir <目錄>]")
			os.Exit(1)
		}
		if err := db.BackupRestore(*backupPath); err != nil {
			fmt.Fprintf(os.Stderr, "還原備份失敗: %v\n", err)
			os.Exit(1)
		}
		outputJSON(map[string]any{"success": true})

	case "backup-list":
		backups, err := db.BackupList()
		if err != nil {
			fmt.Fprintf(os.Stderr, "列出備份失敗: %v\n", err)
			os.Exit(1)
		}
		if backups == nil {
			backups = []string{}
		}
		outputJSON(map[string]any{"backups": backups, "count": len(backups)})

	case "backup-cleanup":
		deletedCount, err := db.BackupCleanup(*backupDays, *backupMaxCount)
		if err != nil {
			fmt.Fprintf(os.Stderr, "清理備份失敗: %v\n", err)
			os.Exit(1)
		}
		outputJSON(map[string]any{"deleted": deletedCount, "success": true})

	default:
		fmt.Fprintf(os.Stderr, "未知的子命令: %s\n", subCmd)
		os.Exit(1)
	}
}

func dbMergeCmd(args []string) {
	fs := flag.NewFlagSet("db merge", flag.ExitOnError)
	dataDir := fs.String("data-dir", "data/json_db", "資料庫目錄")
	sourceFile := fs.String("source", "", "來源 data.json 檔案路徑")
	overwrite := fs.Bool("overwrite", false, "若番號已存在，是否覆蓋現有資料")
	parseFlagsOrExit(fs, args)

	if strings.TrimSpace(*sourceFile) == "" {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe db merge -source <來源data.json> [-overwrite] [-data-dir <目錄>]")
		os.Exit(1)
	}

	db := database.NewJSONDatabase(*dataDir)
	if err := db.Load(context.Background()); err != nil {
		fmt.Fprintf(os.Stderr, "無法載入資料庫: %v\n", err)
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
}

// dbFixStudiosCmd 批次修正資料庫內的片商欄位
func dbFixStudiosCmd(args []string) {
	fs := flag.NewFlagSet("db fix-studios", flag.ExitOnError)
	dataDir := fs.String("data-dir", "data/json_db", "資料庫目錄")
	studiosFile := fs.String("studios", "studios.json", "片商規則檔案路徑")
	forceFlag := fs.Bool("force", false, "強制覆蓋已有片商資料（非 UNKNOWN）")
	_ = fs.Bool("json", false, "輸出 JSON 格式（預設即為 JSON，保留相容性）")
	parseFlagsOrExit(fs, args)

	// 載入片商識別器
	si, err := studio.NewStudioIdentifier(*studiosFile)
	if err != nil {
		fmt.Fprintf(os.Stderr, "載入片商規則失敗: %v\n", err)
		os.Exit(1)
	}

	// 載入資料庫
	db := database.NewJSONDatabase(*dataDir)
	if err := db.Load(context.Background()); err != nil {
		fmt.Fprintf(os.Stderr, "無法載入資料庫: %v\n", err)
		os.Exit(1)
	}

	videos, err := db.GetAllVideos()
	if err != nil {
		fmt.Fprintf(os.Stderr, "取得影片清單失敗: %v\n", err)
		os.Exit(1)
	}

	type changeEntry struct {
		Code string `json:"code"`
		From string `json:"from"`
		To   string `json:"to"`
	}

	updated := 0
	skipped := 0
	alreadyCorrect := 0
	var changes []changeEntry

	for _, vd := range videos {
		code := vd.GetCode()
		if code == "" {
			skipped++
			continue
		}

		currentStudio := vd.Studio
		needsUpdate := currentStudio == "" || currentStudio == "UNKNOWN"

		if !needsUpdate && !*forceFlag {
			alreadyCorrect++
			continue
		}

		newStudio := si.IdentifyStudio(code)
		if newStudio == "UNKNOWN" || newStudio == "" {
			skipped++
			continue
		}

		if currentStudio == newStudio {
			alreadyCorrect++
			continue
		}

		if err := db.UpdateVideoFields(code, map[string]any{"studio": newStudio}); err != nil {
			fmt.Fprintf(os.Stderr, "更新 %s 失敗: %v\n", code, err)
			continue
		}

		updated++
		changes = append(changes, changeEntry{Code: code, From: currentStudio, To: newStudio})
	}

	if updated > 0 {
		if err := db.Save(); err != nil {
			fmt.Fprintf(os.Stderr, "儲存資料庫失敗: %v\n", err)
			os.Exit(1)
		}
	}

	result := map[string]any{
		"success":         true,
		"total":           len(videos),
		"updated":         updated,
		"skipped":         skipped,
		"already_correct": alreadyCorrect,
		"changes":         changes,
	}
	outputJSON(result)
}
