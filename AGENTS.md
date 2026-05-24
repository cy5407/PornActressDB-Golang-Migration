# AGENTS.md

本檔提供此 repo 目前有效的開發指引（對所有 coding agent 通用；Claude Code 另見 `CLAUDE.md`，主體內容應與本檔保持同步）。

## 語言偏好

**所有回應一律使用繁體中文 (zh-TW)。**

- 預設不使用簡體中文。
- 除非使用者明確指定其他語言，否則說明、註解與文件皆以繁體中文撰寫。

## 專案大圖

**女優分類系統 (Actress Classifier)** — Windows 桌面工具。三層架構：

- **Wails GUI**：`actress-classifier.exe`（Go backend + React/TypeScript frontend）
- **Go CLI**：`classifier.exe`（掃描、移動、SQLite 資料庫、操作歷史；非搜尋主流程的唯一寫入入口）
- **Python 搜尋管線**：`src/scrapers/run_search.py`、`run_batch_search.py`、`src/services/web_searcher.py`（由 GUI 透過 subprocess 呼叫，僅負責爬蟲）
- **Rust `db-tool`**（`tools-rs/`）：runtime SQLite v3 匯入 / 結構驗證 / schema 遷移骨架 (`db-import-json-v3` / `db-verify` / `db-migrate`)；仍保留 legacy v2 shadow-DB 診斷子命令
- **主進入點**：`run.py`（優先啟動已建好的 Wails 執行檔）

## 建置與測試

### 建置 Go CLI

```powershell
go build -o classifier.exe .\cmd\scanner
```

> 必須用套件路徑 `.\cmd\scanner`，不要直接編譯 `cmd\scanner\main.go`，否則會漏掉同套件其他 `.go` 檔案。

### 建置 Wails 桌面應用

```powershell
Set-Location wails-app
wails build
```

> 正式發行請跑 `.\setup.ps1`（根目錄）— 會建置兩支 exe、組裝 `dist\portable\`、把 `studios.json` / `major_studios.json` / `src\` / `requirements.txt` / 啟動器複製到同層、壓成 `dist\PornActressDB-windows-portable.zip`。直接複製單一 EXE 出去會踩 `resolveStudiosPath` 找不到資源的雷。

### Python 相依

```powershell
pip install -r requirements.txt
```

僅搜尋爬蟲需要；GUI 啟動本身不需要 Python。

### 啟動

```powershell
python run.py
```

### 測試

```powershell
# Go 核心
go test .\pkg\... -v
go test .\cmd\scanner -v

# Wails backend
Set-Location wails-app
go test .\backend -v
Set-Location ..

# Rust db-tool
cargo test --manifest-path tools-rs\Cargo.toml

# Python（整體 / 整合 / 單檔）
python -m pytest tests\ -q -p no:cacheprovider
python -m pytest tests\integration\ -v --tb=short -p no:cacheprovider
python -m pytest tests\test_go_cli_contracts.py -q -p no:cacheprovider

# 跑單一 Go 測試
go test .\pkg\database -run TestNewStore_BootstrapFailureReturnsError -v
```

## 架構：runtime SQLite-only（C2 之後）

**Source of truth 已從 JSON DB 切換為 SQLite v3**。

- 主資料：`data\db.sqlite`（`PRAGMA user_version = 3`）
- JSON DB（`data\json_db\data.json`）僅作為**匯入來源、匯出目標、歷史備份**；runtime 不再寫 JSON
- `data\json_db\data.journal` / `data.index` 已停用，沒有 journal replay

### `-data-dir` Compatibility Lookup（spec § 7.1）

- 預設 `-data-dir data/json_db` → SQLite 落在 **sibling** `data/db.sqlite`（不是 `data/json_db/db.sqlite`）
- 自訂 `-data-dir <path>` → `<path>/db.sqlite`
- 解析邏輯：`pkg/database/data_dir_lookup.go::ResolveDataDirPaths`

### Bootstrap 是 fail-loud 的切換閘

`pkg/database/store_factory.go::NewStore` 在以下情境會 **一次性** 把 `data.json` 匯入空的 SQLite：

1. SQLite 不存在或 `videos`+`actresses` 都是空，且
2. 同層有 `data.json`，且
3. caller 沒設 `SkipBootstrap`

**Bootstrap 失敗一定 fatal**：parse error、strict-mode 對不上的 actress、stat 失敗 — 全部會 close store 並回傳錯誤。**不要**改成 log + 回傳空 store，那會把 JSON→SQLite 切換期的資料損失藏成「乾淨 greenfield」。

恢復路徑：操作者讀 stderr 修 JSON，或跑：

```powershell
classifier.exe db migrate-from-json -auto-create-missing-actresses
```

當 SQLite 已有資料時，bootstrap 整段會 short-circuit — 此時手改或壞掉的 `data.json` 完全不會影響 runtime。

## 重要模組地圖

### Go runtime（SQLite-only）

- `pkg/database/store_factory.go` — `NewStore(StoreConfig)`：runtime 開店唯一入口；含 fail-loud bootstrap
- `pkg/database/sqlite_store.go` — `*SQLiteStore` 本體 + schema init（`//go:embed sqlite_schema.sql`）
- `pkg/database/sqlite_runtime.go` — runtime API：`AddVideo` / `UpdateVideo` / `GetActress` / `GetStats` / `Backup*` / `Merge*` / journal-shaped no-ops (`Save` / `Compact` / `CompactJournal` / `CompactIfNeeded`)
- `pkg/database/sqlite_crud.go` — primitive upsert / read
- `pkg/database/sqlite_backup.go` — `VACUUM INTO` 為主、`PRAGMA wal_checkpoint + 檔案 copy` 為 fallback；`RestoreSQLiteFile` 採 rename-aside rollback
- `pkg/database/migrate_from_json.go` / `verify_sync.go` / `export_json.go` — 匯入 / 等價檢查 / 匯出。root `links[]` 在 import 時除了套用 override，還會逐筆寫入 `legacy_video_actress_links`（含 `video_code=""` 的 orphan）；export 從該表照 ordinal 還原 `root.links[]`。
- `pkg/database/sqlite_schema.sql` — **canonical schema**；Go 與 Rust 共用（見下方）。v3 含 `legacy_video_actress_links`（無 FK 的 root `links[]` ordinal 快照）；此表為 additive 新增，`user_version` 保持 3。
- `pkg/database/jsondb.go` — 保留為匯入 / 匯出 / 測試 fixture 助手；**不是 runtime store**

### Go CLI 入口

- `cmd/scanner/db_cmd.go` — `db` 主路由與 `get/update/delete/list/stats/compact/clean-actresses/backup-*` handler
- `cmd/scanner/db_sqlite_cmd.go` — `migrate-from-json` / `verify-sync` / `resync-from-json` / `export-json`

backup / restore CLI 名稱**固定**為：

- `classifier.exe db backup-create`
- `classifier.exe db backup-list`
- `classifier.exe db backup-restore`
- `classifier.exe db backup-cleanup`

不要新增 `db backup` / `db restore` / `db sync` 等別名。

### Schema 共用（Go ↔ Rust）

| 端 | 內嵌方式 |
|----|---------|
| Go runtime (`pkg/database/sqlite_store.go`) | `//go:embed sqlite_schema.sql` |
| Rust `tools-rs/src/v3_schema.rs` | `include_str!("../../pkg/database/sqlite_schema.sql")` |

**不要**把 schema 搬到 `schemas/sqlite/v3.sql` — Go `//go:embed` 拒絕 `..` 開頭的相對路徑。漂移由四道測試固定：

- `pkg/database/sqlite_store_test.go::TestSQLiteSchemaSQL_MatchesCanonicalFile`
- `tools-rs/src/v3_schema.rs::tests::embedded_schema_matches_canonical_file_on_disk`
- `tools-rs/tests/integration_db_tool.rs::embedded_v3_schema_matches_canonical_go_package_file`
- `tools-rs/tests/integration_db_tool.rs::db_verify_*`

### Rust `db-tool` 新定位

| 子命令 | schema | 狀態 |
|--------|--------|------|
| `db-import-json-v3` | v3 runtime | **生效** — 用 Rust 把 `data.json` 精準匯入 runtime v3 SQLite；與 Go `migrate-from-json` 對齊 |
| `db-verify` | v3 runtime | **生效** — 驗證 `data/db.sqlite` 結構與 `user_version` |
| `db-migrate` | v3 runtime | **生效** — 目前僅 v3→v3 no-op 骨架 |
| `db-init` / `db-stats` / `db-compare-json` / `db-benchmark` / `query` | v2 shadow | **legacy 保留** — 歷史診斷工具 |
| `db-import-json` | v2 shadow | **deprecated** — 仍可執行但 stderr 印 deprecation warning |

### Python 委派層（薄）

- `src/services/go_cli.py` — Python 呼叫 `classifier.exe` 的唯一入口；`is_available(...)` / `run(...)` 都必須收到 `go_exe_path` / `exe_path`
- `src/models/json_database.py` — `JSONDBManager`：Go-only 委派層
- `src/models/incremental_json_database.py` — `IncrementalJSONDB`：增量 DB / compact 委派層（SQLite 沒 journal，`compact` 為 no-op 但保留 contract）
- `src/scrapers/cache_manager.py` — 爬蟲快取層（仍呼叫 Go CLI）
- `src/utils/scanner.py` — Go CLI 掃描薄適配層

### Wails

- `wails-app/backend/app.go` — 透過 `database.NewStore(StoreConfig{...})` 取 `*SQLiteStore`；前端契約不變
- `wails-app/frontend/src/` — React + TypeScript UI
- `wails-app/go.mod` — 獨立 module，`replace actress-classifier => ../`

## 開發規範

### Go-only 邊界

- **非爬蟲層採 Go-only**：DB、掃描、搬移、操作歷史的能力一律透過 `src/services/go_cli.py` 委派給 `classifier.exe`。不要新增或恢復 Python fallback。
- 若 Go CLI 不可用，非爬蟲層應明確回報錯誤，**不要**靜默假成功。
- 不要在 `scanner.py` 自己寫一套 classifier 路徑解析；統一走 `go_cli.is_available(...)/run(...)`。

### 爬蟲層例外

- `src/scrapers/` 與搜尋器仍可保留 Python-first 實作。
- 搜尋順序固定為：**AV-WIKI → JAVDB**。
- 修正爬蟲時優先考慮穩定性、限流、快取、錯誤語意。

### GUI 規範

- 舊版 Python GUI 已移除。
- GUI 改動：`wails-app/frontend/src/`（畫面與互動）、`wails-app/backend/`（bindings 與後端流程）。

### 資料庫規範

- **不要**手改 `data\db.sqlite`（也不要手改 `data\json_db\data.json`）。所有寫入都走 `classifier.exe db ...` 或 `*SQLiteStore` API。
- Python helper 期望的 `db stats` JSON 仍含 `journal_size` / `needs_compact` / `dirty_videos` / `sync_degraded_total` / `sqlite_read_fallback_total` 等欄位 — 這些是 **C2 故意保留的 zero/false 值**，刪掉會打壞 Python helper。
- 維護工具：
  - `classifier.exe db verify-sync` — SQLite ↔ JSON 等價檢查
  - `classifier.exe db export-json -output ...` — 從 SQLite 產生 JSON 快照
  - `classifier.exe db resync-from-json -source ...` — wipe & 重建（drift 時用）
  - `cargo run --manifest-path tools-rs\Cargo.toml -- db-import-json-v3 --json data\json_db\data.json --sqlite data\db.sqlite --replace` — Rust runtime v3 匯入（需要從 JSON 重建 SQLite 時使用）
  - `python tools\verify\verify_json_db_schema.py data\json_db\data.json` — JSON 端 schema 驗證

## 常見工作

### 修改 Go CLI

1. 修改 `pkg\...` 或 `cmd\scanner\...`
2. 跑對應 `go test`
3. 重新建置 `classifier.exe`
4. Python / Wails / 整合測試呼叫端維持同一份 CLI 契約（`tests/test_go_cli_contracts.py` 是契約鎖）

### 修改 SQLite schema

1. 改 `pkg/database/sqlite_schema.sql`（唯一來源）
2. 同步更新 `pkg/database/sqlite_store.go::SQLiteSchemaVersion` 與 `tools-rs/src/v3_schema.rs::V3_SCHEMA_VERSION`（兩邊都是 `3`，目前一致）
3. 跑 schema-drift 測試（前段「Schema 共用」列出的四個）
4. 視需要在 `tools-rs/src/migrate.rs` 加實際 v3→v4 遷移；目前 `db-migrate` 僅 v3→v3 no-op

### 修改 GUI

1. 調整 `wails-app/frontend/src/components/` 或 `App.tsx`
2. 需要新 backend 能力時更新 `wails-app/backend/app.go`
3. 視需要補 `wails-app/backend/app_test.go`

### 修改 wiki

修改 `wiki/**/*.md` 後必須一次完成三件事，否則 viewer 仍顯示舊內容：

1. 編輯 Markdown
2. 在 `wiki/log.md` 追加當日紀錄（格式對照既有 entry，最新在上）
3. 跑 `python wiki/gen_data.py` 重新產生 `wiki/wiki-data.js`（Windows console 若報 `UnicodeEncodeError`，用 `PYTHONIOENCODING=utf-8` 重跑）

## CI 注意點

`.github/workflows/sqlite-verify-sync.yml` 是 Phase A 釋出閘 — `pkg/database/**`、`cmd/scanner/**`、`tests/fixtures/json_db_minimal/**` 的改動會觸發 build → `db migrate-from-json` → `db verify-sync`。任何非零 exit 都會擋 PR。本機重現：

```powershell
go build -o classifier.exe .\cmd\scanner
.\classifier.exe db migrate-from-json -data-dir tests\fixtures\json_db_minimal
.\classifier.exe db verify-sync -data-dir tests\fixtures\json_db_minimal
```

## 備註

- `README.md` 是對外使用說明；架構或測試命令改變時請同步更新。
- `implementation-notes.md` 是 SQLite 遷移各 slice 的設計決策紀錄（C1 / C2 / C3）；改 SQLite 相關行為前先讀。
- `wiki/architecture/database.md` 是目前最權威的 DB 架構參考；`wiki/architecture/sqlite-shadow-db.md` 已標為 historical / 退役。
- `tools-rs/` 是 Rust crate (`db-tool`)。第一版的 shadow-DB 角色已退役，但 binary 仍保留 v2 子命令（`db-init` / `db-stats` / `db-compare-json` / `db-benchmark` / `query`）作為診斷工具；`db-import-json` 跑時 stderr 會顯示 deprecated warning。`db-import-json-v3` / `db-verify` / `db-migrate` 對象是 v3 runtime DB（`data/db.sqlite`）。
