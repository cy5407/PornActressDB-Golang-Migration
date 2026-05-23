# 資料庫架構

> 來源：`pkg/database/sqlite_schema.sql`、`pkg/database/sqlite_store.go`、`pkg/database/sqlite_runtime.go`、`pkg/database/sqlite_crud.go`、`pkg/database/sqlite_backup.go`、`cmd/scanner/db_cmd.go`、`wails-app/backend/app.go`、`src/services/go_cli.py`、`src/models/incremental_json_database.py`、`src/models/json_database.py`
> 更新：2026-05-23（C2 切換為 SQLite-only runtime，C3 確認 schema 共用）

---

## 概述

本專案目前的 source of truth 是 **SQLite v3** 資料庫，預設位置 `data/db.sqlite`。
寫入、讀取、備份、還原、stats、compact 等全部走 Go 端 `SQLiteStore`（`pkg/database/sqlite_store.go` + `sqlite_runtime.go` + `sqlite_crud.go`）。

JSON 資料庫（`data/json_db/data.json`）目前的角色：

- **不是 runtime source of truth**（C2 之後）
- 仍是 `db migrate-from-json` 的輸入、`db export-json` / `db backup-create` 的輸出檔
- 對歷史備份與外部診斷腳本保留可讀寫格式
- 沒有 journal replay；`data.journal` / `data.index` 已停用

Python 端的 `IncrementalJSONDB` / `JSONDBManager` 兩層包裝仍存在，但呼叫實作都委派回 Go CLI。

---

## 檔案結構

```text
data/
├── db.sqlite            # ← 主資料（SQLite v3，user_version=3）
├── db.sqlite-wal        # WAL，由 SQLite 自管理
├── db.sqlite-shm        # 共享記憶體，由 SQLite 自管理
├── json_db/
│   ├── data.json        # 匯入 / 匯出用 JSON 快照（不再 runtime 寫入）
│   └── backup/          # backup_<timestamp>.json + .sqlite 雙快照
└── backup/              # （備援目錄，視 -data-dir 而定）
```

`-data-dir` compatibility lookup（spec § 7.1）：

- 預設 `data/json_db` → SQLite 落在 `data/db.sqlite`（**不是** `data/json_db/db.sqlite`）
- 自訂 `<path>` → `<path>/db.sqlite`

完整解析邏輯位於 `pkg/database/data_dir_lookup.go`。

---

## SQLite v3 Schema 概覽

canonical 來源檔：`pkg/database/sqlite_schema.sql`
Go 端透過 `//go:embed` 內嵌；Rust `tools-rs/db-tool` 透過 `include_str!("../../pkg/database/sqlite_schema.sql")` 共用同一份檔案（細節見「Schema 共用 (Go + Rust)」段）。

| 表 / View | 用途 |
|-----------|------|
| `db_meta` | key/value：schema_version、description、encoding、data_hash、created_at、updated_at |
| `videos` | 影片本體；以 `code` 為 primary key，欄位對應 `pkg/database/types.go` 的 `VideoData` |
| `actresses` | 女優 entity；`id` 為 stable hash，`name` 為顯示名稱 |
| `actress_aliases` | 女優別名（多對一） |
| `video_actress_links` | 影片 ↔ 女優關聯；含 `role_type`、`ordinal`、`display_name`、`timestamp` |
| `actress_video_counts`（view） | 每位女優的影片數 |
| `studio_statistics`（view） | 每個片商的影片數 |
| `enhanced_actress_studio_statistics`（view） | 女優 × 片商交叉統計 |

`PRAGMA user_version = 3` 由 Go 端 `SQLiteStore.InitSchema()` 設定，常數 `SQLiteSchemaVersion = 3`（`pkg/database/sqlite_store.go`）。

---

## Schema 共用 (Go + Rust)

canonical 檔案：`pkg/database/sqlite_schema.sql`。

| 端 | 內嵌方式 | 路徑 |
|----|---------|------|
| Go runtime (`pkg/database/sqlite_store.go`) | `//go:embed sqlite_schema.sql` | package-local |
| Rust `tools-rs/db-tool` (`src/v3_schema.rs`) | `include_str!("../../pkg/database/sqlite_schema.sql")` | 跨 crate 相對路徑 |

**為什麼不是 `schemas/sqlite/v3.sql` at repo root？** Go `//go:embed` 不接受 package 目錄外的相對路徑（`../../schemas/...` 編譯失敗）。Rust `include_str!` 沒有這個限制，因此採「Go 為 canonical 位置，Rust 反過來 include」這個方向，避免引入 build pipeline（go:generate / build.rs 複製檔）複雜度。

**漂移防護**：

- `pkg/database/sqlite_store_test.go::TestSQLiteSchemaSQL_MatchesCanonicalFile` — Go embed bytes 與 on-disk 檔案比對
- `tools-rs/src/v3_schema.rs::tests::embedded_schema_matches_canonical_file_on_disk` — Rust include_str! 與 on-disk 比對
- `tools-rs/tests/integration_db_tool.rs::embedded_v3_schema_matches_canonical_go_package_file` — 整合層級的相同比對
- 上述三個測試任何一個失敗，都代表有人偷偷編了第二份 schema

---

## Go CLI 介面（與 Python / Wails 共用）

```bash
classifier.exe db get STARS-707
classifier.exe db update STARS-707 video.json
classifier.exe db list --full
classifier.exe db stats
classifier.exe db compact -json            # no-op；保留 JSON 期望欄位（C1 後）
classifier.exe db clean-actresses
classifier.exe db clean-actresses -write
classifier.exe db backup-create            # 雙快照：.sqlite + .json
classifier.exe db backup-list
classifier.exe db backup-restore -backup-path <file.sqlite|file.json>
classifier.exe db backup-restore -from-json <file.json>
classifier.exe db backup-cleanup
classifier.exe db migrate-from-json -source data\json_db\data.json
classifier.exe db verify-sync
classifier.exe db resync-from-json -source data\json_db\data.json
classifier.exe db export-json -output data\json_db\data.json
```

CLI 契約已鎖定於 `tests/test_go_cli_contracts.py`（spec § 7.1）。

### Python 端入口

```python
from models.incremental_json_database import IncrementalJSONDB

db = IncrementalJSONDB('data/json_db')
db.get_video_info('STARS-707')
db.add_or_update_video('STARS-707', {'studio': 'S1'})
db.compact_if_needed()      # 委派 Go；SQLite 沒有 journal，回傳 noop
db.compact()                # 同上
```

Python 端讀到的 `db stats` JSON 仍含 `journal_size` / `needs_compact` / `dirty_videos` 等 JSON 時代欄位（C2 故意保留，避免 Python helper `KeyError`）。

### Wails Backend 入口

`wails-app/backend/app.go` 透過 `database.NewStore(database.StoreConfig{...})` 取得 `*SQLiteStore`，前端契約不變。

---

## Rust `db-tool`（`tools-rs/`）

`db-tool` 目前同時包含兩種角色：

| 子命令 | 對象 schema | 用途 | 狀態 |
|--------|-------------|------|------|
| `db-init` | v2（legacy shadow DB） | 建立 shadow DB | legacy，留作歷史診斷 |
| `db-import-json` | v2 | 從 JSON 匯入 shadow DB | **deprecated**（stderr 顯示 warning） |
| `db-stats` / `db-compare-json` / `db-benchmark` / `query …` | v2 | shadow DB 診斷 / 比對 / benchmark | legacy |
| `db-verify` | v3 | runtime SQLite 結構檢查（PRAGMA integrity_check / user_version / 必要表 view） | **new in C3** |
| `db-migrate` | v3 | runtime SQLite 遷移骨架；目前僅實作 v3 → v3 no-op | **new in C3** |

詳細歷史定位見 [sqlite-shadow-db.md](sqlite-shadow-db.md)（已標 historical / 退役）。

---

## 影片資料 Schema（持久化欄位）

正式定義以 `pkg/database/types.go::VideoData` 與 `pkg/database/sqlite_schema.sql` 的 `videos` 表為準。

```json
{
  "code": "STARS-707",
  "id": "",
  "title": "影片標題",
  "studio": "S1",
  "studio_code": "STARS",
  "release_date": "2026-01-01",
  "url": "https://example.com/title/STARS-707",
  "actresses": ["女優名"],
  "search_status": "searched_found",
  "search_method": "AV-WIKI",
  "last_search_date": "2026-04-22T00:00:00Z",
  "avwiki_actress_status": "found",
  "avwiki_last_search_date": "2026-04-22T00:00:00Z",
  "javdb_actress_status": "not_found",
  "javdb_last_search_date": "2026-04-22T00:05:00Z",
  "created_at": "2026-04-21T23:50:00Z",
  "updated_at": "2026-04-22T00:05:00Z",
  "original_filename": "STARS-707.mp4",
  "file_path": "D:\\Videos\\STARS-707.mp4",
  "metadata": {
    "source": "",
    "confidence": 0.0
  },
  "error": "",
  "error_kind": ""
}
```

`videos.actresses` 是讀取時從 `video_actress_links` JOIN `actresses` 重建出來的字串陣列，並非 `videos` 表的實體欄位。

### 欄位說明

| 欄位 | 說明 |
|------|------|
| `code` | 影片番號；primary key |
| `id` | 舊相容欄位，保留為空字串 |
| `title` | 片名 |
| `studio` / `studio_code` | 片商名稱與短碼 |
| `release_date` | 發行日期 |
| `url` | 搜尋結果頁 / 詳情頁 URL |
| `actresses` | 從 `video_actress_links` 還原的女優顯示名稱清單 |
| `search_status` | 整體搜尋狀態（見下） |
| `search_method` | 本次資料的搜尋來源 / 方法字串 |
| `last_search_date` | 整體搜尋狀態最後更新時間 |
| `avwiki_actress_status` / `avwiki_last_search_date` | AV-WIKI 單一來源的狀態 |
| `javdb_actress_status` / `javdb_last_search_date` | JAVDB 單一來源的狀態 |
| `created_at` / `updated_at` | 建立 / 更新時間 |
| `original_filename` / `file_path` | 原始檔名與完整路徑 |
| `metadata.source` / `metadata.confidence` | 來源與信心值 |
| `error` / `error_kind` | 持久化錯誤訊息與分類 |

---

## `search_status` 目前使用值

| 值 | 說明 |
|----|------|
| `imported` | 僅導入，尚未完成搜尋 |
| `searched_found` | 已搜尋且找到資料 |
| `searched_not_found` | 已搜尋但找不到資料 |
| `search_error` | 搜尋流程失敗或來源異常 |

---

## 單一來源欄位：`avwiki_*` / `javdb_*`

| 欄位 | 來源 |
|------|------|
| `avwiki_actress_status` / `avwiki_last_search_date` | AV-WIKI-only 搜尋 |
| `javdb_actress_status` / `javdb_last_search_date` | JAVDB-only 搜尋 |

常見值：`found` / `not_found` / `error`。

---

## `search_method`

常見值：`legacy-import` / `AV-WIKI` / `JAVDB` / `cascade`。
這是字串欄位，DB 不做 enum 強制。

---

## `error` / `error_kind`

`error_kind` 目前至少出現：`not_found` / `error` / `timeout` / `stderr` / `json_parse`；可擴充。
通常與 `search_status = "search_error"` 一起寫入。

---

## Backup / Restore

- `db backup-create`：同時產 `backup_<ts>.sqlite` + `backup_<ts>.json`（C1）
  - SQLite 快照透過 `VACUUM INTO` → 失敗 fallback `wal_checkpoint(FULL)` + 檔案複製（`pkg/database/sqlite_backup.go`）
  - JSON 快照由 `SQLiteStore.ExportToJSON` 產生（語意源頭是 SQLite，不是 `data.json`）
- `db backup-restore -backup-path <file>`：依副檔名分支
  - `.sqlite` → `RestoreSQLiteFile`（rollback-safe rename）
  - `.json` → 走 legacy `JSONDatabase.BackupRestore`
- `db backup-restore -from-json <file>`：走 `resync-from-json` 流程
- `db backup-cleanup`：依日期保留策略刪 `backup_<ts>.json`（C1 已知限制：`.sqlite` sibling 暫不一起刪）

---

## Verify / Migrate（runtime SQLite）

| 工具 | 用途 |
|------|------|
| `classifier.exe db verify-sync` | 比對 SQLite 與最近一份 JSON 是否語意一致 |
| `cargo run --manifest-path tools-rs\Cargo.toml -- db-verify --sqlite data\db.sqlite` | 結構檢查：integrity_check / user_version / 必要表 view 存在 |
| `cargo run --manifest-path tools-rs\Cargo.toml -- db-migrate --sqlite data\db.sqlite` | 遷移骨架；同版本 no-op，未來擴充用 |

`db-verify` 與 `db-migrate` 只讀取 SQLite，不改 JSON、不改任何 CLI contract。

---

## 維護注意事項

- schema 異動：請改 `pkg/database/sqlite_schema.sql` 並同步調整：
  - Go：`sqlite_store_test.go::TestSQLiteSchemaSQL_ContainsExpectedV3Markers`、`TestSQLiteStore_InitSchema_CreatesAllTablesAndViews`
  - Rust：`tools-rs/src/v3_schema.rs::V3_REQUIRED_TABLES` / `V3_REQUIRED_VIEWS`
  - Rust：`tools-rs/tests/integration_db_tool.rs::db_verify_*` 測試
- 變更欄位：請對齊 `pkg/database/types.go::VideoData` 與 `src/models/json_types.py`
- 不要再把 `data.json` 視為主資料；若要修改大量資料，請走 `db migrate-from-json` / `db resync-from-json` / `db export-json` 流程

---

## 相關頁面

- [wiki/architecture/go-bridge.md](go-bridge.md)
- [wiki/architecture/go-cli.md](go-cli.md)
- [wiki/architecture/sqlite-shadow-db.md](sqlite-shadow-db.md)（**歷史 / 退役**）

## 相關踩坑

| 踩坑 | 觸發點 |
|------|--------|
| [wails-db-path-wrong-dir](../pitfalls/wails-db-path-wrong-dir.md) ✅ | `resolveConfigPath` 沒往上找專案根，DB 落到 build/bin |
| [wails-db-json-never-updated](../pitfalls/wails-db-json-never-updated.md) ✅ | `BatchSearch` / `ensureDB` 缺 `Compact()` 呼叫（C2 後 compact 為 no-op；此 pitfall 為 JSON 時代歷史紀錄） |
| [wails-db-format-migration](../pitfalls/wails-db-format-migration.md) ✅ | `success` vs `searched_found` 雙值；`SearchStatusSuccess` 常數誤用 |
| [wails-dbonce-no-reset](../pitfalls/wails-dbonce-no-reset.md) ✅ | `sync.Once` 初始化 DB，設定變更後不生效 |
| [wails-cache-status-mismatch](../pitfalls/wails-cache-status-mismatch.md) | 前後端對「已搜尋」的判斷不一致 |
| [python-search-method-field-mismatch](../pitfalls/python-search-method-field-mismatch.md) ✅ | Python 輸出 `method`、Go journal 期望 `search_method` |
