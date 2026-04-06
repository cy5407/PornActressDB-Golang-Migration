# 專案程式碼巡檢持續追蹤報告

最後更新：2026-04-06 17:41 (Asia/Taipei)
基準提交：`da535ca` `fix(extractor): siteRe 通用化`

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
