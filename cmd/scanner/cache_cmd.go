package main

import (
	"context"
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
		os.Exit(1)
	}

	switch args[0] {
	case "stats":
		cacheStatsCmd(args[1:])
	case "prune":
		cachePruneCmd(args[1:])
	case "clear":
		cacheClearCmd(args[1:])
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
