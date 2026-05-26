# Task.md — Phase D（SQLite-only runtime 收尾）

> 建立：2026-05-24
> Branch：`codex/shadow-db-sqlite`
> 前置：Phase A0 → C3 全部已 merge 進本 branch
> 範圍：**只動 agent 指引 + 契約測試**，不擴張功能、不改 runtime / schema / docs/plans。

---

## 1. Phase D 目標

把 Phase C2 / C3 後**已實作但未完整鎖定**的「SQLite-only runtime」狀態，透過**指引同步**與**契約測試補洞**固定下來，避免日後人類 / AI / agent 在「JSON 是主資料庫」這個過時模型上回退。

具體目標：

1. `AGENTS.md` 對齊到 `CLAUDE.md` 已寫好的 SQLite-only 世界觀（兩份不能再互相矛盾）。
2. Python / 整合測試補上 SQLite-only CLI 新子命令的契約鎖（`migrate-from-json` / `verify-sync` / `resync-from-json` / `export-json` / `backup-*` 雙快照）。
3. 確認 Phase A/B/C 留下的既有測試**全部仍綠**；任何紅燈視為 Phase C 漏修，回報到該 Phase 而不是在 Phase D 補。
4. 不擴張功能、不改 schema、不重組目錄。

---

## 2. 硬性規則

H1. **SQLite v3 是唯一 source of truth**，位置 `data/db.sqlite`。runtime 不再以 JSON 做主資料。
H2. JSON DB（`data/json_db/data.json`）只剩三種用途：**import 來源、export 快照、歷史備份**。不再 runtime 寫入。
H3. `-data-dir data/json_db` 預設**映射到 sibling** `data/db.sqlite`，**不是** `data/json_db/db.sqlite`。自訂 `-data-dir <path>` → `<path>/db.sqlite`。
H4. `pkg/database/store_factory.go::NewStore` 的 bootstrap-from-JSON 必須維持 **fail-loud**：當 SQLite 為空且 sibling `data.json` 存在時，匯入失敗一律 abort（close store + return err），**不准**改成 log + 回傳空 store。
H5. canonical SQLite schema 是 `pkg/database/sqlite_schema.sql`。Go 走 `//go:embed`、Rust 走 `include_str!("../../pkg/database/sqlite_schema.sql")` 引用同一份檔案。
H6. **嚴禁**把 schema 搬到 repo root 的 `schemas/sqlite/v3.sql`（Go `//go:embed` 拒絕 `..` 路徑，搬了會編譯失敗；且會打壞既有的四道 schema-drift 測試）。
H7. backup / restore CLI 名稱**固定**為：`db backup-create` / `db backup-list` / `db backup-restore` / `db backup-cleanup`。任何文件 / 測試 / wrapper 使用 `db backup` / `db restore` 等別名都視為錯誤。
H8. Phase D **不新增大型功能**。新增物件僅限「測試 case」、「agent 指引段落」、「fixture 微調」。

---

## 3. 允許修改的檔案範圍

> **範圍精修（2026-05-24 補）**：原規劃把 `pkg/database/**` / `cmd/scanner/**` / `wails-app/backend/**` 整段列為禁區，但測試補洞需要動到同套件下的 `*_test.go`。改成**檔尾後綴 + 路徑**的細粒度分流：runtime 原始碼禁、同套件測試檔允許。

### 3.1 允許修改

| 路徑 / glob | 用途 | 修改性質 |
|------|------|---------|
| `AGENTS.md` | 對齊 `CLAUDE.md` 的 SQLite-only 內容 | 對齊性改寫 |
| `CLAUDE.md` | 已對齊；本 Phase 僅允許**微調**（typo / 補漏） | 微調 |
| `Task.md` | 本檔，Phase D 期間可追加 sub-task | 增量追加 |
| `tests/**/*.py` | Python 契約 / 整合測試 | 追加 / 修改測試 |
| `tests/fixtures/json_db_minimal/data.json` | CI verify-sync 鎖定的 fixture；只允許**追加** entries，禁止改現有條目與檔案頂層結構 | 追加 only |
| `pkg/database/*_test.go` | Go 套件層級測試 | 追加 / 修改測試 |
| `cmd/scanner/*_test.go` | CLI handler 測試 | 追加 / 修改測試 |
| `wails-app/backend/*_test.go` | Wails backend 測試 | 追加 / 修改測試 |
| `tools-rs/tests/**` 與 `tools-rs/src/**` 內既有 `#[cfg(test)]` 區塊 | Rust 測試 | 限「文件 / 測試契約需要的最小調整」 |

### 3.2 禁區（runtime / 設計史料 / 對外文件）

D-RT1. **嚴禁修改 Go runtime（非測試）**：`pkg/database/*.go`（不含 `*_test.go`）、`pkg/app/**`、`pkg/extractor/**`、`pkg/mover/**`、`pkg/safefile/**`、`pkg/studio/**`、`pkg/contracts/**`、`pkg/cache/**`、`pkg/pathutil/**`、`cmd/scanner/*.go`（不含 `*_test.go`）。
D-RT2. **嚴禁修改 Wails runtime（非測試）**：`wails-app/backend/*.go`（不含 `*_test.go`）、`wails-app/frontend/**`、`wails-app/backend/services/**`（除非該檔本身就是 `*_test.go`）。
D-RT3. **嚴禁修改 Python runtime**：`src/**/*.py`。**允許** `tests/**/*.py`。
D-RT4. **嚴禁修改 Rust runtime**：`tools-rs/src/*.rs`（不含同檔內既有 `#[cfg(test)] mod tests` 區塊；該區塊內 case 允許做「文件 / 測試契約需要的最小調整」）。**允許** `tools-rs/tests/**`。
D-RT5. **嚴禁修改 schema**：`pkg/database/sqlite_schema.sql`。
D-RT6. **嚴禁修改設計史料**：`docs/plans/**`、`docs/superpowers/specs/**`、`implementation-notes.md`。
D-RT7. **嚴禁修改 wiki / README**：`wiki/**`、`README.md`、`README*.md`。若發現過時，記到本檔「Phase D 後續」段，留給後續 Phase 處理。

### 3.3 程序禁制

D-OP1. **嚴禁 commit / stage / push / rebase / amend**。Phase D 結束時 working tree 保持未提交，交人類審查。
D-OP2. **嚴禁 `git add data/`** 或在 staging area 出現 `data/` 內容。`data/` 為本機 runtime 資料，不入 git。
D-OP3. **嚴禁重命名 CLI 子命令**或新增別名（任何 `db backup` / `db restore` / `db sync` 之類的縮寫都不能加）。
D-OP4. **嚴禁**將 fixture 從 `tests/fixtures/json_db_minimal/data.json` 改名或搬位置（CI workflow `sqlite-verify-sync.yml` 把這個路徑寫死）。
D-OP5. **嚴禁**在 Phase D 內補實際 v3→v4 migration 程式碼或實作新 Wails UI 或新功能。

---

## 5. 前後端契約檢查清單

C-FB1. Wails frontend → backend 的 bindings 名稱不變（在 `wails-app/backend/app.go` 列出的方法群）：`DbStats` / `DbGetVideo` / `DbListCodes` / `DbUpdateVideo` 等。**確認 binding 表面零變動**。
C-FB2. backend 透過 `database.NewStore(StoreConfig{...})` 拿 `*SQLiteStore`，**不再持有 `*JSONDatabase`**。
C-FB3. backend `ensureDB` 仍允許 `data.json` mtime 變動觸發 reload；reload **不會** re-bootstrap（因為 SQLite 已有資料）。
C-FB4. Python → `classifier.exe` 唯一路徑為 `src/services/go_cli.py`。Phase D **不**新增 Python wrapper；僅在 contract test 內以 monkeypatch 模擬 raw subprocess。
C-FB5. Python wrapper 對外回傳的 `db stats` 結果**仍含** `journal_size` / `needs_compact` / `dirty_videos` / `sync_degraded_total` / `sqlite_read_fallback_total` 等退役欄位（zero/false 值），刪不得。
C-FB6. `db backup-create` 回傳的 JSON 含三個欄位：`backup_path`（.sqlite）、`json_export_path`（.json）、`path`（legacy alias = `json_export_path`）。三者**全部**必須存在。

## 6. 資料庫契約檢查清單

C-DB1. `data/db.sqlite` 的 `PRAGMA user_version` = 3；常數 `database.SQLiteSchemaVersion = 3` 與 `tools-rs/src/v3_schema.rs::V3_SCHEMA_VERSION = 3` 必須一致。
C-DB2. `pkg/database/sqlite_schema.sql` 是唯一 schema 來源。**嚴禁**在 `schemas/sqlite/v3.sql`、`tools-rs/...` 等其他位置出現第二份。
C-DB3. `ResolveDataDirPaths("data/json_db")` 必須回傳：
- `DataFile = data/json_db/data.json`
- `SQLitePath = data/db.sqlite`（**sibling**，不是 `data/json_db/db.sqlite`）
C-DB4. `ResolveDataDirPaths(<custom>)` 必須回 `<custom>/db.sqlite`。
C-DB5. `NewStore({DataDir: "data/json_db"})` 在 SQLite 為空且 `data.json` 損壞時必須 **return error**；不准吞錯誤、不准沉默回傳。
C-DB6. `db backup-create` 必須在同一個 timestamp 下產生 `backup_<ts>.json` + `backup_<ts>.sqlite` 雙快照；JSON 端必須**來自 SQLite export**（不是從 `JSONDatabase` 複製）。任一邊產出失敗時必須清掉另一邊，避免 `backup-list` 看到不成對的孤兒。
C-DB7. `db verify-sync` 必須能對既有 SQLite + 既有 `data.json` 跑 happy path 且 exit 0。
C-DB8. `db migrate-from-json` 預設 strict 模式；`-auto-create-missing-actresses` 才會自動合成 `auto_<sha1>` 女優。
C-DB9. `db resync-from-json` 必須在單一 transaction 內 wipe `videos` / `video_actress_links` / `actresses` / `actress_aliases` 四表後重建；`db_meta` 走 upsert，不刪除。
C-DB10. `db backup-restore` 接受 `.sqlite` / `.json` 兩種副檔名；`-from-json` 旗標走 resync flow；旗標互斥檢查違反時 exit code = 2。
C-DB11. tools-rs `db-tool db-import-json` 仍可執行但 stderr 須印 deprecation warning（**不要刪掉這條警告**）。

---

## 7. 必須確認的既有測試清單（Phase D 進入時應全綠）

### Go — `go test ./pkg/database -v`

- `data_dir_lookup_test.go`：`-data-dir` compatibility lookup（C-DB3 / C-DB4）
- `store_factory_test.go`：`TestNewStore_BootstrapFailureReturnsError`、`TestNewStore_BrokenJSONIgnoredWhenSQLitePopulated`、`TestNewStore_DefaultDataDirCompatibilityLookup`（C-DB5、C-FB2）
- `sqlite_store_test.go`：`TestSQLiteSchemaSQL_MatchesCanonicalFile`（C-DB2）+ schema 版本一致性
- `sqlite_backup_test.go`：`TestRestoreSQLiteFile_RollsBackOriginalOnCopyFailure`、`TestBackupCreate*`（C-DB6、C-DB10）
- `sqlite_crud_test.go` / `sqlite_read_store_test.go`：runtime CRUD
- `migrate_from_json_test.go`：strict / auto-create 兩條分支（C-DB8）
- `verify_sync_test.go`：happy / drift 偵測（C-DB7）
- `resync_from_json_test.go`：wipe + 重建在 transaction 內（C-DB9）
- `export_json_test.go`：SQLite → JSON round-trip

### Go — `go test ./cmd/scanner -v`

- `main_test.go::TestCreateDualBackup_JSONExportReflectsSQLiteNotJSONDatabase`（C-DB6）
- `main_test.go::TestDBBackupRestore*`（C-DB10）
- 其他 CLI handler 的既有 case

### Wails — `Set-Location wails-app; go test ./backend -v`

- `app_test.go::TestEnsureDB_BootstrapParseErrorClearsInstance`、`TestDbGetVideo_SurfacesBootstrapFailure`（C-DB5、C-FB3）
- `integration_test.go` 既有 happy paths

### Rust — `Set-Location tools-rs; cargo test`

- `src/v3_schema.rs::tests::embedded_schema_matches_canonical_file_on_disk`（C-DB2）
- `tests/integration_db_tool.rs::embedded_v3_schema_matches_canonical_go_package_file`、`db_verify_*`、`db_import_json_emits_deprecation_warning_to_stderr`（C-DB2、C-DB11）

### Python — `python -m pytest tests\ -q -p no:cacheprovider`

- `tests/test_go_cli_contracts.py` 全部
- `tests/integration/test_db_cli_contract.py::test_db_merge_accepts_source_with_data_dir`

> 進入 Phase D **前**這些測試必須全綠；任何紅燈先排查是不是 Phase C 漏修，不要在 Phase D 蓋掉。

---

## 8. 缺測試時要新增的最小測試位置

> 原則：**不**新增 `*_test.py` 或 `*_test.go` 檔；只在現有測試檔內**追加 case**。

### 8.1 `tests/test_go_cli_contracts.py`（Python wrapper 契約鎖）

即使 `src/services/go_cli.py` 目前未 wrap 下列子命令，仍以 monkeypatch 模擬「raw subprocess 結果 → 預期 Python 端可處理的 JSON 形狀」鎖死契約：

- `test_db_migrate_from_json_strict_report_shape`（驗 `report` JSON 含 `videos_imported` / `actresses_imported` / `links_imported` / `unresolved_actresses` / `duplicates` 等欄位 — 以實際 `MigrateReport` 結構為準）
- `test_db_migrate_from_json_auto_create_flag_present`（驗 `-auto-create-missing-actresses` 旗標在 stderr 失敗訊息會被建議）
- `test_db_verify_sync_happy_payload_keys`
- `test_db_resync_from_json_payload_keys`
- `test_db_export_json_payload_keys`
- `test_db_backup_create_dual_snapshot_legacy_path_alias`（補強：除 `backup_path` / `json_export_path` 外，**legacy `path` alias 必須等於 `json_export_path`**）

### 8.2 `tests/integration/test_db_cli_contract.py`（真實 `classifier.exe` 契約）

對 prebuilt `classifier.exe` 跑真實 subprocess，補 happy-path：

- `test_db_migrate_from_json_imports_minimal_fixture`：以 `tests/fixtures/json_db_minimal/data.json` 為來源，在 tmp_path 內跑 migrate，斷言 SQLite 落在 sibling 而非 `json_db/` 下（鎖 C-DB3 / C-DB4）
- `test_db_verify_sync_passes_after_migrate`（鎖 C-DB7）
- `test_db_export_json_round_trips_with_verify_sync`（migrate → export → verify-sync 三段成功）
- `test_db_backup_create_emits_dual_snapshot_pair`：確認同 timestamp 的 `.sqlite` + `.json` 兩個 sibling 檔都存在（鎖 C-DB6）
- `test_db_backup_restore_mutual_exclusion_exit_code_2`（鎖 C-DB10）
- `test_db_backup_restore_accepts_sqlite_and_json_extensions`（鎖 C-DB10）
- `test_db_resync_from_json_wipes_then_repopulates`（鎖 C-DB9）

### 8.3 fixture 追加（如必要）

- `tests/fixtures/json_db_minimal/data.json` 允許**追加** 1–2 筆 video / actress / link 來支援上述新測試。**禁止**改既有 entries（CI workflow 也讀同一份）。

---

## 9. 驗證命令

```powershell
# 1. 建 classifier.exe（整合測試需要 prebuilt 執行檔）
go build -o classifier.exe .\cmd\scanner

# 2. Go 核心
go test .\pkg\... -v
go test .\cmd\scanner -v

# 3. Wails backend
Set-Location wails-app
go test .\backend -v
Set-Location ..

# 4. Rust db-tool
Set-Location tools-rs
cargo test
Set-Location ..

# 5. Python 契約 + 整合
python -m pytest tests\test_go_cli_contracts.py -q -p no:cacheprovider
python -m pytest tests\integration\test_db_cli_contract.py -v --tb=short -p no:cacheprovider

# 6. 全量 Python（檢查沒踩到其他測試）
python -m pytest tests\ -q -p no:cacheprovider

# 7. CI 本機重現（sqlite-verify-sync.yml）
.\classifier.exe db migrate-from-json -data-dir tests\fixtures\json_db_minimal
.\classifier.exe db verify-sync -data-dir tests\fixtures\json_db_minimal
```

---

## 10. 完成條件（Definition of Done）

DoD1. `AGENTS.md` 已對齊 `CLAUDE.md`：JSON DB 不再被描述為 source of truth；模組地圖含 `sqlite_runtime.go` / `store_factory.go` / `sqlite_backup.go` / `migrate_from_json.go` / `verify_sync.go` / `export_json.go`；資料庫規範段提及 `data/db.sqlite` 與 sibling lookup；`tools-rs` 段更新為 v3 verify/migrate + legacy v2 診斷。
DoD2. `tests/test_go_cli_contracts.py` 含第 8.1 節列出的全部新 case 且通過。
DoD3. `tests/integration/test_db_cli_contract.py` 含第 8.2 節列出的全部新 case 且通過（依 prebuilt `classifier.exe`）。
DoD4. 第 7 節列出的既有測試全部仍綠。
DoD5. 第 9 節驗證命令全部 exit 0。
DoD6. 第 3.2 / 3.3 節禁區檔案在 `git diff` 內 0 行變動；`data/` 未被 stage。
DoD7. 不執行 `git commit`、不執行 `git push`、不執行 `git rebase`；working tree 保持未提交，交回給人類審查。

---

## 11. Rollback / Stop Gate

S1. **發現 Phase D 工作會需要動到第 3.2 / 3.3 節禁區檔案或程序**：立刻 stop，回報「這該是 Phase E 或 Phase C 補丁」。
S2. **發現既有測試在 Phase D 開工前就紅了**：立刻 stop，把紅燈歸因到 Phase A/B/C 對應 slice，不在 Phase D 蓋。
S3. **發現 schema-drift 測試紅了**：立刻 stop。檢查是否有人嘗試把 schema 搬到 `schemas/sqlite/v3.sql` 或在他處複製，撤回後重跑。
S4. **發現需要改 CLI 子命令名稱**：立刻 stop。改名屬於 breaking change，不在 Phase D scope。
S5. **發現 `data/db.sqlite` 與 `data/json_db/data.json` 內容不一致且 verify-sync 紅燈**：先跑 `classifier.exe db resync-from-json` 試圖修復；修不掉就 stop，紀錄到本檔「Phase D 後續」。
S6. **AI / agent 把 Task.md 內的硬性規則自行放寬**（例如「我覺得也可以順便動 runtime」）：立刻 stop，回到此檔重新核對 H1-H8 / D1-D9。
S7. **任何試圖 commit / push / rebase 的指令**：立刻 stop；Phase D 完成方式是「working tree 改完不 commit，交人類審查」。

Rollback 程序（若 Phase D 中途決定放棄）：

```powershell
# 1. 確認沒有 commit
git log -1

# 2. 還原本檔（若已寫了一半且要丟棄）
git checkout -- Task.md AGENTS.md tests\test_go_cli_contracts.py tests\integration\test_db_cli_contract.py

# 3. CLAUDE.md 的 SQLite 對齊改寫保留；除非人類另行決定，否則不要 revert
```

---

## Phase D 後續（out of scope，記到此處留給後續 Phase）

- `wiki/` 內可能有過時段落（例如還在描述 dual-write）。需另立 Phase 來梳理 `wiki/architecture/*.md`、跑 `python wiki/gen_data.py` 重新產生 `wiki/wiki-data.js`。
- `README.md` 對外段落仍以 JSON DB 為主軸描述；屬於對外文件改動，建議另立 Phase。
- `wails-app/backend/app.go::ensureDB` 仍 watch `data.json` mtime。Phase C2 implementation-notes 已標記為「待 C3 起 prune」，需獨立 Phase 評估是否在 SQLite-only 後續徹底拿掉。
- tools-rs 的 v2 legacy 子命令（`db-init` / `db-stats` / `db-compare-json` / `db-benchmark` / `query`）長期應退役；現階段保留為診斷工具，未來 Phase 評估完全刪除的時機。
- `db-migrate` 目前僅 v3→v3 no-op；真正 v3→v4 schema 升級需獨立 Phase（要先有 v4 schema design）。
