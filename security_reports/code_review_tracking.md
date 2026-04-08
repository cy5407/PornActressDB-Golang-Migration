# 專案程式碼巡檢持續追蹤報告

最後更新：2026-04-08 靜態安全巡檢第三輪（gosec + bandit 全清零）
基準提交：`12ed533` `fix(security): 收緊 generateUniqueName 佔位檔權限`

---

## 本輪巡檢（2026-04-08 第三輪）— gosec + bandit 靜態掃描

### 工具與範圍
- **Go**：`gosec ./...`（所有 pkg/ 與 cmd/）
- **Python**：`bandit -r src`

### 本輪已修復

| ID | 嚴重度 | 位置 | 問題 | 修復內容 |
|----|--------|------|------|----------|
| S1 | MEDIUM | `pkg/mover/file_move.go:95` G302 | `os.OpenFile` 佔位檔使用 `0666` 權限過寬 | 改為 `0600` |
| S2 | LOW | `pkg/mover/file_move.go:97` G104 | `f.Close()` 回傳值未處理 | 改為 `_ = f.Close()` |
| S3 | LOW | `src/utils/scanner.py:5` B404 | `import subprocess` 存在但從未使用 | 移除無用 import |

### 本輪確認為誤報（suppress）

| ID | 嚴重度 | 規則 | 理由 |
|----|--------|------|------|
| FP1 | MEDIUM | G304 `file_move.go:95` | 路徑由程式內部 `filepath.Join(dir, fmt.Sprintf(...))` 生成，非使用者直接輸入；加 `// #nosec G304` |

### 本輪確認為可接受（不修）

| ID | 嚴重度 | 規則 | 位置 | 理由 |
|----|--------|------|------|------|
| A1 | LOW | B404/B603 | `src/utils/go_cli.py`、`src/utils/scanner.py` | 受控本機 CLI 呼叫，`shell=False`，參數列表傳入 |
| A2 | LOW | B110 | `src/models/extractor.py:22` | try/except/pass 用於 import fallback，已有 logger.debug 記錄 |

### 本輪驗證結果

- `gosec ./...`：**0 issues** ✅（修正後）
- `bandit -r src`：**0 Medium / 0 High**（LOW 4 項均為可接受）✅
- `go test ./pkg/mover/...`：**PASS** ✅
- `python -m py_compile src/utils/scanner.py`：**OK** ✅

### git 提交
- `12ed533` push 到 `main`

---

## 本輪巡檢（2026-04-08 第二輪）— P1/P2/P3 修復驗證

### 本輪已修復

| ID | 位置 | 問題 | 修復內容 |
|----|------|------|----------|
| P1 | `pkg/mover/file_move.go` `generateUniqueName` | TOCTOU：建立佔位檔後立即 `os.Remove`，造成競爭窗口 | 移除 `os.Remove`，保留佔位檔以原子方式鎖定路徑；後續 `copyFile(O_TRUNC)` 或 Linux `os.Rename` 原子覆寫 |
| P2 | `pkg/mover/file_move.go` Rename case | DryRun 模式下仍呼叫 `generateUniqueName` 觸碰檔案系統，建立後立即刪除暫存佔位檔 | 在 Rename case 加 `if m.DryRun` guard，乾跑時合成 `_1` 後綴路徑，完全不觸碰檔案系統 |
| P3 | `pkg/mover/batch.go` `batchMoveDirsWithType` | 合併語意後 `mr.DestDir != item.Destination` 永不成立，`moveResult.Renamed = mr.DestDir` 為死碼 | 移除整個 `if` block，並加註說明 Renamed 維持零值的原因 |

### 本輪驗證結果

- `go test ./pkg/mover -v -count=1`：**20/20 PASS** ✅
- `go test ./backend/... -run "PlanDirMerge|IsSameOrNested"`：**4/4 PASS** ✅

### 本輪狀態

- P1 / P2 / P3 修復完成，測試全通過
- 所有 Remove 操作均為搬移語意，無使用者資料刪除操作

---

## 本輪巡檢（2026-04-08）— Wails 片商分類 / 目錄移動追查

### 本輪先讀取的歷史來源
- `git log --oneline -20`
- `AGENTS.md`：「已修復問題紀錄」「已知未解決問題」
- `security_reports/code_review_tracking.md`
- 目前工作樹未提交變更（`pkg/mover/*`、`wails-app/backend/app.go`、`wails-app/frontend/src/App.tsx`）

### 已驗證不再成立的舊問題
- D2 `Rollback(batch_move_dirs)` 完全失效：**已修**
- D3 `append` 後才設 `Skipped`：**已修**
- D5 `handleStudioMove` stale closure：**已修**
- D6 缺少 `setLastBatchResult`：**已修**
- D7 `batchMoveWithType` 冗餘統計欄位：**已修**

### 本輪已修復

| ID | 位置 | 修復內容 |
|----|------|----------|
| D1 | `pkg/mover/dir_move.go` | 只有在無 error、無 skipped、來源可完整清空時才刪除來源資料夾，避免 skipped 檔案被連帶刪掉 |
| D8 | `pkg/mover/dir_move.go` | `MoveDir` 改為逐層建立目標子目錄，空子目錄也會一起搬移 |
| D9 | `pkg/mover/batch.go`、`wails-app/frontend/src/App.tsx` | `BatchMoveDirs` 以 `FilesSkipped == 0 && DeletedSrc` 判定完整成功；前端只移除真正完整搬走的女優資料夾 |
| D10 | `wails-app/frontend/src/App.tsx` | 新增 `normalizeDirKey()` 後再比較 `inputDir` / `parentDir()`，避免 `/` 與 `\` 混用時誤搬根目錄 |
| D11 | `pkg/mover/dir_move.go`、`ConflictResolutionDialog.tsx` | directory `rename` 改為整個目標資料夾改名（如 `Julia_1`），UI 說明同步對齊真實行為 |
| D12 | `wails-app/frontend/src/App.tsx` | 片商分類的 non-conflict / conflict 兩批 `BatchMoveDirs` 結果會合併後再更新 summary、`scanResults`、`lastBatchResult` |

### 本輪驗證方式
- 定向閱讀：
  - `pkg/mover/batch.go`
  - `pkg/mover/dir_move.go`
  - `pkg/mover/rollback.go`
  - `wails-app/backend/app.go`
  - `wails-app/frontend/src/App.tsx`
  - `wails-app/frontend/src/components/ConflictResolutionDialog.tsx`
- 補充使用 code-review agent 檢查目前未提交變更

### 本輪驗證結果
- `go test ./pkg/mover -v`：通過
- `cd wails-app && go build ./backend/...`：通過
- `cd wails-app/frontend && npx tsc --noEmit`：通過

### 本輪狀態
- D1 / D8 / D9 / D10 / D11 / D12 已在目前工作樹修復完成
- 已同步更新 SQL `issues` / `todos` 追蹤表

---

## 本輪巡檢（2026-04-06）— Python→Go 遷移現狀全盤盤點

### 基線
- **測試**：251 passed（`python -m pytest tests/ -q`）
- **分支**：`phase9-migration`（比 `main` 新 3 commits：Phase 9 e2e + error handling + incremental db）
- **Go 檔案數**：31 個（`pkg/` + `cmd/`）
- **Python 檔案數**：52 個（`src/`）

### 已完成（已在 commit 中驗證）

| Phase | 內容 | commit |
|-------|------|--------|
| 6A-6D | Python fallback 全移除（~1217 行）| `8353136` |
| 7-7E  | actress CRUD、backup、json_database 瘦身 | `559f8aa`~`6ddbf39` |
| 8     | 移除 Phase 7 殘留 fallback（-328 行）| `558afed` |
| 9     | OpenClaw e2e + error handling + incremental db | `ae66216` |
| extractor | siteRe 通用化（489155.com@ 等前綴排除）| `da535ca` |

### 本輪發現的殘留問題

| 問題 | 位置 | 影響 |
|------|------|------|
| `_GO_DB_AVAILABLE` guard × 17 | `json_database.py`（1782 行）| 無意義 guard，可移除 ~200 行 |
| `_GO_DB_AVAILABLE` guard × 4 | `incremental_json_database.py`（555 行）| Phase 9C 完成後清除 |
| `_GO_CACHE_AVAILABLE` guard × 3 | `cache_manager.py`（754 行）| 可直接委派 Go |
| `GoBridgeError` 語意不清 | `go_runner.py` | 無法區分 NotFound vs ExecError |
| `add_video`/`delete_video` Python journal | `incremental_json_database.py` | 雙份業務邏輯（Phase 9C 目標）|
| e2e 測試無 CI 自動化 | `.github/workflows/` | 本機需手動執行 classifier.exe 測試 |

### 待辦 Todo（已入 SQL）

| ID | 任務 | 優先 |
|----|------|------|
| `p9-merge` | phase9-migration → main | ⭐⭐⭐ 立即可做 |
| `p9b-exception` | GoBridgeError 語意細化 | ⭐⭐⭐ 立即可做 |
| `p9c-incremental` | IncrementalJSONDB add/delete 委派 Go | ⭐⭐ 待 merge 後 |
| `p10-json-db-guards` | json_database.py 移除 17 個 guards | ⭐⭐ 待 merge 後 |
| `p10-incremental-guards` | incremental_json_database.py guards 清除 | ⭐⭐ 待 p9c |
| `p10-cache-guards` | cache_manager.py guards 清除 | ⭐⭐ 待 merge 後 |
| `p10-slim-db` | json_database.py 瘦身 1782→800 行 | ⭐ 待 p10-json |
| `p11-e2e-ci` | CI 自動執行 e2e 測試 | ⭐⭐ 待 merge 後 |
| `doc-migration-status` | MIGRATION_STATUS.md 補 Phase 7-9 | ⭐ 待 merge 後 |
| `doc-wiki-phase9` | wiki log + go-bridge.md Phase 9 記錄 | ⭐ 待 merge 後 |

---

## 本輪檢查範圍

- 先讀取 automation memory：
  - `C:\Users\cy5407\.codex\automations\automation\memory.md`
- 先讀取既有報告：
  - `security_reports/manual_fix_progress_2026-03-31.md`
  - `security_reports/one_time_fix_schedule_2026-03-31.md`
  - `security_reports/security_fix_summary_2026-03-31.md`
  - 既有 `security_reports/code_review_tracking.md`
- 先比對最近提交：
  - `7c71346`、`8e0cf0c`、`ad15933` 起的最近 20 筆 commit
- 本輪增量檢查與修正方式：
  - `python -m bandit -q -r src`
  - 定向檢查 `base_scraper.py`、`encoding_handler.py`、`rate_limiter.py`、`retry_utils.py`
  - 定向檢查 `classifier_core.py`、`javdb_scraper.py`、`unified_cache.py`、`go_bridge.py`
  - 補上最小回歸測試並重新驗證

## 本輪環境狀態

- 目前工作樹狀態：`HEAD (no branch)`，屬於 detached HEAD。
- 本輪已直接修改程式碼以完成使用者要求的 LOW 修復。
- 本輪未切換到 `codex/automation-review`：
  - 原因是當前工作樹已先有報告檔變更，為避免切 branch 時干擾現場，先在目前工作樹完成最小修正與驗證。

## 本輪已修正

### 1. 移除 4 個 jitter `random.uniform` LOW 告警

- 位置：
  - `src/scrapers/base_scraper.py`
  - `src/scrapers/enhanced/encoding_handler.py`
  - `src/scrapers/rate_limiter.py`
  - `src/utils/retry_utils.py`
- 類型：安全性靜態告警 / 一致性
- 修正：
  - 改用基於 `secrets.randbelow` 的 `_secure_uniform()` helper 產生等待抖動。
  - 保留原本行為語意，不改變重試與限流策略，只移除 Bandit 對一般亂數來源的告警。

### 2. 補回 `classifier_core.py` 的 stale record 日期解析 fallback

- 位置：`src/services/classifier_core.py`
- 類型：錯誤處理 / 可觀測性 / 一致性
- 問題：
  - 原本 `last_search_date` 解析失敗會被 `except Exception: pass` 靜默吞掉。
  - 這會讓應重新搜尋的舊資料被略過。
- 修正：
  - 新增 `_should_research_stale_record()`。
  - 日期無法解析時改記錄 warning，並保守改為重新搜尋。

### 3. 補回 `encoding_handler.py` 的 Session 關閉修正

- 位置：`src/scrapers/enhanced/encoding_handler.py`
- 類型：資源管理 / 穩定性
- 問題：
  - 每次請求建立 `requests.Session()`，但沒有明確關閉。
- 修正：
  - 改為 `with requests.Session() as session:`，確保連線資源可被釋放。

### 4. 收斂兩個吞錯點

- 位置：
  - `src/scrapers/sources/javdb_scraper.py`
  - `src/services/unified_cache.py`
- 類型：可觀測性 / 維護性
- 修正：
  - `javdb_scraper.py` 的評分解析改為只捕捉 `TypeError` / `ValueError`，並記錄 debug log。
  - `unified_cache.py` 的 cache 設定讀取失敗改記錄 warning，保留預設值 fallback。

### 5. 清理 `go_bridge.py` 的 subprocess Bandit 靜態提醒

- 位置：`src/services/go_bridge.py`
- 類型：Bandit 靜態告警 / 可讀性
- 修正：
  - 將 `subprocess.run(...)` 收斂到 `_run_subprocess()` helper。
  - 保持 `shell=False`、參數列表執行。
  - 對受控本機 CLI 呼叫加上 `# nosec B404`、`# nosec B603`。

## 本輪 Bandit 結果

- 修正前：`10 LOW / 0 Medium / 0 High`
- 修正後：`0 LOW / 0 Medium / 0 High`

## 本輪驗證指令

```text
python -m py_compile src/scrapers/base_scraper.py src/scrapers/enhanced/encoding_handler.py src/scrapers/rate_limiter.py src/utils/retry_utils.py src/services/unified_cache.py src/scrapers/sources/javdb_scraper.py src/services/classifier_core.py src/services/go_bridge.py tests/test_code_review_regressions.py
結果：通過
```

```text
python -m pytest tests/test_code_review_regressions.py src/services/go_bridge_test.py -q -p no:cacheprovider
結果：28 passed, 3 skipped
```

```text
python -m bandit -q -r src
結果：0 LOW / 0 Medium / 0 High
```

```text
@'
from src.services.go_bridge import GoBridge
bridge = GoBridge()
print('EXE_PATH', bridge.exe_path)
print('IS_AVAILABLE', bridge.is_available)
'@ | python -
結果：
- EXE_PATH classifier.exe
- IS_AVAILABLE False
- 原因：目前工作樹不存在 classifier.exe，僅能驗證橋接層會正確降級，不可完成實際 CLI smoke test
```

## 本輪未完成項目與原因

1. `go_bridge.py` 的實際 CLI smoke test 未完成
   - 預期命令：`classifier.exe help`
   - 實際狀況：目前工作樹找不到 `classifier.exe`
   - 目前風險：
     - Python 橋接層的受控 subprocess 路徑已由單元測試覆蓋，但本輪無法驗證真實 CLI 可執行。
   - 下一步需要：
     - 在工作樹放置可執行的 `classifier.exe`，或先執行 `go build -o classifier.exe .\cmd\scanner`

## 後續建議

1. 若要把這輪修正納入 automation 正規修復流程，下一步可在 `codex/automation-review` 上整理並重跑一次相同驗證。
2. 若接著要補橋接 smoke test，先建置 `classifier.exe`，再執行 `classifier.exe help`。
3. 若要繼續維持低雜訊巡檢，後續優先看真實功能風險，不必再花時間清同一批 Bandit LOW。
