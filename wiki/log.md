# Log

> append-only，每次 ingest / 重大更新 / 踩坑修復 後追加一筆。
> 格式：`## [YYYY-MM-DD] <類型> | <摘要>`
> 類型：`init` / `feature` / `fix` / `refactor` / `pitfall` / `lint`

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

