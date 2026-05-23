# Implementation Notes — Slice C1 (Backup / Export / Restore)

## Design decisions

### SQLite backup strategy: VACUUM INTO + checkpoint/file-copy fallback

The slice C1 plan listed three options for `sqlite_backup.go`:

1. `sqlite3_backup_*` C API (online incremental backup)
2. `VACUUM INTO` (single SQL statement)
3. WAL checkpoint + file copy

We use `modernc.org/sqlite` (pure-Go, no CGo) wrapped behind
`database/sql`. That driver does **not** expose the `sqlite3_backup_*`
handle through `database/sql`, and reaching for the lower-level driver
internals would mean importing `modernc.org/sqlite/lib` and dealing
with the runtime's connection pool internals, which fights the layering
the rest of the codebase relies on.

We therefore drop option (1) and ship the remaining two as a single
`BackupStrategyAuto` path: VACUUM INTO is tried first (it produces a
fully compacted snapshot in one atomic statement); when that fails we
remove the partial output, run a `PRAGMA wal_checkpoint(FULL)` and
byte-copy `s.path` into the destination. Both strategies are exported
individually (`BackupStrategyVacuumInto` / `BackupStrategyCheckpointCopy`)
so callers (and tests) can pin a branch when they need to.

Fault injection: the primary strategy is reached through a package-level
`vacuumIntoExecutor` function variable. Tests substitute it to simulate
the VACUUM INTO failure path without depending on the modernc driver's
internal error surface.

### `db backup-create` filename scheme

Snapshots keep the existing `backup_<timestamp>.json` prefix so
`db backup-list` / `db backup-cleanup` continue to discover the JSON
side. The SQLite sibling lives next to it with the same stem and a
`.sqlite` extension (`backup_<timestamp>.sqlite`). Plan slice C1
mentions a `db_*.sqlite` / `db_*.json` shape but the surrounding
`backup-list` / `backup-cleanup` code keys off `backup_…`; renaming
the prefix would silently break those subcommands, which are explicitly
out of scope here (no C2/C3 work). Keeping the prefix preserves the
existing helpers untouched while still introducing the dual-snapshot
shape.

### `db backup-restore` extension routing

The new `-from-json` flag is explicit and always invokes the
resync-from-json flow. `-backup-path` now accepts both `.sqlite`
(new SQLite restore via `RestoreSQLiteFile`) and `.json` (legacy
`JSONDatabase.BackupRestore`). The legacy branch is kept because
`src/services/go_cli.py:db_backup_restore` is locked to passing
JSON files through `-backup-path` today and the user task disallows
changing the Python helper. Extension detection happens after the
mutual-exclusion check so misuse still hits the canonical exit-2
message.

### `db compact -json` is now a pure no-op

Per the user task and plan slice C1 the subcommand emits the no-op
payload only — `CompactJournal()` on the JSON side is **not** called.
Python's `IncrementalJSONDB.compact()` consumes `success: true` and
re-loads `base_db` from disk afterwards, so the contract still holds.
Direct internal Go callers that need actual JSON compaction (e.g.
`cleanActressesAction` in `cmd/scanner/db_cmd.go`) continue to call
`db.CompactJournal()` programmatically and are unaffected.

## Deviations

- `runDBBackupRestore` validation failures exit with code 2; the
  previous "missing arg" branch exited 1. Exit 2 mirrors the
  `flag.ExitOnError` convention and gives callers a clean signal to
  distinguish "bad CLI input" from "restore failed".

## Review fixes (post-initial C1 pass)

### `createDualBackup` — JSON snapshot must come from SQLite

The first C1 pass produced the JSON snapshot by calling
`ctx.db.BackupCreate()`, which copies `data.json` from the JSONDatabase
side. That is the wrong artefact: it freezes JSON-side state and does
not reflect the live SQLite mirror that operators consider canonical
after C1. We now derive both files from one timestamp and produce them
through the SQLite store:

- `.sqlite` via `sqlite.Backup(BackupOptions{DestPath: …})`.
- `.json` via `sqlite.ExportToJSON(ExportOptions{OutputPath: …})` — the
  same code path `db export-json` already uses, so the JSON snapshot
  carries SQLite-derived statistics views, refreshed `updated_at`, etc.

If the JSON export step fails after the SQLite snapshot has been
written, the SQLite snapshot is removed so `backup-list` never surfaces
an incomplete pair.

Regression test: `TestCreateDualBackup_JSONExportReflectsSQLiteNotJSONDatabase`
in `cmd/scanner/main_test.go` deliberately drifts the SQLite mirror's
title via `sqlite.UpsertVideo` (bypassing JSON) and asserts the JSON
backup reflects the SQLite value. The earlier `data.json` copy path
would fail this check.

### Legacy `path` alias on the `backup-create` JSON reply

`JSONDBManager.create_backup()` in `src/models/json_database.py` reads
`result["path"]` only. The user task forbids changing Python helpers
to match Go, so the Go reply now carries `path` as an alias of
`json_export_path`. New explicit consumers should still read
`backup_path` / `json_export_path`; `path` exists only to keep the
existing JSON-helper contract intact.

The matching Python contract test (`test_db_backup_create_returns_dual_snapshot_paths`)
now asserts `result["path"] == result["json_export_path"]` instead of
"legacy field is gone".

### `RestoreSQLiteFile` — rollback-safe replacement

The first pass implemented "remove target, then copy backup". A copy
failure mid-restore (Windows file lock, low disk space after probe
succeeded, sync error) would leave the operator with no SQLite file
at all. The new flow:

1. Validate `srcPath` is openable and its `SchemaVersion` is readable
   (unchanged).
2. If the existing target file is present, rename it aside to
   `<target>.pre_restore_<UTC nanosecond timestamp>` using
   `os.Rename`. Stale collisions are cleared first.
3. Copy the backup into `<target>`.
4. On any failure between (2) and (3): remove whatever (possibly
   partial) file landed at `<target>`, then rename the staged old
   target back into place. Surface both the original failure and any
   rollback failure in the error chain so callers can act on either.
5. On success: remove the staged old target plus stale `<target>-wal`
   / `<target>-shm` sidecars so SQLite re-derives them on the next
   open.

A package-level `restoreCopyFile = copyFile` indirection lets the new
test (`TestRestoreSQLiteFile_RollsBackOriginalOnCopyFailure`) inject a
copy failure once the original target has been moved aside, and assert
that the target is restored and openable with its original two videos.
The same test scans the target directory afterwards to confirm no
`.pre_restore_*` artefact is left behind.

### Removed helper / dead test

`sqliteBackupPathFromJSON` and its unit test
(`TestSQLiteBackupPathFromJSON_SwapsExtension`) were dropped — the
new `createDualBackup` derives both paths directly from one timestamp,
so an extension-swap helper is no longer needed.

## Tradeoffs

- We do **not** synchronise the `.sqlite` backup with `backup-cleanup`
  pruning. Cleanup will continue to delete `backup_<ts>.json` siblings
  by date; the matching `.sqlite` files accumulate until C2/C3 work
  revisits the cleanup surface. Marked as a known limitation; the
  filesystem footprint per snapshot is modest because VACUUM INTO
  produces a compacted file.
- The SQLite restore path closes the `DualWriteStore` before swapping
  the file (Windows would otherwise hold the handle open). The JSON
  side is left untouched; after a SQLite-side restore the operator
  is expected to follow up with `db export-json` to re-sync JSON, or
  accept the drift until the next dual-write convergence.
