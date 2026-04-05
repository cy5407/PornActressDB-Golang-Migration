package main

import (
	"context"
	"encoding/base64"
	"flag"
	"fmt"
	"os"

	"actress-classifier/pkg/cache"
)

func cacheCmd(args []string) {
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "cache 子命令:")
		fmt.Fprintln(os.Stderr, "  stats   顯示快取統計資訊")
		fmt.Fprintln(os.Stderr, "  prune   清理過期或超大的快取")
		fmt.Fprintln(os.Stderr, "  clear   清空所有快取")
		fmt.Fprintln(os.Stderr, "  get     讀取快取值")
		fmt.Fprintln(os.Stderr, "  set     寫入快取值")
		fmt.Fprintln(os.Stderr, "  delete  刪除快取條目")
		os.Exit(1)
	}

	switch args[0] {
	case "stats":
		cacheStatsCmd(args[1:])
	case "prune":
		cachePruneCmd(args[1:])
	case "clear":
		cacheClearCmd(args[1:])
	case "get":
		cacheGetCmd(args[1:])
	case "set":
		cacheSetCmd(args[1:])
	case "delete":
		cacheDeleteCmd(args[1:])
	default:
		fmt.Fprintf(os.Stderr, "未知的 cache 子命令: %s\n", args[0])
		os.Exit(1)
	}
}

func cacheStatsCmd(args []string) {
	fs := flag.NewFlagSet("cache stats", flag.ExitOnError)
	cacheDir := fs.String("cache-dir", "cache", "快取目錄")
	parseFlagsOrExit(fs, args)
	stats, err := cache.NewCacheManager(*cacheDir).GetStats()
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
	parseFlagsOrExit(fs, args)

	result, err := cache.NewCacheManager(*cacheDir).AutoCleanup(context.Background(), cache.PruneConfig{
		TTLDays:        *ttlDays,
		MaxSizeMB:      *maxSizeMB,
		MinKeepEntries: *minKeep,
		DryRun:         *dryRun,
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ 清理快取失敗: %v\n", err)
		os.Exit(1)
	}
	if *dryRun {
		fmt.Fprintln(os.Stderr, "🔍 模擬執行結果:")
	} else {
		fmt.Fprintln(os.Stderr, "🧹 清理完成:")
	}
	outputJSON(result)
}

func cacheClearCmd(args []string) {
	fs := flag.NewFlagSet("cache clear", flag.ExitOnError)
	cacheDir := fs.String("cache-dir", "cache", "快取目錄")
	confirm := fs.Bool("confirm", false, "確認清空所有快取")
	dryRun := fs.Bool("dry-run", false, "模擬執行（不實際刪除）")
	parseFlagsOrExit(fs, args)

	if !*confirm && !*dryRun {
		fmt.Fprintln(os.Stderr, "⚠️ 清空所有快取需要 -confirm 參數")
		fmt.Fprintln(os.Stderr, "   使用 -dry-run 可以預覽將被刪除的檔案")
		os.Exit(1)
	}

	result, err := cache.NewCacheManager(*cacheDir).ClearAll(*dryRun)
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌ 清空快取失敗: %v\n", err)
		os.Exit(1)
	}
	if *dryRun {
		fmt.Fprintln(os.Stderr, "🔍 模擬執行結果:")
	} else {
		fmt.Fprintln(os.Stderr, "🗑️ 已清空所有快取:")
	}
	outputJSON(result)
}

// cacheGetCmd 讀取快取值，以 JSON 格式輸出 base64 編碼的資料。
func cacheGetCmd(args []string) {
	fs := flag.NewFlagSet("cache get", flag.ExitOnError)
	cacheDir := fs.String("cache-dir", "cache", "快取目錄")
	parseFlagsOrExit(fs, args)

	if fs.NArg() < 1 {
		fmt.Fprintln(os.Stderr, "用法: cache get <key> [-cache-dir DIR]")
		os.Exit(1)
	}
	key := fs.Arg(0)

	value, found, err := cache.NewCacheManager(*cacheDir).Get(key)
	if err != nil {
		outputJSON(map[string]any{"success": false, "error": err.Error()})
		os.Exit(1)
	}
	if !found {
		outputJSON(map[string]any{"success": false, "error": "not found"})
		return
	}
	outputJSON(map[string]any{
		"success": true,
		"value":   base64.StdEncoding.EncodeToString(value),
	})
}

// cacheSetCmd 以 base64 字串寫入快取值。
func cacheSetCmd(args []string) {
	fs := flag.NewFlagSet("cache set", flag.ExitOnError)
	cacheDir := fs.String("cache-dir", "cache", "快取目錄")
	ttlHours := fs.Int("ttl-hours", 24, "快取存活時數 (<=0 視為立即過期)")
	parseFlagsOrExit(fs, args)

	if fs.NArg() < 2 {
		fmt.Fprintln(os.Stderr, "用法: cache set <key> <base64_value> [-cache-dir DIR] [-ttl-hours N]")
		os.Exit(1)
	}
	key := fs.Arg(0)
	rawB64 := fs.Arg(1)

	decoded, err := base64.StdEncoding.DecodeString(rawB64)
	if err != nil {
		outputJSON(map[string]any{"success": false, "error": fmt.Sprintf("base64 解碼失敗: %v", err)})
		os.Exit(1)
	}

	if err := cache.NewCacheManager(*cacheDir).Set(key, decoded, *ttlHours); err != nil {
		outputJSON(map[string]any{"success": false, "error": err.Error()})
		os.Exit(1)
	}
	outputJSON(map[string]any{"success": true})
}

// cacheDeleteCmd 刪除快取條目。
func cacheDeleteCmd(args []string) {
	fs := flag.NewFlagSet("cache delete", flag.ExitOnError)
	cacheDir := fs.String("cache-dir", "cache", "快取目錄")
	parseFlagsOrExit(fs, args)

	if fs.NArg() < 1 {
		fmt.Fprintln(os.Stderr, "用法: cache delete <key> [-cache-dir DIR]")
		os.Exit(1)
	}
	key := fs.Arg(0)

	if err := cache.NewCacheManager(*cacheDir).Delete(key); err != nil {
		outputJSON(map[string]any{"success": false, "error": err.Error()})
		os.Exit(1)
	}
	outputJSON(map[string]any{"success": true})
}
