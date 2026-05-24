# Implementation Notes — Slice C3 (docs + Rust db-tool relocation)

## Design decisions

### Schema sharing direction: Go-canonical, Rust includes Go

Plan slice C3 nominally moves the v3 schema to `schemas/sqlite/v3.sql`
at the repo root and embeds it from both Go and Rust. Go cannot do
this — `//go:embed` rejects any pattern containing `..` and refuses to
read files outside the package directory, by design. The literal plan
path would break `go build` immediately.

Adopted alternative (documented in
`wiki/pitfalls/schema-share-go-embed-vs-rust-include.md`):

- Canonical schema stays at `pkg/database/sqlite_schema.sql` (where Go
  already embeds it via `//go:embed sqlite_schema.sql`).
- Rust `tools-rs/src/v3_schema.rs` embeds the **same byte stream** via
  `include_str!("../../pkg/database/sqlite_schema.sql")`. `include_str!`
  resolves paths relative to the calling `.rs` file and Cargo tracks
  external dependencies through rustc's dep-info, so editing the
  schema rebuilds the Rust crate automatically.

This avoids `go:generate` / `build.rs` copy pipelines and keeps the
single-source-of-truth property.

Drift is pinned by three test layers + one CI integration:

1. `pkg/database/sqlite_store_test.go::TestSQLiteSchemaSQL_MatchesCanonicalFile`
2. `tools-rs/src/v3_schema.rs::tests::embedded_schema_matches_canonical_file_on_disk`
3. `tools-rs/tests/integration_db_tool.rs::embedded_v3_schema_matches_canonical_go_package_file`
4. `tools-rs/tests/integration_db_tool.rs::db_verify_*` — applies the
   embedded schema to a fresh SQLite, then runs `db-verify` against
   it; failure here means the schema is structurally broken even
   though the bytes match.

Any single failure means someone forked the schema.

### Rust `db-tool` v2-vs-v3 split

`db-tool` previously only knew about the legacy v2 shadow-DB schema
(`videos` + `video_actresses` + `import_runs` + `videos_with_actresses`
view). C3 keeps that surface untouched and bolts the v3 runtime
commands on alongside it:

| Subcommand | Schema | Status after C3 |
|------------|--------|-----------------|
| `db-init` / `db-stats` / `db-compare-json` / `db-benchmark` / `query …` | v2 shadow | unchanged; historical |
| `db-import-json` | v2 shadow | unchanged + stderr deprecation warning |
| `db-verify` | v3 runtime | **new** |
| `db-migrate` | v3 runtime | **new**; v3 → v3 no-op only |

The two new commands operate on the SQLite file that C2 made
authoritative (`data/db.sqlite`). They do **not** touch the v2 shadow
DB and vice versa.

### `db-verify` checks: integrity + version + structural presence

`tools-rs/src/verify.rs::verify` opens the SQLite with
`SQLITE_OPEN_READ_ONLY`, so verifying a missing path does not create a
new empty database, then checks:

1. `PRAGMA integrity_check` returns `ok`.
2. `PRAGMA user_version` equals `V3_SCHEMA_VERSION` (= 3, mirrored from
   `database.SQLiteSchemaVersion` on the Go side).
3. Every table in `V3_REQUIRED_TABLES` exists in `sqlite_master`.
4. Every view in `V3_REQUIRED_VIEWS` exists in `sqlite_master`.

Output is a single JSON object with `success`, `failure_reason`, plus
the raw values so the caller can decide what to do. Exit code is 0 on
success, 1 on any failure — driven by `verify::run` which checks
`report.success` after printing.

This is **not** a JSON-vs-SQLite consistency check; that is the Go
side `db verify-sync` subcommand's job and is already wired up in
`pkg/database/verify_sync.go`. The two are deliberately split:
`db verify-sync` validates content equality with an exported JSON
snapshot; `db-verify` validates that the SQLite file itself is
internally well-formed.

### `db-migrate` ships only the v3 → v3 no-op

The plan accepts a "v3 → v3 no-op + skeleton for v3 → v4" framing. The
implemented behaviour:

- Same target as current `user_version` → success + `noop: true`.
- `user_version == 0` → failure: "initialise via the Go runtime first".
- Target `> V3_SCHEMA_VERSION` → failure: "beyond the highest known
  schema; update db-tool first".
- Anything else (e.g. existing user_version 1 or 2) → failure: "not
  implemented".

Adding actual migration code is intentionally deferred — there is no
real future-version schema yet, and writing speculative migration code
violates the "minimum that solves the problem" guideline.

### `db-import-json` deprecation without behaviour change

`db-import-json` is the only legacy subcommand external shell scripts
might still call (notably the manual shadow-DB workflows). The C3 task
specifies "保留相容入口但 stderr 顯示 deprecated"; that is exactly what
ships:

- Implementation logic untouched (same v2 schema write path).
- A single `eprintln!` at the top of `db_import_json` explains the
  deprecation and points at `classifier.exe db migrate-from-json`.
- Integration test
  (`db_import_json_emits_deprecation_warning_to_stderr`) asserts the
  warning is on stderr without affecting stdout JSON parseability.

The warning does not affect exit code, output, or downstream tooling.

## Deviations

- **Canonical schema path differs from the plan**: stays at
  `pkg/database/sqlite_schema.sql` rather than moving to
  `schemas/sqlite/v3.sql`. Reason: Go embed constraint, documented in
  the new pitfall page and in this file. No `schemas/` directory was
  created.
- **No `tools-rs/build.rs`**: not needed because `include_str!` causes
  rustc to track the external file automatically; adding a build
  script would only duplicate that behaviour.
- **No Wails maintenance UI** for db-verify / db-migrate — the plan's
  "open item" leaves the timing flexible, and there is no user-facing
  ask for it yet.

## Tradeoffs

- The `v2`-shaped subcommands (`db-init`, `db-stats`,
  `db-compare-json`, `db-benchmark`, `query …`) are kept in the binary
  with no functional change. Deleting them would shrink the binary
  but break any operator scripts that still query the shadow DB for
  diagnostics; deprecating one at a time is safer.
- `db-verify` outputs a single JSON report with structured failure
  fields rather than line-oriented log output. This is more verbose
  for humans but cleaner for any caller that wants to parse the
  result (CI, GUI maintenance UI, etc.).

## Limitations

- `db-migrate` cannot upgrade legacy `user_version` 1 or 2 databases
  to v3. The shadow DB and the runtime DB live in different files
  (`data/shadow.sqlite` vs `data/db.sqlite`), so the upgrade path is
  not "in-place migrate" — it would be "rebuild from JSON via Go's
  `db migrate-from-json`". The error message in `db-migrate` says
  exactly this.
- Schema drift tests on the Go side run the same string-equality
  comparison the Rust tests do. If someone removes the `//go:embed`
  directive and replaces it with a literal string, the on-disk file
  test still catches the drift; but a more sophisticated attack
  (substituting the file at build time only) would slip through.
  Considered acceptable — Cargo's dep-info path tracking covers the
  Rust side, and `go:embed` reads the file at compile time directly.

---

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

# Implementation Notes — Rust runtime v3 JSON import

## Design Decisions

- Added `db-import-json-v3` instead of changing `db-import-json`.
  The existing `db-import-json` command still targets the deprecated v2 shadow schema and is covered by legacy tests. A new command keeps the v2 diagnostic path stable while giving Rust an explicit runtime-v3 import path.

- The Rust importer applies the canonical `pkg/database/sqlite_schema.sql` via `tools-rs/src/v3_schema.rs`.
  This preserves the Go/Rust schema-sharing contract and avoids creating a second schema file under `tools-rs/` or `schemas/`.

- The Rust importer mirrors Go `MigrateFromJSON` semantics.
  It imports `db_meta`, `videos`, `actresses`, `actress_aliases`, and `video_actress_links`; strict mode fails loudly on unresolved actress names; `--auto-create-missing-actresses` uses `auto_<sha1(trim(name))[:16]>`; duplicate actress references inside one video roll back the transaction.

## Tradeoffs

- The v3 Rust command ignores legacy `data.journal`.
  The requested source is `data.json`, and runtime SQLite no longer replays JSON journal files. If an operator needs journal-era data, they must compact/export it before invoking `db-import-json-v3`.

# Implementation Notes — Root `links[]` 100 % round-trip via `legacy_video_actress_links`

## Design Decisions

- 新增 `legacy_video_actress_links` 作為 root `links[]` 的逐筆快照表。
  `pkg/database/sqlite_schema.sql` 加入一張無 FK 約束的表：`ordinal INTEGER PRIMARY KEY`、`video_code/actress_id/role_type/timestamp` 都是 `TEXT NOT NULL DEFAULT ''`。任何 `video_code=""` 或 `actress_id=""` 的 legacy/orphan link 都靠這張表保存；FK-constrained 的 `video_actress_links` 因為外鍵指向 `videos(code)` / `actresses(id)`，無法接受空字串的 orphan，所以必須另開一張表。

- 維持 `PRAGMA user_version = 3`。
  這次改動只新增 table，沒有修改既有欄位或既有表的語意。`SQLiteSchemaVersion` (Go) 與 `V3_SCHEMA_VERSION` (Rust) 都保持 `3`；只更新 `V3_REQUIRED_TABLES` 把新表加入結構驗證清單。屬於 additive backward-compatible schema 異動，不需要走 `db-migrate` 升版流程。為了支援既有 v3 SQLite，`InitSchema` 在 `user_version=3` 時也會重新套用 `CREATE TABLE IF NOT EXISTS` / view DDL，確保 `legacy_video_actress_links` 可被補建；若要讓表內有資料，仍需要 import / resync 一次以從 JSON 填入 root `links[]`。

- `MigrateFromJSON` / `ResyncFromJSON`：override 之後逐筆寫入新表，`ordinal = 原 JSON 陣列 index`。
  既有 `applyLinkOverrides` 仍照舊只更新 FK-constrained `video_actress_links`（spec § 3.1 Pass 3 行為不變）。`saveLegacyRootLinks` 額外用 root `links[]` 的原始順序寫入 `legacy_video_actress_links`，作為 export / verify 的 ground truth。

- `ExportToJSON`：`loadLinksFromSQLite` 改讀 `legacy_video_actress_links ORDER BY ordinal`。
  以 import 時記下的順序還原 root `links[]`，包含 orphan。`videos[].actresses[]` 仍由 `video_actress_links` 還原（行為不變）。

- `VerifySync`：原本 `verifyLinks` 對 `video_actress_links` 的 role_type / timestamp 比對保留；新增 `verifyLegacyLinks` 對新表做 1:1 ordinal 比對。
  原 `verifyLinks` 遇到 `VideoCode == ""` 會 skip 該筆（orphan 改由 `verifyLegacyLinks` 負責），避免誤報「missing_in_sqlite」。新 diff 種類 `legacy_link`，key 形如 `ordinal:<n>`。

- Rust `db-import-json-v3` 同步加入 `save_legacy_root_links` 與 wipe 名單。
  Go 與 Rust 兩條匯入路徑都會把 orphan 寫進新表；schema-drift 測試 (`V3_REQUIRED_TABLES` 含新表) 鎖住兩端一致。

## Tradeoffs

- `legacy_video_actress_links` 是 **import-time 快照**，runtime 的 `AddVideo` / `UpdateVideo` 不會回填。
  也就是說，在 migrate 之後再用 runtime API 新增影片，export 出來的 root `links[]` 不會包含這些 runtime 新增的關聯。`videos[].actresses[]` 仍會包含，因為它由 `video_actress_links` 還原。原本的 round-trip 行為（runtime-add 後 export 出來的 root `links[]` 會反映 runtime 新增）有所改變——但這是達成「JSON `links[]` 100 % 逐字保存」的必要取捨；如果之後 runtime 需要也讓新增進入 root `links[]`，可在 `sqlite_runtime.AddVideo` 順手 append 到新表，留待後續 slice 決定。

- Orphan 在 `verifyLinks` 端的處理是 skip 而非「比對到 NULL」。
  這避免了「missing_in_sqlite」誤報，但代價是 `verifyLinks` 無法察覺 `video_actress_links` 端漏掉一筆原本有 `video_code` 的 link——這層保護改由 `verifyLegacyLinks` 的 ordinal 比對承擔，配合上原本針對 `video_actress_links` 的 role/timestamp 比對，覆蓋率與原本相當。

---

# Implementation Notes — 2026-05-25 Session (runtime JSON cleanup → lint sweep → multi-part fix)

> 一個 session 內把分支從「Python subprocess 仍讀 data.json」收尾到 release-ready：
> 移除 runtime JSON 讀取 → tool-scan 全面清理 → Rust clippy strict → 修 multi-part bug + 文件。

## Design decisions

### Python search subprocess 改走 `_GoCLIDB`，而非 lazy-load `IncrementalJSONDB`

C2 切到 SQLite-only 後，Python `run_search.py` 的 `db=None` fallback 仍會建構 `IncrementalJSONDB(...)` →
`JSONDBManager(...)` → 開啟並全檔讀 `data.json` + `data.index`。每次 Wails GUI 觸發單筆搜尋
subprocess 都會踩一次。

採用「新增 `_GoCLIDB` thin adapter，純委派 `services.go_cli` subprocess」而非「lazy load `IncrementalJSONDB`」：
- lazy load 只能延後問題，第一次 method call 仍會打開 `data.json`。
- thin adapter 永遠不直接打開 JSON 檔，符合 C2 之後「runtime 不讀 JSON」的硬性目標。
- 命名 `_GoCLIDB` 而非 `_FallbackDB`：production runtime（GUI subprocess 跑 `run_search.py main()`）
  根本不傳 `db=`，必走此類別 → Go CLI subprocess。`db=` 參數是測試注入點，反過來叫 fallback 會誤導維護者。

`_GoCLIDB.update_video` 對齊 `IncrementalJSONDB.update_video` 契約：影片不存在時 raise，而非 silent
upsert — 即使 outer `_update_source_search_status` 的 `try/except` 會把 raise 轉成 silent return，
contract 仍要對齊以避免 caller assumption 漂移。

### gosec G401/G505：sha1 在 `StableActressID` 用途為 deterministic ID 非 crypto，採 `#nosec` 而非換 SHA-256

`pkg/database/migrate_from_json.go::StableActressID` 用 sha1 生 `auto_<hex[:16]>` 作為自動建立女優的
deterministic id（spec § 3.3）。**這不是 cryptographic 用途**，collision-resistance 不是需求；改 SHA-256 反而
會改變每個既有 auto-created actress 的 id，打破 referential integrity 與既有 export。

採 `#nosec G401`（行內標註）+ `#nosec G505`（import 標註）+ 中文 inline 註解解釋語意。

### gosec G301：`0o755` → `0o750` 是 surgical 修法而非 `#nosec`

`pkg/database/store_factory.go` / `sqlite_backup.go` / `cmd/scanner/db_sqlite_cmd.go` 共 6 處 `os.MkdirAll(..., 0o755)`。
Windows ACL 不真的看 unix perm bits（NTFS 走 DACL），所以 0o755 → 0o750 在 Windows 行為完全無變。
但 POSIX 環境（WSL / Linux 跑 Go test）會更嚴格 — others 不能 read/execute。
本專案是 user-scope 桌面 app，0o750 合理；改 perm 比加 `#nosec` 抑制更乾淨。

### gosec G304：`filepath.Clean` + `#nosec`，不引入 allowlist 機制

`os.Open(path)` / `os.ReadFile(path)` 的 path 來自 operator CLI flag（`db migrate-from-json -source`、
`db backup-restore -backup-path` 等）。沒有不可信輸入面，但 lint 需要 hint 它已被驗證。
採 `filepath.Clean` 標準化（strip `..` 殘留）+ `#nosec G304` 註解，**不引入 path allowlist 機制** —
那層複雜度對單機桌面工具是 overkill。

### Root `Cargo.toml` workspace 而非改 tool-scan orchestrator

tool-scan `cargo clippy` / `cargo audit` 在 repo root 失敗：`could not find Cargo.toml`。原因是
Rust crate 在 `tools-rs/` 子目錄，root 沒 manifest。

選項：(A) 加 root workspace `Cargo.toml`、(B) 改 `~/.claude/skills/tool-scan/run_tool_scan.py` 支援
子目錄、(C) 跑 tool-scan 加 `--target tools-rs`。

採 A：(B) 動全域 skill，影響其他 repo；(C) 每次手動指定且會漏掉 Python/Go scan。
A 是 multi-language repo 的標準做法，且 root 從此可直接跑 `cargo build` / `cargo test`，IDE Rust analyzer
也能從 root 開。`tools-rs/Cargo.lock` 在 workspace 模式下成為 vestigial（cargo 忽略它），auto mode 拒絕刪
tracked 檔所以暫留，留 follow-up 清理。

### Clippy strict 三項收斂：context struct + type alias

`tools-rs/src/runtime_import.rs`：

- `migrate_actresses` 回傳 `Result<(HashMap, HashMap, HashMap)>` → 引入 `struct ActressMaps { id_by_name, id_by_alias, id_to_name }` + `impl ActressMaps { fn resolve(&self, display) }`，回傳 `Result<ActressMaps>`。
- `migrate_video_actresses` 8 個參數收成 `&mut ActressMaps`（減 3 個 args → 5 個，過 7 個門檻）。
- `auto_create_actress` 同步改吃 `&mut ActressMaps`。

對齊 clippy `type_complexity` 與 `too_many_arguments` 而不用 `#[allow]` — 因為三個 map 在邏輯上就是
「actress resolution state」一個概念，本來就該 bundle，這個 refactor 同時提升可讀性。

`verify.rs::to_ascii_lowercase() != "ok"` → `!eq_ignore_ascii_case("ok")`：one-liner。

### Scan dedupe 移除：multi-part fix 暴露 latent edge case

`wails-app/backend/app.go::ScanDirectory` 原本 `seen[code]` map「同番號只保留第一個 path」。
GUI 實測發現 multi-part 切割檔（`KUSE-042-1.mp4` + `KUSE-042-2.mp4`）只搬到第一個，第二個被 scan 階段就丟掉。

根因：dedupe 的職責應該在 BatchSearch（每 code 只爬一次）而非 scan（列出磁碟上每個影片）。
Scan 階段提早 drop file path 把資料殺在最上游，下游沒救。

修法：移除 `seen` map，每個帶番號的影片檔各自一筆 `ScanResult`。前端 React key 用 `r.path`、
selection 用 `r.code`（multi-part 兩 part 一起選 = 想要的 UX）、BatchSearch 對重複 code 走 DB cache。

**暴露的 latent edge case**：同檔名跨目錄（`A\KUSE-042-1.mp4` + `B\KUSE-042-1.mp4`）會在 BatchMove 撞 dest。
GUI 預設 `skip` 保資料安全，但 `overwrite` 會丟資料。記錄為 wiki pitfall + 4 種未來修法選項，現階段不修
（採「選項 A 接受現狀」）。詳見 `docs/茶包射手/scan-multi-part-and-same-name-cross-dir.md`。

### `config.ini` `[go_integration]` section 有 duplicate option 是本機檔損壞

GUI 實測每筆搜尋都失敗，stderr 訊息 `option 'enable_operation_log' in section 'go_integration' already exists`。
查 `config.ini` line 33-38 是重複 + garbage（`gy = skip` 看起來是 partial-write 殘骸）。

`config.ini` 在 `.gitignore` 內，是本機檔；`config.ini.example` 才是 repo 範本。直接刪重複段保留 line 26-32 乾淨版本。
不修 `configparser strict mode` 行為（strict 抓重複 option 是正確的）；不改 `config.ini.example`（範本本來就 OK）。

不確定哪個寫入路徑造成 duplicate write — Wails preferences UI 寫 config / 手動編輯 / 某次 import 流程都可能。
**Open question** 列入下節。

## Deviations

- **gosec G304 不引入 path validation framework**：採 `filepath.Clean + #nosec`。代價是若未來有不可信輸入面（例如 HTTP API），需要重新審視；目前是純本機 CLI / Wails，無此面向。

- **`tools-rs/Cargo.lock` 沒刪**：workspace 模式下成為 vestigial，但 auto mode classifier 拒絕刪 tracked 檔。功能上 cargo 會忽略它，無 build 問題；視覺乾淨度小傷。留 follow-up。

- **ruff `--unsafe-fixes` 把 `from X import (a as A, b as B, ...)` 拆成多個 single-line `from X import (a as A,)`**：醜但 valid。沒手動 revert — 改回去得逐檔 manual edit，且 ruff 下一次 strict 跑會再拆開。接受。

- **同名跨目錄 edge case 不立即修**：在 wiki + docs 完整記錄 4 種修法（A 接受現狀 / B in-batch dest 偵測 / C `(dir, code)` 複合 key / D 完整修法），現階段選 A 因為 GUI 預設 `skip` 保資料安全，且 user 還沒主動回報踩雷。

## Tradeoffs

- **Scan 不再 dedupe 之後，selection UX 略不直觀**：兩個 multi-part part 共享一個 code，`toggleSelected(r.code)` 會同時選/取消兩個 row。對 multi-part 是想要的行為，對「同名跨目錄」是違反直覺的行為。選 surgical 修法（保留 selection 邏輯），等同名跨目錄 case 有人實際踩雷再考慮重構 selection identity。

- **Test 改 stateful fake 而非真實 SQLite 整合測試**：`tests/test_split_search_entrypoints.py` 新增 5 個 `_GoCLIDB` fallback 路徑測試，用 `_install_stateful_go_cli_fakes` monkeypatch `services.go_cli.db_get_video` / `db_update_video`。比拉真實 `classifier.exe` subprocess 快很多但少一層 contract 驗證；那層由既有 `tests/test_go_cli_contracts.py` 補。

- **Multi commit 拆分**：本 session 切了 5 個 commit（A 組 / lint cleanup / B 組 + Cargo workspace + gosec / clippy strict + gitignore / 多 part fix + 文件）。每個都通過全套測試 + push。代價是 PR review 多看幾次，益處是 `git revert` 顆粒度好。

## Open questions

1. **`config.ini` `[go_integration]` 為何 duplicate write**：本 session 修了損壞檔，但沒查出寫入來源。可能 candidate：Wails `PreferencesDialog` 寫 config、Python 某 helper、過去 commit 的 partial-write bug 殘留。建議未來踩到時抓 `git log -p config.ini.example` + Wails preferences flow。

2. **Wails 是否還有其他 ConfigParser strict 觸發點**：只看到 search subprocess 的 stderr 報錯，但其他 Python helper（`tools/`, `src/services/`）也有 `ConfigParser`，未驗證它們是否會被 duplicate option 弄掛。

3. **同名跨目錄 BatchMove race**：若 BatchMove goroutine pool 並行，兩個 worker 同時 stat 同 dest 不存在 → 兩個都 rename → 後者覆蓋前者。預設 `skip` 也救不了 race。要驗證 BatchMove 是序列還是並行，或加 dest-level mutex。

4. **`tools-rs/Cargo.lock` 清理**：workspace 模式下成為 vestigial，下次有適合的 commit 時 `git rm`。

5. **`ScanResult` selection identity**：multi-part 兩 part 用同 `code` selection 是正解，同名跨目錄是 false positive。長期考慮把 selection key 改成 `path` 並調整 UX（顯示「全選 2 個檔」等）。

## Timeline cross-check

Commit timestamps below are from `git log --date=iso-strict origin/main..HEAD`
and are therefore the source of truth for what actually landed on the branch.
All commits show author `Yuta`; the Claude/Codex owner column is inferred from
the local session transcript, not from git metadata.

| Time (Asia/Taipei) | Commit / event | Owner in session | Evidence / scope |
|--------------------|----------------|------------------|------------------|
| 2026-05-24 20:42:14 | `9e4cb80` `docs: Phase D align agent guidance with SQLite runtime contracts` | Claude Code | Agent guidance aligned with SQLite-only runtime. |
| 2026-05-24 20:58:31 | `ffc4bca` `feat: add Rust runtime v3 JSON import` | Claude Code | Rust `db-import-json-v3` added before main-data smoke. |
| 2026-05-24 22:04 approx. | Main desktop data import, no commit | Codex + Claude worker output | `C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\data\json_db\data.json` imported into `data\db.sqlite` with Rust importer; verified `videos=3485`, `actresses=1087`, `links=3807`, `legacy_root_link_mismatches=0`. This is a local data operation, intentionally not versioned. |
| 2026-05-24 22:08 approx. | `setup.ps1` Wails build, no commit | Codex local verification | Built `classifier.exe`, `actress-classifier.exe`, and `dist\PornActressDB-windows-portable.zip` in the worktree for manual smoke testing. |
| 2026-05-24 22:16-22:17 approx. | Wails manual smoke, no commit | User + Codex verification | Worktree `config.ini` was pointed at the main desktop `data` directory so Wails read `data\db.sqlite`; GUI scanned/searched 9 codes and SQLite contained all 9 while `data.json` contained none. |
| 2026-05-24 23:16:37 | `72af0d5` `feat: route Python search subprocess writes through Go CLI` | Claude Code, reviewed after Codex prompt | Runtime JSON read path removed from `run_search.py`; later wording corrected so Go CLI is documented as the default runtime backend, not fallback. |
| 2026-05-24 23:37:59 | `66e4292` `chore: address tool-scan findings (gitleaks fp, bandit B108, ruff sweep, gofmt)` | Claude Code | tool-scan cleanup. |
| 2026-05-24 23:53:15 | `2d570a0` `feat: root-links round-trip via legacy_video_actress_links + Rust v3 importer` | Claude Code + Codex review/prompt | Root `links[]` preservation and gosec cleanup committed after the local main-data import proved the missing root-link issue. |
| 2026-05-25 00:05:56 | `ac600e8` `chore: make Rust clippy strict clean and ignore local DB artifacts` | Claude Code | Root Cargo workspace strict clippy cleanup + ignored DB artefacts. |

Cross-check conclusion: the commit order matches the session order. The main
desktop data migration and Wails 9-code smoke test happened **between**
`ffc4bca` and `72af0d5`; they are not commits because they touched local data
and build artefacts only. The later commits (`72af0d5`, `66e4292`,
`2d570a0`, `ac600e8`) are code/doc/tooling changes that made the behaviour
reproducible from source.
