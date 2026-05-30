package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"actress-classifier/pkg/database"
	"actress-classifier/pkg/safefile"
	"actress-classifier/pkg/studio"
)

type dbCommandOptions struct {
	dataDir        string
	jsonOutput     bool
	fullOutput     bool
	actressStats   bool
	studioStats    bool
	write          bool
	backupPath     string
	fromJSON       string
	backupDays     int
	backupMaxCount int
}

type dbCommandContext struct {
	db   *database.SQLiteStore
	opts dbCommandOptions
}

type dbCleanActressesResult struct {
	Success          bool                            `json:"success"`
	DryRun           bool                            `json:"dry_run"`
	BackupPath       string                          `json:"backup_path,omitempty"`
	ScannedVideos    int                             `json:"scanned_videos"`
	ChangedVideos    int                             `json:"changed_videos"`
	RemovedActresses int                             `json:"removed_actresses"`
	Changes          []database.ActressCleanupChange `json:"changes"`
}

type changeEntry struct {
	Code string `json:"code"`
	From string `json:"from"`
	To   string `json:"to"`
}

type dbFixStudiosOptions struct {
	dataDir     string
	studiosFile string
	force       bool
}

type studioFixStatus string

const (
	studioFixUpdate         studioFixStatus = "update"
	studioFixSkip           studioFixStatus = "skip"
	studioFixAlreadyCorrect studioFixStatus = "already-correct"
)

type studioFixPlan struct {
	status studioFixStatus
	change changeEntry
}

type studioFixSummary struct {
	updated        int
	skipped        int
	alreadyCorrect int
	changes        []changeEntry
}

func dbCmd(args []string) {
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe db <get|update|delete|list|stats|compact|merge|fix-studios|actress-get|actress-update|actress-delete|actress-list|backup-create|backup-restore|backup-list|backup-cleanup|migrate-from-json|verify-sync|resync-from-json|export-json> [選項]")
		os.Exit(1)
	}

	subCmd := args[0]
	if routeDBSpecialSubcommand(subCmd, args[1:]) {
		return
	}

	opts, remaining := parseDBCommandOptions(subCmd, args[1:])
	handler, ok := dbHandlers[subCmd]
	if !ok {
		fmt.Fprintf(os.Stderr, "未知的子命令: %s\n", subCmd)
		os.Exit(1)
	}

	handler(dbCommandContext{
		db:   loadDBOrExit(opts.dataDir),
		opts: opts,
	}, remaining)
}

func routeDBSpecialSubcommand(subCmd string, args []string) bool {
	switch subCmd {
	case "fix-studios":
		dbFixStudiosCmd(args)
		return true
	case "merge":
		dbMergeCmd(args)
		return true
	case "migrate-from-json":
		dbMigrateFromJSONCmd(args)
		return true
	case "verify-sync":
		dbVerifySyncCmd(args)
		return true
	case "resync-from-json":
		dbResyncFromJSONCmd(args)
		return true
	case "export-json":
		dbExportJSONCmd(args)
		return true
	default:
		return false
	}
}

func parseDBCommandOptions(subCmd string, args []string) (dbCommandOptions, []string) {
	fs := flag.NewFlagSet("db "+subCmd, flag.ExitOnError)
	dataDir := fs.String("data-dir", "data/json_db", "資料庫目錄")
	jsonOutput := fs.Bool("json", false, "以 JSON 格式輸出")
	fullOutput := fs.Bool("full", false, "輸出完整影片資料（僅 list 子命令）")
	actressStats := fs.Bool("actress", false, "顯示女優統計")
	studioStats := fs.Bool("studio", false, "顯示片商統計")
	write := fs.Bool("write", false, "真正寫入資料庫（預設為 dry-run）")
	backupPath := fs.String("backup-path", "", "備份檔案路徑（用於 backup-restore；可為 .sqlite 或 .json）")
	fromJSON := fs.String("from-json", "", "從 JSON export 還原（與 -backup-path 互斥；走 resync-from-json 流程）")
	backupDays := fs.Int("days", 30, "備份保留天數（用於 backup-cleanup）")
	backupMaxCount := fs.Int("max-count", 50, "最大備份數量（用於 backup-cleanup）")
	parseFlagsOrExit(fs, args)
	return dbCommandOptions{
		dataDir:        *dataDir,
		jsonOutput:     *jsonOutput,
		fullOutput:     *fullOutput,
		actressStats:   *actressStats,
		studioStats:    *studioStats,
		write:          *write,
		backupPath:     *backupPath,
		fromJSON:       *fromJSON,
		backupDays:     *backupDays,
		backupMaxCount: *backupMaxCount,
	}, fs.Args()
}

func loadDBOrExit(dataDir string) *database.SQLiteStore {
	store, err := database.NewStore(database.StoreConfig{DataDir: dataDir})
	if err != nil {
		fmt.Fprintf(os.Stderr, "無法載入資料庫: %v\n", err)
		os.Exit(1)
	}
	return store
}

var dbHandlers = map[string]func(dbCommandContext, []string){
	"get":             runDBGet,
	"update":          runDBUpdate,
	"delete":          runDBDelete,
	"list":            runDBList,
	"stats":           runDBStats,
	"compact":         runDBCompact,
	"actress-get":     runDBActressGet,
	"actress-update":  runDBActressUpdate,
	"actress-delete":  runDBActressDelete,
	"actress-list":    runDBActressList,
	"clean-actresses": runDBCleanActresses,
	"backup-create":   runDBBackupCreate,
	"backup-restore":  runDBBackupRestore,
	"backup-list":     runDBBackupList,
	"backup-cleanup":  runDBBackupCleanup,
}

// notFoundExitCode is the dedicated exit code for "lookup miss" — a legal
// empty result, not a runtime error. Slice B2 (see docs/boundary-cleanup-tasks.md)
// introduces this so callers (Python helper, future GUIs) can tell apart
// "row absent" from "DB unavailable / SQL error" without scraping stderr
// strings. exit 0 = success, exit 1 = runtime/IO error, exit 2 = bad CLI
// input, exit 3 = not-found. Reordering or reusing 3 will break
// _is_not_found_error in src/services/go_cli.py.
const notFoundExitCode = 3

// buildNotFoundPayload assembles the structured stdout envelope a
// not-found lookup emits before exiting. Split out from
// emitNotFoundAndExit so unit tests can verify the JSON shape without
// the test process having to trap an os.Exit.
func buildNotFoundPayload(kind, keyField, key string) map[string]any {
	return map[string]any{
		"success":    false,
		"error_kind": "not_found",
		"kind":       kind,
		keyField:     key,
		"message":    kind + " not found",
	}
}

// emitNotFoundAndExit writes a structured stdout JSON envelope for a
// not-found lookup and exits 3. kind is "video" or "actress"; keyField
// distinguishes "code" (videos) from "id" (actresses); key is the value
// the caller asked for. Both the exit code (primary signal) and the
// stdout payload (auxiliary detail, e.g. for future GUI surfacing) are
// load-bearing — _is_not_found_error in src/services/go_cli.py reads
// the exit code first and the stdout payload second.
func emitNotFoundAndExit(kind, keyField, key string) {
	outputJSON(buildNotFoundPayload(kind, keyField, key))
	os.Exit(notFoundExitCode)
}

func runDBGet(ctx dbCommandContext, remaining []string) {
	if len(remaining) < 1 {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe db get <番號>")
		os.Exit(1)
	}
	code := remaining[0]
	video, err := ctx.db.GetVideo(code)
	if err != nil {
		if errors.Is(err, database.ErrNotFound) {
			emitNotFoundAndExit("video", "code", code)
		}
		fmt.Fprintf(os.Stderr, "取得影片失敗: %v\n", err)
		os.Exit(1)
	}
	outputJSON(video)
}

func runDBUpdate(ctx dbCommandContext, remaining []string) {
	if len(remaining) < 2 {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe db update <番號> <JSON檔案>")
		os.Exit(1)
	}
	code, jsonFile := remaining[0], remaining[1]
	var video database.Video
	readJSONFileOrExit(jsonFile, &video)
	if err := ctx.db.UpdateVideo(code, &video); err != nil {
		fmt.Fprintf(os.Stderr, "更新影片失敗: %v\n", err)
		os.Exit(1)
	}
	if ctx.opts.jsonOutput {
		outputJSON(map[string]any{"success": true, "action": "update", "code": code, "data_dir": ctx.opts.dataDir})
		return
	}
	printSuccess("影片 %s 更新成功", code)
}

func runDBDelete(ctx dbCommandContext, remaining []string) {
	if len(remaining) < 1 {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe db delete <番號>")
		os.Exit(1)
	}
	code := remaining[0]
	// SQLiteStore.DeleteVideo is idempotent. Slice B2: the Python helper
	// relies on exit 3 + structured stdout JSON (or, transitionally, the
	// "not found" stderr string) to return False from db_delete_video,
	// so check existence first and emit the structured not-found envelope
	// when the row is absent.
	if _, err := ctx.db.GetVideo(code); err != nil {
		if errors.Is(err, database.ErrNotFound) {
			emitNotFoundAndExit("video", "code", code)
		}
		fmt.Fprintf(os.Stderr, "刪除影片失敗: %v\n", err)
		os.Exit(1)
	}
	if err := ctx.db.DeleteVideo(code); err != nil {
		if errors.Is(err, database.ErrNotFound) {
			emitNotFoundAndExit("video", "code", code)
		}
		fmt.Fprintf(os.Stderr, "刪除影片失敗: %v\n", err)
		os.Exit(1)
	}
	if ctx.opts.jsonOutput {
		outputJSON(map[string]any{"success": true, "action": "delete", "code": code, "data_dir": ctx.opts.dataDir})
		return
	}
	printSuccess("影片 %s 刪除成功", code)
}

func runDBList(ctx dbCommandContext, _ []string) {
	if ctx.opts.fullOutput {
		videos, err := ctx.db.GetAllVideos()
		if err != nil {
			fmt.Fprintf(os.Stderr, "列出影片失敗: %v\n", err)
			os.Exit(1)
		}
		outputJSON(videos)
		return
	}
	codes, err := ctx.db.ListVideos()
	if err != nil {
		fmt.Fprintf(os.Stderr, "列出影片失敗: %v\n", err)
		os.Exit(1)
	}
	outputJSON(codes)
}

func runDBStats(ctx dbCommandContext, _ []string) {
	if ctx.opts.actressStats {
		stats, err := ctx.db.GetActressStats()
		if err != nil {
			fmt.Fprintf(os.Stderr, "取得女優統計失敗: %v\n", err)
			os.Exit(1)
		}
		outputJSON(stats)
		return
	}
	if ctx.opts.studioStats {
		stats, err := ctx.db.GetStudioStats()
		if err != nil {
			fmt.Fprintf(os.Stderr, "取得片商統計失敗: %v\n", err)
			os.Exit(1)
		}
		outputJSON(stats)
		return
	}
	stats, err := ctx.db.GetStats()
	if err != nil {
		fmt.Fprintf(os.Stderr, "取得統計失敗: %v\n", err)
		os.Exit(1)
	}
	outputJSON(stats)
}

// runDBCompact handles `db compact` and `db compact -json`.
//
// Phase C1 retires JSON-side journal compaction: SQLite is the new
// canonical store and has no journal a CLI caller can flush. Per the
// migration plan (spec § 5 / Slice C1) and the user-facing contract in
// docs/plans/2026-05-23-sqlite-migration-plan.md, this subcommand is
// now a no-op that still returns a well-formed JSON payload Python's
// IncrementalJSONDB.compact() can consume — it only inspects "success".
//
// The reply also carries the legacy "action"/"data_dir" keys for
// backward compatibility, plus the Phase C-specific keys "noop",
// "journal_size", "needs_compact" and "reason".
func runDBCompact(ctx dbCommandContext, _ []string) {
	payload := compactNoopPayload(ctx.opts.dataDir)
	if ctx.opts.jsonOutput {
		outputJSON(payload)
		return
	}
	printSuccess("Compact 為 no-op：SQLite 無 journal 需要合併")
}

// compactNoopPayload is the canonical Phase C compact -json reply.
// Exposed in package main (lower-case) for tests in main_test.go.
func compactNoopPayload(dataDir string) map[string]any {
	return map[string]any{
		"success":       true,
		"noop":          true,
		"journal_size":  0,
		"needs_compact": false,
		"reason":        "sqlite has no journal to compact",
		"action":        "compact",
		"data_dir":      dataDir,
	}
}

func runDBActressGet(ctx dbCommandContext, remaining []string) {
	if len(remaining) < 1 {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe db actress-get <女優ID>")
		os.Exit(1)
	}
	actressID := remaining[0]
	actress, err := ctx.db.GetActress(actressID)
	if err != nil {
		if errors.Is(err, database.ErrNotFound) {
			emitNotFoundAndExit("actress", "id", actressID)
		}
		fmt.Fprintf(os.Stderr, "取得女優失敗: %v\n", err)
		os.Exit(1)
	}
	outputJSON(actress)
}

func runDBActressUpdate(ctx dbCommandContext, remaining []string) {
	if len(remaining) < 2 {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe db actress-update <女優ID> <JSON檔案>")
		os.Exit(1)
	}
	actressID, jsonFile := remaining[0], remaining[1]
	var actress database.ActressData
	readJSONFileOrExit(jsonFile, &actress)
	actress.ID = actressID
	if err := ctx.db.UpsertActress(&actress); err != nil {
		fmt.Fprintf(os.Stderr, "更新女優失敗: %v\n", err)
		os.Exit(1)
	}
	if ctx.opts.jsonOutput {
		outputJSON(map[string]any{"success": true, "action": "actress-update", "id": actressID})
		return
	}
	printSuccess("女優 %s 更新成功", actressID)
}

func runDBActressDelete(ctx dbCommandContext, remaining []string) {
	if len(remaining) < 1 {
		fmt.Fprintln(os.Stderr, "用法: classifier.exe db actress-delete <女優ID>")
		os.Exit(1)
	}
	actressID := remaining[0]
	// SQLiteStore.DeleteActress is idempotent; mirror runDBDelete's
	// existence check so callers (including the Python helper) keep
	// observing the Slice B2 structured not-found signal (exit 3 +
	// stdout error_kind=not_found) when the actress doesn't exist.
	if _, err := ctx.db.GetActress(actressID); err != nil {
		if errors.Is(err, database.ErrNotFound) {
			emitNotFoundAndExit("actress", "id", actressID)
		}
		fmt.Fprintf(os.Stderr, "刪除女優失敗: %v\n", err)
		os.Exit(1)
	}
	if err := ctx.db.DeleteActress(actressID); err != nil {
		if errors.Is(err, database.ErrNotFound) {
			emitNotFoundAndExit("actress", "id", actressID)
		}
		fmt.Fprintf(os.Stderr, "刪除女優失敗: %v\n", err)
		os.Exit(1)
	}
	if ctx.opts.jsonOutput {
		outputJSON(map[string]any{"success": true, "action": "actress-delete", "id": actressID})
		return
	}
	printSuccess("女優 %s 刪除成功", actressID)
}

func runDBActressList(ctx dbCommandContext, _ []string) {
	ids, err := ctx.db.ListActresses()
	if err != nil {
		fmt.Fprintf(os.Stderr, "列出女優失敗: %v\n", err)
		os.Exit(1)
	}
	outputJSON(ids)
}

func runDBCleanActresses(ctx dbCommandContext, _ []string) {
	result, err := cleanActressesAction(ctx.db, ctx.opts.write)
	if err != nil {
		fmt.Fprintf(os.Stderr, "清洗女優資料失敗: %v\n", err)
		os.Exit(1)
	}
	outputJSON(result)
}

func cleanActressesAction(db *database.SQLiteStore, write bool) (*dbCleanActressesResult, error) {
	cleaner := database.NewActressCleaner()
	result := &dbCleanActressesResult{
		Success: true,
		DryRun:  !write,
		Changes: []database.ActressCleanupChange{},
	}

	if write {
		backupPath, err := db.BackupCreate()
		if err != nil {
			return nil, err
		}
		result.BackupPath = backupPath
	}

	// Slice C2: ApplyToDatabase now takes the minimal
	// ActressCleanupTarget interface, so the SQLite-only runtime drops
	// straight in. UpdateVideo on *SQLiteStore writes through to the
	// canonical store; the JSON DB is no longer in the loop here.
	report, err := cleaner.ApplyToDatabase(db, write)
	if err != nil {
		return nil, err
	}

	result.ScannedVideos = report.ScannedVideos
	result.ChangedVideos = report.ChangedVideos
	result.RemovedActresses = report.RemovedActresses
	result.Changes = report.Changes

	return result, nil
}

// runDBBackupCreate handles `db backup-create`.
//
// Phase C1 makes this a dual-snapshot rooted in SQLite: both files are
// derived from the live SQLite mirror (the JSON snapshot is `db
// export-json` semantics, not a copy of data.json). Either side missing
// means the backup is unusable, so we fail the whole subcommand if
// either step errors. Naming keeps the "backup_<ts>" prefix used by
// backup-list / backup-cleanup so existing tooling still discovers the
// JSON snapshot.
//
// The reply carries an extra `path` alias of `json_export_path` so the
// legacy JSONDBManager.create_backup() helper (which only reads `path`)
// keeps working without touching Python.
func runDBBackupCreate(ctx dbCommandContext, _ []string) {
	jsonPath, sqlitePath, err := createDualBackup(ctx)
	if err != nil {
		fmt.Fprintf(os.Stderr, "建立備份失敗: %v\n", err)
		os.Exit(1)
	}
	outputJSON(map[string]any{
		"success":          true,
		"backup_path":      sqlitePath,
		"json_export_path": jsonPath,
		// Legacy alias for JSONDBManager.create_backup() / restore_from_backup
		// which still read `path` and expect a JSON-snapshot file.
		"path": jsonPath,
	})
}

// createDualBackup writes both the SQLite backup file and a JSON export
// of the SQLite store, then returns their paths. Both snapshots share
// the same timestamp and live in <data-dir>/backup/. Splitting the side
// effects out of runDBBackupCreate keeps the testable boundary on a
// function that returns errors instead of calling os.Exit.
//
// The JSON snapshot is produced via sqlite.ExportToJSON — it must
// reflect SQLite state, not a copy of data.json. The dual-write store
// keeps the two in lockstep on the happy path, but during incident
// response (resync-from-json, manual SQL fixes) they can drift, and an
// operator triggering backup-create expects the new canonical SQLite
// data, not stale JSON.
func createDualBackup(ctx dbCommandContext) (jsonPath, sqlitePath string, err error) {
	if ctx.db == nil {
		return "", "", errors.New("sqlite store unavailable; cannot produce dual backup")
	}

	backupDir := filepath.Join(ctx.opts.dataDir, "backup")
	if err := safefile.MkdirAll(backupDir, 0o700); err != nil {
		return "", "", fmt.Errorf("backup mkdir: %w", err)
	}

	timestamp := time.Now().Format("2006-01-02_15-04-05")
	jsonPath = filepath.Join(backupDir, "backup_"+timestamp+".json")
	sqlitePath = filepath.Join(backupDir, "backup_"+timestamp+".sqlite")

	if _, err := ctx.db.Backup(database.BackupOptions{DestPath: sqlitePath}); err != nil {
		return "", "", fmt.Errorf("backup sqlite: %w", err)
	}
	if _, err := ctx.db.ExportToJSON(database.ExportOptions{OutputPath: jsonPath}); err != nil {
		// Roll back the SQLite snapshot so we don't leave a half-finished
		// backup pair on disk that backup-list would later surface.
		_ = os.Remove(sqlitePath)
		return "", "", fmt.Errorf("backup json export: %w", err)
	}
	return jsonPath, sqlitePath, nil
}

// runDBBackupRestore handles `db backup-restore`.
//
// Phase C1 introduces the -from-json flag for restoring SQLite from a
// JSON export (resync-from-json flow). -backup-path remains the canonical
// "restore the SQLite database file" entrypoint and additionally accepts
// a legacy .json path for backward compatibility with the Python helper
// (src/services/go_cli.py:db_backup_restore), which passes JSON files
// via -backup-path.
//
// The two flags are mutually exclusive; missing both is also an error.
// Both validation failures exit with code 2 to distinguish them from
// run-time backup errors (exit 1).
func runDBBackupRestore(ctx dbCommandContext, _ []string) {
	if vErr := validateBackupRestoreInputs(ctx.opts.backupPath, ctx.opts.fromJSON); vErr != nil {
		fmt.Fprintln(os.Stderr, vErr.message)
		os.Exit(vErr.exitCode)
	}

	bp := strings.TrimSpace(ctx.opts.backupPath)
	fj := strings.TrimSpace(ctx.opts.fromJSON)

	if bp != "" {
		runBackupRestoreFromBackupPath(ctx, bp)
		return
	}
	runBackupRestoreFromJSON(ctx, fj)
}

// backupRestoreInputError carries the validation outcome out of the
// pure helper so main_test.go can assert exit code + message without
// the test ever calling os.Exit.
type backupRestoreInputError struct {
	message  string
	exitCode int
}

func validateBackupRestoreInputs(backupPath, fromJSON string) *backupRestoreInputError {
	bp := strings.TrimSpace(backupPath)
	fj := strings.TrimSpace(fromJSON)
	if bp != "" && fj != "" {
		return &backupRestoreInputError{
			message:  "error: -backup-path and -from-json are mutually exclusive; pass exactly one",
			exitCode: 2,
		}
	}
	if bp == "" && fj == "" {
		return &backupRestoreInputError{
			message:  "error: db backup-restore requires either -backup-path <sqlite> or -from-json <json>",
			exitCode: 2,
		}
	}
	return nil
}

func runBackupRestoreFromBackupPath(ctx dbCommandContext, backupPath string) {
	lower := strings.ToLower(backupPath)
	switch {
	case strings.HasSuffix(lower, ".sqlite"):
		runBackupRestoreFromSQLite(ctx, backupPath)
	default:
		// Legacy JSON backup path: keep working so the Python helper
		// doesn't break when callers still hand it backup_*.json files.
		if err := ctx.db.BackupRestore(backupPath); err != nil {
			fmt.Fprintf(os.Stderr, "還原備份失敗: %v\n", err)
			os.Exit(1)
		}
		outputJSON(map[string]any{
			"success":     true,
			"restored":    "json",
			"backup_path": backupPath,
		})
	}
}

func runBackupRestoreFromSQLite(ctx dbCommandContext, backupPath string) {
	paths := database.ResolveDataDirPaths(ctx.opts.dataDir)
	// Release the SQLite handle so Windows can overwrite the target file.
	if err := ctx.db.Close(); err != nil {
		fmt.Fprintf(os.Stderr, "釋放 SQLite 連線失敗: %v\n", err)
		os.Exit(1)
	}
	if err := database.RestoreSQLiteFile(paths.SQLitePath, backupPath); err != nil {
		fmt.Fprintf(os.Stderr, "還原 SQLite 失敗: %v\n", err)
		os.Exit(1)
	}
	outputJSON(map[string]any{
		"success":     true,
		"restored":    "sqlite",
		"backup_path": backupPath,
		"sqlite_path": paths.SQLitePath,
	})
}

func runBackupRestoreFromJSON(ctx dbCommandContext, jsonPath string) {
	if ctx.db == nil {
		fmt.Fprintln(os.Stderr, "還原 JSON 失敗: SQLite 不可用，無法執行 resync")
		os.Exit(1)
	}
	report, err := ctx.db.ResyncFromJSON(jsonPath, database.MigrationOptions{})
	if err != nil {
		fmt.Fprintf(os.Stderr, "還原 JSON 失敗: %v\n", err)
		os.Exit(1)
	}
	outputJSON(map[string]any{
		"success":   true,
		"restored":  "json",
		"from_json": jsonPath,
		"report":    report,
	})
}

func runDBBackupList(ctx dbCommandContext, _ []string) {
	backups, err := ctx.db.BackupList()
	if err != nil {
		fmt.Fprintf(os.Stderr, "列出備份失敗: %v\n", err)
		os.Exit(1)
	}
	if backups == nil {
		backups = []string{}
	}
	outputJSON(map[string]any{"backups": backups, "count": len(backups)})
}

func runDBBackupCleanup(ctx dbCommandContext, _ []string) {
	deletedCount, err := ctx.db.BackupCleanup(ctx.opts.backupDays, ctx.opts.backupMaxCount)
	if err != nil {
		fmt.Fprintf(os.Stderr, "清理備份失敗: %v\n", err)
		os.Exit(1)
	}
	outputJSON(map[string]any{"deleted": deletedCount, "success": true})
}

func readJSONFileOrExit(path string, target any) {
	data, err := safefile.ReadFile(path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "無法讀取 JSON 檔案: %v\n", err)
		os.Exit(1)
	}
	if err := json.Unmarshal(data, target); err != nil {
		fmt.Fprintf(os.Stderr, "JSON 解析錯誤: %v\n", err)
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

	db, err := database.NewStore(database.StoreConfig{DataDir: *dataDir})
	if err != nil {
		fmt.Fprintf(os.Stderr, "無法載入資料庫: %v\n", err)
		os.Exit(1)
	}
	defer db.Close()

	stats, err := db.MergeFromFile(*sourceFile, *overwrite)
	if err != nil {
		fmt.Fprintf(os.Stderr, "合併資料庫失敗: %v\n", err)
		os.Exit(1)
	}
	outputJSON(stats)
}

// dbFixStudiosCmd 批次修正資料庫內的片商欄位
func dbFixStudiosCmd(args []string) {
	opts := parseDBFixStudiosOptions(args)
	si, err := studio.NewStudioIdentifier(opts.studiosFile)
	if err != nil {
		fmt.Fprintf(os.Stderr, "載入片商規則失敗: %v\n", err)
		os.Exit(1)
	}
	db := loadDBOrExit(opts.dataDir)
	defer db.Close()
	videos := getAllVideosOrExit(db)
	summary := applyStudioFixes(db, videos, si, opts.force)
	// SQLite-only runtime: every UpdateVideoFields call inside
	// applyStudioFixes already durably wrote through to SQLite (WAL
	// handles fsync), so there is no separate "save changes" step.

	result := map[string]any{
		"success":         true,
		"total":           len(videos),
		"updated":         summary.updated,
		"skipped":         summary.skipped,
		"already_correct": summary.alreadyCorrect,
		"changes":         summary.changes,
	}
	outputJSON(result)
}

func parseDBFixStudiosOptions(args []string) dbFixStudiosOptions {
	fs := flag.NewFlagSet("db fix-studios", flag.ExitOnError)
	dataDir := fs.String("data-dir", "data/json_db", "資料庫目錄")
	studiosFile := fs.String("studios", "studios.json", "片商規則檔案路徑")
	forceFlag := fs.Bool("force", false, "強制覆蓋已有片商資料（非 UNKNOWN）")
	_ = fs.Bool("json", false, "輸出 JSON 格式（預設即為 JSON，保留相容性）")
	parseFlagsOrExit(fs, args)
	return dbFixStudiosOptions{
		dataDir:     *dataDir,
		studiosFile: *studiosFile,
		force:       *forceFlag,
	}
}

func getAllVideosOrExit(db *database.SQLiteStore) []*database.VideoData {
	videos, err := db.GetAllVideos()
	if err != nil {
		fmt.Fprintf(os.Stderr, "取得影片清單失敗: %v\n", err)
		os.Exit(1)
	}
	return videos
}

func applyStudioFixes(db *database.SQLiteStore, videos []*database.VideoData, si *studio.StudioIdentifier, force bool) studioFixSummary {
	summary := studioFixSummary{
		changes: make([]changeEntry, 0),
	}
	for _, video := range videos {
		plan := buildStudioFixPlan(video, si.IdentifyStudio(video.GetCode()), force)
		if !applyStudioFixPlan(db, plan, &summary) {
			continue
		}
	}
	return summary
}

func buildStudioFixPlan(video *database.VideoData, newStudio string, force bool) studioFixPlan {
	code := video.GetCode()
	if code == "" || newStudio == "" || newStudio == "UNKNOWN" {
		return studioFixPlan{status: studioFixSkip}
	}
	currentStudio := video.Studio
	if (currentStudio != "" && currentStudio != "UNKNOWN" && !force) || currentStudio == newStudio {
		return studioFixPlan{status: studioFixAlreadyCorrect}
	}
	return studioFixPlan{
		status: studioFixUpdate,
		change: changeEntry{Code: code, From: currentStudio, To: newStudio},
	}
}

func applyStudioFixPlan(db *database.SQLiteStore, plan studioFixPlan, summary *studioFixSummary) bool {
	switch plan.status {
	case studioFixSkip:
		summary.skipped++
		return false
	case studioFixAlreadyCorrect:
		summary.alreadyCorrect++
		return false
	}
	if err := db.UpdateVideoFields(plan.change.Code, map[string]any{"studio": plan.change.To}); err != nil {
		fmt.Fprintf(os.Stderr, "更新 %s 失敗: %v\n", plan.change.Code, err)
		summary.skipped++
		return false
	}
	summary.updated++
	summary.changes = append(summary.changes, plan.change)
	return true
}
