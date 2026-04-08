# Log

> append-only，每次 ingest / 重大更新 / 踩坑修復 後追加一筆。  
> 格式：`## [YYYY-MM-DD] <類型> | <摘要>`  
> 類型：`init` / `feature` / `fix` / `refactor` / `pitfall` / `lint` / `docs` / `ingest`  
> **排序：最新在上**

## [2026-04-08] fix | DB journal 未合併、資料格式不一致、資料庫合併

**commits**：`ad7d278`（compact fix）、`33ed079`（search_status fix）

### 問題一：journal 資料永遠不寫入 data.json（完整修正）

原有修正只補了 `BatchSearch()` 末尾的 `Compact()`，但漏了兩個路徑：

| 缺漏路徑 | 症狀 | 修正 |
|---------|------|------|
| `BatchSearch()` 全快取命中早期返回 | 63 筆全命中 → 跳過 compact → data.json 永遠空的 | 補 `CompactIfNeeded()` |
| `ensureDB()` 啟動時 | App 重啟後 journal 仍殘留 | 補 `CompactIfNeeded()` |

詳見：[pitfalls/wails-db-json-never-updated.md](pitfalls/wails-db-json-never-updated.md)

### 問題二：search_status 格式不一致

Go backend 寫入 `"success"`，資料庫標準為 `"searched_found"`，造成雙值並存。

- `app.go` 寫入改為 `"searched_found"`
- 快取判斷移除多餘的雙重條件
- 一次性腳本修正現有資料：63 筆 `success`→`searched_found`、6 筆 `searched_multiple`→`searched_found`、47 筆 `JAVDB (安全增強版)`→`JAVDB`、63 筆空白 `search_method`→`cascade`

詳見：[pitfalls/wails-db-format-migration.md](pitfalls/wails-db-format-migration.md)

### 問題三：`data.json` 僅有 63 筆，原始資料未合併

`dist/data/json_db/data.json`（2903 筆）合併進 `wails-app/build/bin/data/json_db/data.json`：
- 63 筆重疊 → 保留較新版本（`updated_at` 較近）
- 新增 2840 筆
- 合併後 2903 筆，journal 清空

---

## [2026-04-08] feature | W7 片商分類移動功能實作完成

**branch**：`feature/w7-studio-classification`  
**commits**：55fd292 → 62b6747（6 commits）

### 實作內容

| Task | 說明 | 修改檔案 |
|------|------|---------|
| T1 | `GetActressPrimaryStudio(actressName)` TDD + 品質修復（db.loaded + nil check）| `pkg/database/jsondb.go`, `jsondb_test.go` |
| T2 | `majorStudios` 欄位、`loadMajorStudios()`、`GetActressPrimaryStudios()` binding | `wails-app/backend/app.go` |
| T3 | 手動新增 Wails stubs（build 後自動覆蓋生成）| `App.js`, `App.d.ts` |
| T4 | `handleStudioMove()` + 「🏢 片商分類」按鈕 | `wails-app/frontend/src/App.tsx` |
| T5 | `wails build` 驗證（build/bin/actress-classifier.exe）| — |

### 路徑規則
- 大片商（major_studios.json）→ `outputDir\片商名\女優名\番號.ext`
- 非大片商 → `outputDir\單體企劃女優\女優名\番號.ext`
- 無女優資料 → `outputDir\未分類\番號.ext`

---

## [2026-04-07] docs | W7 片商分類設計完成

**Wiki 新增**：[architecture/studio-classification.md](architecture/studio-classification.md)

設計重點：
- 路徑：`outputDir\片商名\女優名\番號.ext`
- 判定規則：查 DB 作品最多的片商 → 對照 `major_studios.json`
- 大片商 → 片商名資料夾；非大片商 → 單體企劃女優；無女優 → 未分類
- 實作分三層：`pkg/database`（DB 統計）、`app.go`（binding）、`App.tsx`（按鈕）

---

## [2026-04-07] fix | Wails 六大問題全修復（T1-T6）

**commit**：e2b0289  

| Task | 說明 | 修改檔案 |
|------|------|---------|
| T1 | `getStatus` 加 `title` 判定，有標題無女優不標記 failed | `SearchResultDialog.tsx` |
| T2 | `BatchSearch workers` 讀 `config.ThreadCount`，前端傳 0 | `app.go`、`App.tsx` |
| T3 | 移動後從 `scanResults` 清除已成功移動項目 | `App.tsx` |
| T4 | `dbOnce` 改為 `mutex+nil`，`UpdatePreferences/ResetPreferences` 後重置 DB | `app.go` |
| T5 | 移動路徑改為 `outputDir\女優名\番號.ext`，無資料放「未分類」 | `App.tsx` |
| T6 | 移動前顯示 N 個檔案 → M 個資料夾的預覽訊息 | `App.tsx` |



**涉及檔案**：
- `wiki/pitfalls/wails-move-stale-paths.md` — 新建：移動後 scanResults 路徑未更新
- `wiki/pitfalls/wails-dbonce-no-reset.md` — 新建：dbOnce 不會重置（設定變更需重啟）
- `wiki/pitfalls/wails-cache-status-mismatch.md` — 新建：快取狀態判定 Go 後端與前端不一致

**分析結果**（尚未修復）：
1. 移動目標路徑平鋪（無女優分資料夾）——功能設計缺失
2. searchResults 與移動操作脫鉤——設計問題
3. 移動後 scanResults 路徑未更新——已建 pitfall
4. BatchSearch workers 固定寫死 5——忽視 config thread_count
5. dbOnce 不會重置——已建 pitfall
6. 快取狀態判定不一致——已建 pitfall



**涉及檔案**：
- `wiki/pitfalls/wails-db-path-wrong-dir.md` — 新建：DB 寫入 build/bin/ 而非專案根
- `wiki/pitfalls/wails-db-json-never-updated.md` — 新建：CompactIfNeeded 從未被呼叫
- `wails-app/backend/app.go` — resolveConfigPath 往上找 config.ini；BatchSearch 末尾加 Compact()

**踩坑**：
1. `resolveConfigPath` 只找 exe 同目錄，dev 模式下找不到 project root 的 config.ini，DB 落到 `build/bin/data/json_db/`
2. `CompactIfNeeded()` 從未被呼叫，63 筆搜尋遠低於 1000 筆閾值，`data.json` 永遠不更新，快取完全失效

**修法**：`resolveConfigPath` 增加往上 3 層的候選路徑；`resolveDataDir`/`resolveLogDir` 改為相對 config.ini 目錄解析；`BatchSearch` 末尾強制 `Compact()`。

## [2026-04-07] pitfall | Wiki Viewer 導覽選單與 wiki-data.js 脫鉤

**涉及檔案**：
- `wiki/pitfalls/wiki-viewer-nav-out-of-sync.md` — 新建踩坑文件
- `wiki/viewer.html` — 補入 3 個遺漏的 Wails 條目
- `.agents/skills/wiki-maintenance/SKILL.md` — 強化 Step 5 警示

**問題**：`gen_data.py` 自動產生 `wiki-data.js`（含頁面內容），但 `viewer.html` 的導覽選單是獨立手動維護的 JS 陣列，兩者脫鉤——新增 `.md` 後忘了同步 viewer.html，導致 3 個 Wails 踩坑頁面在選單消失。

**修法**：手動補入 viewer.html nav 陣列；SKILL.md Ingest/Pitfall 步驟加 ⚠️ 提示。

## [2026-04-07] perf | Wails 批次搜尋效能優化 75s→10s（7.5x）

**涉及檔案**：
- `src/scrapers/run_batch_search.py` — thread-local + rate limiter 停用
- `wails-app/backend/app.go` — workers 升至 20
- `wiki/pitfalls/wails-search-perf.md` — 新建效能優化踩坑文件
- `wiki/pitfalls/wails-scan-duplicate.md` — 補充四輪效能數據
- `docs/茶包射手/wails-e2e-scan.md` — 更新完整效能歷程表

**四輪優化歷程（63 筆，1G 網路）**：
1. 原始：75s（每筆獨立 Python process）
2. batch script：39s（單一 process + ThreadPoolExecutor(15)）
3. 主 thread 預建 searcher（反效果）：50s（串行初始化 14s）
4. **thread-local 並行初始化 + 停用 rate limiter：🚀 10s**

**關鍵發現**：
- Rate limiter（min/max_interval=0.5/1.5s）在批次模式完全無效（各 thread 獨立 SafeSearcher，不共用 `last_request_time`）
- GIL 在 I/O 密集段自動讓步，threads 並行初始化比主 thread 串行更快

## [2026-04-07] pitfall | Wails 掃描重複番號 & E2E 效能記錄

**涉及檔案**：
- `wails-app/backend/app.go` — `ScanDirectory()` 加入 `seen map` 去重
- `wiki/pitfalls/wails-scan-duplicate.md` — 新建踩坑文件
- `docs/茶包射手/wails-e2e-scan.md` — E2E 實測記錄

**問題**：`filepath.WalkDir` 不去重，同番號（`EBON-004`、`CEMD-818`）出現兩次，導致重複搜尋。

**修法**：`seen map` 在 Go 端去重，progress counter 改為顯示有效番號序號。

**E2E 效能（2026-04-07 實測）**：掃描 99 個檔案 <1 秒；搜尋 65 筆約 75 秒（1.15 秒/筆，5 workers）；成功率 100%。

---

## [2026-04-07] feature | Wails W1~W6 全部實作完成（Nova agent）

**涉及檔案**：
- `wails-app/` — 新建 Wails v2 + React TypeScript 完整專案
- `wails-app/backend/app.go` — 17 個 Go bindings（ScanDirectory、MoveFile、BatchMove、DB、Studio、Preferences、PythonSearch、BatchSearch）
- `wails-app/backend/services/config.go` — ConfigService（config.ini 讀寫）
- `wails-app/frontend/src/components/` — 所有 UI 元件（MainLayout、VideoList、SearchPanel、ProgressBar、StatusBar、三個對話框）
- `wails-app/frontend/src/stores/taskStore.ts` — Zustand 狀態管理
- `src/scrapers/run_search.py` — Python 爬蟲 CLI 入口（subprocess 呼叫入口）
- `wiki/architecture/wails-gui.md` — 新建架構文件

**移除**：
- `src/ui/`（~2,588 行 Tkinter GUI）
- `src/services/go_bridge.py` / `go_runner.py` / `go_api/`（~1,587 行橋接層）
- `src/services/classifier_core.py` / `interactive_classifier.py` / `studio_classifier.py`（~2,606 行）
- 孤立模組：`encoding_enhancer.py`、`japanese_site_enhancer.py`、`unified_scraper.py`（~944 行）

**累計移除**：W1~W6 共 **~7,725 行** Python 程式碼

---

## [2026-04-07] docs | 技術選型決策紀錄建立

**涉及檔案**：
- `wiki/architecture/tech-stack-decisions.md` — 新建

**內容**：
- 爬蟲層語言比較（Python vs Node.js vs Go vs Rust），結論：Python 保留
- GUI 層比較（Tkinter vs PyQt6 vs Wails vs Tauri），長期目標：Wails
- 未來升級路線：Wails (Go-based GUI) 可讓整個 Python 橋接層消失
- 語言分工原則確立（Phase 10 後）

---

## [2026-04-07] refactor | p12~p16 Python 程式碼縮減（src/ -976 行）

**涉及檔案**：
- `src/services/go_bridge_test.py` → **移到 `tests/test_go_bridge.py`**（p12，-592 行 from src）
- `src/models/json_database.py` — 移除 Python filelock 機制（p13，-88 行）
- `src/models/incremental_json_database.py` — journal dead code 清除（p14，-60 行）
- `src/services/classifier_core.py` — dead code + 重複邏輯精簡（p16，-130 行）
- `src/services/studio_classifier.py` — `_identify_major_studios()` + 重複常數精簡（p15，-33 行）

**統計**：
- src/ 行數：16,362 → **15,386 行**（-976 行，-6.0%）
- 測試：276 passed

**p15 委派 Go 結論**：統計分析方法目前無法委派（Go 缺 AnalyzeDistribution API），記錄為未來任務。

---

## [2026-04-07] refactor | Phase 10 Go guards 全移除（247 tests pass）

**涉及檔案**：
- `src/models/json_database.py` — 移除 `_GO_DB_AVAILABLE` flag + 13 個 guard 分支
- `src/models/incremental_json_database.py` — 移除 `_GO_DB_AVAILABLE` 類別屬性 + 4 個 guard
- `src/scrapers/cache_manager.py` — 移除 `_GO_CACHE_AVAILABLE` flag + set/get/delete early-return guard

**結果**：
- 三個模組全部改為直接委派 Go，無 availability check 包裹
- try/except import 改為直接 import（Go api 必須可用）
- `test_incremental_db_go_delegation.py` / `test_json_db_go_delegation.py` 更新對應測試
- 247 tests passed, 0 failed

---

## [2026-04-07] feat | extractor siteRe 通用化（支援任意 *.com@ 前綴）

**涉及檔案**：
- `pkg/extractor/extractor.go` — siteRe 從 `hhd800.com@|xxx.com-` 改為通用 `(?i)^([a-z0-9.-]+\.com[@-])`
- `pkg/extractor/extractor_test.go` — 補 `489155.com@MIMK-273`、`abc123.com@STARS-001` 等測試
- `tests/test_extractor.py` — 補 Python 側委派測試

**原因**：用戶發現 `489155.com@MIMK-273` 資料夾前綴未被剝除，舊 siteRe 只硬編碼兩個特定網域。

---

## [2026-04-07] docs | Phase 9D 文件收尾完成

**涉及檔案**：
- `wiki/log.md` — 新增 Phase 9 完成記錄
- `wiki/architecture/go-bridge.md` — 更新遷移進度表
- `docs/superpowers/plans/2026-04-06-phase-9-migration.md` — 勾選 Phase 9D 文件收尾完成

**內容**：
完成 Phase 9D 文件收尾，將 Phase 9A / 9B / 9C 的完成狀態回寫到 wiki 與遷移計畫，補齊 Go Bridge 進度表與最終完成記錄，並重新產生 `wiki-data.js`。

**更新重點**：
- Phase 9A：e2e 整合測試
- Phase 9B：GoBridgeError 語意細化
- Phase 9C：IncrementalJSONDB 委派 Go
- `wiki/gen_data.py`：已重新產生 wiki 資料索引

---

## [2026-04-06] docs | OpenClaw 遷移審閱計畫建立

**涉及檔案**：
- `openclaw-review/OPENCLAW_PLAN.md` — 新建

**內容**：
建立 OpenClaw 審閱計畫文件，供外部工具（OpenClaw）執行 Python→Go 遷移完整度稽核。

計畫包含四大任務：
1. **Python 端逐方法審閱**（11 個檔案，逐方法標記 ✅⚠️❌🔵）
2. **Go 端完整性確認**（10 個 Go 檔案，確認 CLI 子命令、JSON 格式、測試覆蓋）
3. **Phase 9+ 可遷移項目評估**（含「不應遷移」清單）
4. **產出 `OPENCLAW_AUDIT_2026-04-06.md` 報告**

稽核重點：
- Python 委派呼叫的 Go CLI 子命令必須真正存在（pkg 層 + CLI 層分別確認）
- `_GO_DB_AVAILABLE` 的 false 分支是否全改成 `raise RuntimeError`
- incremental_json_database.py journal 邏輯是否有遷移空間

---

## [2026-04-06] refactor | Phase 8 — 移除 Phase 7 殘留 Python fallback

**涉及檔案**：

| 檔案 | 移除內容 | 行數 |
|------|---------|------|
| `src/models/json_database.py` | create_backup/restore_from_backup/get_backup_list/cleanup_old_backups fallback | -82 行 |
| `src/scrapers/cache_manager.py` | cleanup_expired/cleanup_by_size/get_cache_stats/clear_all/auto_cleanup fallback | -222 行 |

**程式碼變動**：-328 行重複 Python 程式碼

**保留唯一例外**：
- `get_actress_info()` 第 1 行記憶體 fallback：`return self.data.get("actresses", {}).get(actress_id)`
- 理由：符合 Phase 6 原則（記憶體讀取，非 IO 操作）

**設計原則確立**：
> backup、cache cleanup 等「工具性功能」同樣適用 Phase 6 原則 —— 凡涉及磁碟寫入/刪除，Go 不可用時一律 `raise RuntimeError`，不接受降級。  
> 唯一合法的 Python fallback 是從 `self.data`（已載入記憶體）直接讀取，且僅限讀取操作。

**測試結果**：226 passed，0 failed（1.78s）

---

## [2026-04-06] refactor | Phase 7 全部完成 — 深度 Go 委派

**涉及檔案**：

| 檔案 | 變更內容 |
|------|---------|
| `pkg/database/jsondb.go` | 新增 10 個方法：GetActress/UpsertActress/DeleteActress/ListActresses/GetActressStats/GetStudioStats/BackupCreate/BackupRestore/BackupList/BackupCleanup |
| `cmd/scanner/db_cmd.go` | 新增子命令：actress-get/update/delete/list、stats --actress/--studio、backup-create/restore/list/cleanup |
| `src/services/go_api/db.py` | 新增 12 個橋接函式（actress CRUD + stats + backup） |
| `src/services/go_api/cache.py` | 新增 3 個橋接函式（cache_get_stats/cache_prune/cache_clear） |
| `src/scrapers/cache_manager.py` | 5 個方法委派 Go（cleanup_expired/cleanup_by_size/get_cache_stats/clear_all/auto_cleanup） |
| `src/models/json_database.py` | 委派 Go 新增 8 個方法；Phase 7E 移除 Python fallback **-137 行** |

**程式碼變動**：
- Phase 7A-7D：+1,296 行
- Phase 7E：-137 行
- 總淨變動：**+1,159 行**（新增 Go 功能 + 精簡 Python 殼）

**關鍵決策**：
- Actress 寫入操作：Go 不可用 → `raise RuntimeError`（與 Phase 6 寫入策略一致）
- Actress 讀取操作：Go 不可用 → 記憶體 cache 返回（`self.data["actresses"].get(id)`）
- 統計查詢：`if result:` → `if result is not None:`（修正空陣列被誤判為 Go 失敗的 bug）
- Backup：Phase 8 後已全面改為 `raise RuntimeError`

**測試結果**：226 passed，0 failed（1.74s）

---

## [2026-04-06] refactor | Phase 6 — 全數移除 Python fallback（~1,440 行）

**涉及檔案**：
- `src/models/extractor.py` — 刪除 `_extract_code_python()` 等（6A-1）
- `src/models/studio.py` — 刪除 `_identify_studio_python()`（6A-2）
- `src/utils/scanner.py` — 刪除 rglob fallback（6A-3）
- `src/utils/file_mover.py` — 刪除 shutil fallback（6A-4）
- `src/scrapers/cache_manager.py` — 刪除 `_set/get/delete_python()`（6B-1）
- `src/models/go_accelerated_db.py` — **整個刪除**（6C-1）
- `src/models/go_accelerated_studio.py` — **整個刪除**（6C-2）
- `src/models/incremental_json_database.py` — 刪除 2 個 Python 方法（6D-1）
- `src/models/json_database.py` — 刪除 4 個 Python 方法（6D-2）

**程式碼變動**：
- +526 / **-1,966 行**，淨刪除 **-1,440 行**
- 測試速度：167s → 1.9s（**88x**，移除整合測試後）
- 最終測試：226 passed，0 failed（1.79s）

**關鍵設計決策**：
- 寫入操作 Go 不可用 → `raise RuntimeError`（不接受降級）
- 讀取操作 Go 不可用 → 從記憶體 cache 返回
- `_get_video_info_python` 只是 memory 讀取，直接 inline（非 IO fallback）
- `code_to_studio` 雖由 `_identify_studio_python` 建立，仍需保留供 `normalize_studio_name()` 使用

**新增 wiki**：
- `wiki/patterns/remove-python-fallback.md` — 完整 fallback 移除策略與流程

---

## [2026-04-06] fix | CI/CD Issues 16-21 — GitHub Actions 連鎖問題修正

**背景**：規劃 Phase 6（刪除 Python fallback）並設定 GitHub Actions 自動執行期間，連續發現六個 CI/CD 問題。

| Issue | 問題 | 修正 |
|-------|------|------|
| 16 | Guard 誤判 Linux classifier binary（無副檔名）為 out-of-scope | Guard 前 `rm -f classifier classifier.exe` + regex 白名單加 `classifier(\.exe)?$` |
| 17 | `git add <已刪除路徑>` 靜默失敗，Phase 6C 整檔刪除不被記錄 | 改用 `git add -u src/` 追蹤刪除 |
| 18 | timeout 45min + continues 5 每次只能完成一個小任務 | timeout 45→90、continues 5→20 |
| 19 | Phase 6 九個任務需手動逐次觸發 | 鏈式觸發設計：成功後自動 `gh workflow run` |
| 20 | `_find_exe()` 只找 `classifier.exe`，Linux CI 找不到 `classifier` | `_find_exe()` 跨平台修正；`.gitignore` 補 Linux binary |
| 21 | Guard step `rm -f classifier.exe` 刪除後，Test step 找不到 CLI | Test step 前加 `go build -o classifier.exe ./cmd/scanner` |

**涉及檔案**：
- `.github/workflows/copilot-refactor-go.yml`
- `src/services/go_bridge.py` — `_find_exe()` 跨平台修正
- `.gitignore` — 補上 Linux binary（classifier, scanner, ralph-loop）

**踩坑**：Issue 16-21（見 pitfalls/github-actions-issues.md）

---

## [2026-04-06] ingest | Wiki 知識庫全量餵入

**觸發原因**：掃描 16 個既有資料來源，批次建立所有缺失的 wiki 頁面

**新增頁面**：
- `wiki/architecture/overview.md` ← README.md + AGENTS.md
- `wiki/architecture/go-cli.md` ← cmd/scanner/main.go
- `wiki/architecture/go-bridge.md` ← MIGRATION_STATUS.md + go_bridge.py
- `wiki/architecture/database.md` ← incremental_json_database.py
- `wiki/architecture/search-engine.md` ← avwiki_scraper.py + README
- `wiki/patterns/naming-conventions.md` ← CODING_STANDARDS.md（完整版）
- `wiki/patterns/pyinstaller.md` ← 女優分類系統_修復版.spec
- `wiki/patterns/zero-actress-retry.md` ← QUICK_START_GUIDE.md
- `wiki/pitfalls/github-actions-issues.md` ← docs/茶包射手/（Issue 1-15 摘要）

---

## [2026-04-06] feature | DB 片商批次修正功能 (db fix-studios)

**涉及檔案**：
- `cmd/scanner/db_cmd.go` — 新增 `fix-studios` 子命令
- `src/services/go_api/db.py` — 新增 `db_fix_studios()`
- `src/services/go_api/__init__.py` — 匯出補齊
- `src/services/go_bridge.py` — 重匯出補齊
- `src/ui/main_gui.py` — 新增「🔧 修正片商資料」按鈕

**踩坑**：Issue 13、14、15（見 pitfalls/）

---

## [2026-04-06] fix | JAVDB False Positive

**涉及檔案**：`src/services/safe_javdb_searcher.py`  
**踩坑**：Issue 12（見 pitfalls/javdb-false-positive.md）

---

## [2026-04-06] fix | PyInstaller 打包路徑修正

**涉及檔案**：`src/models/studio.py`  
**踩坑**：PyInstaller 打包後 studios.json 應從 sys._MEIPASS 讀取（見 pitfalls/pyinstaller-path.md）

---

## [2026-04-06] init | Wiki 初始建立

**內容**：
- 根據專案現況（v6.0.0）建立 wiki/ 初始結構
- 涵蓋架構總覽、5 個開發模式、5 個踩坑紀錄
- 來源：CLAUDE.md、AGENTS.md、茶包射手 Issue 1-15、本輪 session

**觸發原因**：
本次新增「DB 片商批次修正」功能期間，連續發生三個可預防的 Bug（Issue 13-15），根因都是缺乏明確的開發模式文件，AI 和開發者都沒有可查閱的快速參考。


**涉及檔案**：
- `openclaw-review/OPENCLAW_PLAN.md` — 新建

**內容**：
建立 OpenClaw 審閱計畫文件，供外部工具（OpenClaw）執行 Python→Go 遷移完整度稽核。

計畫包含四大任務：
1. **Python 端逐方法審閱**（11 個檔案，逐方法標記 ✅⚠️❌🔵）
2. **Go 端完整性確認**（10 個 Go 檔案，確認 CLI 子命令、JSON 格式、測試覆蓋）
3. **Phase 9+ 可遷移項目評估**（含「不應遷移」清單）
4. **產出 `OPENCLAW_AUDIT_2026-04-06.md` 報告**

稽核重點：
- Python 委派呼叫的 Go CLI 子命令必須真正存在（pkg 層 + CLI 層分別確認）
- `_GO_DB_AVAILABLE` 的 false 分支是否全改成 `raise RuntimeError`
- incremental_json_database.py journal 邏輯是否有遷移空間

---

## [2026-04-06] init | Wiki 初始建立

**內容**：
- 根據專案現況（v6.0.0）建立 wiki/ 初始結構
- 涵蓋架構總覽、5 個開發模式、5 個踩坑紀錄
- 來源：CLAUDE.md、AGENTS.md、茶包射手 Issue 1-15、本輪 session

**觸發原因**：
本次新增「DB 片商批次修正」功能期間，連續發生三個可預防的 Bug（Issue 13-15），根因都是缺乏明確的開發模式文件，AI 和開發者都沒有可查閱的快速參考。

---

## [2026-04-06] feature | DB 片商批次修正功能 (db fix-studios)

**涉及檔案**：
- `cmd/scanner/db_cmd.go` — 新增 `fix-studios` 子命令
- `src/services/go_api/db.py` — 新增 `db_fix_studios()`
- `src/services/go_api/__init__.py` — 匯出補齊
- `src/services/go_bridge.py` — 重匯出補齊
- `src/ui/main_gui.py` — 新增「🔧 修正片商資料」按鈕

**踩坑**：Issue 13、14、15（見 pitfalls/）

---

## [2026-04-06] fix | JAVDB False Positive

**涉及檔案**：`src/services/safe_javdb_searcher.py`
**踩坑**：Issue 12（見 pitfalls/javdb-false-positive.md）

---

## [2026-04-06] fix | PyInstaller 打包路徑修正

**涉及檔案**：`src/models/studio.py`
**踩坑**：PyInstaller 打包後 studios.json 應從 sys._MEIPASS 讀取（見 pitfalls/pyinstaller-path.md）

---

## [2026-04-06] ingest | Wiki 知識庫全量餵入

**觸發原因**：掃描 16 個既有資料來源，批次建立所有缺失的 wiki 頁面

**新增頁面**：
- `wiki/architecture/overview.md` ← README.md + AGENTS.md
- `wiki/architecture/go-cli.md` ← cmd/scanner/main.go
- `wiki/architecture/go-bridge.md` ← MIGRATION_STATUS.md + go_bridge.py
- `wiki/architecture/database.md` ← incremental_json_database.py
- `wiki/architecture/search-engine.md` ← avwiki_scraper.py + README
- `wiki/patterns/naming-conventions.md` ← CODING_STANDARDS.md（完整版）
- `wiki/patterns/pyinstaller.md` ← 女優分類系統_修復版.spec
- `wiki/patterns/zero-actress-retry.md` ← QUICK_START_GUIDE.md
- `wiki/pitfalls/github-actions-issues.md` ← docs/茶包射手/（Issue 1-15 摘要）

---

## [2026-04-06] fix | Guard step 刪除 binary 導致 Test step 失敗（Issue 21）

**涉及檔案**：`.github/workflows/copilot-refactor-go.yml`

**根因**：Guard step `rm -f classifier classifier.exe` 刪除 binary 後，Test step 無法找到 Go CLI，`is_available = False`，Phase 6A-1 移除 Python fallback 後所有 extract_code 測試失敗。

**修正**：Test step 前加 `go build -o classifier.exe ./cmd/scanner` 重新建置。

**踩坑**：Issue 21（見 pitfalls/github-actions-issues.md）

**涉及檔案**：
- `src/services/go_bridge.py` — `_find_exe()` 跨平台修正
- `.gitignore` — 補上 Linux binary（classifier, scanner, ralph-loop）

**根因**：`_find_exe()` 只搜尋 `classifier.exe`，在 Linux CI 上找不到 `classifier`（無副檔名），導致 `is_available = False`。Phase 6A-1 移除 Python fallback 後，所有番號提取返回 None（靜默失敗）。

**踩坑**：Issue 20（見 pitfalls/github-actions-issues.md）

**背景**：規劃 Phase 6（刪除 Python fallback）並設定 GitHub Actions 自動執行期間，連續發現四個 CI/CD 設定問題。

**Issue 16：Guard 誤判 Linux classifier binary**
- `go build` 在 Linux 產生 `classifier`（無副檔名）被 Guard 視為 out-of-scope 新建檔案
- 修正：Guard 前 `rm -f classifier classifier.exe` + regex 白名單加 `classifier(\.exe)?$`

**Issue 17：`git add` 無法 stage 刪除操作**
- `git add <已刪除路徑>` 靜默失敗，Phase 6C 整檔刪除不被記錄
- 修正：改用 `git add -u src/` 追蹤刪除，再補 `git add src/` 追蹤新建

**Issue 18：執行時間與深度不足**
- `timeout-minutes: 45` + `--max-autopilot-continues 5` 每次只能完成一個小任務
- 修正：timeout 45→90、continues 5→20、prompt 允許同 Phase 最多 3 任務

**Issue 19：Phase 6 九個任務需手動逐次觸發**
- 完整鏈式觸發設計：成功後自動 `gh workflow run`，prompt TODO 歸零時停止
- 需要 `permissions: actions: write`，失敗時 Guard 自動阻斷無限迴圈

---

## [2026-04-06] refactor | Phase 8 — 移除 Phase 7 殘留 Python fallback

**涉及檔案**：

| 檔案 | 移除內容 | 行數 |
|------|---------|------|
| `src/models/json_database.py` | create_backup/restore_from_backup/get_backup_list/cleanup_old_backups fallback | -82 行 |
| `src/scrapers/cache_manager.py` | cleanup_expired/cleanup_by_size/get_cache_stats/clear_all/auto_cleanup fallback | -222 行 |

**程式碼變動**：-328 行重複 Python 程式碼

**保留唯一例外**：
- `get_actress_info()` 第 1 行記憶體 fallback：`return self.data.get("actresses", {}).get(actress_id)`
- 理由：符合 Phase 6 原則（記憶體讀取，非 IO 操作）

**設計原則確立**：
> backup、cache cleanup 等「工具性功能」同樣適用 Phase 6 原則 —— 凡涉及磁碟寫入/刪除，Go 不可用時一律 `raise RuntimeError`，不接受降級。
> 唯一合法的 Python fallback 是從 `self.data`（已載入記憶體）直接讀取，且僅限讀取操作。

**測試結果**：226 passed，0 failed（1.78s）

---

## [2026-04-06] refactor | Phase 7 全部完成 — 深度 Go 委派

**涉及檔案**：

| 檔案 | 變更內容 |
|------|---------|
| `pkg/database/jsondb.go` | 新增 10 個方法：GetActress/UpsertActress/DeleteActress/ListActresses/GetActressStats/GetStudioStats/BackupCreate/BackupRestore/BackupList/BackupCleanup |
| `cmd/scanner/db_cmd.go` | 新增子命令：actress-get/update/delete/list、stats --actress/--studio、backup-create/restore/list/cleanup |
| `src/services/go_api/db.py` | 新增 12 個橋接函式（actress CRUD + stats + backup） |
| `src/services/go_api/cache.py` | 新增 3 個橋接函式（cache_get_stats/cache_prune/cache_clear） |
| `src/scrapers/cache_manager.py` | 5 個方法委派 Go（cleanup_expired/cleanup_by_size/get_cache_stats/clear_all/auto_cleanup） |
| `src/models/json_database.py` | 委派 Go 新增 8 個方法；Phase 7E 移除 Python fallback **-137 行** |

**程式碼變動**：
- Phase 7A-7D：+1,296 行
- Phase 7E：-137 行
- 總淨變動：**+1,159 行**（新增 Go 功能 + 精簡 Python 殼）

**關鍵決策**：
- Actress 寫入操作：Go 不可用 → `raise RuntimeError`（與 Phase 6 寫入策略一致）
- Actress 讀取操作：Go 不可用 → 記憶體 cache 返回（`self.data["actresses"].get(id)`）
- 統計查詢：`if result:` → `if result is not None:`（修正空陣列被誤判為 Go 失敗的 bug）
- Backup：保留 Python fallback（工具性功能，Python file copy 仍有價值）

**測試結果**：226 passed，0 failed（1.74s）

---



**涉及檔案**：
- `src/models/extractor.py` — 刪除 `_extract_code_python()` 等（6A-1）
- `src/models/studio.py` — 刪除 `_identify_studio_python()`（6A-2）
- `src/utils/scanner.py` — 刪除 rglob fallback（6A-3）
- `src/utils/file_mover.py` — 刪除 shutil fallback（6A-4）
- `src/scrapers/cache_manager.py` — 刪除 `_set/get/delete_python()`（6B-1）
- `src/models/go_accelerated_db.py` — **整個刪除**（6C-1）
- `src/models/go_accelerated_studio.py` — **整個刪除**（6C-2）
- `src/models/incremental_json_database.py` — 刪除 2 個 Python 方法（6D-1）
- `src/models/json_database.py` — 刪除 4 個 Python 方法（6D-2）

**程式碼變動**：
- +526 / **-1,966 行**，淨刪除 **-1,440 行**
- 測試速度：167s → 1.9s（**88x**，移除整合測試後）
- 最終測試：226 passed，0 failed（1.79s）

**關鍵設計決策**：
- 寫入操作 Go 不可用 → `raise RuntimeError`（不接受降級）
- 讀取操作 Go 不可用 → 從記憶體 cache 返回
- `_get_video_info_python` 只是 memory 讀取，直接 inline（非 IO fallback）
- `code_to_studio` 雖由 `_identify_studio_python` 建立，仍需保留供 `normalize_studio_name()` 使用

**新增 wiki**：
- `wiki/patterns/remove-python-fallback.md` — 完整 fallback 移除策略與流程

