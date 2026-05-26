# SQLite 主資料庫遷移 — Implementation Plan

> 建立：2026-05-23（slice 拆細版）
> Spec 來源：`docs/superpowers/specs/2026-05-23-sqlite-migration-design.md`
> 範圍：把 JSON DB（`data/json_db/data.json` + journal + index）為 source of truth 的現況，遷移為 SQLite（`data/db.sqlite`）為 source of truth；shadow DB 同時退役。

本計畫**只描述步驟與驗收**，不含程式碼。實作時請對照 spec 的 schema 與 API 草案。

高階保持 Phase A/B/C 三階段；每階段拆成更小的 execution slice，方便小 PR、TDD、review 與 rollback。

---

## 共通假設與環境

- 主要 SQLite driver：`modernc.org/sqlite`（純 Go，無 CGo），透過 `database/sql` 標準介面包裝。
- 既有 build pipeline 不動：`go build -o classifier.exe .\cmd\scanner` 與 `wails build` 均不需引入 CGo。
- 既有 CLI 契約沿用，禁止取代名稱（spec § 5.2）：
  - `db get` / `db update` / `db list` / `db stats`
  - `db backup-create`（**不是** `db backup`）
  - `db backup-list`
  - `db backup-restore -backup-path <file>`（**不是** `db restore`）
  - `db backup-cleanup`
  - `db clean-actresses`
  - `db compact -json`
- `-data-dir` 旗標保留並採 compatibility lookup（spec § 7.1）：預設 `data/json_db` → `data/db.sqlite`；自訂 `<path>` → `<path>/db.sqlite`；不在 `data/json_db/` 下建 `db.sqlite`；`filepath.Clean` 後比對絕對路徑。

---

## Slice 總覽

| Phase | Slice | 標題 | 大略時程 |
|-------|-------|------|---------|
| A | A0 | 契約鎖定（lock current behavior with tests） | 2–3 天 |
| A | A1 | SQLite schema + offline migration | 3–5 天 |
| A | A2 | resync / export round-trip | 3–4 天 |
| A | A3 | DualWrite runtime | 5–7 天 |
| B | B1 | SQLite read path for CLI | 2–3 天 |
| B | B2 | Wails backend read flip | 2–3 天 |
| C | C1 | Backup / export / restore 完整化 | 3–5 天 |
| C | C2 | SQLite-only runtime | 2–3 天 |
| C | C3 | 文件與 Rust db-tool 重定位 | 2–4 天 |

時程僅供參考；每個 slice 各自小 PR，可在 dogfood 期內並行 review。

---

# Phase A — 雙寫上線

## Slice A0 — 契約鎖定

### 目標

在引入 SQLite 之前，先用測試把既有 JSON DB 行為與 CLI 契約鎖住。後續任何 Phase 的修改都必須通過這些測試。

### 受影響檔案

**新增**

- `pkg/database/data_dir_lookup.go` — `-data-dir` 解析 helper（Phase A0 只實作 JSON 端：`<path>` → `<path>/data.json` + `data.journal` + `data.index`，尚未對映 SQLite）
- `pkg/database/data_dir_lookup_test.go`
- `tests/fixtures/json_db_minimal/data.json`（CI fixture，2–3 筆 video + actress + link）

**修改**

- `tests/test_go_cli_contracts.py` — 補強為每個 db 子命令的 happy path JSON 回傳格式都有 case（特別補 `db compact -json` 既有回傳含 `journal_size` / `needs_compact` 欄位的 case，為 Phase C no-op 預鋪）

### TDD 策略

採嚴格 TDD（`data_dir_lookup` 為新檔；CLI contract tests 屬 characterization，但仍先寫測試再補洞）。

**先寫哪些測試**：

- `data_dir_lookup_test.go`
  - 預設 `data/json_db` 解析
  - 自訂路徑解析（如 `D:\custom\db_dir`）
  - 不存在路徑（解析應仍回 Path 結構，由 caller 判斷是否存在）
  - 相對 vs 絕對路徑經 `filepath.Clean` 後一致
- `test_go_cli_contracts.py`
  - 每個 db 子命令的 happy path JSON 回傳 key 存在性
  - `db compact -json` 既有完整回傳格式（journal_size / needs_compact / dirty_videos 等）

### 主要步驟

1. 列舉現有 `cmd/scanner/db_cmd.go` 與 `src/services/go_cli.py` 內的所有 db 子命令
2. 為每個子命令在 `tests/test_go_cli_contracts.py` 補 happy-path JSON 回傳格式測試
3. 寫 `data_dir_lookup_test.go`（先紅）
4. 實作 `data_dir_lookup.go`（JSON 端解析，**尚不**動 SQLite 對映）
5. 跑全套測試確認綠
6. 建立 `tests/fixtures/json_db_minimal/data.json`（後續 slice CI 用）

### 驗證命令

```powershell
go test .\pkg\database -v
go test .\cmd\scanner -v
python -m pytest tests\test_go_cli_contracts.py tests\test_incremental_db.py tests\test_json_database.py -v -p no:cacheprovider
```

### Rollback / Stop gate

- 本 slice 只加測試與一個新 helper 檔，不影響 runtime；rollback = 還原新增檔
- 若新測試發現現有 CLI 回傳與 spec § 7.1 描述不一致 → 暫停，回去改 spec 或補 CLI 行為（兩者擇一，**不**繞過測試）

### 不做事項

- 不引入 SQLite 任何依賴（`go.mod` 不動）
- 不改既有 runtime 行為
- 不動 Python 端 helper 邏輯（只加測試覆蓋）
- 不動 Wails

### 完成條件

1. 新測試全綠
2. 既有測試 100% 仍綠
3. spec § 7.1 契約表的每一項在測試套件中有對應 case
4. `tests/fixtures/json_db_minimal/data.json` 建立

---

## Slice A1 — SQLite schema + offline migration

### 目標

加 SQLite 依賴與 schema；新增離線 CLI `db migrate-from-json` 與 `db verify-sync`。不接 runtime 寫入、不接 Wails。

### 受影響檔案

**新增**

- `pkg/database/sqlite_schema.sql` — embedded schema；**Phase A 只由 Go embed**，Rust 共用留到 C3
- `pkg/database/sqlite_store.go` — 最小 SQLiteStore（`Open` / `InitSchema` / `Close`；CRUD 留到 A3 補）
- `pkg/database/sqlite_store_test.go`
- `cmd/scanner/db_cmd.go` 內新增 `migrate-from-json` 與 `verify-sync` 兩個子命令（**或**視實作膨脹拆出 `db_cmd_migrate.go` / `db_cmd_verify.go`；不為拆而拆）
- `cmd/scanner/main_test.go` 內補 case，或新增 `cmd/scanner/db_cmd_migrate_test.go` / `db_cmd_verify_test.go`

**修改**

- `pkg/database/data_dir_lookup.go` — 補 SQLite 端 compatibility lookup（spec § 7.1）
- `pkg/database/data_dir_lookup_test.go` — 補 SQLite 路徑 case
- `go.mod` / `go.sum` — 加 `modernc.org/sqlite`
- `.github/workflows/`（CI yml）— 在現有測試後加 4 步序列（見「驗證命令」）

### TDD 策略

採嚴格 TDD（`migrate-from-json` / `verify-sync` / `data_dir_lookup` SQLite 補丁皆新邏輯）。

**先寫哪些測試**：

- `sqlite_store_test.go`
  - 開啟新檔、`InitSchema` 建表、`PRAGMA user_version = 3`
  - 開啟既有 v3 檔不重 init
  - 開啟 v1/v2 檔 fail loudly（除非顯式 replace flag）
- `data_dir_lookup_test.go`（補）
  - 預設 `data/json_db` → 對映到 `data/db.sqlite`（**不是** `data/json_db/db.sqlite`）
  - 自訂 `<path>` → `<path>/db.sqlite`
  - `filepath.Clean` 正規化後絕對路徑比對
- `cmd/scanner` 測試（migrate-from-json）
  - fixture 帶 2 video + 2 actress + 2 link → migrate 成功，輸出 report JSON
  - fixture 帶未對齊 actress（`videos[].actresses` 有名字但 `actresses{}` 缺）→ 預設 fail loudly + 列 unresolved
  - 加 `--auto-create-missing-actresses` → 自動建 `auto_<sha1>` entity，列 auto_created
  - fixture 帶同 video 重複 actress → fail loudly + 列 (video_code, actress_name, ordinals)
- `cmd/scanner` 測試（verify-sync）
  - migrate 後立即 verify → `{"consistent":true,...}` exit 0
  - 手動改 SQLite（漏一筆 video）→ exit 非 0 + `diffs` 列出
  - 兩邊 `data_hash` 不同 → verify 忽略（不列入 diffs）
  - 兩邊 `updated_at` 秒級差異 → verify 忽略

### 主要步驟

1. `go get modernc.org/sqlite`；確認 `go build` 與 `wails build` 仍為純 Go
2. 寫 `sqlite_schema.sql`（依 spec § 2 的 4 個表 + 3 個 view，schema_version 寫死為 3）
3. 寫 `sqlite_store_test.go`（先紅）
4. 實作 `pkg/database/sqlite_store.go` 最小版（`Open` / `InitSchema` / `Close` / `SchemaVersion()`）
5. 寫 `data_dir_lookup_test.go` SQLite 補測（先紅）
6. 實作 `data_dir_lookup.go` SQLite 端 compatibility lookup
7. 寫 `cmd/scanner` migrate-from-json 測試（先紅）
8. 實作 `db migrate-from-json`：Pass 1 (actresses) → Pass 2 (videos[].actresses → links，預設嚴格) → Pass 3 (JSON.links 覆寫)；`--auto-create-missing-actresses` flag；輸出 migration report JSON
9. 寫 `cmd/scanner` verify-sync 測試（先紅）
10. 實作 `db verify-sync` 依 spec § 4.2 規則
11. CI yml 加 4 步序列

### 驗證命令

```powershell
go test .\pkg\database -v
go test .\cmd\scanner -v

# CI 4 步序列
go build -o classifier.exe .\cmd\scanner
.\classifier.exe db migrate-from-json -source tests\fixtures\json_db_minimal\data.json -data-dir tests\fixtures\json_db_minimal
.\classifier.exe db verify-sync -data-dir tests\fixtures\json_db_minimal
# 預期：exit 0、{"consistent":true,...}

# 真實資料 smoke（journal 為空時）
.\classifier.exe db migrate-from-json -source data\json_db\data.json
.\classifier.exe db verify-sync
```

### Rollback / Stop gate

- 本 slice 仍是離線指令，未動 runtime；rollback = 移除 SQLite 相關新檔 + `go.mod` entry
- migrate 在真實資料 fail loudly 大量 unresolved → 跑 `db clean-actresses` 後重試，或審查報告後啟用 auto-create flag
- modernc.org/sqlite 在 Windows 編譯失敗 → 暫停評估 `mattn/go-sqlite3`（需 CGo + gcc）

### 不做事項

- 不寫入 runtime 路徑（migrate 是離線指令）
- 不抽 `DatabaseStore` interface（延到 A3）
- 不動 Wails / Python helper
- 不動 backup/restore / compact CLI
- Rust db-tool 不動

### 完成條件

1. 所有 A1 新測試綠
2. CI 4 步序列在 fixture 上通過
3. 真實 `data/json_db/data.json`（journal 為空時）migrate + verify-sync 通過
4. `go build` / `wails build` 仍為純 Go

---

## Slice A2 — resync / export round-trip

### 目標

加 `db resync-from-json` 與 `db export-json`；驗證 JSON → SQLite → JSON 語意等價。仍不接 runtime 寫入。

### 受影響檔案

**新增**

- `pkg/database/export_json.go` — SQLite → JSON 匯出邏輯（用 statistics views 填回）
- `pkg/database/export_json_test.go`
- `cmd/scanner/db_cmd.go` 新增 `resync-from-json` 與 `export-json` 兩個子命令（或拆檔；視實作）
- 對應 `cmd/scanner` 測試

**修改**

- `pkg/database/sqlite_store.go` — 加 bulk DELETE + INSERT 的 `Resync()` 方法
- `pkg/database/sqlite_store_test.go` — 補 view query 測試（actress_video_counts / studio_statistics / enhanced_actress_studio_statistics）

### TDD 策略

採嚴格 TDD。

**先寫哪些測試**：

- `resync-from-json`
  - 空 SQLite + 有 JSON → resync 成功
  - 有 SQLite（不同內容）+ JSON → resync 後 SQLite 內容 = JSON
  - resync 中斷（如 JSON 不存在）→ transaction rollback，SQLite 維持原狀
- `export-json`
  - 給定 SQLite → 產出符合 JSON DB schema 的檔
  - `actresses[].video_count` 從 `actress_video_counts` view 算
  - `statistics.actress_statistics` 從 `actress_video_counts` 算（spec § 2.5）
  - `statistics.studio_statistics` 與 `enhanced_actress_studio_statistics` 從對應 view 算
  - `statistics.computed_at` 為當下 RFC3339
  - `data_hash` 即時計算寫入 JSON 輸出，**不**回填 SQLite（spec § 4.2）
  - 根層 `metadata.description` / `encoding` / `schema_version` 從 `db_meta` 讀
- Round-trip
  - JSON A → migrate → SQLite → export → JSON B；A 與 B 語意等價（容許 `updated_at` 秒級差異與 `data_hash` 差異）

### 主要步驟

1. 寫 `resync-from-json` 測試（先紅）
2. 實作 `SQLiteStore.Resync()`：1 個 transaction 內 DELETE 全表 + bulk INSERT
3. 寫 `cmd/scanner` resync 子命令測試
4. 實作 `db resync-from-json` 子命令
5. 寫 `export_json_test.go`（先紅）
6. 實作 `pkg/database/export_json.go`：依 spec § 2.1 / § 2.5 / § 4.2 規則
7. 寫 `cmd/scanner` export 子命令測試
8. 實作 `db export-json` 子命令（含 `-output <path>` 旗標）
9. 寫 round-trip 整合測試（A → SQLite → B 語意比對）

### 驗證命令

```powershell
go test .\pkg\database -v
go test .\cmd\scanner -v

# Round-trip with fixture
.\classifier.exe db migrate-from-json -source tests\fixtures\json_db_minimal\data.json -data-dir tests\fixtures\json_db_minimal
.\classifier.exe db export-json -output tests\fixtures\json_db_minimal\data.export.json
# 語意比對由 Go round-trip 測試或 Python 簡易腳本完成

# Round-trip with real data
.\classifier.exe db migrate-from-json -source data\json_db\data.json
.\classifier.exe db export-json -output data\json_db\data.roundtrip.json
```

### Rollback / Stop gate

- 仍是離線指令；rollback = 移除 export / resync 相關檔
- round-trip 不等價 → 暫停，分析差異（可能是 view SQL 錯、actress 順序差異、`data_hash` 演算法錯）；**不**將語意差異視為可忽略

### 不做事項

- 不接 runtime 寫入
- 不動 backup/restore CLI（仍 JSON 備份）
- 不動 Python / Wails / Rust db-tool

### 完成條件

1. round-trip 測試在 fixture 與真實 `data/json_db/data.json` 上通過
2. `db export-json` 輸出與最後一份 `data.json` 語意等價（容許 timestamp 與 `data_hash` 差異）
3. `db resync-from-json` 可從 JSON 重灌 SQLite，後續 verify-sync 通過

---

## Slice A3 — DualWrite runtime

### 目標

抽 `DatabaseStore` interface；包既有 JSON DB 進入點為 `JSONStore`；加 `DualWriteStore`、degraded log、replay；runtime 寫入雙寫；**讀仍走 JSON**。

### 受影響檔案

**新增**

- `pkg/database/store.go` — `DatabaseStore` interface（spec § 7.3 草案）+ `StoreConfig` + `NewStore()`
- `pkg/database/json_store.go` — JSONStore wrapper（包既有 JSON DB 邏輯）
- `pkg/database/dual_write_store.go` — DualWriteStore（協調寫入順序）
- `pkg/database/dual_write_replay.go` — degraded log replay（啟動同步、寫入後背景）
- 對應 `*_test.go`

**修改**

- `pkg/database/sqlite_store.go` — 補 runtime 寫入方法（`GetVideo` / `UpdateVideo` / `DeleteVideo` / `AddLink` / `GetActress` / `UpdateActress` / `GetAllVideos` / `GetStats` 等，依 spec § 7.3 草案）；`QueryVideos` 可先回 `ErrNotImplemented`
- 既有 `pkg/database/manager.go` 或 JSON DB 進入點 — 改為透過 `DatabaseStore` interface 出口
- `cmd/scanner/main.go` — 註冊 `DualWriteStore` 為主 store；保留 `ModeJSONOnly` 透過 env flag（如 `ACTRESS_DB_MODE=json_only`）作為 rollback
- `wails-app/backend/app.go` — 改用 `NewStore(StoreConfig{Mode: ModeDualWrite, ...})`

### TDD 策略

**混合**：

- DualWriteStore 寫入順序、degraded log / replay 規則 → **TDD**（新邏輯）
- JSONStore 包既有邏輯 → **characterization**（既有測試應該繼續綠，不硬套 TDD）
- cmd/scanner main 接線、Wails backend 接線 → **characterization**

**先寫哪些測試**：

- `dual_write_store_test.go`
  - JSON 寫成功 + SQLite 寫成功 → return nil，無 degraded
  - JSON 寫失敗 → 整筆 error，**不**嘗試寫 SQLite
  - JSON 寫成功 + SQLite 寫失敗 → return nil（不阻擋整筆），degraded log 加一行，`sync_degraded_total` 計數遞增
  - 連續多筆寫入順序保留
- `dual_write_replay_test.go`
  - 啟動時讀 degraded log，replay 每筆，成功則移除
  - 寫入後背景 goroutine replay（測時用同步包裝 + channel 確認）
  - 寫入前 `os.Stat` log size > 32 KiB → log.Warn，**不** block
  - degraded log 為空時自動刪檔
- `json_store_test.go` — characterization：對既有 JSON DB 行為 1:1 包裝，所有既有 `tests/test_json_database.py` / `test_incremental_db.py` 對應的 case 都該轉接過來
- 接線 characterization
  - cmd/scanner 切到 DualWrite 後，A0 的 contract tests 仍全綠
  - Wails backend `app_test.go` 既有 case 仍全綠

### 主要步驟

1. 抽 `DatabaseStore` interface（spec § 7.3 草案）；建 `StoreConfig` + `NewStore`
2. 寫 JSONStore wrapper（先包既有邏輯，**不**改行為）
3. 跑所有既有測試確認沒 regression（**characterization gate** — 任何 regression 都停下）
4. 補 SQLiteStore 的 runtime 寫入方法（依 spec § 7.3）；單元測試
5. 寫 `dual_write_store_test.go`（先紅）
6. 實作 DualWriteStore：寫入順序「JSON 成功 → SQLite 嘗試 → 失敗寫 degraded log，不阻擋整筆」
7. 寫 `dual_write_replay_test.go`（先紅）
8. 實作 degraded log + replay（啟動同步 + 寫入後背景 goroutine + 寫入前輕量 stat）
9. cmd/scanner main 改 `NewStore(...DualWrite)`，保留 `ACTRESS_DB_MODE=json_only` rollback flag
10. Wails backend 切 DualWriteStore；跑 `app_test.go` 確認綠
11. CI 4 步序列繼續跑（A1 之後已建立）
12. dogfood 1–2 週、監看 `sync_degraded_total`

### 驗證命令

```powershell
go test .\pkg\database -v
go test .\cmd\scanner -v
Set-Location wails-app ; go test .\backend -v ; Set-Location ..
python -m pytest tests\ -q -p no:cacheprovider

# 觀察 degraded
.\classifier.exe db stats | Select-String "sync_degraded_total"
# 預期：0（或 replay 後降回 0）

# CI verify-sync
.\classifier.exe db migrate-from-json -source tests\fixtures\json_db_minimal\data.json -data-dir tests\fixtures\json_db_minimal
.\classifier.exe db verify-sync -data-dir tests\fixtures\json_db_minimal
```

### Rollback / Stop gate

- SQLite 寫入失敗率 > 1%（或 degraded log 持續成長） → `ACTRESS_DB_MODE=json_only` env 切回 JSONStore；保留 SQLite 檔分析
- verify-sync 大量 diff → 先跑 `db resync-from-json` 對齊一次；復現則切 `json_only`
- 整合測試 regression（characterization 沒抓到）→ 暫停，補 case；**不**繞過

### 不做事項

- 不切讀路徑（讀仍 JSON）
- 不改 backup/restore CLI
- 不改 Python helper
- 不改 schema
- Rust db-tool 不動
- 不加 GUI maintenance UI

### 完成條件

1. 所有單元與整合測試通過
2. `tests/test_go_cli_contracts.py` 全綠（Python 相容契約未破）
3. dogfood 1–2 週 `sync_degraded_total = 0`
4. CI verify-sync 連續 1 個 release 全綠
5. Wails backend 與 GUI smoke test 無回歸

---

# Phase B — 讀路徑反轉

## Slice B1 — SQLite read path for CLI

### 目標

在 feature flag 下讓 CLI `db get` / `db list` / `db stats` 讀路徑走 SQLite；fallback **僅限** SQLite 整體 unavailable 情境。

### 受影響檔案

**新增**

- `pkg/database/sqlite_read_store.go` — read wrapper（先 SQLite，失敗 fallback JSON）
- `pkg/database/sqlite_read_store_test.go`

**修改**

- `pkg/database/store.go` — `StoreConfig` 加 `UseSQLiteReads bool`
- `pkg/database/dual_write_store.go` — 讀方法依 `UseSQLiteReads` 切讀來源
- `cmd/scanner/main.go` — 從 env（`USE_SQLITE_READS`）或 config 讀 flag
- `pkg/database/sqlite_store.go` 或 `manager.go` — `GetStats()` 回傳加 `sqlite_read_fallback_total` 欄位
- `tests/test_go_cli_contracts.py` — 補 `db stats` 含 `sqlite_read_fallback_total` 的 case，並補 flag 開關下 `db get` / `db list` 行為一致 case
- `.github/workflows/` — Phase B 期間 CI 跑時設 `USE_SQLITE_READS=true`

### TDD 策略

採嚴格 TDD（read wrapper 是新邏輯）。

**先寫哪些測試**：

- `sqlite_read_store_test.go`
  - `UseSQLiteReads=false` → 走 JSONStore（行為與 A3 完全一致）
  - `UseSQLiteReads=true`、SQLite 正常 → 走 SQLite
  - `UseSQLiteReads=true`、SQLite open 失敗（檔案損毀 / 權限）→ fallback JSONStore，計數 +1
  - `UseSQLiteReads=true`、查詢 panic / I/O error → fallback JSONStore，計數 +1
  - `UseSQLiteReads=true`、SQLite 與 JSON 內容不一致 → **不** fallback，回 SQLite 結果（不一致由 verify-sync 處理）
- `db stats` 回傳 JSON 含 `sqlite_read_fallback_total` 整數欄位
- Python contract tests 補：`stats` JSON 解析不爆

### 主要步驟

1. 寫 `sqlite_read_store_test.go`（先紅）
2. 實作 `SQLiteReadStore` wrapper：try SQLite → 成功 return；失敗（限整體錯誤）→ log + 計數 + fallback
3. 寫 DualWriteStore 讀方法切換測試
4. DualWriteStore 讀方法依 `UseSQLiteReads` 切
5. cmd/scanner main 讀 `USE_SQLITE_READS` env
6. `db stats` 回傳加 `sqlite_read_fallback_total`
7. 跑 `tests/test_go_cli_contracts.py` 確認 Python helper 解析 stats 不會 KeyError
8. CI Phase B 期間設 `USE_SQLITE_READS=true`
9. dogfood 1 週 fallback=0

### 驗證命令

```powershell
go test .\pkg\database -v
go test .\cmd\scanner -v

$env:USE_SQLITE_READS = "true"
.\classifier.exe db list
.\classifier.exe db get STARS-707
.\classifier.exe db stats
# 預期：sqlite_read_fallback_total = 0

# Fallback 強制觸發（模擬 SQLite 不可開）
# 把 data\db.sqlite 改唯讀或寫垃圾
.\classifier.exe db get STARS-707
.\classifier.exe db stats
# 預期：sqlite_read_fallback_total > 0

# verify-sync 仍跑
.\classifier.exe db verify-sync
```

### Rollback / Stop gate

- `sqlite_read_fallback_total > 0` 持續累加 → `USE_SQLITE_READS=false` 切回 JSON 讀；分析 SQLite 端問題
- 讀取效能比 JSON 明顯慢（hot path > 200ms） → 檢查 index / SQL plan；暫不切讀
- 讀到的資料與 GUI 預期不符但 verify-sync 通過 → 視為應用層 bug，**不**回退讀路徑

### 不做事項

- 不切 Wails backend 讀路徑（B2 處理）
- 不改寫入路徑（仍雙寫）
- 不改 Python helper
- 不改 schema
- 不改 backup/restore

### 完成條件

1. CLI 讀路徑單元測試在 flag=true / false 下皆綠
2. CLI smoke：`db get` / `db list` / `db stats` 在 flag=true 下行為與 flag=false 一致（除 fallback 計數）
3. fallback 計數可在 `db stats` 觀測
4. dogfood 1 週 `sqlite_read_fallback_total = 0`

---

## Slice B2 — Wails backend read flip

### 目標

Wails backend 在 flag 下切 SQLite reads，保留 fallback JSON；前端不動。

### 受影響檔案

**修改**

- `wails-app/backend/app.go` — 接 `UseSQLiteReads`（從 env / config），預設 false
- `wails-app/backend/app_test.go` — 補 flag=true case
- 視需要新增 `wails-app/backend/integration_test.go` 或補既有測試

**不動**

- `wails-app/frontend/`（**只**讀路徑切換，行為應對前端透明）

### TDD 策略

**混合**：

- Wails 接線 → characterization（既有 backend tests 須仍綠）
- read flip 整合 → integration test（flag=true 全套）

**先寫哪些測試**：

- characterization gate：Wails backend `UseSQLiteReads=false` 行為與 B1 前一致
- 新增 case：`UseSQLiteReads=true` 下，backend 讀方法走 SQLite，fallback 時計數遞增
- 整合測試：`USE_SQLITE_READS=true` 下，既有 `tests/integration/` 全套綠

### 主要步驟

1. Wails backend 加 flag handler（從 env / config 讀）
2. 跑既有 backend tests 確認沒 regression（characterization）
3. 加 flag=true 的 backend / integration test
4. CI Phase B2 期間 `USE_SQLITE_READS=true`
5. 觀察 fallback 計數 1–2 週

### 驗證命令

```powershell
Set-Location wails-app
go test .\backend -v
Set-Location ..

$env:USE_SQLITE_READS = "true"
python -m pytest tests\integration -v --tb=short -p no:cacheprovider
.\classifier.exe db verify-sync
.\classifier.exe db stats | Select-String "sqlite_read_fallback_total"
# 預期：0
```

### Rollback / Stop gate

- Wails backend fallback 計數持續累加 → `USE_SQLITE_READS=false`
- 前端發現行為改變（不該發生）→ 暫停，補 backend test 抓到差異點

### 不做事項

- 不改寫入路徑（仍雙寫）
- 不改 backup/restore
- 不移除 JSONStore
- 不改 Python helper

### 完成條件

1. Wails backend 在 flag=true 下測試綠
2. integration tests 在 flag=true 下綠
3. `sqlite_read_fallback_total = 0` 連續 1–2 release
4. verify-sync 連續綠

---

# Phase C — JSON 退役

## Slice C1 — Backup / export / restore 完整化

### 目標

完整實作 `backup-create` 雙快照、`backup-restore` 雙模式（互斥）、`compact -json` no-op；保證 Python 相容契約（spec § 7.1）。

### 受影響檔案

**新增**

- `pkg/database/sqlite_backup.go` — 三層 backup fallback（`sqlite3_backup_*` API → `VACUUM INTO` → checkpoint+copy）
- `pkg/database/sqlite_backup_test.go`

**修改**

- `cmd/scanner/db_cmd.go` — 既有所有 db 子命令仍在此檔；本 slice 修改下列三組行為（**或**視膨脹拆出 `db_cmd_backup.go`，不為拆而拆）：
  - `db compact -json` 改 no-op，回 `{"success":true,"noop":true,"journal_size":0,"needs_compact":false,"reason":"sqlite has no journal to compact"}`
  - `db backup-create` 同時產 `db_*.sqlite` 與 `db_*.json`；回傳含 `backup_path`（既有）與新增 `json_export_path`
  - `db backup-restore` 新增 `-from-json <file>` 旗標；與既有 `-backup-path <sqlite>` 互斥
- `tests/test_go_cli_contracts.py` — 補 round-trip case、互斥 negative case、compact no-op 欄位完整性 case

### TDD 策略

**混合**：

- CLI flag 互斥、`compact -json` 相容回傳、backup round-trip → **嚴格 TDD**
- backup strategy 三層 fallback → **integration + fault injection**（不純單元）

**先寫哪些測試**：

- `backup-create`
  - 同時產 `db_*.sqlite` 與 `db_*.json`
  - 回傳 JSON 含 `backup_path` 與 `json_export_path`
- `backup-restore` 互斥規則
  - `-backup-path <sqlite>` 走 SQLite restore
  - `-from-json <json>` 走 resync-from-json 流程
  - **同時傳兩者** → exit 2 + stderr `error: -backup-path and -from-json are mutually exclusive; pass exactly one`
  - **兩者皆未傳** → exit 2 + stderr `error: db backup-restore requires either -backup-path <sqlite> or -from-json <json>`
  - **不**回退到「互動式列出 backup-list 讓使用者選」
  - 上述 2 條 negative case 必須在 `tests/test_go_cli_contracts.py` 有對應
- `compact -json` no-op
  - 回 `{"success":true,"noop":true,"journal_size":0,"needs_compact":false,"reason":"sqlite has no journal to compact"}`
  - Python `IncrementalJSONDB` 解析不爆（欄位齊全）
- backup strategy（integration + fault injection）
  - `sqlite3_backup` 路徑成功 → 採用之
  - 模擬 `sqlite3_backup` 失敗 → 走 `VACUUM INTO`
  - 模擬 `VACUUM INTO` 失敗 → 走 checkpoint + controlled copy
  - 鎖定超過 5 秒 → abort + 回傳 error

### 主要步驟

1. 寫 `backup-restore` 旗標互斥測試（先紅）
2. 修 `db_cmd.go` 加互斥檢查（不需要 backup strategy 已可實作）
3. 寫 `compact -json` no-op 測試（先紅）
4. 改 `db compact -json` 為 no-op，保留完整 Python 期望欄位
5. 寫 `backup-create` 雙快照測試（先紅）
6. 修 `db backup-create` 同時呼叫 `db export-json` 產出 .json，回傳加 `json_export_path`
7. 改 `db backup-restore` 加 `-from-json <file>` 旗標（走 `resync-from-json` 流程）
8. 寫 `sqlite_backup_test.go`（integration + fault injection）
9. 實作 `sqlite_backup.go` 三層 fallback；鎖定上限 5 秒
10. 跑 `tests/test_go_cli_contracts.py` 確認相容契約全綠

### 驗證命令

```powershell
go test .\pkg\database -v
go test .\cmd\scanner -v
python -m pytest tests\test_go_cli_contracts.py -v -p no:cacheprovider

# Round-trip
.\classifier.exe db backup-create
.\classifier.exe db backup-list
# 預期：含 backup_path 與 json_export_path

# Restore from SQLite
.\classifier.exe db backup-restore -backup-path data\backup\db_*.sqlite
# Restore from JSON
.\classifier.exe db backup-restore -from-json data\backup\db_*.json

# 互斥 negative
.\classifier.exe db backup-restore -backup-path X -from-json Y
# 預期：exit 2、stderr "mutually exclusive"
.\classifier.exe db backup-restore
# 預期：exit 2、stderr "requires either -backup-path or -from-json"

# Compact no-op
.\classifier.exe db compact -json
# 預期：{"success":true,"noop":true,"journal_size":0,"needs_compact":false,...}
```

### Rollback / Stop gate

- Python contract test 破 → 立即修 Go 端回傳格式；**不**改 Python
- backup strategy 三層皆失敗 → 暫退到「一律 VACUUM INTO」並接受短暫阻塞
- 鎖定 5 秒 timeout 觸發率高 → 調高至 8 秒並補 monitor，但不**移除**上限

### 不做事項

- 不移除 JSONStore / DualWriteStore（C2 處理）
- 不切寫入路徑（C2 處理）
- 不動 Rust db-tool（C3 處理）
- 不改 schema

### 完成條件

1. backup round-trip 測試綠（建 → list → restore-sqlite → restore-json）
2. 互斥規則測試綠（2 條 negative case）
3. `compact -json` no-op 通過 Python `IncrementalJSONDB` 解析
4. `tests/test_go_cli_contracts.py` 全綠
5. backup strategy fault injection 測試綠

---

## Slice C2 — SQLite-only runtime

### 目標

移除 DualWriteStore / JSONStore runtime；SQLiteStore 單寫；JSON 只剩 export/backup 用途。

### 受影響檔案

**刪除**

- `pkg/database/json_store.go` + test
- `pkg/database/dual_write_store.go` + test
- `pkg/database/dual_write_replay.go` + test

**修改**

- `pkg/database/store.go` — 移除 `ModeJSONOnly` / `ModeDualWrite`；`NewStore` 只回 SQLiteStore；`StoreConfig` 簡化
- `cmd/scanner/main.go` — 移除 `ACTRESS_DB_MODE` env 切換
- `wails-app/backend/app.go` — 不再支援 DualWrite mode，直接 SQLiteStore
- `pkg/database/sqlite_store.go` — 補檢查所有 `DatabaseStore` 方法已實作（A3/A2/A1 應已完整；若有 `QueryVideos` 仍 `ErrNotImplemented` 可保留）

### TDD 策略

採 **characterization**：既有測試套件在 SQLite-only 下都該綠（若不綠，代表 A3 漏實作某 method）。

**先寫哪些測試**：

- SQLite-only 起跑全套既有測試 → 全綠（characterization gate）
- 加 SQLite-only integration smoke：移除 DualWrite 後 contract / integration tests 全綠
- 若發現某 method 在 DualWrite 下走 JSON、SQLite 沒實作 → 在 C2 補上並補單元測試

### 主要步驟

1. **進入 C2 前必跑**：`db backup-create` 產出最新雙快照（.sqlite + .json）— 這是 rollback gate 的前提
2. 移除 DualWriteStore / JSONStore 相關檔
3. SQLite-only mode 跑既有測試套件 → 找出漏實作的 SQLiteStore method
4. 補上漏實作 method + 單元測試
5. 跑 Python contract test、integration test
6. Wails backend smoke test
7. dogfood 1–2 週

### 驗證命令

```powershell
go test .\pkg\... -v
go test .\cmd\scanner -v
Set-Location wails-app ; go test .\backend -v ; Set-Location ..

python -m pytest tests\ -q -p no:cacheprovider
python -m pytest tests\integration\ -v --tb=short -p no:cacheprovider

.\classifier.exe db verify-sync
# C2 後 verify-sync 仍可跑（拿最近 export 的 JSON 快照與 SQLite 比對）；但 source of truth 已是 SQLite
```

### Rollback / Stop gate

- Python helper 出錯（違反 § 7.1）→ 立即修 Go 端契約
- SQLite-only 後性能異常 → git revert 加回 DualWriteStore + 切 `ACTRESS_DB_MODE=dual_write`；保留現場分析
- 寫入失敗率高（SQLite 整體不穩）→ rollback 同上；前提是 C2 進入前已有最近一次雙快照

### 不做事項

- 不改 Rust db-tool（C3 處理）
- 不改 wiki（C3 處理）
- 不改 schema
- 不加新 CLI 子命令

### 完成條件

1. 既有測試套件 100% 在 SQLite-only 下綠
2. Python contract / integration 全綠
3. Wails backend 與 GUI smoke test 全綠
4. 進入 C3 前必須有最近一次 `db backup-create` 雙快照

---

## Slice C3 — 文件與 Rust db-tool 重定位

### 目標

更新 wiki / pitfalls；Rust db-tool 重定位（`db-import-json` deprecate；新增 `db-verify` / `db-migrate`）；schema 統一到雙方共用位置。

### 受影響檔案

**新增 / 移動**

- `schemas/sqlite/v3.sql`（從 `pkg/database/sqlite_schema.sql` 移動或複製，雙方都 embed 此份）
- `wiki/pitfalls/sqlite-migration-*.md`（依踩坑紀錄）

**修改**

- `pkg/database/sqlite_store.go` — embed 改從 `schemas/sqlite/v3.sql`
- `tools-rs/build.rs` 或 source — embed 同一份 `schemas/sqlite/v3.sql`
- `tools-rs/src/main.rs` + `commands.rs` — `db-import-json` 加 deprecation warning（stderr）；新增 `db-verify` 子命令；新增 `db-migrate` 骨架
- `tools-rs/tests/integration_db_tool.rs` 或新增 — 補 verify / migrate / schema embed 一致性 test
- `wiki/architecture/database.md` — 大幅更新為 SQLite-only schema 描述
- `wiki/architecture/sqlite-shadow-db.md` — 改寫為「歷史 / 已退役」標記
- `wiki/log.md` — 追加當日紀錄（依 CLAUDE.md 規範）
- `wiki/wiki-data.js` — 跑 `python wiki/gen_data.py` 重新產生

### TDD 策略

採嚴格 TDD（Rust verify / migrate / schema embed 一致性都是新邏輯）。

**先寫哪些測試**：

- Rust db-tool `db-verify`
  - 對 v3 SQLite 跑 `PRAGMA integrity_check` → 回 ok
  - 對損毀 SQLite → 報錯，exit 非 0
- Rust db-tool `db-migrate v3 → v3`
  - 同版本 no-op
  - 預留 v3 → v4 升級骨架（無動作但介面可呼叫）
- Schema embed 一致性
  - Go 端 embed 內容 = Rust 端 embed 內容（雙方都讀 `schemas/sqlite/v3.sql` 後字串比對）
- Deprecation
  - `db-import-json` 跑時 stderr 含 `deprecated`

### 主要步驟

1. 寫 schema embed 一致性測試（先紅）
2. 把 `pkg/database/sqlite_schema.sql` 移到 `schemas/sqlite/v3.sql`
3. Go 端 embed 改路徑（`//go:embed ../../schemas/sqlite/v3.sql`）
4. Rust `build.rs` 加 embed 同一份 .sql；或在 source 用 `include_str!("../../schemas/sqlite/v3.sql")`
5. 跑 schema 一致性測試 → 綠
6. 寫 Rust `db-verify` 測試（先紅）
7. 實作 Rust `db-verify`
8. 寫 Rust `db-migrate` 骨架測試（先紅）
9. 實作 Rust `db-migrate` 骨架（v3 → v3 no-op；預留升級接口）
10. Rust `db-import-json` 加 deprecation warning（stderr）
11. wiki 更新（依 CLAUDE.md 規範三步驟）：
    - 編輯 `wiki/architecture/database.md`（重寫為 SQLite-only schema）
    - 標 `wiki/architecture/sqlite-shadow-db.md` 為歷史
    - 新增 `wiki/pitfalls/sqlite-migration-*.md`（依實際踩坑）
    - 追加 `wiki/log.md`（最新在上）
    - 跑 `python wiki/gen_data.py`（必要時 `$env:PYTHONIOENCODING="utf-8"`）

### 驗證命令

```powershell
go test .\pkg\database -v
cargo test --manifest-path tools-rs\Cargo.toml

# 整合 verify
cargo run --manifest-path tools-rs\Cargo.toml -- db-verify --sqlite data\db.sqlite
# 預期：exit 0、integrity_check ok

# Schema 一致性
# 由 Go 與 Rust 測試各自比對 `schemas/sqlite/v3.sql` 內容

# wiki 同步
python wiki\gen_data.py
# 檢查 wiki/wiki-data.js 更新時間
```

### Rollback / Stop gate

- Rust db-tool 編譯失敗 → 暫停 C3；保留 Go-only `pkg/database/sqlite_schema.sql` embed（這份 .sql 仍可保留為 Go embed 起點，等待 Rust 補完）
- `python wiki/gen_data.py` `UnicodeEncodeError` → 用 `$env:PYTHONIOENCODING="utf-8"` 重跑（依 CLAUDE.md）
- wiki 內容矛盾 / 交叉引用斷裂 → 跑 `wiki-maintenance` skill 的 lint，補修

### 不做事項

- 不改 schema 結構（v3 維持）
- 不改 runtime code（前面 slice 已完成）
- 不刪除 Rust db-tool（只重定位 + deprecation）

### 完成條件

1. Rust db-tool 測試全綠
2. Go 與 Rust 雙方 embed 同一份 `schemas/sqlite/v3.sql`，內容一致性測試綠
3. `wiki/architecture/database.md` 已更新為 SQLite-only
4. `wiki/architecture/sqlite-shadow-db.md` 已標記為歷史
5. `wiki/log.md` 已追加當日紀錄
6. `wiki/wiki-data.js` 已重新產生
7. Rust `db-import-json` 跑時 stderr 含 deprecation warning

---

## TDD 策略總覽

| 模組 | 所屬 slice | 策略 |
|------|----------|------|
| `data_dir_lookup`（JSON 與 SQLite 端） | A0 + A1 | 嚴格 TDD |
| `migrate-from-json` | A1 | 嚴格 TDD |
| `verify-sync` | A1 | 嚴格 TDD |
| `resync-from-json` | A2 | 嚴格 TDD |
| `export-json`（含 statistics view、`data_hash` 規則） | A2 | 嚴格 TDD |
| Round-trip 等價 | A2 | 嚴格 TDD |
| `DatabaseStore` 抽象、`JSONStore` 包裝 | A3 | characterization + 小步重構（既有測試擔任 gate） |
| `DualWriteStore` 寫入順序、`degraded log` / `replay` | A3 | 嚴格 TDD |
| Wails / cmd/scanner 接線 | A3、B2 | characterization |
| `SQLiteReadStore` fallback 規則 | B1 | 嚴格 TDD |
| Wails backend read flip | B2 | characterization + integration |
| `backup-restore` 旗標互斥 | C1 | 嚴格 TDD |
| `compact -json` 相容回傳 | C1 | 嚴格 TDD |
| `backup-create` 雙快照 | C1 | 嚴格 TDD |
| backup strategy 三層 fallback / WAL | C1 | integration + fault injection（**不**純單元 TDD） |
| SQLite-only 移除 DualWrite | C2 | characterization（既有測試擔任 gate） |
| Rust `db-verify` / `db-migrate` | C3 | 嚴格 TDD |
| Schema embed 一致性（Go ↔ Rust） | C3 | 嚴格 TDD |
| 效能 / benchmark | 跨 slice | benchmark（Rust db-tool 與 Go 端對照） |

---

## 跨 slice 共通檢查

每個 slice 進入與完成前都跑：

```powershell
# 既有測試套件（slice 變動不該破壞既有測試）
python -m pytest tests\ -q -p no:cacheprovider
go test .\pkg\... -v
go test .\cmd\scanner -v
Set-Location wails-app ; go test .\backend -v ; Set-Location ..

# Build pipeline 仍是純 Go
go build -o classifier.exe .\cmd\scanner
Set-Location wails-app ; wails build ; Set-Location ..
```

---

## 開放項目（spec § 10，實作時定案）

- **degraded log threshold 具體值**：spec 給 32 KiB 為建議起點，A3 dogfood 期內依寫入頻率調整
- **背景 replay goroutine 退避策略**：可從「失敗即記錄、下次寫入再試」做起；A3 觀察後再決定是否加指數退避
- **`actresses.name` 是否未來加 UNIQUE**：A3 完成後依 audit 結果決定
- **Wails maintenance UI 時程**：B2 或 C3 加入皆可
- **Python `IncrementalJSONDB` stats 欄位實際使用情況**：A0 已在 `tests/test_go_cli_contracts.py` 補測試覆蓋；B1 加 `sqlite_read_fallback_total` 時補檢查

---

## Plan 自審摘要

**spec 條款覆蓋**：

- § 1 終點架構 → A3 + C2 + C3
- § 2 Schema（含 db_meta / videos / actresses / actress_aliases / video_actress_links） → A1（schema 建立 + Go embed）、C3（schema 共用到 Rust）
- § 2.5 statistics view → A1（schema 內定義）、A2（export 時填回 JSON）
- § 3 Migration 策略（含 fail loudly、`auto_<sha1>` ID、display_name、Pass 1/2/3） → A1
- § 4 三階段過渡 → 各 Phase / slice
- § 4.1 雙寫失敗策略（寫入順序、degraded log、replay） → A3
- § 4.2 verify-sync 規則（含 `data_hash` 忽略） → A1（基本實作）、A2（round-trip）、A3（runtime 雙寫期驗證）
- § 4.3 Phase B fallback → B1（CLI）、B2（Wails）
- § 5 CLI 變更 → A1（migrate / verify / resync）、A2（export）、C1（backup / restore / compact）
- § 6.2 backup 三層 fallback → C1
- § 7.1 Python 相容契約（含 `-data-dir` compatibility lookup） → A0 + A1（補 lookup）、C1（compact / backup 相容回傳）
- § 7.3 DatabaseStore interface 草案 → A3
- § 8 風險 → 各 slice rollback / stop gate
- § 9 工程量 → 本 plan slice 時程

**CLI 名稱**：全部沿用 `db backup-create` / `db backup-list` / `db backup-restore` / `db backup-cleanup` / `db compact -json` / `db migrate-from-json` / `db verify-sync` / `db resync-from-json` / `db export-json`；無殘留 `db backup` / `db restore`。

**Placeholder 掃描**：無「TBD」「之後再處理」；開放項目集中在最後章節並標明處理時機。

**檔案結構正確性**：`cmd/scanner/` 下既有為 `db_cmd.go` 單檔；本 plan 寫「修改 `cmd/scanner/db_cmd.go`，視膨脹再拆檔」，不假設既不存在的 `db_compact.go` / `db_backup_create.go` / `db_backup_restore.go`。

**CI verify-sync gate**：A1 明確列出 4 步序列（build → fixture → migrate / resync → verify-sync）。

**schema 共用時點**：A1 只 Go embed；C3 才搬到 `schemas/sqlite/v3.sql` 雙方共用。

**`go test` 命令**：用 `go test .\cmd\scanner -v`（單一 package），不用 `.\cmd\scanner\...`。

**`backup-restore` 旗標互斥**：C1 完整列出兩種錯誤輸入的 exit 2 + stderr 訊息，並要求 `tests/test_go_cli_contracts.py` 補 2 條 negative case。
