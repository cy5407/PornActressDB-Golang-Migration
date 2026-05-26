package main

import (
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"actress-classifier/pkg/database"
)

// dbMigrateFromJSONCmd handles `classifier.exe db migrate-from-json`.
//
// Flags:
//
//	-source <path>                      Source JSON DB; defaults to <data-dir>/data.json.
//	-data-dir <dir>                     JSON DB directory; controls SQLite location
//	                                    via compatibility lookup (see pkg/database.ResolveDataDirPaths).
//	-auto-create-missing-actresses      Promote unresolved video.actresses[] names
//	                                    into synthesised auto_<sha1> actress entities
//	                                    (default: strict mode, fail loudly).
//
// On success: report JSON to stdout, exit 0.
// On migration failure: report JSON to stdout (still well-formed), exit 1.
func dbMigrateFromJSONCmd(args []string) {
	fs := flag.NewFlagSet("db migrate-from-json", flag.ExitOnError)
	source := fs.String("source", "", "來源 data.json 檔案路徑（預設：<data-dir>/data.json）")
	dataDir := fs.String("data-dir", database.DefaultDataDir, "資料庫目錄")
	autoCreate := fs.Bool("auto-create-missing-actresses", false, "對未對齊的 video.actresses[] 名字自動建立 auto_<sha1> 女優實體")
	parseFlagsOrExit(fs, args)

	paths := database.ResolveDataDirPaths(*dataDir)
	srcPath := *source
	if srcPath == "" {
		srcPath = paths.DataFile
	}

	if err := os.MkdirAll(filepath.Dir(paths.SQLitePath), 0o750); err != nil {
		fmt.Fprintf(os.Stderr, "建立 SQLite 目錄失敗: %v\n", err)
		os.Exit(1)
	}

	store, err := database.OpenSQLiteStore(paths.SQLitePath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "開啟 SQLite 失敗: %v\n", err)
		os.Exit(1)
	}
	defer store.Close()

	if err := store.InitSchema(); err != nil {
		fmt.Fprintf(os.Stderr, "初始化 SQLite schema 失敗: %v\n", err)
		os.Exit(1)
	}

	report, migErr := store.MigrateFromJSON(srcPath, database.MigrationOptions{
		AutoCreateMissingActresses: *autoCreate,
	})
	outputJSON(report)

	if migErr != nil {
		if errors.Is(migErr, database.ErrMigrationUnresolved) ||
			errors.Is(migErr, database.ErrMigrationDuplicate) {
			// Strict-mode failure: report is the canonical artefact; print
			// a short reminder line on stderr.
			fmt.Fprintf(os.Stderr, "migrate-from-json failed: %v\n", migErr)
			os.Exit(1)
		}
		fmt.Fprintf(os.Stderr, "migrate-from-json error: %v\n", migErr)
		os.Exit(1)
	}
}

// dbResyncFromJSONCmd handles `classifier.exe db resync-from-json`.
//
// Flags are identical to db migrate-from-json. The semantic difference
// is that resync wipes the four data tables (videos /
// video_actress_links / actresses / actress_aliases) before re-applying
// the three migration passes, inside the same transaction. db_meta
// singletons are upserted, never deleted.
//
// Use when SQLite has drifted from JSON and a clean rebuild is cheaper
// than diffing.
func dbResyncFromJSONCmd(args []string) {
	fs := flag.NewFlagSet("db resync-from-json", flag.ExitOnError)
	source := fs.String("source", "", "來源 data.json 檔案路徑（預設：<data-dir>/data.json）")
	dataDir := fs.String("data-dir", database.DefaultDataDir, "資料庫目錄")
	autoCreate := fs.Bool("auto-create-missing-actresses", false, "對未對齊的 video.actresses[] 名字自動建立 auto_<sha1> 女優實體")
	parseFlagsOrExit(fs, args)

	paths := database.ResolveDataDirPaths(*dataDir)
	srcPath := *source
	if srcPath == "" {
		srcPath = paths.DataFile
	}

	if err := os.MkdirAll(filepath.Dir(paths.SQLitePath), 0o750); err != nil {
		fmt.Fprintf(os.Stderr, "建立 SQLite 目錄失敗: %v\n", err)
		os.Exit(1)
	}

	store, err := database.OpenSQLiteStore(paths.SQLitePath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "開啟 SQLite 失敗: %v\n", err)
		os.Exit(1)
	}
	defer store.Close()

	if err := store.InitSchema(); err != nil {
		fmt.Fprintf(os.Stderr, "初始化 SQLite schema 失敗: %v\n", err)
		os.Exit(1)
	}

	report, resyncErr := store.ResyncFromJSON(srcPath, database.MigrationOptions{
		AutoCreateMissingActresses: *autoCreate,
	})
	outputJSON(report)

	if resyncErr != nil {
		if errors.Is(resyncErr, database.ErrMigrationUnresolved) ||
			errors.Is(resyncErr, database.ErrMigrationDuplicate) {
			fmt.Fprintf(os.Stderr, "resync-from-json failed: %v\n", resyncErr)
			os.Exit(1)
		}
		fmt.Fprintf(os.Stderr, "resync-from-json error: %v\n", resyncErr)
		os.Exit(1)
	}
}

// dbExportJSONCmd handles `classifier.exe db export-json`.
//
// Flags:
//
//	-output <path>      Destination file. Required unless -stdout is set.
//	-stdout             Write the JSON DB to stdout instead of -output.
//	-data-dir <dir>     SQLite location (compatibility lookup).
//
// Output is the JSON DB structure (DatabaseData), recomputed from SQLite
// at export time per spec § 4.2: data_hash stays empty, statistics views
// flow into root.statistics, actresses[].video_count comes from
// actress_video_counts.
func dbExportJSONCmd(args []string) {
	fs := flag.NewFlagSet("db export-json", flag.ExitOnError)
	output := fs.String("output", "", "輸出 JSON 路徑（與 -stdout 互斥）")
	toStdout := fs.Bool("stdout", false, "輸出到 stdout（與 -output 互斥）")
	dataDir := fs.String("data-dir", database.DefaultDataDir, "資料庫目錄")
	parseFlagsOrExit(fs, args)

	if *output != "" && *toStdout {
		fmt.Fprintln(os.Stderr, "error: -output 與 -stdout 互斥；請只傳一個")
		os.Exit(2)
	}
	if *output == "" && !*toStdout {
		fmt.Fprintln(os.Stderr, "error: db export-json 必須帶 -output <path> 或 -stdout")
		os.Exit(2)
	}

	paths := database.ResolveDataDirPaths(*dataDir)
	store, err := database.OpenSQLiteStore(paths.SQLitePath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "開啟 SQLite 失敗: %v\n", err)
		os.Exit(1)
	}
	defer store.Close()

	if *toStdout {
		root, err := store.ExportToJSON(database.ExportOptions{})
		if err != nil {
			fmt.Fprintf(os.Stderr, "export-json 錯誤: %v\n", err)
			os.Exit(1)
		}
		outputJSON(root)
		return
	}

	if err := os.MkdirAll(filepath.Dir(*output), 0o750); err != nil {
		fmt.Fprintf(os.Stderr, "建立輸出目錄失敗: %v\n", err)
		os.Exit(1)
	}
	if _, err := store.ExportToJSON(database.ExportOptions{OutputPath: *output}); err != nil {
		fmt.Fprintf(os.Stderr, "export-json 錯誤: %v\n", err)
		os.Exit(1)
	}
	outputJSON(map[string]any{
		"success":     true,
		"output":      *output,
		"sqlite_path": paths.SQLitePath,
	})
}

// dbVerifySyncCmd handles `classifier.exe db verify-sync`.
//
// Flags:
//
//	-source <path>      JSON DB to compare against; defaults to <data-dir>/data.json.
//	-data-dir <dir>     JSON DB directory; controls SQLite location.
//
// Always prints the report JSON to stdout. Exit code: 0 on consistent,
// 1 on inconsistent or I/O failure. The boolean "consistent" key on the
// JSON report is the canonical pass/fail signal for callers; the exit
// code mirrors it for shell scripts.
func dbVerifySyncCmd(args []string) {
	fs := flag.NewFlagSet("db verify-sync", flag.ExitOnError)
	source := fs.String("source", "", "JSON DB 來源檔（預設：<data-dir>/data.json）")
	dataDir := fs.String("data-dir", database.DefaultDataDir, "資料庫目錄")
	parseFlagsOrExit(fs, args)

	paths := database.ResolveDataDirPaths(*dataDir)
	srcPath := *source
	if srcPath == "" {
		srcPath = paths.DataFile
	}

	store, err := database.OpenSQLiteStore(paths.SQLitePath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "開啟 SQLite 失敗: %v\n", err)
		os.Exit(1)
	}
	defer store.Close()

	report, err := store.VerifySync(srcPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "verify-sync 錯誤: %v\n", err)
		os.Exit(1)
	}
	outputJSON(report)
	if !report.Consistent {
		os.Exit(1)
	}
}
