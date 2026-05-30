# 架構參考：契約 / 介面 / 入口（給未來 AI）

> **這份文件是什麼**：女優分類系統 (Actress Classifier) 從 Python 遷移到 Golang 後的**契約 / 介面 / 入口架構地圖**，聚焦「誰呼叫誰、資料怎麼跨語言流動、哪些契約不可破壞、哪裡有陷阱」。
> **與其他文件的關係**：`CLAUDE.md` 是**規則**（你必須遵守的指令），`wiki/architecture/database.md` 是 DB 細節，本檔是**跨子系統的結構總圖**。三者衝突時以 `CLAUDE.md` 為準。
> **產出**：2026-05-30，由 8 路唯讀子系統測繪彙整。**反映 2026-05-30 契約/死碼 remediation 後的當前狀態**。檔案以路徑標示、不含行號（行號會漂移；用符號名 grep）。

---

## 0. TL;DR — 一分鐘心智模型

- **兩個 Go binary，一個 Python 爬蟲層，一個 Rust 工具**：
  - `classifier.exe`（root module，`./cmd/scanner`）= CLI；掃描/移動/操作歷史/SQLite DB 的**唯一寫入入口**。
  - `actress-classifier.exe`（`wails-app/`，**獨立 go module** + `replace`）= GUI 後端（Wails，Go+React）。
  - Python（`src/scrapers/`, `src/services/web_searcher.py`）= **只負責爬蟲搜尋**（AV-WIKI→JAVDB）。
  - `db-tool`（`tools-rs/`，Rust）= 離線匯入/驗證/遷移工具（**非 runtime 寫入路徑**）。
- **runtime = SQLite-only**：source of truth 是 `data/db.sqlite`（`user_version=3`）。`data/json_db/data.json` 只做匯入來源 / 匯出目標 / 備份。
- **跨語言唯一閘門**：Python 非爬蟲層的所有能力（DB/掃描/移動/歷史）一律經 `src/services/go_cli.py` 委派 `classifier.exe`。**禁止 Python fallback、禁止靜默假成功**。
- **schema 單一來源**：`pkg/database/sqlite_schema.sql`，Go `//go:embed` + Rust `include_str!` 共用，四道 drift 測試固定。

---

## 1. 系統大圖與資料流

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 使用者                                                                          │
│   ├── GUI: actress-classifier.exe (Wails)            ├── CLI: classifier.exe   │
│   │     wails-app/backend/app.go (*App bound methods) │     cmd/scanner/*.go    │
│   │                                                   │                         │
│   └──────────────┬────────────────────────┬──────────┴─────────┬──────────────┘
│                  │ subprocess              │ database.NewStore   │ (Python 委派)
│                  ▼ (python -X utf8)        ▼                     ▼
│        ┌───────────────────┐      ┌──────────────────┐   src/services/go_cli.py
│        │ Python 爬蟲層      │      │ pkg/database      │   （subprocess classifier.exe）
│        │ run_search.py      │      │ *SQLiteStore      │◄──────────┘
│        │ run_batch_search.py│      │ NewStore(fail-loud│
│        │ web_searcher.py    │      │   bootstrap)      │
│        │ AV-WIKI → JAVDB    │      │ data/db.sqlite    │
│        └─────────┬─────────┘      └────────┬─────────┘
│                  │ 搜尋結果回寫             │ 讀寫
│                  │ (_GoCLIDB→go_cli /       │
│                  │  Go persistBatchSearch)  ▼
│                  └────────────────►  data/db.sqlite (user_version=3)
│                                      ▲  匯入/匯出/備份（非 runtime 寫）
│                                      │
│   data/json_db/data.json ───────────┘   tools-rs/ db-tool（離線匯入/驗證）
└─────────────────────────────────────────────────────────────────────────────┘
```

**端到端鏈（掃描 → 搜尋 → 分類 → 移動）有兩條路徑**：

| 階段 | GUI 路徑 (Wails) | CLI 路徑 (classifier.exe) |
|---|---|---|
| 掃描 | `App.ScanDirectory` → `pkg/extractor` | `scan` → `app.ScanFiles` → `pkg/extractor` |
| 搜尋 | `App.BatchSearch/PythonSearch` → subprocess `run_*search.py` | （無 CLI 搜尋；搜尋是 GUI/Python 專屬） |
| 寫 DB | **Go 端** `persistBatchSearchResult` → `*SQLiteStore`；單筆由 **Python** `_GoCLIDB`→`go_cli.db_update_video` 回寫 | `db update/...` → `*SQLiteStore` |
| 片商分類 | `App.IdentifyStudio/GetStudiosByCodes` → `pkg/studio` | `identify` → `pkg/studio` |
| 移動落地 | `App.BatchMoveDirs/MoveFile/...` → `pkg/mover`（寫 opLog 支援 rollback） | `move` → `app.MoveFile/MoveDir/BatchMove` → `pkg/mover` |

> ⚠️ **搜尋寫 DB 責任不對稱**：GUI 批次搜尋由 **Go** 直接寫 SQLite；單筆 `PythonSearch`/`run_search.py` 由 **Python** 經 `go_cli` 回寫。不要假設 Python 一律不碰 DB——它經 `go_cli` 委派寫。

---

## 2. 契約邊界總表（最重要）

| 邊界 | 生產端 | 消費端 | 契約載體 | 鎖 |
|---|---|---|---|---|
| **Python → Go CLI** | `src/services/go_cli.py`（組 argv） | `cmd/scanner/*.go`（解析） | argv 子命令+flag、stdout JSON 形狀 | `tests/test_go_cli_contracts.py`（argv 鎖） |
| **Go contracts ↔ mover** | `pkg/mover/types.go` | `pkg/app/*ToContract` → `cmd/scanner` 序列化 | `pkg/contracts/*.go` DTO（json tag） | 同上 + `pkg/app` 對齊測試 |
| **Python 搜尋 → Go (Wails)** | `run_search.py`/`run_batch_search.py`（stdout JSON / JSON Lines） | `app.go` `SearchResult`（`json.Unmarshal`） | `search_method`∥`method` 鍵 | `wails-app/backend/search_result_test.go` |
| **Wails Go ↔ React** | `app.go` `*App` bound methods | `frontend/src/**` + `wailsjs/go/backend/App.d.ts` | Wails 自動產生 bindings（28 個方法） | 改 bound method 要 `wails build` 重生 bindings |
| **Go ↔ Rust schema** | `pkg/database/sqlite_schema.sql`（canonical） | Go `//go:embed` + Rust `include_str!` | `user_version=3`、`V3_SCHEMA_VERSION`==`SQLiteSchemaVersion`==3 | 四道 drift 測試（見 §7） |
| **JSON ↔ SQLite** | `data/json_db/data.json` | `*SQLiteStore` migrate/export/verify + `db-tool` | `DatabaseData` 自由函式（非 `JSONDatabase` 型別） | `verify-sync` + CI 釋出閘 |

---

## 3. 各子系統速覽

### S1 — CLI 入口（`cmd/scanner/`）→ `classifier.exe`
**角色**：把 argv 路由到 6 個頂層子命令，每個 handler 解析 flag → 呼叫 `pkg/*` → stdout JSON 回傳。是 Python 與 GUI 都依賴的穩定對外契約。
- **子命令**：`scan` / `move` / `history` / `db <sub>` / `identify` / `cache <sub>` / `help`。
- **`db` 子路由**（`db_cmd.go`）：特殊子命令（`fix-studios`/`merge`/`migrate-from-json`/`verify-sync`/`resync-from-json`/`export-json`）各有獨立 FlagSet；其餘走 `dbHandlers` map（`get`/`update`/`delete`/`list`/`stats`/`compact`/`actress-get`/`actress-update`/`actress-delete`/`actress-list`/`clean-actresses`/`backup-create`/`backup-restore`/`backup-list`/`backup-cleanup`）。
- **輸出契約**：成功一律 stdout `json.MarshalIndent`（兩空格）；所有錯誤/狀態提示走 stderr。exit code：一般錯誤 `1`、FlagSet 解析失敗 `2`、`verify-sync` 不一致 `1`。
- **不可違反**：`backup-*` 四個名稱固定（禁止 `db backup`/`db restore`/`db sync` 別名）；`db stats` 保留 `journal_size`/`needs_compact`/`dirty_videos`/`sync_degraded_total`/`sqlite_read_fallback_total` 等 zero/false 鍵；`db delete`/`actress-delete` 先做存在性檢查讓非零 exit 推回 `False`。

### S2 — Python→Go 橋（`src/services/go_cli.py`）
**角色**：Python 非爬蟲層呼叫 `classifier.exe` 的**唯一薄包裝層**。
- **入口**：`run()`（唯一跑 subprocess 的點）、`is_available()`、`_resolve_exe()`，加上 `scan`/`identify`/`db_*`/`cache_*`/`move_*`/`history` 各系列 wrapper（約 30 個）。
- **錯誤語意**：`GoError`（非零退出/JSON 解析失敗/timeout）、`GoNotFoundError`（exe 不存在）；`_is_not_found_error()` 靠 Go stderr 英文子字串 `"not found"` 把「資料不存在」轉成 `None`/`False`。
- **不可違反**：argv 必與 S1 一致；`data_dir==data/json_db` 時省略 `-data-dir`（交給 §7.1 sibling 規則）；傳 dict/list 一律先寫 `NamedTemporaryFile(.json)` 再傳路徑（WSL+.exe 走 `wslpath -w`）。
- **委派層定位**：`json_database.py`(`JSONDBManager`) / `incremental_json_database.py`(`IncrementalJSONDB`) 是**生產死碼、刻意保留為測試 fixture**（docstring 已標「非 runtime store」），CRUD 全委派 `go_cli.db_*`。
- **陷阱**：`list_operations` 的 `-limit` 在 Go 端不存在（Go 硬寫 `0`）；`run()` type hint 標 dict 但可能回 list（消費端靠 `isinstance` 分流）；`_resolve_exe` 用模組級快取，測試切 exe 要 reset。

### S3 — Go contracts + app 服務（`pkg/contracts/`, `pkg/app/`）
**角色**：`pkg/contracts` 定義對外 JSON DTO；`pkg/app` 包住 `pkg/mover`/`pkg/extractor` 內部型別並**手寫**轉成 `contracts.*` 交給 `cmd/scanner` 序列化。
- **入口**：`app.ScanFiles` / `MoveFile` / `MoveDir` / `BatchMove` / `BatchMoveStdin` / `ListOperations` / `ShowOperation` / `Rollback`。
- **DTO**：`ScanResult` / `MoveItem` / `MoveResult` / `MergeResult`（含 `files_skipped`）/ `BatchResult` / `OperationLog`。
- **已知 interface 風險**：`contracts.*` 與 `pkg/mover/types.go` 是**兩套 byte-identical 的平行 DTO**，靠 `pkg/app` 手寫 `*ToContract` 橋接。**改 DTO 欄位要動四處**：`pkg/contracts/*.go` + `pkg/mover/types.go` + `pkg/app` 轉換函式 + `tests/test_go_cli_contracts.py`——漏任一處不會編譯失敗。
- **陷阱**：`parseStrategy` 只收 `skip/overwrite/rename`（`merge` 常數存在但 app 層不接受）；`OnConflict` 在 contracts 是 string、mover 是 enum，`toMoverItems` 直接 cast 不驗證。

### S4 — Wails backend（`wails-app/backend/`）→ `actress-classifier.exe`
**角色**：把掃描/搬移/Python 搜尋/SQLite 查詢/設定/片商以 `*App` bound methods 暴露給 React。**獨立 go module**（`replace actress-classifier => ../`）。
- **入口**：28 個 bound methods（`ScanDirectory`/`BatchMoveDirs`/`CheckDirConflicts`/`MoveFile`/`BatchMove`/`RollbackOperation`/`ListOperations`/`GetOperation`/`DbGetVideo`/`IdentifyStudio`/`GetPreferences`/`PythonSearch`/`BatchSearch`/`BatchSearchAVWiki`/`BatchSearchJAVDB`/`GetActressPrimaryStudios`/...）；`ConfigService.Load/Save/Reset`。
- **runtime DB**：一律 `database.NewStore(StoreConfig{DataDir})` → `*SQLiteStore`；`ensureDB` 用 `dbMu` 保護，偵測 `data.json` mtime 變動會 `Close` 舊 store 重開（Windows SQLite 獨佔 handle）。
- **搜尋**：`SearchResult.UnmarshalJSON` 接受 `search_method`∥`method`（marshal 仍出 `method`，前端不變）；Python 子程序一律 `python -X utf8` + `PYTHONUTF8=1` + `hideWindow`。
- **陷阱**：`DbListVideos`/`DbUpdateVideo` 已於 2026-05-30 刪除（只剩 `DbGetVideo`）——**勿照舊文件加回**；`proc_windows.go` 無 `//go:build` 標頭、靠 `_windows.go` 檔名約束 GOOS（搬檔會破壞 Linux CI）；`wails-app` 要在 `wails-app/` 下 `go test ./backend`（root `go test ./pkg/...` 不涵蓋）。

### S5 — Runtime SQLite store（`pkg/database/`）
**角色**：`classifier.exe` 與 Wails 共用的 runtime 資料層，SQLite-only。
- **入口**：`NewStore(StoreConfig)`（**唯一開店入口** + fail-loud bootstrap）、`OpenSQLiteStore`、`ResolveDataDirPaths`、`MigrateFromJSON`/`ResyncFromJSON`/`VerifySync`/`ExportToJSON`、CRUD（`AddVideo`/`UpdateVideo`/`UpdateVideoFields`/`GetStats`/`Merge*`/`Backup*`）。
- **型別**：`VideoData`(alias `Video`) / `ActressData` / `DatabaseData`(alias `JSONDatabaseRoot`) / `VideoActressLink` / `MigrationReport` / `VerifyReport` / `BackupResult`。
- **不可違反**：bootstrap fail-loud（空 SQLite + 有 `data.json` 時匯入失敗一律 close+error，不退化成空 store）；**§7.1 sibling 規則**（預設 `-data-dir data/json_db` → SQLite 落 sibling `data/db.sqlite`，自訂 path → `<path>/db.sqlite`）；`legacy_video_actress_links` 是 `root.links[]` 的 ordinal 快照（含 orphan，無 FK）；`StableActressID` = `auto_` + SHA-1[:16]（僅 TrimSpace，改演算法會使既有 id 失效）。
- **陷阱**：`JSONDatabase`(`jsondb.go`/`journal.go`) 是**刻意保留的測試 fixture，非 runtime**（docstring 已標）；`SQLiteStore.Save()`/`CompactJournal()` 已刪（只剩 `Compact()`/`CompactIfNeeded()` no-op）——但 `JSONDatabase` 仍有 `Save/CompactJournal`，那是 fixture，勿照抄到 `SQLiteStore`；`RestoreSQLiteFile` 前必須先 `Close()`（Windows rename）。

### S6 — Python 搜尋管線（`src/scrapers/`, `src/services/web_searcher.py`）
**角色**：GUI 經 subprocess 呼叫的**純爬蟲層**；非爬蟲的 DB/cache 一律委派 `classifier.exe`。
- **入口**：`run_search.py <code> [source_mode]`（stdout 單行 JSON）、`run_batch_search.py`（stdin JSON `{codes,workers,source_mode}` → stdout JSON Lines）、`WebSearcher.search_info`（級聯）。
- **不可違反**：搜尋順序固定 **AV-WIKI → JAVDB**；輸出鍵 `search_method`，值來源優先序 `raw['search_method']∥['method']∥['source']`；`source_mode` 三終值 `cascade`/`avwiki`/`javdb`（Go 端常數 `batchSearchSourceAVWiki='avwiki'` 等須對齊）；source-status 寫入走 `_GoCLIDB`→`go_cli`（Python 不直接寫 `data.json`/`db.sqlite`）。
- **陷阱**：`ShiroutoWikiScraper` 在 `__init__` 被實例化但 `search_info` 不呼叫它（保留屬性）；`AVWikiScraper`/`JAVDBScraper`(aiohttp) 與 `WebSearcher`/`SafeJAVDBSearcher`(httpx/curl_cffi) 是**兩套並存**抓取實作，live 路徑走後者；`rate_limiter.py`/`unified_cache.py` 在 live 路徑幾乎不被呼叫（各 searcher 自己退避/各自快取）。

### S7 — Rust db-tool（`tools-rs/`，binary 名 `db-tool`）
**角色**：離線匯入/驗證/遷移工具，與兩支 Go binary 完全分離（**非 runtime 寫入路徑**）。
- **生效 (v3)**：`db-import-json-v3`（all-or-nothing tx）/ `db-verify`（READ_ONLY，缺檔不建）/ `db-migrate`（v3→v3 骨架，僅回 not-implemented）。
- **legacy (v2 shadow)**：`db-init`/`db-stats`/`db-compare-json`/`db-benchmark`/`query`（對 `data/shadow.sqlite`，`SCHEMA_VERSION=2`）；`db-import-json` **deprecated**（stderr 印 warning）。
- **不可違反**：schema 共用 `include_str!("../../pkg/database/sqlite_schema.sql")`，`V3_SCHEMA_VERSION==3`；四道 drift 測試；v2/v3 是兩個獨立 schema 世界（v2 的 `videos` 表 ≠ v3 的）。
- **陷阱**：CLI 子命令名由 clap 從 enum variant 自動 kebab 化（改 variant 名會改 CLI 介面）；`V3_SCHEMA_SQL`/`apply_v3_schema` 標 `#[allow(dead_code)]`（runtime 用 Go 的 `InitSchema`，Rust 這份只供測試/import/migrate 骨架）；`tools-rs/target/` 下的 `.rs` 是 build artifact 非來源。

---

## 4. 不可違反的契約（consolidated invariants）

> 改動下列任一項前，先確認沒有違反。多數有測試/CI 鎖。

1. **DB 寫入唯一入口**：runtime 寫入只經 `*SQLiteStore`（GUI/Wails）或 `classifier.exe db ...`（CLI/Python 委派）。**`data/db.sqlite` 與 `data/json_db/data.json` 都不可手改。**
2. **Go-only 邊界**：DB/掃描/搬移/操作歷史一律經 `src/services/go_cli.py` 委派；不得新增 Python fallback；Go CLI 不可用須明確報錯，不得靜默假成功。
3. **爬蟲層 Python-first 例外**：`src/scrapers/` 保留 Python；搜尋順序固定 AV-WIKI → JAVDB。
4. **Bootstrap fail-loud**：`NewStore` 在空 SQLite + 有 `data.json` 時 bootstrap 必跑必成功，失敗 close+error，不退化成空 store。
5. **JSON 角色限定**：`data.json` 只做匯入來源/匯出目標/備份；runtime 不寫 JSON、無 journal replay。
6. **schema 單一來源**：`pkg/database/sqlite_schema.sql`；`user_version=3`，Go/Rust 版本常數都是 3；四道 drift 測試。
7. **backup-* 名稱固定**：`db backup-create/backup-list/backup-restore/backup-cleanup`，禁止別名。
8. **`db stats` 保留欄位**：`journal_size`/`needs_compact`/`dirty_videos`/`sync_degraded_total`/`sqlite_read_fallback_total` 等 zero/false 鍵（Python helper 依賴）。
9. **`§7.1` sibling 規則**：預設 `data/json_db` → sibling `data/db.sqlite`。
10. **搜尋 method 雙鍵相容**：Python 出 `search_method`，Go `UnmarshalJSON` 接受 `search_method`∥`method`。
11. **DTO 四處同步**：改 move/scan/history DTO 要同時改 `contracts` + `mover` + `pkg/app` 轉換 + 契約鎖測試。
12. **跨平台檔名約束**：`*_windows.go` / `*_other.go`（`//go:build !windows`）的 GOOS 分離不可破壞。

---

## 5. 死碼 vs 測試 fixture 地圖（2026-05-30 後）

| 對象 | 狀態 | 說明 |
|---|---|---|
| `pkg/database/jsondb.go`, `journal.go`（`JSONDatabase` 型別） | 🔒 **保留為測試 fixture** | 生產零呼叫，但 CLAUDE.md 明文保留；共享 fixture `setupTestDB`/`loadedJSONDB`/`seededJSONDB` 被眾多測試依賴。**勿當 runtime store**。 |
| Python `JSONDBManager`/`IncrementalJSONDB` | 🔒 **保留為測試 fixture** | 同上（使用者 2026-05-30 決定）；docstring 已標「非 runtime store」。 |
| `pkg/database/db_helpers.go` | ✅ live | `JSONDatabase` 旁的 package-level helper（merge/backup/欄位更新/主要片商）被 `SQLiteStore` 依賴。 |
| `SQLiteStore.Save()` / `CompactJournal()` | ❌ **已刪** | 真死碼（零呼叫）；`Compact()`/`CompactIfNeeded()` no-op 保留（wails 呼叫）。 |
| wails `DbListVideos`/`DbUpdateVideo` | ❌ **已刪** | 前端零呼叫；只剩 `DbGetVideo`。 |
| `pkg/cache` `New`/`CleanupExpired`/`CleanupBySize`/`Exists`/`DefaultPruneConfig` | ❌ **已刪** | live 的 `AutoCleanup`/`Get`/`Set`/`Delete`/`Stats`/`Clear` 保留。 |
| Python `UnifiedFileScanner`(scanner.py)、`WebSearcher` 4 cascade 孤兒方法、`tools/studio_updates/` | ❌ **已刪** | src/ 生產零呼叫。 |
| Rust `sqlite_db.rs`/`json_db.rs`（v2 shadow）、`scripts/db-sync.*` | 🟡 legacy 保留 | 已加退役註解；非 runtime 路徑。 |
| `database.NewVideo`/`Mover.BatchMoveDirs`/`Mover.GetOperation` | ⚠️ **勿誤刪** | 從 `cmd/scanner` 看似死碼，實為 **wails GUI 活路徑**（雙 binary 假陽性）。 |

> **雙 binary 陷阱**：`pkg/database`/`pkg/mover`/`pkg/cache` 被 `classifier.exe` 與 `actress-classifier.exe`（獨立 module）共同消費。單一入口的 `deadcode` 對「另一 binary 才用的函數」會假陽性。**刪任何 Go 函數前一律 grep 兩個 module 的生產碼 + 前端 bindings。**

---

## 6. 驗證閘

**CI workflows**（`.github/workflows/`）：
| workflow | 觸發 | 內容 |
|---|---|---|
| `go-lint.yml` | `**/*.go` 等 | `golangci-lint@latest`（未釘版，linter 升級可能無關紅）+ test |
| `python-test.yml` | Python | pytest |
| `integration-test.yml` | Go+Python | 跨語言整合（含 migrate-from-json+verify-sync on tmp） |
| `sqlite-verify-sync.yml` | `pkg/database/**`/`cmd/scanner/**`/fixtures | **釋出閘**：build → `db migrate-from-json` → `db verify-sync`（非零 exit 擋 PR） |
| `rust.yml` | `tools-rs/**` | **`cargo fmt --check` + `cargo clippy -- -D warnings` + `cargo test`**（三步；只 `cargo test` 會漏 fmt/clippy） |
| `sonar.yml` | push | SonarCloud |
| `copilot-refactor-go.yml` | `workflow_dispatch`（排程已暫停） | **暫停的手動 Copilot 實驗，非 CI gate，可忽略其紅燈** |

**本機全域驗證**：
```powershell
go build ./... ; go vet ./... ; go test ./... -count=1                       # root
cd wails-app; go build ./...; go test ./backend/... -count=1; cd ..           # wails（獨立 module）
cargo fmt --manifest-path tools-rs\Cargo.toml --check                         # Rust 三步（缺一不可）
cargo clippy --manifest-path tools-rs\Cargo.toml -- -D warnings
cargo test --manifest-path tools-rs\Cargo.toml
python -m pytest tests\ -q -p no:cacheprovider                               # Python
go build -o classifier.exe .\cmd\scanner                                     # CI 釋出閘（注意：別對真 fixture 跑會污染）
```
schema 改動必跑四道 drift 鎖：`TestSQLiteSchemaSQL_MatchesCanonicalFile`（Go）、`embedded_schema_matches_canonical_file_on_disk`（Rust lib）、`embedded_v3_schema_matches_canonical_go_package_file` 與 `db_verify_*`（Rust 整合）。

---

## 7. 給未來 AI 的高頻陷阱索引

1. **雙 binary 假陽性**：`deadcode ./cmd/scanner` 會把 wails-only 函數誤報為死碼。永遠 grep 兩個 module。
2. **`§7.1` 反直覺**：預設 `data/json_db` 的 SQLite 在 **sibling** `data/db.sqlite`；`NewStore(StoreConfig{})` 空 DataDir 會 fallback 到 `DefaultDataDir` 而非 cwd。
3. **改 DTO 漏同步**：`contracts`/`mover`/`pkg/app`/契約鎖四處要一起改，漏了不會編譯失敗、會默默丟欄位。
4. **wails 是獨立 module**：`root go test ./...` 不涵蓋 `wails-app/`；改 bound method 要 `wails build` 重生 bindings。
5. **Rust CI 三步**：動 `tools-rs/**` 後 `cargo fmt --check` 會抓到**整個 crate**的既有 fmt 違規（不限你改的檔），只跑 `cargo test` 會漏。
6. **fixture 污染**：別對真 `tests/fixtures/json_db_minimal/` 跑 `migrate-from-json`（會留下 `db.sqlite` 被整合測試 copy 進去而紅）；整合測試自己在 tmp 跑。
7. **不要把 `JSONDatabase`/`JSONDBManager`/`IncrementalJSONDB` 當 runtime**：它們是刻意保留的測試 fixture；runtime 一律 `*SQLiteStore` / `classifier.exe db`。
8. **not-found 語意脆弱**：`go_cli._is_not_found_error` 靠 Go stderr 英文 `"not found"` 子字串；Go 改措辭會讓 `db_get/delete_*` 把「資料不存在」誤判成真錯誤。
9. **搜尋 method 鍵**：Python 出 `search_method`、Go 讀 `search_method`∥`method`、前端讀 `.method`；三方任一改動要全鏈檢查。
10. **`db stats` zero 欄位是契約**：別當冗餘刪掉，Python helper 依賴。

---

*本檔由 8 路唯讀子系統測繪彙整（2026-05-30）。各子系統的完整 entry-point 簽章、key types、invariants 與 gotchas 細節可重跑測繪取得；本檔為導覽層。權威規則仍以 `CLAUDE.md` 為準。*
