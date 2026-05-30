# 修復任務清單 — Python→Go 契約 / 死碼審查

> 來源報告：[`docs/contract-deadcode-audit-2026-05-30.md`](./contract-deadcode-audit-2026-05-30.md)
> 產出：2026-05-30 ｜ 狀態：**全部處理完成（Wave 1–3 + T6，2026-05-30）；死型別依 CLAUDE.md/使用者決定保留為測試 fixture**
> 每項任務格式：**問題 → 修復方法 → 修復完成條件(DoD) → 驗證程序**。所有任務完成後跑全域驗證 + `/tool-scan`。

## 執行狀態總表（2026-05-30）

| 任務 | 狀態 | commit / 備註 |
|------|------|------|
| T1 move_dir -kind dir + shape | ✅ DONE | Wave 1 `1b636b0`（+argv lock 測試） |
| T2 search method UnmarshalJSON | ✅ DONE | Wave 1 `1b636b0`（最小爆炸半徑：Go UnmarshalJSON + Python source fallback，前端不動） |
| T3 DTO 對齊守門 | ✅ DONE | Wave 2 `3d64cf2`（TestMergeResultToContract_CopiesEveryField；採最小版，不做轉換層大重構） |
| T4 files_skipped | ✅ DONE | Wave 1 `1b636b0` |
| T5 cache prune 鍵名 | ✅ DONE（保守修補） | Wave 2 `3d64cf2`（修鍵名 deleted_files/remaining_files、移除 current_size_mb；死鏈未移除，見 D4-4/D4-5 連動風險） |
| T6 dormant 邊界 | ✅ DONE（緩解） | `fd03b52` 兩類別 docstring 標「非 runtime store、勿在 runtime 實例化」（使用者決定保留類別，採 docstring guard 緩解） |
| T7 切割 live helper | ➖ 不需要 | T8 撤回後 jsondb.go 保留原狀，無需搬移 |
| T8 刪 JSONDatabase | ⚠️ **部分 + DEFERRED** | Wave 3 `d51415c` 只刪 Save()/CompactJournal() no-op；**JSONDatabase 型別依 CLAUDE.md「保留為測試 fixture 助手」不刪**（且需重寫測試 fixture，需確認） |
| T9 wails 死碼 | ✅ DONE | Wave 2 `3d64cf2`（連帶解 D5-6） |
| T10 pkg/cache 死函數 | ✅ DONE | Wave 2 `3d64cf2` |
| T11 Python 死碼 | ✅ 低風險子集 DONE / 🔒 DB 類別保留（使用者決定） | Wave 2 `3d64cf2`（UnifiedFileScanner/WebSearcher 孤兒/tools）；**JSONBDManager/IncrementalJSONDB 保留為測試 fixture**（使用者 2026-05-30 決定，採 T6 docstring guard；不做 ~92 測試 fixture 重寫） |
| T12 tools/studio_updates | ✅ DONE | Wave 2 `3d64cf2` |
| T13 Rust legacy 註解 | ✅ DONE | Wave 2 `3d64cf2` |
| T14 文件更正 | ✅ DONE | Wave 2 `3d64cf2`（wiki overview + 重產 wiki-data.js） |
| T15 契約鎖 argv | ✅ DONE | Wave 2 `3d64cf2`（11 條） |

**最終定案（死型別保留）**：T8 的 `JSONDatabase`（Go）與 T11 的 `JSONBDManager`/`IncrementalJSONDB`（Python）三個生產死型別**一律保留為測試 fixture 助手，不刪**——Go 端由 CLAUDE.md 明文保留指令決定（不可違反）；Python 端由使用者 2026-05-30 決定（與 Go 同處置，避免 ~92 測試 fixture 重寫）。三者皆已用 docstring/註解標明「非 runtime store、勿在 runtime 實例化」。完整移除屬「測試 fixture 重寫」型獨立大 slice（非修 bug），未來若要做需另開 slice。其餘 13 項任務全數完成並四工具鏈驗證。

## 通用驗證指令庫（各任務「驗證程序」引用）

```powershell
# G1 Go root 編譯 + 靜態檢查
go build ./...
go vet ./...
go build -o classifier.exe .\cmd\scanner

# G2 Go root 測試
go test .\pkg\... -count=1
go test .\cmd\scanner -count=1

# G3 Wails backend 編譯 + 測試（獨立 module）
Set-Location wails-app; go build ./backend/...; go vet ./backend/...; go test .\backend -count=1; Set-Location ..

# G4 Rust db-tool
cargo test --manifest-path tools-rs\Cargo.toml

# G5 Schema-drift 四道鎖（改 Go/Rust schema 或刪 pkg/database 時必跑）
go test .\pkg\database -run TestSQLiteSchemaSQL_MatchesCanonicalFile -count=1
cargo test --manifest-path tools-rs\Cargo.toml embedded_schema_matches_canonical_file_on_disk
cargo test --manifest-path tools-rs\Cargo.toml embedded_v3_schema_matches_canonical_go_package_file
cargo test --manifest-path tools-rs\Cargo.toml db_verify

# G6 Python 測試 + 契約鎖
python -m pytest tests\ -q -p no:cacheprovider
python -m pytest tests\test_go_cli_contracts.py -q -p no:cacheprovider

# G7 CI 釋出閘（Phase A）— 本機重現
go build -o classifier.exe .\cmd\scanner
.\classifier.exe db migrate-from-json -data-dir tests\fixtures\json_db_minimal
.\classifier.exe db verify-sync -data-dir tests\fixtures\json_db_minimal

# G8 死碼回歸（刪 Go 函數後）— 確認目標已消失且無新增不可達
deadcode ./cmd/scanner            # 在 repo root
Set-Location wails-app; deadcode .; Set-Location ..   # 參考用（Bind interface 會放大可達集）
```

---

# Wave 1 — P1 契約缺陷（會壞功能，最優先）

## T1 — 修 `move_dir` 的 `-dir` flag 與回傳 shape（D1-1）

**問題**：`go_cli.py:622-632` 送出 Go 不存在的 `-dir`，導致 `flag provided but not defined: -dir` → exit 2 → 目錄移動恆失敗。且成功路徑（透傳 Go `source_dir/dest_dir/files_moved`）與 fallback/except 路徑（`source/destination/skipped`）回傳 shape 不一致。

**修復方法**
1. `src/services/go_cli.py:631`：`"-dir"` → `"-kind", "dir"`（對齊 `cmd/scanner/main.go:164` 的 `-kind` 與 `runSingleMove` 的 `case "dir"`）。
2. 統一 `move_dir()` 回傳 shape：讓成功 dict-passthrough（`go_cli.py:635-636`）與 fallback/except（`637-651`）回同一組 keys。建議統一成 Go `contracts.MergeResult` 形狀：`{success, source_dir, dest_dir, files_moved, files_total, files_skipped, error}`；或在 wrapper 內把 Go dict normalize 成既有 `{success, source, destination, ...}`。二擇一但**兩條路徑必須一致**。
3. `tests/test_go_cli_contracts.py` 補 argv 鎖：`captured["args"] == ["move","-src",src,"-dst",dst,"-strategy",strategy,"-kind","dir"]`。

**修復完成條件 (DoD)**
- `classifier.exe move -src A -dst B -kind dir` 正常結束（exit 0），不再出現 `flag ... not defined`。
- `move_dir()` 成功與失敗回傳的 key 集合相同。
- 新增的 argv 鎖測試通過。

**驗證程序**：`G1` → `G6`（含新契約鎖）→ 手動 `.\classifier.exe move -src <臨時目錄A> -dst <臨時目錄B> -kind dir` 確認 exit 0 與 JSON 欄位。

---

## T2 — 統一搜尋結果 `method` 鍵（D4-1）

**問題**：Python 輸出 `search_method`，Go `SearchResult` 只吃 `json:"method"`（`app.go:537`，批次 subprocess 直接 `json.Unmarshal`），導致 `Method=""`，搜尋方法永遠遺失。**只改一邊無效**。

**修復方法**（兩處一起改）
1. `wails-app/backend/app.go:537`：`json:"method"` → `json:"search_method"`。
2. `src/services/web_searcher.py` 的 AV-WIKI / JAVDB 結果 dict 補上 `search_method`（用 `source` 值或既有的方法常數），讓 `run_search.py:275` / `run_batch_search.py:98` 的 fallback 取得到值。

**修復完成條件 (DoD)**
- 端到端跑一次搜尋，回傳的 `SearchResult.Method`（或對應欄位）非空字串。
- 補一條測試斷言：`{"search_method":"AV-WIKI"}` unmarshal 後 method 欄位 == `"AV-WIKI"`（非空）。

**驗證程序**：`G3`（wails go test）→ `G6`（python）→ 手動跑一次 `python -m src.scrapers.run_search <番號>` 確認輸出含非空 method。

---

## T3 — 收斂 `contracts.*` 與 `mover.*` 雙套 DTO（D2-2，連帶解 D2-1/D2-3）

**問題**：`pkg/contracts` 與 `pkg/mover`（及 wails 自定義 `ScanResult`）平行定義同名 DTO，靠 `pkg/app` 手寫逐欄位 copy 橋接；GUI 用 `mover.*`、CLI 用 `contracts.*`，靠 hand-copy 維持 → 漂移來源（D2-1 漏 `files_skipped` 即此結構造成）。

**修復方法**（二擇一，需先決策）
- **(a) 移除轉換層**：讓 `cmd/scanner` 直接序列化 `mover.*`，刪 `pkg/contracts` + `pkg/app` 的轉換函式（GUI 已證明 `mover.*` 可直接當對外 DTO）。
- **(b) 保留 contracts 當 CLI 邊界**：讓 wails 後端也改用 `contracts.*`，並新增「`contracts` 欄位集 == `mover` 欄位集」對齊測試鎖住漂移。

**修復完成條件 (DoD)**
- 全專案只剩一套對外 move/scan/history DTO，或兩套之間有自動對齊測試。
- CLI 與 GUI 的 move-dir 輸出欄位齊平（`files_skipped` 不再消失，見 T4）。

**驗證程序**：`G1` `G2` `G3`（雙 module 編譯+測試）→ 比對 `classifier.exe move ... -kind dir` 與 GUI BatchMoveDirs 的 JSON 欄位一致。

---

# Wave 2 — P2 契約 / 邊界

## T4 — 補回 `files_skipped`（D2-1）

**問題**：`mover.MergeResult.FilesSkipped`（`types.go:38`）轉成 `contracts.MergeResult`（`move.go:34`）時被靜默丟棄，CLI `move-dir` 輸出缺 `files_skipped`。

**修復方法**：`pkg/contracts/move.go` 補 `FilesSkipped int \`json:"files_skipped"\``；`pkg/app/move_service.go:43-56` 的 `mergeResultToContract` 補 `FilesSkipped: result.FilesSkipped`。（若刻意不暴露，則在 `move.go` 註解寫明原因，本任務改為「加註解」。）

**修復完成條件 (DoD)**：CLI move-dir 的 JSON 含 `files_skipped` 且值正確。

**驗證程序**：`G1` `G2` → 手動 move-dir 觀察 `files_skipped`。（若採 T3(a) 移除 contracts，本任務自動消解。）

---

## T5 — 決策 cache prune 死鏈：修補鍵名 vs 移除整鏈（D4-2 + D4-5 + D4-4）

**問題**：Go `cache prune` 回 `deleted_files/remaining_files`，Python 讀 `deleted_count/remaining_count/current_size_mb`（`cache_manager.py:578-581…`），鍵名不一致且 `current_size_mb` Go 端不存在。此契約問題被「無生產入口觸發」的死鏈遮蓋。

> ⚠️ **兩層死鏈（codex 覆核修正）**：`CacheManager.auto_cleanup/clear_all/get_cache_stats` 經 `UnifiedCacheManager._cleanup_single_source` 的 `hasattr` 反射（`unified_cache.py:204-206,241-244,320-321`）**間接可達**，但 `UnifiedCacheManager` 的 cleanup/stats 入口本身（D4-4）無生產呼叫者。**不可單獨刪 `CacheManager` 鏈。**

**修復方法**（二擇一，需先決策）
- **(a) 啟用並修正**：若要支援「離開時自動清理」，在 wails 關閉流程實際呼叫 `classifier cache prune`，並把 Python 三處改讀 `deleted_files/remaining_files`，`current_size_mb` 在 Go `CleanupResult` 補欄位或從 Python 移除。
- **(b) 移除整鏈**：刪 `cache_manager.py` 的 `cleanup_expired/cleanup_by_size/auto_cleanup/get_cache_stats/clear_all` + `UnifiedCacheManager`（D4-4）資料操作方法 + `cache_auto_cleanup_on_exit` 偏好。**連帶評估 Go 端 `pkg/cache` 的 cleanup 命令是否一併下架**（見 T11）。

**修復完成條件 (DoD)**：要嘛 prune 端到端鍵名一致且有實際呼叫者；要嘛整條 unified→CacheManager cleanup/stats 鏈與相關偏好一併移除、無殘留引用。

**驗證程序**：`G6`（python）→ 若採 (a)：手動觸發清理確認鍵名；若採 (b)：`rg "auto_cleanup|cleanup_expired|cleanup_by_size|clear_all|get_cache_stats"` 確認無生產殘留 + `G3`（wails）。

---

## T6 — 處理 dormant 邊界違規（D3-5）

**問題**：`JSONDBManager.__init__`（`json_database.py:93,135`）會建目錄 / 寫 `data.json`；`IncrementalJSONDB`（`incremental_json_database.py:100-108`）touch journal / 寫 index，違反「Python 不再寫 JSON」邊界。目前因零生產呼叫者為**潛伏**狀態。

**修復方法**：與 T9（Python 死碼）合併決策。若保留類別 → 移除 `__init__` 的 JSON/journal/index 寫入（改純讀或純委派 Go），並在 docstring 標「非 runtime store、不應在 runtime 實例化」。若淘汰 → 隨 T9 移除。

**修復完成條件 (DoD)**：runtime 路徑下不存在任何 Python 對 `data.json/data.journal/data.index` 的寫入；或類別已移除。

**驗證程序**：`rg "data\.json|data\.journal|data\.index" src/models` 檢查寫入點 → `G6`。

---

# Wave 3 — Go 死碼清理（**先切割再刪**）

## T7 — 【前置】切割 `jsondb.go`/`journal.go` 的活 helper（D6-7，刪 JSONDatabase 前必做）

**問題**：死方法與**仍被 SQLiteStore 依賴的活 package-level helper** 同檔交錯，整檔刪會破壞生產路徑。活 helper：`jsondb.go:865,909,1196,1200,1231,1313`、`journal.go:172`。另 `journal.go:149` 的 `(*JSONDatabase).applyVideoFieldUpdates`（死）與 `sqlite_runtime.go:264` 的 package-level `applyVideoFieldUpdates`（活）同名孿生，勿誤刪活版本。

**修復方法**：把 7 個活 helper 搬到中性檔（新建 `pkg/database/merge_helpers.go` / `backup_helpers.go`，或併入 `sqlite_runtime.go`/`sqlite_backup.go`）。**純移動，不改邏輯。**

**修復完成條件 (DoD)**：活 helper 已移出 `jsondb.go`/`journal.go`；`jsondb.go`/`journal.go` 剩下的非測試引用符號只剩 `JSONDatabase` 型別本身。

**驗證程序**：`G1` `G2` `G5`（schema 鎖）`G7`（釋出閘）全綠 → 此 commit 為「純搬移、行為不變」。

---

## T8 — 刪除 `JSONDatabase` 型別與相關 Go 真死碼（D6-6/D6-8/D6-3/D6-4，依賴 T7）

**問題**：生產零引用的 Go 死碼。

**修復方法**（T7 完成後）
- 刪 `JSONDatabase` 型別 + 55 個 receiver 方法 + `NewJSONDatabase` + `journal.go` 的 `apply*` 死群 + `jsondb.go`/`journal.go` 內 8 個 package-level 死函式（`jsondb.go:371,1003,1100,1135,1142,1301`、`journal.go:428`）+ 對應 `*_test.go`。
- 刪 `SQLiteStore.Save()`（`sqlite_runtime.go:574`）、`SQLiteStore.CompactJournal()`（`:580`）+ 其測試。
- **切割依據**：以 `deadcode ./cmd/scanner` 的 unreachable 清單為準——列出的刪、未列出的（T7 那 7 個）保留。

**修復完成條件 (DoD)**：`deadcode ./cmd/scanner` 不再列出 `JSONDatabase.*` / `Save` / `CompactJournal`；無新增不可達；雙 module 編譯與全測試綠。

**驗證程序**：`G1` `G2` `G3` `G5` `G7` `G8` 全綠。

> ⚠️ **保留**：`SQLiteStore.Compact()`/`CompactIfNeeded()`（D6-1/D6-2，wails 仍呼叫）、CLI `db compact` 的 `compactNoopPayload`（D6-5，Python 依賴）— **故意 no-op，不可刪**（見 T13）。

---

## T9 — 清理 wails 後端死碼（D5-2/D5-3/D5-4/D5-5）

**問題**：前端與測試皆未使用的生產死碼。

**修復方法**
- 刪 `DbListVideos` / `DbUpdateVideo` bound method（`app.go:419-434`）——同時解決 D5-6 的 `ensureDB` 錯誤吞沒。**先 `rg` 前端確認無 `DbListVideos`/`DbUpdateVideo` 呼叫**再刪。
- 收斂 ini shim 鏈（D5-3）：移除 `app.go:75-89` 的 `defaultPreferences/buildIni/parseIni` 三層測試 shim 與 `services/config.go:109-116` 的 exported `ParseIni/BuildIni`（若無其他用途）；測試改直接用 `ConfigService.Load/Save`。
- 刪 `app.go:80-81` 的死變數 `svc := services.NewConfigService(""); _ = svc`（D5-5）。
- 刪 `ConfigService.CfgPath()`（`config.go:77-80`，D5-4，全模組零呼叫者）——刪前 `rg "CfgPath"` 確認。

**修復完成條件 (DoD)**：上述符號移除後 `deadcode .`（wails）與 `rg` 皆無殘留引用；前端 build 正常。

**驗證程序**：`rg "DbListVideos|DbUpdateVideo|CfgPath|ParseIni|BuildIni" wails-app` → `G3` → wails 前端 `npm run build`（於 `wails-app/frontend`）。

---

## T10 — 清理 `pkg/cache` 個別死函數（D8-1~D8-5）

**問題**：`pkg/cache` 整包是 live 的（CLI + Python 用），但 5 個個別函數生產零引用：`New`(別名,`cache.go:62`)、`CacheManager.CleanupExpired`(`:172`)、`CleanupBySize`(`:211`)、`Exists`(`:540`)、`DefaultPruneConfig`(`types.go:60`)。

**修復方法**：刪這 5 個函數 + 對應測試。`CleanupExpired/CleanupBySize` 已被 `AutoCleanup` 取代；`DefaultPruneConfig` 已被 CLI inline 組 `PruneConfig` 取代。**勿動 `AutoCleanup`、`Get/Set/Delete/Stats/Clear` 等 live 方法。**

**修復完成條件 (DoD)**：`deadcode ./cmd/scanner` 不再列出這 5 個；`pkg/cache` 其餘函數仍可達。

**驗證程序**：`G1` `G2` `G8`。

---

# Wave 4 — Python 死碼（刪除型，建議逐項與使用者確認）

## T11 — 移除 Python 生產死碼類別 / 方法（D3-1~D3-4、D4-3、D4-4）

**問題**：`src/` 生產零呼叫者。

**修復方法**（每項先 `rg` 確認 GUI/搜尋管線無呼叫再刪，連同專屬測試）
- `JSONDBManager`（`json_database.py`）、`IncrementalJSONDB`（`incremental_json_database.py`）— 與 T6 合併決策。
- `UnifiedFileScanner`（`scanner.py:11`）。
- `WebSearcher` 四個孤兒方法（`web_searcher.py:723,896,1137,1270`）+ 其私有 helper。若要保留 batch 併發，改讓 `run_batch_search.py` 真正走 `batch_cascade_search`。
- `UnifiedCacheManager` 資料操作方法（`unified_cache.py`，與 T5 連動；保留 `register_cache_source` 需連 WebSearcher 註冊一併評估）。

**修復完成條件 (DoD)**：移除的符號全專案 `rg` 無生產殘留；`pytest` 全綠（含移除對應測試後）。

**驗證程序**：`G6` → `python -m pytest tests\integration\ -q -p no:cacheprovider`。

---

## T12 — 移除已壞的一次性腳本（D3-3）

**問題**：`tools/studio_updates/` 四支腳本以 `IncrementalJSONDB()` 無參數呼叫，必拋 TypeError（事實上已死）。

**修復方法**：直接移除 `tools/studio_updates/`（過時的片商標準化腳本）；若仍需保留，改為 `IncrementalJSONDB('data/json_db')` 並先確認 SQLite-only 下可運作（依賴 T6 結論）。

**修復完成條件 (DoD)**：目錄移除，或腳本可實際執行不拋 TypeError。

**驗證程序**：`rg "IncrementalJSONDB\(\)" tools` 無結果。

---

# Wave 5 — Rust / 文件 / 契約鎖補強（低風險）

## T13 — Rust legacy 標註（D7-1/D7-2，**不硬刪**）

**修復方法**：`scripts/db-sync.{ps1,sh}` 頂部加退役註解（引導改用 `db verify-sync`/`export-json`/`resync-from-json` 或 `db-import-json-v3`/`db-verify`），或移除（已確認 `.github/workflows/rust.yml` 無引用）。`sqlite_db.rs`/`json_db.rs`（v2 shadow）維持現狀或移到 legacy module 加退役註解。
**DoD**：腳本有明確退役指引或已移除；無 CI/排程引用。
**驗證程序**：`G4` → `rg "db-sync" .github`（確認無引用）。

## T14 — 文件措辭更正（D2-4/D7-5）

**修復方法**：`wiki/architecture/overview.md:117` 把 `pkg/contracts` 從「Scanner/Mover/HistoryService 介面」改述為「DTO 結構」；`tools-rs/src/main.rs:16-18,33-50` 的 about 字串把 `db-import-json` 標 deprecated（與實際 deprecation 分層一致）。改 wiki 後須跑 `python wiki/gen_data.py` 重新產生 `wiki/wiki-data.js`。
**DoD**：文件與實際分層一致；wiki viewer 顯示更新內容。
**驗證程序**：`python wiki/gen_data.py`（必要時 `PYTHONIOENCODING=utf-8`）→ `G4`。

## T15 — 補契約鎖 argv 測試（D1-2~D1-5）

**修復方法**：在 `tests/test_go_cli_contracts.py` 仿 `db_backup_cleanup` 的 `captured["args"] == [...]` 樣板，為 `cache_get/set/delete/prune/clear/get_stats`、`history rollback/rollback_last/list_operations`、`move_file/batch_move` 補 argv 鎖。
**DoD**：每個線上 wrapper 都有 argv 斷言；flag 改名會被測試攔到。
**驗證程序**：`G6`（特別是 `test_go_cli_contracts.py`）。

---

# 勿動清單（守門 — 任何清理 PR 都不可碰）

| 對象 | 原因 |
|------|------|
| `SQLiteStore.Compact()` / `CompactIfNeeded()`（D6-1/D6-2） | 故意 no-op，**wails 生產碼仍呼叫** |
| CLI `db compact` 的 `compactNoopPayload`（D6-5）、Python `compact/compact_if_needed`（D3-6） | 故意 no-op，**Python helper contract 依賴** |
| `db stats` 保留欄位 `journal_size/needs_compact/dirty_videos/sync_degraded_total/sqlite_read_fallback_total`（D1-6） | 故意 zero/false 值，刪掉打壞 Python helper |
| `database.NewVideo`（D8-6）、`Mover.BatchMoveDirs`（D8-7）、`Mover.GetOperation`（D8-8） | `deadcode ./cmd/scanner` 假陽性，**實為 wails GUI 活路徑**（app.go:747/281/399 → 前端） |
| `pkg/cache` 的 `Get/Set/Delete/Stats/Clear/AutoCleanup`（D8-14） | CLI + Python live 使用，只有 T10 那 5 個是死的 |
| §B4 測試專用符號（`DatabaseError`、`types.go` 工廠群、`safefile.ReadAll`，D8-10~12） | 生產死碼但服務現有測試；刪除須連測試一起評估，不在死碼清理範圍內 |

---

# 全域完成條件 + 最終驗證

**全部任務完成後，依序執行並全綠：**

1. `G1` `G2`（Go root build+vet+test）
2. `G3`（Wails backend build+vet+test）
3. `G4`（Rust test）
4. `G5`（Schema-drift 四道鎖）
5. `G6`（Python pytest + 契約鎖）
6. `G7`（CI 釋出閘 migrate-from-json + verify-sync）
7. `G8`（`deadcode ./cmd/scanner` 確認目標死碼消失、無新增不可達）
8. **`/tool-scan`**（lint / format / 安全 / CVE / secret 全 repo 掃描）→ 與修正前 baseline 比對，**無 P0/P1 新增問題**。

> ⚠️ **`/tool-scan` 是修正完成後的最終閘**：必須在 T1–T15 對應的 fix 實際落地（程式碼已改）之後才執行，用來確認清理 / 修補沒有引入新的 lint / 安全 / secret 問題。**不要在尚未動手修正前、對未改動的 baseline 跑**——那只會掃到既有狀態，對驗證本批修正毫無意義。
>
> 註：清理型 PR 建議拆成「純搬移（T7）」與「刪除（T8）」兩個 commit，便於 review 與回溯。
