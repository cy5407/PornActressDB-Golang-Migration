# Implementation Notes — Slice C2 (SQLite-only runtime)

## Design decisions

### Runtime store is now `*SQLiteStore` directly

`NewStore(StoreConfig)` returns `*database.SQLiteStore` (the JSON-side
`*DualWriteStore` wrapper and its tests have been deleted). The runtime
surface lives in a new `pkg/database/sqlite_runtime.go` file that hangs
methods on `*SQLiteStore`:

- Mutations: `AddVideo`, `UpdateVideo`, `UpdateVideoFields`,
  `UpsertActress`, `DeleteActress`, `DeleteVideo` (the last three were
  already there; `DeleteVideo` stays idempotent so the CLI handlers
  pre-check existence to preserve the "False on missing" Python
  contract).
- Reads: `GetActress`, `ListActresses`, `GetVideoCount`,
  `GetActressStats`, `GetStudioStats`, `GetActressPrimaryStudio`
  (read-only equivalents of the JSONDatabase API).
- Aggregates: `GetStats` reports the full Phase A0/A3/B1 key set — see
  "Python CLI contract" below.
- Backup family: `BackupCreate`, `BackupRestore`, `BackupList`,
  `BackupCleanup`.
- Merge: `MergeFromFile`.
- Journal-shaped no-ops: `Save`, `Compact`, `CompactJournal`,
  `CompactIfNeeded` (kept so cmd/scanner / Wails / Python callers don't
  have to branch on backend; SQLite has no JSON-style journal).

`SQLiteStore` gained a `dataDir` field (populated by `NewStore`) so the
backup helpers locate `<data-dir>/backup/`. Stores opened directly via
`OpenSQLiteStore` (tests, one-shot CLI subcommands) fall back to the
SQLite file's parent directory.

### Auto-create unknown actresses on the runtime write path

`AddVideo` / `UpdateVideo` / `UpdateVideoFields` route through a new
`upsertVideoRuntime` helper that auto-creates synthetic actress
entities (`StableActressID` / `auto_<sha1>`) for any
`video.actresses[]` name not already present in `actresses` /
`actress_aliases`. Without this, the strict `UpsertVideo` primitive
would silently drop link rows for unknown actresses — the JSON-side
equivalent had no such loss because actress names lived inline on the
video map.

Duplicate display strings inside the same `actresses[]` collapse to
one link (first occurrence wins) so the UNIQUE constraint never fires
from caller-side dirty data. The strict `migrate-from-json` path still
reports duplicates loudly — those are a data-quality signal users want
to see, not a runtime hot path.

### Bootstrap from JSON on a brand-new SQLite file

`NewStore` runs a one-shot `MigrateFromJSON` against the JSON-
compatible data directory when:

1. The SQLite file did not exist before the open, OR exists but
   `videos` AND `actresses` are both empty.
2. A sibling `data.json` is present at `paths.DataFile`.
3. The caller did NOT pass `SkipBootstrap: true`.

**Bootstrap is the cutover safety gate. Failure is fatal.**

If SQLite is empty and `data.json` is present, the migration MUST
succeed. Any failure — parse error, strict-mode unresolved actresses,
stat failure, anything `MigrateFromJSON` returns — causes `NewStore`
to close the SQLite handle and return the wrapped error. The earlier
draft of this slice logged the failure and returned the empty store;
that was rejected because nothing downstream of `NewStore`
(`video_count` checks, the Wails frontend, `db stats`) can tell a
silently failed bootstrap apart from a clean greenfield install, so a
broken `data.json` would manifest as silent data loss during the
JSON → SQLite cutover.

Recovery is explicit and survives the abort:

- Operator reads the bootstrap error from logs / stderr.
- Either fixes `data.json` by hand, or runs
  `classifier.exe db migrate-from-json
  -auto-create-missing-actresses` to import with auto-creation
  enabled.
- Restart. SQLite is still empty, so bootstrap re-runs against the
  now-valid input.

A populated SQLite store is **never** blocked by a broken `data.json`:
`NewStore` short-circuits before the bootstrap check, so a hand-edited
or stale `data.json` next to a healthy SQLite file just sits there and
does nothing.

Wails backend tests track this: `TestEnsureDB_BootstrapParseErrorClearsInstance`
and `TestDbGetVideo_SurfacesBootstrapFailure` pin the failure surface;
`pkg/database/store_factory_test.go` adds
`TestNewStore_BootstrapFailureReturnsError` and
`TestNewStore_BrokenJSONIgnoredWhenSQLitePopulated`.

### `-data-dir` compatibility lookup is preserved

`ResolveDataDirPaths` is untouched. The default `-data-dir data/json_db`
still maps to the sibling SQLite path `data/db.sqlite`. New regression:
`TestNewStore_DefaultDataDirCompatibilityLookup` chdirs to a tempdir,
creates `data/json_db/`, calls `NewStore({})`, and asserts the SQLite
file lands at `data/db.sqlite` (NOT inside `data/json_db/`).

### Python CLI contract preserved

`db stats` still emits every key the Python helper / Wails frontend
ever read, including the retired ones:

- A0 keys (Python parses these): `video_count`, `actress_count`,
  `link_count`, `schema_version`, `created_at`, `updated_at`,
  `journal_size`, `journal_age_seconds`, `dirty_videos`,
  `dirty_actresses`, `dirty_links`, `needs_compact`, `total_videos`.
- A3 retired counters: `sync_degraded_total`, `sync_degraded_log_size`
  — both `int64(0)`.
- B1 retired counter: `sqlite_read_fallback_total` — `int64(0)`.

The retired counters return zero/false instead of being deleted, so
the Python helper's existing `result["sync_degraded_total"]` /
`result["needs_compact"]` access patterns don't `KeyError`.

`db compact -json` payload (`success`, `noop`, `journal_size`,
`needs_compact`, `reason`, `action`, `data_dir`) is unchanged from C1.

`db backup-create` payload (`success`, `backup_path`,
`json_export_path`, `path`) is unchanged from C1; the legacy `path`
alias still mirrors `json_export_path` for
`JSONDBManager.create_backup()`.

### `BackupList` surfaces only `.json` siblings

JSON-side helpers (`isBackupJSONFileName`, `parseBackupDate`) work on
`backup_*.json` files; the `.sqlite` siblings produced by
`createDualBackup` accumulate alongside them. `BackupList` keeps
returning only the `.json` filenames so Python wrappers see the same
shape. `runDBBackupRestore` routes by extension when the operator
passes a path explicitly.

### `JSONDatabase` is retained as a fixture / import / export helper

`pkg/database/jsondb.go` and its tests are unchanged. It is no longer
the runtime source of truth, but tooling and tests that need to
read/write the on-disk `data.json` directly (e.g. legacy fixtures,
hand-curated test data, `tools/diagnostics/normalize_json_db_schema.py`)
keep their existing entrypoint.

## Deviations

- `DeleteVideo` on `*SQLiteStore` stays idempotent (its existing
  contract). The CLI handlers `runDBDelete` / `runDBActressDelete`
  pre-check existence with `GetVideo` / `GetActress` so the Python
  helper's "False on missing" return value still works end-to-end.
- `Save` / `Compact` / `CompactJournal` / `CompactIfNeeded` are
  no-ops. `saveDBOrExit` / `saveStudioFixChangesIfNeeded` helpers in
  `cmd/scanner/db_cmd.go` were dropped — every write through SQLite
  is already durable (WAL journal handles fsync).
- `loadVideoActresses` now returns `[]string{}` instead of nil when a
  video has no links, so the BatchSearch test that asserts
  `video.Actresses != nil` still passes and JSON consumers see `[]`
  instead of `null`.

## Tradeoffs

- The bootstrap-from-JSON pass is **fail-loud**: a failed migration
  blocks `NewStore` from returning a usable store. The alternative
  (fire-and-forget log + empty SQLite) was rejected because it makes
  silent data loss during the JSON → SQLite cutover invisible to
  anything downstream. Operators recover by fixing `data.json` (or
  running the explicit `db migrate-from-json
  -auto-create-missing-actresses` flow) and restarting. A populated
  SQLite store is never affected — bootstrap is skipped entirely
  once SQLite has any data, so a stale `data.json` next to it is a
  no-op.
- `Actresses []string` on a video is reconstructed from the link
  table on every read. For videos with auto-created actresses, the
  display string round-trips losslessly (we store `display_name =
  ""` because the auto-created actress's canonical `name` equals the
  display). For pre-existing actresses with alias entries, the alias
  spelling is preserved as before.
- `BackupCleanup` only knows about `.json` siblings. The matching
  `.sqlite` files are NOT pruned — this matches the C1 deferral
  noted earlier. A follow-up slice should teach the cleanup helper
  about the `.sqlite` pair.

## Limitations

- The Wails backend still tracks `data.json` mtime in `ensureDB` so a
  hand-edit of the legacy JSON file triggers a reload. The reload
  WON'T re-bootstrap (SQLite already has data) — the JSON file is
  no longer authoritative. The mtime watch stays for now so operators
  who manually replace `data.json` and then need to re-open SQLite
  see a fresh handle; the C3 slice can prune it once we relocate the
  schema / fixture surface.

---

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
