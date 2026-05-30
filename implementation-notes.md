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

3. ~~**同名跨目錄 BatchMove race**~~：**已關閉（2026-05-26）**。
   - 原疑慮：若 BatchMove 走 goroutine pool 並行，兩個 worker 同時 stat 同 dest 不存在 → 兩個都 rename → 後者覆蓋前者，預設 `skip` 也救不了 race。
   - 結論：**BatchMove 目前為序列，race 不存在**。`pkg/mover/batch.go:22` 為 `for i, item := range items` 單迴圈，每筆同步呼叫 `m.MoveFile` 並等回傳，無 goroutine pool / errgroup / worker channel。同名跨目錄場景下，第一筆搬完成、dest 已落地後第二筆才進入 `MoveFile`，於 `os.Stat(dst)` 偵測到既有檔，套用 `skip` 留在原處 — 不存在「兩 worker 同時 stat 看不到對方」的 race window。
   - Invariant 鎖定：`pkg/mover/batch_test.go::TestBatchMove_SerialExecutionInvariant` 雙層擋人 — (a) AST static guard 直接 parse `batch.go`，檢查 `batchMoveWithType` body 沒有 `*ast.GoStmt`、且 `range items` 迴圈直接同步呼叫 `m.MoveFile`；(b) runtime observer goroutine 鎖定 source 消失時間單調非遞減 + `Results` 與 input 同順序。任何把 MoveFile 包進 `go func(){...}()` / errgroup / channel worker 的改動會在 PR CI 立刻被擋下。
   - 殘留：skip 後 file B 留在原地不是 race，是「user 不知道第一筆搬到哪」+「按片商分類時 file B 被誤認成獨立女優目錄」— 已切成獨立任務，見 `docs/sqlite-migration-tail-tasks.md` T2（前端 skip reason 串接）與 T3（`handleStudioMove` guard）。

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

## T3 — handleStudioMove guard (2026-05-26)

### Design decisions

- **Block signal = skipped-source-still-in-scanResults**, not the
  `parentDir(r.path) ∉ movedActressDirs` test the original T3 sketch
  proposes. The sketch's set comparison only works when
  `outputDir === inputDir` (input-side parentDir then aligns with
  destination-side actress dir); the chosen signal is precise for the
  actual T3 scenario (`removeMovedFilesFromStore` strips successful
  moves, so any remaining scan row whose path matches a skipped source
  is the residual file that would mislead `handleStudioMove` into
  treating its parent as an actress folder). `movedActressDirs` is
  still computed but only emitted for debug visibility.
- **Guard lives in a pure helper** (`wails-app/frontend/src/lib/studioMoveGuard.ts`)
  so the no-runner frontend can still get automated coverage via
  `npm run test:guard` (esbuild transform + `node:assert/strict`,
  11 cases). The Wails UI integration itself is not covered by an
  automated test; manual GUI repro:
  1. inputDir 建 `A\KUSE-042-1.mp4` 與 `B\KUSE-042-1.mp4`（同 code 同 basename）
  2. GUI 掃描 → 兩筆都進 scanResults
  3. 點「移動」（衝突策略 = skip）→ A 搬到
     `<outputDir>\<actress>\KUSE-042-1.mp4`、B 留在 `B\KUSE-042-1.mp4` 並在
     `lastBatchResult` 標為 skipped
  4. 直接點「片商分類」→ 預期：狀態列出現「偵測到 1 個檔案未進入女優目錄
     （番號：KUSE-042），請先處理略過清單或重新 scan」+ Debug 列出
     `[T3 阻擋] C:\...\B\KUSE-042-1.mp4`，**不**進入 `setStatus('moving')`、
     **不**呼叫 `BatchMoveDirs`
- **Block UX is fail-loud, not silent**: status bar warning + Debug
  event per blocked row; we do not auto-resolve (no silent skip, no
  implicit merge) because T3's whole point is letting the user notice
  the dangling-skip state before they nuke a stray directory.

### Tradeoffs

- The guard relies on `lastBatchResult`. If the user reloaded the app
  between handleMove and handleStudioMove, lastBatchResult is null and
  the guard returns no blocks. That's accepted: by then the residual
  file's parent dir is ambiguous from the frontend's perspective, and
  a fresh scan would normally precede the next move flow.
- `test:guard` is a TS-via-esbuild side-channel, not vitest. We avoided
  introducing a test framework just for one helper; if more frontend
  unit tests appear, this should be replaced with vitest + JSDOM.

## T4 / T5 — config.ini duplicate write 追因與 ConfigParser strict 觸發點審計 (2026-05-26)

> 對應 `docs/sqlite-migration-tail-tasks.md` T4 / T5；open questions 1 / 2 收尾。
> 結論：**未發現可修補的 code-level bug**，duplicate write 來源不在 repo 內任一寫入路徑。

### 搜尋範圍

```text
rg "enable_operation_log"  src/ tools/ wails-app/
rg "go_integration"        src/ tools/ wails-app/
rg "ConfigParser|configparser" .（全 repo，過濾出 src/ tools/ wails-app/）
rg "O_APPEND|\"a\"|\"ab\"|>>.*config\.ini" .
git log --all -S "enable_operation_log" / -S "gy = skip"
```

### 已盤點到的 config.ini 寫入點（生產代碼，非測試）

| # | 檔案 | API | 模式 | 風險 |
|---|------|-----|------|------|
| W1 | `src/models/config.py::ConfigManager.save_config` | `with self.config_file.open("w") + self.config.write(f)` | `O_TRUNC`，full canonical rewrite | 不會產生 duplicate option（`ConfigParser.write` 永遠輸出 canonical form） |
| W2 | `wails-app/backend/services/config.go::ConfigService.Save` | `os.WriteFile(c.cfgPath, []byte(content), 0600)` | `O_TRUNC`，full rewrite | 不會產生 duplicate option（`buildIni` 對每個 key 只寫一次，見 L207-240） |
| W3 | `wails-app/backend/services/config.go::ConfigService.Reset` | 同 W2，內容換成 `DefaultPreferences()` | `O_TRUNC` | 同 W2 |

`os.WriteFile` 與 Python `open("w")` 都是 `O_CREAT|O_WRONLY|O_TRUNC`：先截斷再寫；行程被殺只會留下「比預期短」的 prefix，**不會**留下「舊內容 + 新內容」的 duplicate。`pkg/safefile.WriteFile`（pkg/safefile/safefile.go:69）同樣是 `O_TRUNC`，行為一致。

### 已盤點到的 config.ini 讀取點

| 檔案 | API | 對 duplicate option 的反應 |
|------|-----|----------------------------|
| `src/models/config.py` (L57) | `configparser.ConfigParser().read(...)` | `strict=True`（預設）→ `DuplicateOptionError` 立刻 raise；caller 整個 init 失敗 |
| `wails-app/backend/services/config.go::parseIni` (L118-137) | 手寫掃描 + `setField` switch | 寬鬆解析：duplicate key 直接以「最後一筆」覆蓋；不報錯 |

### 沒有找到的東西（也是結論的一部分）

- **零個** `O_APPEND` 或 `open(..., "a")` 寫入到 `config.ini` 的 codepath（grep 結果為空）。
- **零個** 其他 ConfigParser 使用點：`tools/` 完全沒有 `configparser` import；`src/services/` 也沒有；唯一第二處是 `tests/test_batch_d_services_core.py:2` 屬測試 fixture。
- `git log -S "enable_operation_log"` 與 `git log -S "gy = skip"` 都沒翻出歷史上的 append-style 寫入或 partial-write fixer；config.ini 自己曾被 commit (`d60cfa8 chore: stop tracking local config and obsolete docs` 移除前)，但內容只有 32 行單份 section。
- `setup.ps1` 只 copy `config.ini.example` 不寫 `config.ini`；`Setup-SearchRuntime.ps1` 完全不碰 config.ini；`run.py` / `Start-ActressClassifier.bat` 也都不寫。

### 結論

1. **T4**：當前 repo 任一寫入路徑都不會在單次 save 內產生 `[go_integration]` duplicate option。Wails Save 是 truncating writer + buildIni canonical 序列化；Python `ConfigManager.save_config` 是 truncating writer + `ConfigParser.write` canonical 序列化。**Wails GUI 實際上是 self-healing**：load → parseIni 寬鬆吸收 duplicate（last wins） → struct → buildIni 寫回 canonical。
2. **T5**：production 程式中 `ConfigParser` 唯一使用點是 `ConfigManager`（其建構式 `__init__ → load_config → ConfigParser.read`），這正是 search subprocess 看到 `DuplicateOptionError` 的源頭。**沒有第二個 helper 會被 duplicate option 弄掛**；`tools/` 與 `src/services/` 內無其他 strict trigger。
3. 2026-05-25 觀察到的損壞檔（line 33-38 重複 + `gy = skip` garbage）成因不在 repo 內。最合理的解釋是 repo 外部事件之一：
   - 操作者手動編輯（如把舊版範本貼到既有 config.ini 尾端）；
   - 行程／編輯器於非 `os.WriteFile`-style 寫入過程被殺造成 FS-level 殘留（極罕見，但若曾用過 text editor 的「Save As 之後再 Save」可能踩到）；
   - 過去某個已被刪除的 helper（如 `tools/integration/go_integration.py`，commit `0019901` 已移除，但歷史上也不寫 config.ini）。

### 剩餘風險與建議

- **無 code patch 可下**：所有 in-tree writers 都是 canonical truncating writer。引入 atomic-write（tmp + rename）能擋掉「行程在 `Write` 中被殺造成短 prefix」這種極端情境，但**不能擋 duplicate-option 損壞**（duplicate 不可能來自單次 `O_TRUNC` 寫入）。
- **strict 模式不放寬**（沿用 2026-05-25 決策，本檔 L655）：`configparser strict=True` 抓到重複 option 立刻 fail 是正確行為；放寬會把資料損壞藏成「靜默 last-wins」，搬移／搜尋時更難 debug。
- **若未來再踩到**，建議補一段防禦碼在 `ConfigManager.__init__`：捕 `DuplicateOptionError` → log file path + 建議「先比對 `config.ini.example` 還原 `[go_integration]` 區塊」+ raise（保持 fail-loud）。**這次不下**，因為（a）無 repro、（b）使用者已在 implementation-notes L655 明確說「不修 strict mode 行為」，需先確認方向再寫補丁。
- **無新增測試**：本次調查屬「無 bug 確認」型，沒有 regression hook 可錨定；強行加 test 會變成測 stdlib 行為（`ConfigParser.write` 是 canonical、`os.WriteFile` 是 truncating），無意義。

### 沒跑的測試 / 環境限制

- 本次未跑 `python -m pytest tests`、未跑 `go test`、未跑 Rust tests。原因：未動任何代碼，純文檔追加；同時 worktree 不確定有無 `classifier.exe` 構建，CLAUDE.md 也說明 Go-only 邊界對 Python 測試是契約鎖定（`tests/test_go_cli_contracts.py`）。若未來補 `ConfigManager` 防禦碼，再跑 `python -m pytest tests/test_batch_d_services_core.py -q`（含 ConfigManager validation 測試）即可。

- **Supervisor verify 全量 pytest 失敗 — 與 T4/T5 結論無關**：外層 review 跑 `python -m pytest tests -q -p no:cacheprovider` 得到 exit=2，原因是 **collection failure**：`tests/test_pornactressdb_audit.py` 嘗試 `import docs.pornactressdb_audit`，但 `docs/pornactressdb_audit.py` 不在 repo 內（baseline 早已缺檔，與本次 T4/T5 文檔追加無因果）。這是 pre-existing collection 障礙，不是 T4/T5 引入的回歸，也不是 `classifier.exe` 或 SQLite runtime 問題。**不要把 verify exit=2 解讀為「T4/T5 全 pytest 通過」**。
- **替代驗證命令**（避開缺檔模組，鎖定 T4/T5 相關契約）：
  - `python -m pytest tests/test_batch_d_services_core.py -q -p no:cacheprovider` — 覆蓋 `ConfigManager` validation；T4 / T5 結論若未來補上防禦碼，這是首要 regression hook。
  - `python -m pytest tests/test_go_cli_contracts.py -q -p no:cacheprovider` — Go CLI 契約鎖；T4/T5 不動 contract，跑這支只是回歸保險。
  - `python -m pytest tests --ignore=tests/test_pornactressdb_audit.py -q -p no:cacheprovider` — 跳過缺檔模組後可進入正常 run（仍可能有其他 baseline 失敗，但 collection 不再卡關）。
- 替代驗證實際執行狀態：
  - 全量 `python -m pytest tests -q -p no:cacheprovider` 因 `tests/test_pornactressdb_audit.py` 缺 `docs/pornactressdb_audit.py` 而 collection fail（exit=2），與 T4/T5 無因果。
  - **已實際執行** `python -m pytest tests/test_batch_d_services_core.py -q -p no:cacheprovider`（supervisor revision verify 階段）→ **7 tests 全數通過**，覆蓋 `ConfigManager` validation；本檔接下來若補防禦碼，可直接以此為 regression hook。
  - 其他列出的命令（`tests/test_go_cli_contracts.py`、`tests --ignore=tests/test_pornactressdb_audit.py`）僅為建議的後續驗證入口，本次調查未執行。
- T4/T5 的「無 code-level bug」結論主體仍建立在 **靜態原始碼盤點**（grep 寫入點 / 讀取點 / git log），非 runtime 驗證 — 這是調查範圍本身的限制，請外層 review 留意。

## T7 — 工作區未提交檔案決議 (2026-05-26)

> 對應 `docs/sqlite-migration-tail-tasks.md` T7（不修改該檔，本節為報告型決議）。
> 範圍：盤點 `codex/shadow-db-sqlite` 上 `git status` 的所有 dirty + untracked，
> 分到「本輪 backlog 產物應納入」「應 ignore」「應刪除」「需要 owner 決策」四桶。
> **本次未刪除任何檔案、未 commit、未 push、未 reset、未 checkout、未 clean、未 revert。**

### 盤點來源

```text
$ git status --porcelain
 M .gitignore
 D docs/superpowers/specs/2026-05-23-sqlite-migration-design.md
 M docs/茶包射手/scan-multi-part-and-same-name-cross-dir.md
 M implementation-notes.md
D  tools-rs/Cargo.lock
 M wails-app/frontend/package.json
 M wails-app/frontend/src/App.tsx
?? .agents/skills/claude-api/
?? .agents/skills/mcp-builder/
?? .agents/skills/source-command-ralph-loop/
?? .agents/skills/webapp-testing/
?? docs/agent-loop-demo.md
?? docs/sqlite-migration-tail-tasks.md
?? docs/supervisor-worktree-check.md
?? pkg/mover/batch_test.go
?? wails-app/frontend/scripts/
?? wails-app/frontend/src/lib/skipReason.ts
?? wails-app/frontend/src/lib/studioMoveGuard.ts
```

### Bucket 1：本輪 backlog 產物應納入（T1～T6 收尾的代碼/文件）

| Status | 路徑 | 對應 Task | 角色 |
|--------|------|-----------|------|
| `??` | `pkg/mover/batch_test.go` | T1 | `TestBatchMove_SerialExecutionInvariant`（AST static guard + runtime observer） |
| `M`  | `docs/茶包射手/scan-multi-part-and-same-name-cross-dir.md` | T1 | 「若並行會踩 race」段更新為「目前序列不踩，T1 鎖住」 |
| `M`  | `implementation-notes.md` | T1 / T3 / T4 / T5 | open question 3 收尾 + T3 設計筆記 + T4/T5 調查紀錄（含本節 T7 報告） |
| `??` | `wails-app/frontend/src/lib/skipReason.ts` | T2 | skip reason 後處理（將 skip 行配對到同 dest 的成功筆） |
| `??` | `wails-app/frontend/src/lib/studioMoveGuard.ts` | T3 | `handleStudioMove` 前置 guard 純函式 |
| `??` | `wails-app/frontend/scripts/studio-move-guard.test.mjs` | T3 | 透過 esbuild + `node:assert/strict` 驗證 guard 11 個 case |
| `M`  | `wails-app/frontend/src/App.tsx` | T2 + T3 | 引入 `buildSkipCompanionMap` / `formatSkipReason`（T2）+ `evaluateStudioMoveGuard` 前置 guard（T3） |
| `M`  | `wails-app/frontend/package.json` | T3 | 新增 `test:guard` script |
| `D`(staged) | `tools-rs/Cargo.lock` | T6 | workspace 後 vestigial member lock 移除 |
| `M`  | `.gitignore` | T6 | 加入 `/tools-rs/Cargo.lock` ignore 條目（防 `cargo` 再產生時被誤追蹤） |

**建議**：上列檔案組成 T1～T6 的可提交批次；應該在後續 commit 一併納入（owner 決定要單 PR 還是切多 commit）。本次不擅自 `git add` / `git commit`。

### Bucket 2：應 ignore

- **目前 dirty/untracked 集合內，無「應立刻加進 .gitignore」的新檔**。
  - `/tools-rs/Cargo.lock` 已在 Bucket 1 的 `.gitignore` 變更內處理；除此之外 .gitignore 既有規則對本次盤點足夠。

### Bucket 3：應刪除（受限指令範圍內，本次不執行）

- **本輪 Claude session 沒有產生任何臨時檔**：此 T7 audit 純讀檔 + 一次 `implementation-notes.md` append，不寫 supervisor / agent log、不放 fixture、不留 scratch artifact。
- 既有的 `docs/agent-loop-demo.md`、`docs/supervisor-worktree-check.md` 來自**先前**的 supervisor / agent-loop demo session（見下方 Bucket 4 細節），不在「本次 supervisor demo 明確產生且不屬於 repo 的臨時檔」的授權刪除範圍內 → 不刪、轉 Bucket 4 由 owner 決策。
- **結論：本桶為空，無刪除動作。**

### Bucket 4：需要 owner 決策

#### 4-1. 原 T7 顯式列出的三個

| Status | 路徑 | 性質 | 建議思考的問題 |
|--------|------|------|----------------|
| `D`(unstaged) | `docs/superpowers/specs/2026-05-23-sqlite-migration-design.md` | 原 SQLite 遷移 spec（commit `4ae4138` 引入，647 行），已在工作樹刪除但未 stage | 內容是否確認**全數**已轉錄到 `implementation-notes.md` / `docs/plans/2026-05-23-sqlite-migration-plan.md`？若是 → `git add -u` 該路徑、隨 T1～T6 一起 commit；若否 → 補轉錄再刪 |
| `??` | `docs/agent-loop-demo.md` | 2026-05-26 Codex App outer driver 透過 `ask-supervisor.ps1` 驅動 Claude worker 的閉環 demo 產物（內文自述「本次 demo 不觸碰產品程式碼」） | 此檔意圖是長期文檔還是一次性 demo log？若長期 → commit；若 demo log → `.gitignore` 或刪除（owner 拍板） |
| `??` | `docs/supervisor-worktree-check.md` | 2026-05-26 對本 worktree 做的唯讀盤點報告，內文自述「未修改任何原始碼、設定檔或依賴檔」 | 同上：長期 reference 還是一次性 check report？決定 commit / ignore / 刪除 |

#### 4-2. 原 T7 撰寫後新增、但仍屬 owner 決策範疇

| Status | 路徑 | 性質 | 建議思考的問題 |
|--------|------|------|----------------|
| `??` | `docs/sqlite-migration-tail-tasks.md` | T7 自身來源檔（本次 backlog 任務列） | 此 backlog 是否該進版控？若是 → commit；若視為本機 working doc → `.gitignore`。**不擅自處理**：它正是 T7 的母文件，動到它要 owner 同意 |
| `??` | `.agents/skills/claude-api/` | 新 skill 套件（含 `LICENSE.txt` + `SKILL.md` + 多語言 reference samples） | 既有 `.agents/skills/<skill>/SKILL.md` 多數已 tracked（見 `git ls-files .agents/`）。是否要追蹤此 skill？team 策略決定 |
| `??` | `.agents/skills/mcp-builder/` | 新 skill 套件（含 reference + scripts） | 同上 |
| `??` | `.agents/skills/source-command-ralph-loop/` | 新 skill 套件（單一 SKILL.md） | 同上 |
| `??` | `.agents/skills/webapp-testing/` | 新 skill 套件（含 examples + scripts） | 同上 |

**為何不擅自處理 `.agents/skills/*/` 新增**：其他既有 skills 已 tracked，意味本 repo 確實是 skill 文件的歸屬地之一；但這四個 dir 也可能是 Claude Code 環境/外部插件 sync 自動落地，team 可能不希望版控（如 plugin marketplace 同步產物）。屬於跨「IDE 環境 vs repo」邊界的 owner 決策，不在 T7 spec 範圍內，先列出待裁示。

### 仍剩的 dirty / untracked 對照表（決議套用前 vs 套用後預期）

> 套用 Bucket 1 的 commit 後（owner 真的 commit 之後），剩下的就只有 Bucket 4 的 owner-decision 集合。

| 狀態 | 路徑 | 套用 Bucket 1 後是否仍 dirty/untracked |
|------|------|---------------------------------------|
| `M`  | `.gitignore` | 否（隨 T6 一起 commit） |
| `D`  | `docs/superpowers/specs/2026-05-23-sqlite-migration-design.md` | 是 — owner 決策（Bucket 4-1） |
| `M`  | `docs/茶包射手/scan-multi-part-and-same-name-cross-dir.md` | 否（隨 T1 commit） |
| `M`  | `implementation-notes.md` | 否（隨 backlog batch commit） |
| `D`(staged) | `tools-rs/Cargo.lock` | 否（隨 T6 commit） |
| `M`  | `wails-app/frontend/package.json` | 否（隨 T3 commit） |
| `M`  | `wails-app/frontend/src/App.tsx` | 否（隨 T2+T3 commit） |
| `??` | `.agents/skills/claude-api/` | 是 — owner 決策（Bucket 4-2） |
| `??` | `.agents/skills/mcp-builder/` | 是 — owner 決策（Bucket 4-2） |
| `??` | `.agents/skills/source-command-ralph-loop/` | 是 — owner 決策（Bucket 4-2） |
| `??` | `.agents/skills/webapp-testing/` | 是 — owner 決策（Bucket 4-2） |
| `??` | `docs/agent-loop-demo.md` | 是 — owner 決策（Bucket 4-1） |
| `??` | `docs/sqlite-migration-tail-tasks.md` | 是 — owner 決策（Bucket 4-2，T7 母檔） |
| `??` | `docs/supervisor-worktree-check.md` | 是 — owner 決策（Bucket 4-1） |
| `??` | `pkg/mover/batch_test.go` | 否（隨 T1 commit） |
| `??` | `wails-app/frontend/scripts/` | 否（隨 T3 commit；目前內含 `studio-move-guard.test.mjs`） |
| `??` | `wails-app/frontend/src/lib/skipReason.ts` | 否（隨 T2 commit） |
| `??` | `wails-app/frontend/src/lib/studioMoveGuard.ts` | 否（隨 T3 commit） |

### 與 `docs/sqlite-migration-tail-tasks.md` 列出狀態的差異

T7 spec 撰寫時的盤點（該檔 L196-201）只列了三項：
- `D docs/superpowers/specs/2026-05-23-sqlite-migration-design.md`
- `?? docs/agent-loop-demo.md`
- `?? docs/supervisor-worktree-check.md`

本次盤點時點為 T7 spec 撰寫之後，多出的條目皆為 **T1～T6 進行中產生的代碼/測試/文件**（Bucket 1）以及 **與 T7 spec 同時段或之後落地的外部 skill drop / backlog 母檔**（Bucket 4-2）。原 T7 列舉並未過時，只是新增了未列出的條目，按上述分桶處理即可。

### 未執行也不建議自動執行的動作

- `git add` / `git commit` / `git push` — owner 決定 commit 切分。
- `git rm` / `git restore` — 任何路徑都未 restore / 未 rm。
- 刪除 `docs/agent-loop-demo.md` / `docs/supervisor-worktree-check.md` — 內容看起來是 demo / audit 報告，但**不在「本次 supervisor demo 明確產生且不屬於 repo 的臨時檔」**範圍（它們屬於先前 session 的產物），owner 決定保留或丟棄。
- 對 `.agents/skills/*/` 四個 untracked dir 做任何 `.gitignore` 變更 — 涉及 IDE / plugin sync 邊界政策，不擅自決策。

### 後續 owner 動作建議（非強制，僅 checklist）

1. 確認 Bucket 1 全表 OK → `git add` Bucket 1 條目（含已 staged 的 `D tools-rs/Cargo.lock`）→ 切 commit。
2. 對 Bucket 4-1 的 spec 刪除：確認內容已轉錄 → `git add -u docs/superpowers/specs/2026-05-23-sqlite-migration-design.md` 隨同 batch commit。
3. 對 Bucket 4-1 的兩份 supervisor / agent-loop demo docs：擇一執行 commit / `.gitignore` / 刪除。
4. 對 Bucket 4-2 的 `docs/sqlite-migration-tail-tasks.md`：決定要不要進版控（建議「進」，因 backlog 母檔 cross-reference 已被 `implementation-notes.md` 引用）。
5. 對 Bucket 4-2 的 `.agents/skills/{claude-api,mcp-builder,source-command-ralph-loop,webapp-testing}/`：依 team 對 skill 套件版控的政策決定 commit / `.gitignore`。

## T8 — ScanResult selection identity 重構 deferred rationale (2026-05-26)

> 對應 `docs/sqlite-migration-tail-tasks.md` T8（`scan-multi-part-and-same-name-cross-dir.md` 選項 D 完整修法）。
> 結論：**T1+T2+T3 落地後 T8 不再 release-blocking，延後到實際 user pain 出現再做**。本節不修 `docs/sqlite-migration-tail-tasks.md`，亦不動現有 T8 相關代碼路徑（`pkg/mover/types.go::MoveItemRequest` 無 `ConflictType` 欄位、`wails-app/backend/app.go::CheckConflicts` 無 `seenDest` map、`ConflictResolutionDialog.tsx` 無 in-batch 衝突顯示分支，維持現狀）。

### Release-blocking 風險已被 T1+T2+T3 完整覆蓋

T8 原本要處理的同名跨目錄場景（`A\KUSE-042-1.mp4` + `B\KUSE-042-1.mp4`）拆成三條風險，逐條對應已落地的防線：

| 風險 | 不修 T8 的後果 | 已落地的擋人機制 | 證據 |
|------|----------------|------------------|------|
| 資料遺失（同 dest 被覆蓋） | `overwrite` 策略下後者覆蓋前者；若 BatchMove 並行化甚至 `skip` 也救不了 | 1. GUI 預設 `skip` 已保證序列下不丟資料。2. T1 雙層測試（AST static guard + runtime observer）鎖住 `pkg/mover/batch.go::batchMoveWithType` 嚴格序列，無 worker race window；任何嘗試引入 `go` 語句 / errgroup / channel pool 的改動會在 PR CI 直接被擋 | `pkg/mover/batch_test.go::TestBatchMove_SerialExecutionInvariant` |
| User 不知道第一筆搬到哪 | skip 後 file B 留在原地，user 從 batch result 無法直接看到「同檔已搬至何處」 | T2 `buildSkipCompanionMap`（dest → success result 反查）+ `formatSkipReason`（將 skip 行配對到同 dest 的成功筆）已輸出「同檔已從 `<source>` 搬至此處」到 GUI | `wails-app/frontend/src/lib/skipReason.ts:12-35`；`App.tsx:589` / `App.tsx:785` 兩處 call site |
| 按片商分類誤搬殘留檔 | `handleStudioMove` 用 `parentDir(r.path)` 分組，會把留在 `B\` 的 skip 檔當成女優目錄誤搬整個 `B\` | T3 `evaluateStudioMoveGuard` 在 `setStatus('moving')` 之前以「skipped source 仍出現在 scanResults」為精準訊號 fail-loud 擋下；不靜默處理 | `wails-app/frontend/src/lib/studioMoveGuard.ts:38`；`App.tsx:628`；guard 已有 11-case `studio-move-guard.test.mjs` 覆蓋 |

三條風險全閉合後，T8 的角色從「修 release-blocking bug」變成「proactive UX」— 把 in-batch dest 衝突往前提到 `CheckConflicts → ConflictResolutionDialog` 階段，讓 user 在進入 BatchMove 之前就能挑策略（rename / 取消 / 改 dest），而不是在 batch result 才看到 skip 訊息。差別是「事前選」vs「事後看」，不是資料安全與否。

### 不立即實作 T8 的理由

1. **沒有 user 實際 pain**：原 `scan-multi-part-and-same-name-cross-dir.md` § 「決策軌跡」記錄當下選擇選項 A（接受現狀），條件是「user 還沒主動回報踩雷」。本輪 release 推演中亦未出現 user 投訴，僅是工程內部 risk pre-mortem 列出。在缺乏「user 真的踩到」訊號下實作 T8，違反 user 全域 CLAUDE.md L1 「Simplicity First / No features beyond what was asked」原則。
2. **T2 already covers the post-hoc visibility need**：T2 在 batch result 與 status bar 上顯示「同檔已從 `<source>` 搬至此處」對應的失敗模式（user 想知道發生什麼事）已可滿足；T8 處理的是「user 想在事前就決定怎麼處理」這個更高階的 UX 需求，**屬於增量**而非缺失。
3. **改動面積大且觸及前端對話框**：T8 完整版需要動 `pkg/mover/types.go::MoveItemRequest`（或 `ConflictItem`）加 `ConflictType`、`wails-app/backend/app.go::CheckConflicts` 加 `seenDest` map + `Reason` 文字、前端 `ConflictResolutionDialog.tsx` 加 conflict type 分支顯示與「全選 rename」快速選項、外加回歸測試 4+ 處。對單一未踩雷的 edge case 投這個量是 over-engineering。
4. **不會掩蓋既有 bug**：若未來真的有 user 踩雷，T1/T2/T3 的 fail-loud 訊號（skip reason + studio-move guard block + serial invariant test）會比 T8 沒做更早被看見 — 不存在「不做 T8 會把問題藏起來」的反例。

### 觸發條件（任一成立即重新評估 T8）

- **Trigger A — User pain**：repo issue / wiki pitfall / GUI bug report 出現「同名跨目錄做女優分類時，第二份檔被略過後我不知道該怎麼處理」或「我想在搬之前就看到這兩個檔會撞到」類型的回報 ≥ 1 次。
- **Trigger B — 預設衝突策略改動**：若 `wails-app/backend/services/config.go` 預設 `OnConflict` 從 `skip` 改成 `overwrite` 或 `rename`（後兩者會讓「事後看到」變成「資料已動」），T2 的事後修補就不足，必須改為事前阻擋 → 升 T8 為 release-blocking。
- **Trigger C — BatchMove 並行化提案**：任何 PR 要把 `pkg/mover/batch.go::batchMoveWithType` 改成 goroutine pool / errgroup / channel worker。T1 invariant 會擋下，但若 reviewer 決定放行（例如有性能需求且配對重設計 dest-level lock），race 重現 → 必須在 `CheckConflicts` 階段先把同 dest 攔下，T8 升為 prereq。
- **Trigger D — Bulk import 場景擴張**：若未來 GUI 支援「一次匯入多個來源資料夾」（例如 BatchScan 同時掃 `D:\已分類\` + `E:\待整理\`），同名跨目錄變成主流路徑而非 edge case，需要事前提示 → 升 T8 為功能必需。
- **Trigger E — `handleStudioMove` guard 命中率**：T3 guard 已就位，若 telemetry / 使用者回報顯示「片商分類被 guard 擋下」的事件率非極低值（>2% 月活躍），代表 user 實際上常踩此情境，事前防止比事後阻擋更友善 → 升 T8。

### 未來最小切片（不在本次實作；列入 future work，僅供觸發後對照）

> 觸發條件成立時的最小可動切片，**不**是現在要做的事；亦不對應 `sqlite-migration-tail-tasks.md` T8 段落內任何項目的改寫。

**Phase 1（後端，最小可上線）**：

1. `pkg/mover/types.go::ConflictItem` 加一欄 `Reason string`（不引入 enum，純字串塞「磁碟既有」或「與同批次 `<first source>` 指向同一目的地」），避免動 contract version。
2. `wails-app/backend/app.go::CheckConflicts` 在現有 `os.Stat(item.Destination)` 之前加 `seenDest map[string]string`（absolute dest → first source），命中即追加一筆 `ConflictItem`（帶上 Phase 1 的 Reason）並 `continue`。
3. 加一支單元測試 `wails-app/backend/app_test.go::TestCheckConflicts_InBatchDestCollision`，固定「兩筆 source 指向同 dest 時，第二筆會出現在 conflict list 且 Reason 含 first source path」。

**只做 Phase 1 就能讓 user 看到事前衝突**：既有 `ConflictResolutionDialog.tsx` 已會將 `ConflictItem` 列出來給 user 挑策略，只是不會分類顯示。Phase 1 用 Reason 文字傳達分類，免動 React 元件。

**Phase 2（前端 UX，可選）**：僅在 user pain 證實「事前知道但分類不夠清楚」時才做：

4. `ConflictResolutionDialog.tsx` 把 Reason 拆成兩個區塊顯示（「磁碟已存在」群組 / 「同批次衝突」群組），對後者額外提供「全選 rename」捷徑。
5. 對應的元件測試（若屆時前端已導入 vitest 就用 vitest，否則沿用 `frontend/scripts/` 的 esbuild side-channel 模式）。

**這個切片刻意不做的事**（避免「設計而非實作」漂移）：

- **不**引入 `ConflictType` enum 欄位 — Reason 字串足以區分，加 enum 等於 contract change，要動 wails bindings 與所有 caller。
- **不**動 `MoveItemRequest`，只動 `ConflictItem`（更小的 contract 表面）。
- **不**改 scan 階段任何邏輯 — scan 全保留已是現狀，T8 的職責在 `CheckConflicts`，不該下沉到 `ScanDirectory`。
- **不**動 `ScanResult` selection identity（從 `code` 改 `path`）— `scan-multi-part-and-same-name-cross-dir.md` 提的選項 D 暗示這個改動，但 multi-part 兩 part 用同 `code` selection 是正確 UX，動 selection key 反而會破壞 multi-part 共選。selection 與 in-batch dest 偵測是兩個獨立問題，T8 只解後者。

### 影響檔案盤點（若未來觸發，僅供對照）

| 階段 | 檔案 | 動作 |
|------|------|------|
| Phase 1 | `pkg/mover/types.go` | `ConflictItem` 加 `Reason string` |
| Phase 1 | `wails-app/backend/app.go::CheckConflicts` | 加 `seenDest` map + 兩種 reason 字串 |
| Phase 1 | `wails-app/backend/app_test.go` | 加 `TestCheckConflicts_InBatchDestCollision` |
| Phase 2 | `wails-app/frontend/src/components/ConflictResolutionDialog.tsx` | Reason 分群顯示 + 全選 rename 捷徑 |
| Phase 2 | `wails-app/frontend/scripts/` 或 vitest | 元件測試 |

### 與既有 backlog 的關係

- `docs/sqlite-migration-tail-tasks.md` T8 段（L222-258）保持原狀，**不修改**；本節作為 T1/T2/T3 落地後對 T8 的補充判定，放在 implementation-notes.md 內為單一事實來源。
- `docs/茶包射手/scan-multi-part-and-same-name-cross-dir.md` § 「決策軌跡」目前仍記錄「未來踩雷則走選項 D」，本節將「選項 D」進一步切成 Phase 1+2；待真正觸發 T8 時，可順便回去把該檔的「決策軌跡」表更新為「採 Phase 1 最小切片」。
- 本檔 L692 open question 5（`ScanResult` selection identity 長期改 `path`）**不在 T8 範圍** — 那是 multi-part UX 層的長期討論，與 in-batch dest 衝突無關，繼續以 open question 保留。

## [2026-05-28 02:18] Phase 1 — 機械修復批次（SQL/const/blank import/logging codemod）

**Design decisions**

- 使用既存 `ErrSQLiteStoreClosed` sentinel 作為 4 處 nil-db 檢查回傳值，避免 sqlite_crud.go 與 sqlite_read_store.go 兩邊各自 `errors.New(...)` 失去 `errors.Is` 一致性。
- Codemod 採 libcst 而非 ast-grep — 需要保留原 formatting 並精細處理 `FormattedString` 內的特定 `FormattedStringExpression`，CST 改寫比模式匹配安全。

**Deviations**

- **Schema `= NULL` → `IS NULL` 跳過**：spec 描述 L102/L114 有 `= NULL`，實際是 `WHERE v.studio <> ''`，全檔 0 個 `= NULL`，驗收已成立故無動作。
- **`ErrMsgStoreNotOpen` const 形態與 spec 字面要求往返兩次**：commit `debfb27` 直接複用 sentinel 達 count = 0，被 Stop hook 判定偏離 spec 字面 → commit `0d13814` 新增 `const ErrMsgStoreNotOpen` 並讓 sentinel 包裝它（`pkg/database/sqlite_crud.go:14` 為單一字面值來源）→ commit `799e841` 補 `string` 型別標注。最終 grep count = 1 ✓。
- **`src/scrapers/base_scraper.py:196`** — `{error}` 不在 `{e}/{exc}/{err}` 白名單，且 `error` 是函式參數非 `except as` 綁定，改 `.exception` 會丟 `outside of exception handler` 警告，保留。
- **`src/services/safe_javdb_searcher.py:406`** — `{e}` 在白名單內但 `e` 是 `_handle_unknown_error(self, e: Exception, ...)` 形參，整個 call 不在 except 區塊內，spec 規則 1 「只動 except 區塊內的」排除。
- **遷移數量 48 vs spec 的 "50"**：嚴格符合三條規則的 site 為 **48**，排除上述 2 處函式參數脈絡呼叫即達 50；spec 自身「機械改不掉的列 implementation-notes.md 不要硬改」已涵蓋。

**Tradeoffs**

- I001（imports 順序，2 件 pre-existing）一併修掉而非保留：spec 驗收 `ruff check src/ 0 警告` 強約束要求清零，無法跳過。代價是違反「Surgical Changes」原則但範圍小。
- F841 / F541（codemod 副作用，共 63 件）走 `ruff check --fix` 而非手改：自動修正風險低且 spec 明確要求 `ruff format` 收尾。
- **libcst 不列入 `requirements.txt`**：codemod 是 one-shot dev tool，列入會污染 production deps；改在 `scripts/migrate_log_exception.py` module docstring 標注 `Requires: pip install libcst`。Codex review 提出但 spec「純風格建議列入 implementation-notes.md 不修」適用。
- **不為 codemod 新增 committed test file**：Phase 1 spec 未要求；inline 驗證已覆蓋 top-level / nested def / lambda / class method 四種 case 並確認 idempotent。新增 pytest 檔會擴大 Phase 1 scope。

## [2026-05-28 02:58] Phase 2 — pkg/database CC reduction（9 函式）

**Design decisions**

- 不嘗試 generic loader（`loadAll[T]` 之類）；verify_sync.go 三個查詢分別實作 `loadSQLiteActressRows` / `loadActressAliasesByID` / `loadSQLiteVideoActressLinks`，每個 Scan 簽名都不同，generic 收益低。
- `migrateContext` 用於 migrate_from_json.go 三個函式間共享 `tx/opts/report` + 三個 lookup map；同檔內未擴散至 `autoCreateActress`（仍取 7 個原始參數）以避免變動範圍超出 spec。
- `verifyLinkRow` / `verifyActressRow` 升到 file scope 而非保留 inline 匿名 type；helper 簽名才能在檔尾統一表達，且兩個型別都是 verify 流程內部用，未外洩。

**Deviations**

- L338 `migrateVideoActresses` 收 params 到 3 個（spec 上限是 7），比要求更激進；附帶 `migrateVideosAndLinks` 也改吃 ctx（原 7 params→2），確保 call chain 命名與型別一致。
- sqlite_backup.go 抽出 **4** 個 helper（spec 允許 2–3 個）：`validateRestoreInputs` / `probeBackupSource` / `stageExistingTarget` / `rollbackAfterCopyFailure`。第 4 個 `rollbackAfterCopyFailure` 把回滾分支拉出來，否則 RestoreSQLiteFile 內部 nested-if depth 仍偏高。Codex 接受。

**Tradeoffs**

- `verify_sync.go` 的 missing-in-json 迴圈改成 early-`continue`，原寫法是 `if !ok { if ... { continue }; append }`。觀察上等價，diff 行數略增換可讀性。
- `rebuildLinksForVideoAutoCreate` 只抽 1 個 helper（`resolveOrSynthLinkActress`），保留主迴圈 + `seen` 去重邏輯在原處；dup 判斷與 INSERT 流程合在一起讀比較直觀。
- 不動 `mergeFromRoot`（L611，CC 56）— spec 明示「L596 不在本 phase 範圍」（檔案重新編號後實際在 L611）。
- gocognit 額外標示 `TestRestoreSQLiteFile_RollsBackOriginalOnCopyFailure`（CC 19，test）— 不是生產 code，不動。

**Open questions**

- `migrateContext` 是否應推廣到 export / verify 流程也用？目前只在 migrate 路徑出現；如果未來 import / export 共享更多狀態可考慮。

## [2026-05-29 00:16] Phase 1.1 — logger.exception 補漏

**Deviations**

- 手改 2 處而非擴 `scripts/migrate_log_exception.py` 白名單：codemod 凍結為 Phase 1 spec、白名單 `{e}/{exc}/{err}` 是明文約束；只 2 site 手改 5 分鐘，擴白名單再跑要額外評估有沒有意外吸到 `{ex}`、`{exception}` 等非預期 case 的 side effect。
- `src/scrapers/cache_manager.py:141` 改完 `as fallback_error` 變 unused，我直接同步移除（沒呼叫 `ruff --fix`）— ruff 走完也是同結果，省一輪。
- `src/models/json_database.py:292` 的 `as pe` 保留 — `pe` 在 L288 (logger.warning) 與 L293 (`raise DataIntegrityError(...) from pe`) 還在用，動了會炸。

**Tradeoffs**

- `logger.exception("...")` 訊息字串移除 `: {pe}` / `: {fallback_error}` 結尾；traceback 由 `.exception` 自動附上、不需再 inline exception repr。對比保留 `{pe}` 但只改 method 名的方案，這版較貼近 Python logging idiom。
- 不處理 SonarQube 的 schema NULL false positive（L102/L114 是 `<> ''`，不是 NULL 比較）與 5 個 dynamic SQL hotspot（hardcoded table list / int 常數 / escaped path，逐個都安全）— 留給 SonarQube UI 端 mark Won't Fix / Safe。

## [2026-05-29 14:40] Phase — pkg/mover file_move/dir_move coverage

**Deviations**
- 任務描述的基線（file_move 67.2% / dir_move 74.5%）已過時：前一個「pkg 覆蓋率 → 90%」session 已把兩檔拉到 88.5% / 88.1%（透過 `pkg/mover/error_paths_test.go` 與 `renameFile` seam）。本 phase 起步即已 ≥85%，本次再補可達邊界的 branch 拉到 91.0% / 91.1%。
- 只在 `file_move_test.go` / `dir_move_test.go` 加 test，未動 production code（遵守紀律）。

**Tradeoffs / mock 邊界決定**
- `copyFile`（file_move.go）剩餘未覆蓋分支為 `dstFile.Sync()` 失敗、`dstFile.Close()` 失敗、`applyFileMode` 在 close 後失敗 —— 這些要 OS 層級故障注入或在 production 加 seam（如 prior session 的 `renameFile`）。本 phase 紀律禁止改 production，故不補；以「directory source 觸發 io.Copy 失敗」覆蓋了主要錯誤分支（56.5%→69.6%）。
- `walkMoveDirEntries` / `tryFastMoveDirRename` 的 `filepath.Walk` 中途失敗、`os.Rename` cross-device 失敗、`finalizeMoveDir` 的 `os.RemoveAll` 失敗分支同屬故障注入類，Windows 單一 volume 測不到，未補。
- `isSameFilePath` 的非-Windows 比較行（line 80）在 Windows build 下不可達（平台分支），未補。
- 以上皆未超過 3 個 mock dependency；無新增 mock，全部用真實檔案系統 + 直接呼叫 package-private helper（in-package test）。

**Open questions**
- 工作樹中有非本任務白名單的既存未提交檔案：`pkg/database/final9_coverage_test.go`（前一個 DB-coverage task 遺漏 commit，導致已 push 的 78b9a5e 實際少這檔、aggregate 略低於我當時回報的 90.1%）、`docs/task-prompt-*.md`（modified）、`docs/20260526-...Task copy.md`（untracked）。這些不在本 phase 白名單，未一併提交，待 user 指示如何處理。

## [2026-05-29 15:05] Phase — final9_coverage_test.go fixup

**驗證 78b9a5e 不含此檔**
- `git show 78b9a5e --stat -- pkg/database/final9_coverage_test.go` 輸出為空 → 該 commit 確實未含此檔；先前為 untracked。

**本地 vs CI / 前提修正（自承）**
- 先前回報的「90.1% 已達成/已 push」是 **aggregate `./pkg/...`**、且基於本地含此「未 commit」檔的狀態，**不是 pkg/database 單檔**。
- 實測：pkg/database 單檔 **89.2%**（含 final9）/ **89.0%**（不含）；aggregate **90.3%**（含）/ **90.2%**（不含）。
- 結論修正：final9 貢獻僅 **+0.2pp（db）/ +0.1pp（aggregate）**；**不含 final9 時 aggregate 仍 ≥90%（90.2%）**。原任務前提「78b9a5e 因漏 final9 使 CI 掉到 ~89.9%」**不成立**——CI gate 的 aggregate metric 本來就 ≥90%。
- 補 commit 的真正理由是版控衛生（讓本地 == 已 push 狀態），非「救回 90% 門檻」。

**為何 fixup 而非 amend**
- 78b9a5e 已 push 至 origin/main；amend 已 push commit 會改寫歷史、破壞他人 clone（pitfall）。故用獨立 follow-up commit（981ed9c），message 標 `fixup-of: 78b9a5e`。

**DoD 偏離（停下回報的點）**
- DoD「`go test ./pkg/database/` total ≥90.0%」**寫不出來**：pkg/database 單檔上限 89.2%。CI 實際 gate 的是 aggregate `./pkg/...`（見 `.github/workflows/sonar.yml` 與 `integration-test.yml` 皆跑 `go test ./pkg/...`），該 aggregate = 90.3%，≥90% 達標。per-package 90% 非 CI 指標、且需另補 ~14 個 db statement 測試（超出「只補 commit」範圍、紀律禁止改/加 production 行為）。

**CI 實測 coverage / CI 狀態（重大發現）**
- CI（Integration Test run 26623361328）**RED**：`go test ./pkg/... -race` 在 Linux 上有 5 個測試 FAIL，分屬 pkg/pathutil、pkg/mover、pkg/database 三個套件。
- 失敗測試（全為我先前 coverage-push session 產出，皆依賴 `filepath.Abs("bad ...")` 回傳 error）：
  - TestIsSameOrNestedPath_BadBaseReturnsError（pathutil）
  - TestIsSameOrNestedPath_BadTargetReturnsError（pathutil）
  - TestPathsReferToSameDir_BadInputReturnsError（mover）
  - TestValidateMoveDirDestination_BadInputsErrorsViaIsSameOrNested（mover）
  - TestResolveMergeSourcePath_BadPathErrors（database/final11）
- 根因：null byte 在 **Windows** 會讓 `filepath.Abs` 報錯，但在 **Linux 不會**（只在 syscall 階段才錯）。我先前「全綠」是 Windows-only，從未跑 Linux CI 驗證 → 這些 assert-error 測試在 Linux 全 fail。
- CI 各套件 coverage（Linux，含失敗）：app 95.2% / cache 90.7% / database 89.3% / extractor 100% / safefile 90.1% / studio 91.4%（mover/pathutil 因 FAIL 未正常計）。
- 結論：(a) final9 已 commit+push（981ed9c），版控衛生達成；(b) 但「CI coverage ≥90%」**無法確認**——CI 是 RED，非僅略低於 90；(c) 修這 5 個平台脆弱測試需動 pathutil/mover/database 共 3 個 test 檔，**超出本任務白名單**（只允許 final9 + 本檔），故停下回報，不擅自修。

## [2026-05-29 15:25] Phase — final9 fixup + CI verify

**前提驗證（先驗再動）**
- (a) `git ls-files pkg/database/final9_coverage_test.go` → **已 tracked**（上一輪 commit 981ed9c）。
- (b) 本機 `go test ./pkg/... -coverprofile` aggregate = **90.3%** ≥90%（注意：是 `./pkg/...` 聚合，非 `./pkg/database/` 單檔 89.2%）。
- (c) CI quality gate = **RED**（push 981ed9c 的 run）：SonarCloud Scan / Go Lint & Test / Integration Test 三者 failure；SQLite Verify-Sync + Python Test success。
- 結論：前 2 前提成立，但第 3（gate PASS）不成立 → 進入異常處理分支（驗 root cause、不硬套 DoD）。

**CI red root cause（權威來源：gh run logs）— 非 final9**
- final9 自身 4 個測試在 CI 全 **PASS**（TestSQLiteBackupCopyFile_DirectorySourceIoCopyError、TestMigrateFromJSON_ClosedStoreGuard/MissingSourceFile/CorruptSourceJSON）。
- 紅燈來自 5 個既存跨平台脆弱測試（assert `filepath.Abs("bad\x00...")` 回傳 error；此行為僅 Windows 成立，Linux 不報錯 → CI fail）：
  | 測試 | 檔案（皆在本任務白名單外） |
  |---|---|
  | TestIsSameOrNestedPath_BadBaseReturnsError | pkg/pathutil/nested_path_test.go |
  | TestIsSameOrNestedPath_BadTargetReturnsError | pkg/pathutil/nested_path_test.go |
  | TestPathsReferToSameDir_BadInputReturnsError | pkg/mover/error_paths_test.go |
  | TestValidateMoveDirDestination_BadInputsErrorsViaIsSameOrNested | pkg/mover/error_paths_test.go |
  | TestResolveMergeSourcePath_BadPathErrors | pkg/database/final11_coverage_test.go |
- SonarCloud failure 同因：其 `go test ./pkg/...` 步驟因上述 fail 而 exit≠0，scan 無法完成。

**本機 vs CI 數字差異**
- 本機（Windows）這 5 個測試 PASS、aggregate 90.3%；CI（Linux）這 5 個 fail，且 mover/pathutil 套件因 fail 未正常計 coverage。先前「90.1% 全綠」是 Windows-only 量測，未驗 Linux CI。

**獨立 follow-up（不在本任務修；需另開 /goal）**
- 修 5 個 null-byte 跨平台測試：改用 `runtime.GOOS=="windows"` 條件、或可攜的不可達路徑技巧（非 t.Skip 規避），讓 pathutil/mover/database 在 Linux CI 轉綠。涉及 3 個測試檔，超出本任務白名單。

**本任務結論**
- 交付物「final9 進版控」**已達成**（tracked + CI 自身測試綠）。aggregate ≥90% 本機成立。CI gate red 之 root cause 與 final9 無關，依紀律不擴範圍修，記為獨立議題。

## [2026-05-30 13:48 → 15:40, 1h 52m] 契約/死碼審查 remediation（執行 docs/contract-deadcode-audit-2026-05-30-tasks.md）

來源：`docs/contract-deadcode-audit-2026-05-30.md`（55 confirmed findings）→ `…-tasks.md`（T1–T15）。依相依順序分波執行，每波過驗證閘。

**Design decisions**
- **執行策略不用 worktree 並行編輯**：刪除類改動需落在主工作樹才能 commit；worktree 隔離的 agent 改動不會自動回併，且多任務跨 package 但共用測試基礎建設，平行非隔離編輯會 race。故 **edits 由我序列套用**，workflow 僅用於 (a) 唯讀並行調查產出精確編輯計畫、(b) 最終並行驗證。此即「適當使用 workflow」。
- **T2（D4-1 search method）改為最小爆炸半徑**：`search_method` 鍵被 Python 入口 smoke/split 測試與 DB 欄位鎖定，前端 `SearchResultDialog.tsx` 又讀 `result.method`。故不改 Python 輸出鍵、不改前端；改為 Go `SearchResult` 加 `UnmarshalJSON` 同時接受 `search_method`∥`method`（marshal 仍出 `method`），並修 Python 值來源加 `raw.get("source")`（web_searcher 以 `source` 存方法名）。報告原建議「改 Go tag + 改 web_searcher」會連帶改前端 binding，捨棄。
- **T1 回傳 shape 統一**：fallback/except 對齊 `contracts.MergeResult`（`source_dir/dest_dir/files_moved/files_skipped/files_total/errors/deleted_src`），保留 `success`+`error`（既有測試只驗這兩鍵，未驗舊 `source/destination/skipped`，安全）。

**Tradeoffs**
- T2 用 custom `UnmarshalJSON` 而非改 tag：多 ~12 行 Go，但零前端/binding 風險、既有測試全綠。

**Wave 1 完成（T1/T2/T4）**
- T1 `move_dir` `-dir`→`-kind dir` + shape 統一 + 契約 argv lock（`src/services/go_cli.py`、`tests/test_go_cli_contracts.py`）。
- T2 Go `UnmarshalJSON` + Python `source` fallback（`wails-app/backend/app.go`、`run_search.py`、`run_batch_search.py`、新 `search_result_test.go`）。
- T4 `contracts.MergeResult` 補 `FilesSkipped` + 轉換拷貝（`pkg/contracts/move.go`、`pkg/app/move_service.go`）。
- 驗證：root `pkg/app`+`cmd/scanner` 綠、wails backend 綠、Python 156 passed/2 skipped。

**Open questions（pre-decide，end-of-turn 再回報）**
- T3 DTO 收斂採「保留 contracts + 加對齊守門」最小版，不做移除轉換層的大重構（風險/範圍過大）。
- T5 cache prune：採「移除死鏈」需動 Python+Go 多處且涉 live Get/Set 邊界，將以保守方式處理（優先修 D4-2 鍵名，死鏈移除謹慎評估）。

**Wave 2 完成（T9/T10/T13/T14/T15/T3/T5，並行 workflow 5 agent 執行互斥檔案集）**
- 用唯讀 workflow（6 planner）先產精確編輯計畫（含測試檔「純死碼可刪 vs 混測 live 須拆」分類），再用實作 workflow（5 agent 並行編輯互斥檔案集、各自 self-verify、紅了 revert）。
- T10 pkg/cache：刪 New/CleanupExpired/CleanupBySize/Exists/DefaultPruneConfig + 對應測試；live AutoCleanup/Get/Set/Delete/Stats/Clear 與共用 helper 保留。
- T9 wails：刪 DbListVideos/DbUpdateVideo（連帶解 D5-6）、ConfigService.CfgPath、ini 三層 shim（app.go defaultPreferences/buildIni/parseIni + services exported ParseIni/BuildIni）；app_test.go 改走 ConfigService.Save/Load round-trip。wailsjs bindings 仍含死 JS（需 regenerate，無害）。
- T13/T14：scripts/db-sync.* + tools-rs v2 shadow 加退役註解；main.rs about 標 db-import-json deprecated；wiki overview.md 校正 pkg/contracts 為 DTO；重產 wiki-data.js。
- T11(low)/T12：刪 UnifiedFileScanner(scanner.py 整檔)、WebSearcher 4 孤兒方法 + 私有 helper、tools/studio_updates/ 四腳本；拆分 test_code_review_regressions/test_coverage_web_searcher（只刪對應 test）。**保留** shiroutowiki_scraper 屬性/import（觸 __init__ side-effect 風險，標 skipped）。
- T15/T3/T5：test_go_cli_contracts.py 補 11 條 argv 鎖；pkg/app 加 TestMergeResultToContract_CopiesEveryField；cache_manager.py 修 prune 鍵名（deleted_count→deleted_files 等、移除 current_size_mb）+ 連帶修 normalizer 測試。
- **連帶**：刪孤兒測試 tests/test_pornactressdb_audit.py（其目標 docs/pornactressdb_audit.py 已被使用者 housekeeping commit 6fe8157 刪除，擋住 pytest 收集）。
- 全樹驗證：Root Go `build+vet+test ./...` 全綠、Wails 綠、Rust 58 passed（含 schema-drift 鎖）、Python 1058 passed/2 skipped、CI 釋出閘（migrate-from-json+verify-sync）exit 0。

**Wave 3 + 關鍵決策：T7/T8 JSONDatabase 移除 → 撤回，改 CLAUDE.md-compliant 子集**

**Deviations（重要，違反 task.md T8 原意，但遵 CLAUDE.md）**
- task.md T8 要求刪除 `JSONDatabase` 型別。實作中已先搬 9 個 live helper 到 db_helpers.go、刪 jsondb.go/journal.go、`go build ./...` 通過（live 碼全相容）。但處理測試時發現：共享 fixture helper `setupTestDB`/`loadedJSONDB`/`seededJSONDB`（建構 JSONDatabase）被**包含保留測試在內**的眾多測試依賴（如 actress_cleaner_test.go），乾淨移除需重寫大量測試 fixture（高風險大重構）。
- **更決定性：CLAUDE.md 明文「`pkg/database/jsondb.go` — 保留為匯入/匯出/測試 fixture 助手」，且 CLAUDE.md 指令 OVERRIDE。** 審查報告 §D 本身也寫「刪 JSONDatabase 是清理非修 bug，建議刪前先與你確認」。
- **故撤回 JSONDatabase 刪除**（還原 jsondb.go/journal.go/6 測試檔、刪 db_helpers.go），只保留 T8 中真正無人呼叫、不衝突的 **`SQLiteStore.Save()`/`CompactJournal()` no-op 移除**（D6-3/D6-4，零生產+零其他呼叫者；JSONDatabase 自己的同名方法不受影響）+ 修 sqlite_runtime_test.go 兩段斷言。
- 驗證：root build/test 綠、wails 綠、deadcode 確認 SQLiteStore.Save/CompactJournal 消失。

**Open questions / 已 defer（需使用者確認，不在本輪自動執行）**
- **T7/T8 完整刪 JSONDatabase 型別**：被 CLAUDE.md 保留指令擋下 + 需重寫測試 fixture（setupTestDB/loadedJSONDB/seededJSONDB 連鎖）。若要執行，須先決定「JSONDatabase 改不改為測試專用 build tag / 或測試改走 SQLiteStore 種子」，屬獨立大 slice。
- **T11 完整刪 JSONBDManager/IncrementalJSONDB（Python）**：同性質——src/ 生產零呼叫，但 conftest.py 的 db_manager/seeded_db_manager fixture + ~92 個測試依賴；plan 標高風險，task.md 亦註「建議與使用者確認」。本輪只做 T11 低風險子集（UnifiedFileScanner/WebSearcher 孤兒/tools）。

**最終定案（2026-05-30 15:40）**
- 使用者決定：Python `JSONBDManager`/`IncrementalJSONDB` **保留為測試 fixture，不刪**（與 Go jsondb.go 同處置）。
- T6 緩解已做（`fd03b52`）：兩類別 docstring 標「非 runtime store、勿在 runtime 實例化」；92 個 DB-class 測試仍綠。
- **結論**：15 項任務中 13 項完整完成；T8/T11 的 3 個生產死型別（Go JSONDatabase、Python JSONBDManager/IncrementalJSONDB）依 CLAUDE.md 與使用者決定保留為測試 fixture，已加 docstring/註解 guard；其安全子集（Save/CompactJournal、UnifiedFileScanner/WebSearcher/tools、Python prune 鍵名）皆已執行。
- 交付 commit：Wave 1 `1b636b0`、Wave 2 `3d64cf2`、Wave 3 `d51415c`、狀態 `be0f057`、T6 `fd03b52`（+本文件定案）。四工具鏈全綠：Root Go / Wails / Rust 58 / Python 1058 passed,2 skipped / 整合(CI 閘) 8 passed。
- `/tool-scan`（task.md 全域最終閘第 8 步）保留給此批 fix 全數落地後執行——程式碼已落地，可由使用者觸發；本助手不在未經要求下執行（見 memory [[feedback-verification-step-in-plan]]）。

---

## [2026-05-30 22:24 → 22:38, 14m] Boundary cleanup — A 區並行 (A1+A2+A3)

> 來源：`docs/boundary-cleanup-tasks.md` A 區三任務，檔案集互斥可一批並行。透過 workflow (id: wia9tt1bu, run: wf_e5e87278-c9b) 三 agent 並行執行；workflow ~9m40s + 主流程整合驗證 ~3m。

**Design decisions**
- 採 workflow 並行 (而非單 agent 序列)：三任務檔案集互斥 (`scripts/deadcode-all.*` / `scripts/verify.ps1` / `tests/integration/*` + docs)，無寫入衝突；wall-clock 從序列約 ~30 min 壓成並行約 ~14 min。
- Agent 在 own scope self-verify (A1 跑 deadcode、A2 跑 verify.ps1 -Quick、A3 跑兩次 pytest)；完整 verify.ps1 + 反向 fmt-壞測試留給整合驗證階段。
- 不開 worktree isolation：互斥檔案、Go build cache 不互衝。

**Deviations** (A 區 agent 偏離 spec 之處)
- **A2 wails-app build**：原 spec 寫 `go build ./...`，agent 改為 `go build ./backend`。原因：`wails-app/main.go` 用 `//go:embed all:frontend/dist`，而 `frontend/dist` 是 gitignored 的前端建置產物，fresh worktree 沒有它會編譯失敗，違反「當前樹綠 → exit 0」DoD。改 build `./backend` 與 CLAUDE.md「wails-app 測試 = `go test .\backend -v`」對齊。**已接受此偏離**。
- **A3 fixture 清理**：選 (b) 作法 — 保留 `shutil.copytree` 但 copy 後用 `dst.glob("db.sqlite*")` unlink 殘留 (含 `db.sqlite-shm`/`-wal`)。理由：forward-compatible (未來 fixture 多檔)、防禦 WAL 副產物。

**Tradeoffs**
- A1 必須 `-filter=` (空 regex) 才能跨 module 看可達性 — 不加 filter，wails-app (module name `wails-app`) 預設不會分析 `actress-classifier/pkg/*` 的可達性，導致交集近乎空集 → 大量假陽性。
- A2 verify.ps1 採序列步驟而非並行子步驟：spec 明寫「依序執行任一步紅就退出」，並行會混淆「哪一步先失敗」的 UX。

**Integration verification (主流程)**
- `pwsh scripts/deadcode-all.ps1` → 三個 wails-live 函數 (`database.NewVideo` / `mover.Mover.BatchMoveDirs` / `mover.Mover.GetOperation`) 正確列在 "Single-binary-only (DO NOT DELETE)"，未列在 REAL_DEAD intersection。
- `python -m pytest tests/integration/test_db_cli_contract.py -q` → 8 passed (與 A3 自驗一致)。
- 反向 DoD (A2 缺的)：故意把 `tools-rs/src/runtime_import.rs` 的 `pub replace: bool,` 縮排改成 7 空格 → `cargo fmt --check` exit 1 → `verify.ps1 -Quick` 在 step 3 FAIL 並 exit 1；還原後 worktree 乾淨。證明 fmt --check 確實鎖在 verify chain 內。

**Side observation (B 階段參考)**
- deadcode-all 顯示 intersection 4126 大多是 stdlib internals (bufio/bytes/crypto/...)；first-party 真死碼以 `JSONDatabase.*` 為主 — 即 B3 任務刻意保留為測試 fixture 的型別，刪除前要先做 B3 搬 package。

---

## [2026-05-30 22:50 → 23:12, 22m] Boundary cleanup — B1 DTO 收斂

> 來源：`docs/boundary-cleanup-tasks.md` B1。Workflow (id: wjob3q37u, run: wf_9b1c7c68-8dd) 內部 scout → execute 兩階段；workflow ~10m + 主流程整合驗證 ~3m。

**Design decisions**
- 採作法 (A) 收斂到 `mover.*`：刪 `pkg/contracts/{move,scan,history}.go` 三檔，pkg/contracts 整 package 消失。`cmd/scanner` 序列化點直接吐 `mover.MoveResult`/`mover.MergeResult`/`mover.BatchResult`/`mover.OperationLog`，不再走 `pkg/app/*ToContract` 轉換層。
- **ScanResult 落點**：放在 `pkg/app/scan_service.go` 內 (`type ScanResult struct{Path, Code string}`)，JSON tag `path/code` 完全沿用。理由：兩欄 DTO、放 mover 語意不對 (scan ≠ move)、新建 `pkg/scanner` 是 over-engineering。wails 各自宣告自己的 ScanResult (不共用) 不受影響。
- **toMoverItems 改名 applyDefaultConflictStrategy**：兩邊都 `mover.MoveItem` 後不再做 type 轉換，只保留 per-item `OnConflict` fallback 邏輯。

**Deviations** (vs scout plan)
- 無重大偏離。scout plan 完全可執行。

**Tradeoffs**
- 刪除 `TestMergeResultToContract_PropagatesNonEmptyErrors` / `TestMergeResultToContract_CopiesEveryField` (它們是為 `mergeResultToContract` 函式量身寫的，函式刪除後測試 obsolete)。**新增** `pkg/mover/types_test.go::TestMergeResult_JSONShapeIncludesFilesSkipped` 作 regression guard — `json.Marshal mover.MergeResult` 後斷言 7 個 key 都存在 (含 `files_skipped` 不漏)，對齊原 D2-1 守門意圖。
- 暫不解決 D2-3 (wails 端 ScanResult 與 cmd/scanner 端重複) — 不在 B1 scope。

**Integration verification (主流程)**
- `pwsh scripts/verify.ps1` (full)：root Go (build/vet/test) + wails (build/test ./backend) + Rust (fmt/clippy/test) + Python pytest 全綠。Python：1058 passed, 2 skipped。
- `pwsh scripts/deadcode-all.ps1`：B1 動的 pkg/contracts/pkg/app/pkg/mover 在 REAL_DEAD intersection 為空；wails-live 函數 (Mover.BatchMoveDirs/GetOperation) 仍正確列在 only-root。**B1 沒新增不可達**。
- 手動 CLI JSON 比對 (agent 已做)：scan/move single/move batch/move -kind dir/history list 五種輸出形狀與舊版逐欄一致；`files_skipped` 仍在。

**Wails 影響面**
- 0 影響。`wails-app/` 內無 import `pkg/contracts`，refactor 完全透明。wails build + test 全綠 (verify.ps1 step 2)。

---

## [2026-05-30 23:12 → 23:33, 21m] Boundary cleanup — B2 結構化 not-found 訊號

> 來源：`docs/boundary-cleanup-tasks.md` B2。Workflow (id: wirmo5dwt, run: wf_341732eb-a29) 內部 scout → execute 兩階段；workflow ~17m + 主流程整合驗證 ~3m。

**Design decisions**
- **採 both 設計**：主信號 = `exit code 3`、輔助信號 = stdout JSON `{success:false, error_kind:"not_found", kind:"video"|"actress", code|id:<key>, message:"video not found"}`。理由：(1) stdout 成功時是 video JSON，error 時若也吐 JSON 會混淆 — exit code 是區分器；(2) 沿用既有 exit code convention (1=runtime error / 2=bad CLI input / **3=not-found 業務狀態**)，3 是空缺位；(3) exit code 是 Python 最便宜的判斷 (一個 int 比較)，JSON 是給未來 GUI surface「為什麼找不到」。
- **保留 stderr substring fallback 作一版過渡**：Python `_is_not_found_error` 三段優先級 — (1) `returncode == 3` (2) stdout JSON `error_kind == "not_found"` (3) legacy substring。理由：Python 與 Go 不必同步部署也能跑舊版 classifier.exe，平滑升級。
- **Go 側拆 helper**：新增 `notFoundExitCode=3` 常數 + `buildNotFoundPayload` / `emitNotFoundAndExit` 純函式 helper，讓 Go 單元測試能驗 payload shape 不必處理 `os.Exit`。

**Deviations** (vs scout plan)
- 未處理 `pkg/database/jsondb.go:20` 的 `ErrNotFound = errors.New("video not found")` 訊息中性化 (scout.risks 提到 actress 找不到時 stderr 會吐「取得女優失敗: video not found」)。理由：結構化訊號 (kind: "actress") 已和 stderr 字串脫鉤，字串中性化會擴散到 ~92 個既有 fixture 測試 (與 B3 同性質)，屬獨立 slice。

**Tradeoffs**
- 強化 `tests/integration/test_db_cli_contract.py:421-429` 從寬鬆 `returncode != 0` 改成嚴格 `returncode == 3`，鎖定新契約。其他 `returncode != 0/1` 出現處與 db get/delete 無關，未動。
- `docs/ARCHITECTURE.md:84` 的「非零 exit 推回 False」描述用詞寬鬆未失準，未動 (避免無關文件改動)。

**Integration verification (主流程)**
- `pwsh scripts/verify.ps1` (full)：5 工具鏈全綠。Python：**1071 passed** (vs B1 後 1058，+13 為 B2 新增鎖定測試含 chinese-stderr / legacy-fallback / 4 個 wrapper missing 鎖定 / 真錯誤不吞 negative test)。
- 手動驗證 (主流程):
  - `db get NONEXISTENT` → exit 3 + stdout JSON `{error_kind:"not_found",kind:"video",code:"NONEXISTENT",message:"video not found",success:false}` ✓
  - `db delete NONEXISTENT` → 同上 ✓
  - `db get ""` (invalid input) → **exit 1 + stderr「取得影片失敗: invalid video code」** — 真錯誤路徑**未被破壞** ✓

**Wails 影響面**
- 0 影響。wails-app/backend 透過 `*SQLiteStore` 直接呼叫 Go API，不走 classifier.exe subprocess，所以對 stderr/exit code 零依賴。grep 確認 wails 沒消費 classifier.exe 的 exit code。

---

## [2026-05-30 23:34 → 2026-05-31 00:27, 53m] Boundary cleanup — B3 JSONDatabase 搬獨立 package

> 來源：`docs/boundary-cleanup-tasks.md` B3。Workflow (id: wb1p0gwcv, run: wf_a23df4c0-dc8) 內部 scout → execute；scout ~10m + execute ~39m + 主流程整合驗證 ~3m。最複雜的一個 — 動 ~63 個符號搬 package、~19 個 *_test.go 改 import、jsondb.go/journal.go/sqlite_runtime.go 連動。

**Design decisions**
- **dot-import 解 import cycle**：jsonfixture 必須 import `actress-classifier/pkg/database` 拿共享型別 (VideoData / ActressData / OpAdd / TypeVideo / DataFileName...)，但反向 (test 要碰 unexported fields) 會循環。解法：所有需要 JSONDatabase 的測試 **物理搬到** `pkg/database/jsonfixture/`，宣告 `package jsonfixture` + dot-import database — 同 package 取得 unexported 欄位、dot-import 取得共享型別、零反向依賴。
- **保留 JSONDatabase 大多 unexported field** (mu/dataDir/dataFile/journalFile/.../dirtyVideos/dirtyActresses/deletedVideos)：測試直接戳這些欄位驅動 error tail，搬到同 jsonfixture package 後自然可存取，避免為了測試強制 export 污染契約。
- **混合測試檔逐檔 split**：11 個 _test.go 混了 JSON 端 + SQLite runtime 測試。原則：JSON 相關 → jsonfixture/、SQLite runtime → 留 pkg/database/。例如 `runtime_extra_test.go` 內 5 個 `TestRestoreBackupDataFile_*` 系列搬走、26 個 runtime 內部測試留下。

**Deviations** (vs scout plan)
- 無重大偏離。scout plan 精確盤點正確。
- 小調整：8 個原本 unexported 的 live free function (jsondb.go 內被 sqlite_runtime.go 用) 需要升為 exported 才能跨 package 呼叫：`LoadMergeSourceData`、`PrepareVideoForMerge`、`IsBackupJSONFileName`、`DeleteExpiredBackups`、`RemoveOldestBackups`、`SelectPrimaryStudio`。`resolveMergeSourcePath` / `normalizeMergeSourceData` / `parseBackupDate` 維持 unexported (只在 pkg/database 內用)。
- `videoFieldUpdateHandlers` map 抽到 `pkg/database/journal.go` (極小、純 handler map)；`sqlite_runtime.go` 透過 `ApplyVideoFieldUpdates` wrapper 呼叫、jsonfixture 也透過 `database.ApplyVideoFieldUpdates` 呼叫 — handler map 維持 unexported 跨 package 不需直接看到。

**Tradeoffs**
- `helpers_test.go` 內 `writeJSONDB` / `minimalRoot` / `writeBackupWithMtime` 在 jsonfixture 重新實作一份 (byte-level duplicate 自 pkg/database 內同名 test helper)。理由：跨 package 拉 unexported test helper 需要強制 export，duplicate 量極小且純值 (~30 行)，沒有持續維護成本，比污染 export surface 划算。
- `ActressCleanupTarget` 是結構型介面 (`GetAllVideos` / `UpdateVideo` 等)，`*jsonfixture.JSONDatabase` 自動滿足 (Go 結構介面)，不需 adapter。`actress_cleaner_test.go` 只搬 2 個 `ApplyToDatabase` 測試 (需 `*JSONDatabase` 當 target)、9 個 `CleanActresses` 純測試留 pkg/database (戳 SQLiteStore)。

**Integration verification (主流程)**
- 6 個 boolean DoD 全綠 (agent 自驗):
  - `runtime_has_no_jsondatabase_type`: True (grep `type JSONDatabase` 在 pkg/database/ 排除 jsonfixture/ 無結果)
  - `pkg_database_test_pass`: True
  - `root_build_pass`: True
  - `wails_build_pass`: True
  - `schema_drift_locks_pass`: True (Go + 3 個 Rust drift 鎖綠)
  - `deadcode_no_new_unreachable`: True
- `pwsh scripts/verify.ps1` (full)：5 工具鏈全綠。Python：**1071 passed** (與 B2 後一致 — B3 純 Go 重構不動 Python)。
- `pwsh scripts/deadcode-all.ps1`：protected three (`database.NewVideo` / `mover.Mover.BatchMoveDirs` / `mover.Mover.GetOperation`) 仍正確列在 "Single-binary-only" → wails 路徑未被破壞。intersection (REAL DEAD) 無 jsonfixture 符號 (預期 — jsonfixture 只給 _test.go import，deadcode 看不到 _test.go 路徑，視為「不存在於 main binary」)。
- deadcode 對 pkg/database/ 的影響：actress-classifier/pkg/database.* 死碼從 baseline 81 降到 18 (減 63 — 即搬走的符號)，intersect 從 4126 降到 4063；only-root / only-wails 完全不變 (1503 / 1970)。0 NEW intersection，63 REMOVED。

**Wails 影響面**
- 0 影響。wails 不 import pkg/database/jsonfixture。runtime SQLiteStore 透過 pkg/database 的 exported helpers (升為 `LoadMergeSourceData` 等) 取代之前直接呼叫 unexported 版本，functional 等價。

---

## Boundary cleanup 整體總結 (A 區並行 + B 區序列，2026-05-30 22:24 → 2026-05-31 00:27, ~2h)

| 區 | 任務 | 工具 | 結果 |
|---|---|---|---|
| A1 | deadcode 交集腳本 | workflow 3 agent 並行 | ✅ DoD 綠 |
| A2 | verify.ps1 統一腳本 | (同上) | ✅ DoD 綠 + 反向 fmt-壞測試 |
| A3 | fixture 污染修復 | (同上) | ✅ DoD 綠 (整合測試連跑兩次都綠) |
| B1 | DTO 收斂到 mover.* | workflow scout→exec | ✅ pkg/contracts 整 package 刪、verify.ps1 1058 passed |
| B2 | 結構化 not-found 訊號 | workflow scout→exec | ✅ exit 3 + JSON + legacy fallback、verify.ps1 1071 passed |
| B3 | JSONDatabase 搬獨立 package | workflow scout→exec | ✅ 19 檔新建、63 符號搬遷、verify.ps1 1071 passed |

**C 區 (C1 §7.1 sibling、C2 wails 獨立 module) 維持文件化即解** — A2 的 verify.ps1 已順手補了 C2 的痛點 (一行統一測試腳本)，文件已說明 C1 是 v4 佈局重整時順手做。

**最終 worktree 狀態** (45 個 file changes)：
- 新建：scripts/deadcode-all.{ps1,sh}、scripts/verify.ps1、pkg/mover/types_test.go、pkg/database/jsonfixture/ (19 檔)
- 刪除：pkg/contracts/{move,scan,history}.go、pkg/database/jsondb*_test.go (6 檔)、pkg/database/journal_extra_test.go
- 修改：cmd/scanner/{main,db_cmd,main_test}.go、pkg/app/* (含 3 個測試)、pkg/database/{jsondb,journal,sqlite_runtime,...}.go (含多個 _test.go)、src/services/go_cli.py、tests/test_*.py + integration、CLAUDE.md、docs/contract-deadcode-audit-2026-05-30-tasks.md

**未跑的最終閘**：`/tool-scan` (boundary-cleanup-tasks.md 全域驗證第 8 步) — 留給使用者觸發 (見 memory `feedback_verification_step_in_plan`)。
