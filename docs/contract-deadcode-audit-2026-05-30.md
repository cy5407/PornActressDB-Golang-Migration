# Python → Golang 遷移審查報告：契約 / 介面 / 入口正確性 + 死碼盤點

- **日期**：2026-05-30
- **方法**：`/workflow` 多 agent 編排，8 維度平行審查（單批 ≤9 並行，守住使用者指定的 ≤10 上限）→ 對每筆發現派獨立 skeptic 做對抗式驗證（死碼宣稱一律跨「classifier.exe + actress-classifier.exe 雙 binary + 測試 + go:embed + Python subprocess 字串 + Rust caller」交叉比對）→ 人工彙整。
- **規模**：66 個 subagent、~1.28M token、339 次工具呼叫、~7.2 分鐘。
- **裁決**：58 筆原始發現 → **55 confirmed、0 uncertain、3 refuted**。
- **地基**：root module 與 wails backend 皆 `go build ./... && go vet ./...` 全綠；本報告所有「死碼」皆指「可達性死碼」（編譯通過但無生產呼叫者），非斷鏈。
- **獨立覆核（codex，2026-05-30）**：唯讀覆核確認 P1/P2 契約問題多數成立（D1-1 以 `go run … move -dir` 實測重現 exit 2；D4-1 以 Go JSON tag snippet 驗證 `search_method` 會讓 `Method=""`；D2-1/D2-2/D4-2/D3-5/D5-6 逐筆確認）。提出兩處**措辭修正**（非判定推翻），已併入下文：① D1-1 的回傳 shape 不一致是「wrapper 透傳 vs fallback 分支」層級，非 wrapper 讀錯欄位；② D4-5 不應寫「runtime 不可達」，實為經 `UnifiedCacheManager` 反射呼叫的**兩層死鏈**。

> ⚠️ **雙 binary 陷阱（本次審查最重要的方法論教訓）**：`pkg/database`、`pkg/mover`、`pkg/cache` 被兩個獨立 Go module 消費——`classifier.exe`（`./cmd/scanner`）與 `actress-classifier.exe`（`wails-app/`，獨立 go.mod + replace）。任何單一入口的 `deadcode` 結果，對「另一個 binary 才用到的函數」都是**假陽性**。驗證階段實際攔下了 3 個這類假陽性（`NewVideo`/`BatchMoveDirs`/`GetOperation`，見 §B6）。**刪任何 Go 函數前，務必同時 grep 兩個 module 的生產碼與前端 bindings。**

---

## A. 契約 / 介面 / 入口正確性問題（需修正）

### A1. 實質契約缺陷

| ID | 嚴重度 | 問題 | 位置 |
|----|--------|------|------|
| **D1-1** | **P1** | `go_cli.py` 的 `move_dir` 送出 Go 根本不存在的 `-dir` flag → `flag provided but not defined: -dir` → `os.Exit(2)` → Python `run()` 一律 raise GoError → **目錄移動恆失敗**（已用 `go run .\cmd\scanner move … -dir` 實測重現 exit 2）。即便修了 flag，回傳 shape 仍不一致：`move_dir` 對 Go 的 dict 是**原樣透傳**（`go_cli.py:635-636`，wrapper 本身沒讀錯欄位），於是**成功**時上層拿到 Go `contracts.MergeResult` 的 `source_dir/dest_dir/files_moved`；但 wrapper 的 **fallback / except 分支**（`go_cli.py:637-651`）回的是 `{success, source, destination, skipped}`——兩條路徑 shape 不同，任何期待舊 `source/destination/skipped` 欄位的上層呼叫端會對不上。 | `src/services/go_cli.py:622-651` ↔ `cmd/scanner/main.go:158-179, 248-255`、`pkg/contracts/move.go:34-42` |
| **D4-1** | **P1** | 搜尋結果的 `search_method` 鍵與 Go `SearchResult` 的 `json:"method"` 不一致，**搜尋方法欄位永遠遺失**。只改一邊無效：Go 鍵改了，Python 端 `source → search_method` 仍無映射會拿到空字串，須兩處一起修。 | `src/scrapers/run_search.py:275`、`run_batch_search.py:98`、`wails-app/backend/app.go:537` |
| **D2-1** | P2 | `mover.MergeResult.FilesSkipped` 在轉成 `contracts.MergeResult` 時被**靜默丟棄**，CLI `move-dir` 輸出缺 `files_skipped`（GUI 路徑有、CLI 路徑沒有）。 | `pkg/app/move_service.go:43-56`、`pkg/contracts/move.go:34`、`pkg/mover/types.go:38` |
| **D4-2** | P2 | `cache prune` 的 Go 回傳鍵 `deleted_files/remaining_files` 與 Python 讀的 `deleted_count/remaining_count/current_size_mb` 不一致（`current_size_mb` Go 端根本不存在）。目前被 D4-5 的死鏈遮蓋，未爆出。 | `pkg/cache/types.go:44-47`、`cmd/scanner/cache_cmd.go:65-80`、`src/scrapers/cache_manager.py:579-581,615-618,713-714` |
| **D5-6** | P3 | `DbUpdateVideo` 吞掉 `ensureDB()` 錯誤，與 `DbGetVideo`/`DbListVideos` 的錯誤處理不一致（NewStore 失敗不會上拋前端）。 | `wails-app/backend/app.go:419-426` |

### A2. 介面 / 型別重複（介面破裂風險）

| ID | 嚴重度 | 問題 | 位置 |
|----|--------|------|------|
| **D2-2** | **P1** | `pkg/contracts` 與 `pkg/mover` **平行定義同名 DTO**，靠 `pkg/app` 手寫逐欄位轉換橋接。GUI（wails）直接用 `mover.*`、CLI 用 `contracts.*`，兩套不相通的型別只靠 hand-copy 維持，極易漂移（D2-1 的 `FilesSkipped` 漏欄位就是這個結構造成的）。 | `pkg/contracts/move.go`、`pkg/contracts/history.go`、`pkg/mover/types.go`、`pkg/app/move_service.go`、`pkg/app/history_service.go` |
| **D2-3** | P2 | wails 後端自定義 `ScanResult` 結構，與 `pkg/contracts/scan.go` 的 `ScanResult` **完全重複但無共用**。 | `pkg/contracts/scan.go:4-7`、`wails-app/backend/app.go:112-115,125-173` |

> 修法建議（D2-2）：二選一收斂——(a) 讓 `cmd/scanner` 直接序列化 `mover.*`，移除 `contracts`+`app` 轉換層（GUI 已證明 `mover.*` 可直接當對外 DTO）；或 (b) 保留 `contracts` 當穩定 CLI 邊界，但讓 wails 也改用 `contracts.*` 並補「contracts 欄位 == mover 欄位」對齊測試。

### A3. 邊界違規（SQLite-only）

| ID | 嚴重度 | 問題 | 位置 |
|----|--------|------|------|
| **D3-5** | P2 | `JSONDBManager.__init__` / `IncrementalJSONDB` 仍在 runtime 對 `data.json`/`data.journal`/`data.index` 做 **Python 寫入**，違反「C2 之後 Python 不再寫 JSON」邊界。**但** D3-1/D3-2 已證實這兩個類別在 `src/` 生產碼零呼叫者，故此違規為**潛伏（dormant）**——只有被實例化才觸發。 | `src/models/json_database.py:118,138,258-305`、`src/models/incremental_json_database.py:100,108,135-151` |

> 相關：**D4-6（已 refuted）** 原宣稱 `tools/studio_updates/update_mida101.py` 直接用 IncrementalJSONDB 寫 JSON 違反邊界，驗證後**推翻**——因為該腳本本身已壞（見 D3-3：無參數呼叫必拋 TypeError），是死碼而非 active 違規。

### A4. 契約鎖測試缺口（**無 active bug，但缺守門**）

`tests/test_go_cli_contracts.py` 是契約鎖，但下列線上使用的命令**沒有任何 argv 鎖**，日後任一端改 flag 名都不會被攔到，只會在實機以 GoError/exit 爆出：

- **D1-2 (P2)**：`cache_get/set/delete/prune/clear/get_stats` 六個線上 wrapper（`cache_manager.py` 實際依賴）零 argv 鎖。今日 flag 對齊，純屬日後漂移風險。
- **D1-3 (P3)**：`history rollback / rollback_last / list_operations` 無 argv 鎖。
- **D1-4 (P3)**：`move_file / batch_move` 無 argv 鎖（`move_file` 只測 non-dict fallback）。
- **D1-5 (P3，資訊型)**：Go 有 `db merge` / `db fix-studios`，但 `go_cli.py` 無對應 wrapper、契約鎖也未涵蓋（確認非破裂，僅未覆蓋）。

> 修法：仿 `db_backup_cleanup` 既有的 `captured["args"] == [...]` 樣板，為每個 wrapper 補 argv 斷言。

### A5. 文件 / 措辭不符

- **D2-4 (P3)**：`wiki/architecture/overview.md:117` 把 `pkg/contracts` 誤述為「Scanner/Mover/HistoryService 介面」，實際只含 DTO struct。
- **D7-5 (P3)**：`tools-rs/src/main.rs` 的 about 字串把 `db-import-json` 列在 legacy 群組，而非標 deprecated，與實際 deprecation 分層措辭略不一致。

---

## B. 死碼 / 無作用函數盤點

### B1. Go 真死碼（生產碼零呼叫者，**可刪**）

| ID | 對象 | 位置 | 備註 |
|----|------|------|------|
| **D6-6 / D6-8** | 整個 `JSONDatabase` 型別：**55 個 receiver 方法 + `NewJSONDatabase` + 8 個 package-level 死函式**（`journal.go` 的 `apply*` 群） | `pkg/database/jsondb.go`、`pkg/database/journal.go` | 最大宗死碼。`NewJSONDatabase` 僅在自身定義處 + `*_test.go` 出現，`cmd/scanner`、wails、`migrate_from_json.go`、`export_json.go` 全不用。匯入/匯出實際走 `DatabaseData` 自由函式，與 `JSONDatabase` 型別無關。 |
| **D6-3** | `SQLiteStore.Save()` `return nil` | `pkg/database/sqlite_runtime.go:574` | 兩 module 生產碼皆無呼叫點，僅測試引用。 |
| **D6-4** | `SQLiteStore.CompactJournal()` `return nil` | `pkg/database/sqlite_runtime.go:580` | 同上，真死碼。 |
| **D5-2** | `DbListVideos` / `DbUpdateVideo` bound method | `wails-app/backend/app.go:419-434` | 前端與測試皆未呼叫的生產死碼。（註：`DbUpdateVideo` 同時是 D5-6 錯誤處理不一致的對象，刪除即一併解決。） |
| **D5-4** | `ConfigService.CfgPath()` | `wails-app/backend/services/config.go:77-80` | exported 但全模組零呼叫者。 |
| **D5-3 / D5-5** | ini shim 鏈 + 死變數 | `services/config.go:109-116`、`app.go:75-89` | 三層兩跳 shim（services 私有 → services exported → app.go 私有）；exported `services.ParseIni/BuildIni` 唯一作用是被 app.go 的 test-access shim 包裝；`buildIni` 內 `svc := services.NewConfigService(""); _ = svc` 是建立即丟棄的無作用死碼。 |
| **D8-1~D8-5** | `pkg/cache` 五個函數：`New`(別名)、`CacheManager.CleanupExpired`、`CleanupBySize`、`Exists`、`DefaultPruneConfig` | `pkg/cache/cache.go:62,172,211,540`、`types.go:60` | 生產零引用、僅測試呼叫；cleanup 系列已被 `AutoCleanup` 取代，CLI prune 自行 inline 組 `PruneConfig`。 |

> ⚠️ **D6-7（P1 切割警告，刪 `JSONDatabase` 前必讀）**：`jsondb.go`/`journal.go` 內**死方法與活 helper 同檔交錯**，整檔刪除會破壞 SQLite 生產路徑。有 7 個活的 package-level helper（`jsondb.go:865,909,1196,1200,1231,1313`、`journal.go:172`）被 `SQLiteStore` 依賴。另 `journal.go:149` 的 `(*JSONDatabase).applyVideoFieldUpdates` 是死方法，但與 `sqlite_runtime.go:264` 活的 package-level `applyVideoFieldUpdates` 同名孿生，**別誤刪活版本**。建議分兩步 commit：先把活 helper 搬到中性檔（`merge_helpers.go`/`backup_helpers.go`）→ 測試綠 → 再刪 `JSONDatabase`（驗 `go build ./...` + wails build + 四道 schema-drift 測試全綠）。以 `deadcode ./cmd/scanner` 的 unreachable 清單為切割依據：列出的刪、未列出的搬移保留。

### B2. Python 死碼（`src/` 生產碼零呼叫者）

| ID | 對象 | 位置 |
|----|------|------|
| **D3-1** | `JSONDBManager` 全類別（僅測試 + 壞掉的 tools 腳本引用） | `src/models/json_database.py:77` |
| **D3-2** | `IncrementalJSONDB` 全類別（唯一生產引用是壞掉的 tools 腳本） | `src/models/incremental_json_database.py:53` |
| **D3-3** | `tools/studio_updates/` 四支腳本以 `IncrementalJSONDB()` 無參數呼叫，**必拋 TypeError = 事實上已死** | `tools/studio_updates/update_{s1,mida101,moodyz,faleno}_studio.py` |
| **D3-4** | `UnifiedFileScanner` 整個掃描適配層（僅測試使用） | `src/utils/scanner.py:11` |
| **D4-3** | `WebSearcher` 四個搜尋方法為入口鏈外孤兒（僅測試引用）：`batch_cascade_search`、`cascade_search_single`、`search_shiroutowiki_only`、`search_japanese_sites_only` | `src/services/web_searcher.py:723,896,1137,1270` |
| **D4-4** | `UnifiedCacheManager` 全部資料操作方法（production 只用 `register_cache_source`，但下游無消費者）：`get/set/delete/cleanup_all/clear_all/get_stats/print_stats/cleanup_all_caches` | `src/services/unified_cache.py:88,116,140,157,227,259,301,374` |
| **D4-5** | `CacheManager` 的 `cleanup_expired/cleanup_by_size/auto_cleanup/get_cache_stats/clear_all` **無生產入口主動觸發**（並遮蓋了 D4-2 契約問題）。⚠️ **措辭修正（codex 覆核）**：非「絕對不可達」——`UnifiedCacheManager._cleanup_single_source` 用 `hasattr(cache,"auto_cleanup")` **反射呼叫** `auto_cleanup`（`unified_cache.py:204-206`），`clear_all`（`:241-244`）與 `get_stats→_get_source_stats`（`:320-321`）亦同。準確說法：這是**兩層死鏈**——`CacheManager.*` 經 `UnifiedCacheManager` 間接可達，但 `UnifiedCacheManager` 的 cleanup/stats 入口本身（D4-4）無生產呼叫者；線上只看到 WebSearcher `register_cache_source`。**刪 `CacheManager` 這條鏈必須連 D4-4 的 `UnifiedCacheManager` 間接鏈一起評估，不可單獨移除。** | `src/scrapers/cache_manager.py:550,590,627,656,686`、`src/services/unified_cache.py:204-206,241-244,320-321` |

> 上述多為「刪除型」變更，建議與使用者確認 GUI 無未來規劃後再動。`run_batch_search.py` 若要保留 batch 併發能力，應真正改走 `batch_cascade_search`，否則它就是死碼（D4-3）。

### B3. Rust legacy / 死路徑

| ID | 對象 | 位置 | 建議 |
|----|------|------|------|
| **D7-1** | 整個 `sqlite_db.rs` + `json_db.rs`（v2 shadow 專用）只被已退役的 legacy 命令消費 | `tools-rs/src/sqlite_db.rs`、`json_db.rs`、`main.rs:120-166` | CLAUDE.md 明示 v2 子命令「legacy 保留作診斷」，**維持現狀為合理選項**；若要瘦身可移到 feature flag/獨立 legacy module 並標退役時程，但需先處理 D7-2。 |
| **D7-2** | `scripts/db-sync.ps1` / `db-sync.sh` 仍串接 `db-init→db-import-json→db-compare-json` 寫入已退役的 `data/shadow.sqlite`，且開頭呼叫已是 no-op 的 `classifier db compact` | `scripts/db-sync.{ps1,sh}` | 加退役註解或移除，引導改用 `db verify-sync`/`export-json`/`resync-from-json`（v3）或 `db-import-json-v3`/`db-verify`。已查 `.github/workflows/rust.yml` 只跑 fmt+clippy+test，無 CI 引用這些腳本。 |

### B4. 測試專用（生產死碼，但服務測試套件 — **勿直接刪，需連測試一起評估**）

`deadcode ./cmd/scanner` 列為不可達、且 grep 確認**只被 `*_test.go` 引用**。屬「測試針對比生產更廣的 API 表面在測」——這是本專案 post-migration 死碼的主軸：

- **D8-9**：整個 `JSONDatabase` 型別（同 D6-6，從測試視角再確認一次）。
- **D8-10**：`DatabaseError` 型別 + `Error()/Unwrap()`（`pkg/database/types.go:221/226/233`）。
- **D8-11**：`types.go` 工廠群 `NewJournalEntry/GetEmptyVideo/GetEmptyActress/NewEmptyDirtyIndex/GetCurrentTimestampRFC3339`。
- **D8-12**：`safefile.ReadAll`（`pkg/safefile/safefile.go:171`，注意與 stdlib `io.ReadAll` 不同名同義）。

### B5. 故意保留的 no-op（**非 bug，勿刪** — 刪掉會打壞 Python helper / wails contract）

- **D6-1 / D6-2**：`SQLiteStore.Compact()` / `CompactIfNeeded()` 是故意 no-op，**仍被 wails 生產碼呼叫**（保 contract）。
- **D6-5**：CLI `db compact` 的 `compactNoopPayload` 是故意保留且被 Python 依賴的 no-op。
- **D3-6**：Python `compact / compact_if_needed / get_stats` 委派的 `db compact` 為刻意 no-op contract shim。
- **D7-4**：`db-import-json` deprecation warning 確實輸出至 stderr 且有測試鎖定（正面確認）。

> 對照 §B1：`Save()`/`CompactJournal()`（D6-3/D6-4）是**真死碼**（連呼叫點都沒有），可刪；`Compact()`/`CompactIfNeeded()`（D6-1/D6-2）是**故意 no-op 且有呼叫點**，保留。差別在「有無生產呼叫點」。

### B6. `deadcode` 工具假陽性（雙 binary 陷阱，**確認非死碼、勿刪**）

驗證階段攔下的假陽性——從 `./cmd/scanner` 入口看似不可達，實為 **wails GUI 活路徑**：

- **D8-6（refuted）**：`database.NewVideo` ← `wails-app/backend/app.go:747`。
- **D8-7**：`Mover.BatchMoveDirs` ← `app.go:281` → 前端 `App.tsx:747,764`。
- **D8-8（refuted）**：`Mover.GetOperation` ← `app.go:399` → 前端 `OperationHistoryDialog.tsx:315`。
- **D8-13**：wails `defaultPreferences/buildIni/parseIni` 是 **test-access 薄包裝**，非「重複死碼」（修正本次審查啟動時的初步假設；其冗餘問題另由 D5-3 處理）。
- **D8-14**：`pkg/cache` 整包**並非孤兒**——CLI（`cache_cmd.go`）與 Python（`go_cli.py:375-474`）皆 live 使用；只有 §B1 列的 5 個個別函數是死的。

---

## C. 正面確認（審查確認「沒問題」的項目）

- **D1-6**：`db stats` 保留欄位契約完整——Go 仍輸出 `journal_size/needs_compact/dirty_videos/sync_degraded_total/sqlite_read_fallback_total` 且測試已鎖。
- **D3-7**：委派層在 Go 失敗時一律 raise、不靜默假成功；`scanner.py` 統一走 `go_cli.is_available/run`（Go-only 邊界合規）。
- **D5-1**：`app.go` 對 `database.NewStore` / `*SQLiteStore` API 的使用與 `pkg/database` 端簽章完全一致（無誤用）。
- **D5-8**：`proc_windows.go` / `proc_other.go` 的 `hideWindow` 平台分離正確。
- **D7-3**：schema 單一來源 `include_str!` 與 `V3_SCHEMA_VERSION` 仍與 Go 端對齊，四道 drift 測試覆蓋完整。

---

## D. 建議處置優先序

1. **P1 先修（會壞功能 / 高漂移風險）**
   - D1-1 `move_dir -dir` flag → 改 `-kind dir` 並對齊回傳欄位。
   - D4-1 `search_method` ↔ `method` 鍵兩處一起修，補非空斷言測試。
   - D2-2 收斂 `contracts` vs `mover` 雙套 DTO（決定保留哪一套並補對齊測試）。
2. **P2 修正 / 決策**
   - D2-1 補 `files_skipped`；D4-2 統一 cache prune 鍵名（建議與 D4-5 合併評估「修補 vs 移除死鏈」）。
   - D3-5 邊界：決定 `JSONDBManager`/`IncrementalJSONDB` 去留（最徹底是隨 D3-1/D3-2 淘汰）。
   - **Go 死碼清理：先做 D6-7 切割（搬活 helper）→ 再刪 D6-6/D6-8 `JSONDatabase`**；同批可刪 D6-3/D6-4、D5-2/D5-3/D5-4/D5-5、D8-1~5。
   - Python 死碼 D3-1~D3-4、D4-3~D4-5：確認 GUI 無規劃後整批移除（含 `tools/studio_updates/` 與專屬測試）。
3. **P3 / 低風險**
   - A4 契約鎖測試缺口（D1-2~D1-5）補 argv 鎖。
   - D5-6 錯誤處理對齊（隨 D5-2 刪除一併解決）。
   - 文件 D2-4 / D7-5 措辭更正；Rust D7-1/D7-2 維持現狀或加退役註解。
4. **絕對不要動**：§B5 故意 no-op、§B6 雙 binary 假陽性。刪任何 Go 函數前一律 grep 兩個 module 生產碼 + 前端 bindings。

---

*完整逐筆證據（每筆含 evidence / impact / verdict reasoning）存於 workflow 輸出：`…/tasks/wnfd4afc9.output`（result JSON，58 筆）。*
