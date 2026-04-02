# 專案程式碼巡檢持續追蹤報告

最後更新：2026-04-02 15:00 (Asia/Taipei)
基準提交：`7c71346` `Add automated security scan reports`

## 本輪檢查範圍

- 先讀取既有報告：
  - `security_reports/manual_fix_progress_2026-03-31.md`
  - `security_reports/one_time_fix_schedule_2026-03-31.md`
  - `security_reports/security_fix_summary_2026-03-31.md`
  - `security_reports/code_review_tracking.md`
- 先比對最近提交：
  - `7c71346`、`8e0cf0c`、`ad15933`、`709229c`、`de98fdc` 起的最近 20 筆 commit
- 針對三類問題做增量巡檢：
  - 資安 / 安全性
  - 程式碼冗餘 / 一致性衝突
  - 明顯低效可優化寫法

## 2026-04-02 本輪新增驗證

### 已確認不再列為新問題

1. `src/services/classifier_core.py:31`
   - `IncrementalJSONDB` 初始化失敗時，目前已明確 fallback 到 `JSONDBManager` 並記錄 warning，不再列為待修。

2. `src/scrapers/sources/javdb_scraper.py:64`
   - `Retry-After` 已解析並透過 `ScrapingException.retry_after` 傳遞至 `RateLimiter`，不再列為待修。

3. `src/services/go_bridge.py`
   - 掃描與一般 CLI 呼叫仍統一經過 `_run_command()` timeout 控制；本輪未發現 timeout 回歸。

### 本輪新增待追蹤

1. `src/services/classifier_core.py:443`
   - 類型：一致性 / 可觀測性
   - 問題：
     - `process_and_search_javdb()` 針對既有影片是否需要重新搜尋，會解析 `last_search_date`。
     - 若資料庫內日期格式損壞或混入非 ISO 字串，`fromisoformat()` 例外會被直接吞掉，`should_research` 保持 `False`。
     - 結果是本來應該重新搜尋的舊紀錄會被靜默跳過，尤其是零女優或歷史失敗紀錄，後續可能長期停留在過期狀態。
   - 建議：
     - 至少記錄 warning，並在解析失敗時退回「視為需要重搜」或使用保守 fallback，避免靜默失效。

2. `src/scrapers/enhanced/encoding_handler.py:177`
   - 類型：效能 / 資源管理
   - 問題：
     - `RateLimitedRequester.get()` 每次呼叫都建立新的 `requests.Session()`，但沒有使用 context manager，也沒有明確 `close()`。
     - 這個模組目前看起來未被主流程直接引用，但若被工具腳本或後續功能重新使用，長時間批次抓取會累積未即時釋放的連線資源。
   - 建議：
     - 改成 `with requests.Session() as session:`，或重構成可重用的長生命週期 session。

### 本輪觀察但暫不升級

1. `src/services/unified_cache.py:54`
   - 建構子載入 cache 設定時仍有 `except Exception: pass`。
   - 這會降低設定錯誤的可觀測性，但目前只影響 TTL / 大小上限 fallback，尚未看到直接資料錯誤或安全風險，因此先維持低優先追蹤。

2. `src/scrapers/base_scraper.py:117`
   - `src/scrapers/rate_limiter.py:111`
   - `src/scrapers/enhanced/encoding_handler.py:164`
   - `src/utils/retry_utils.py:56`
   - 這些 `random.uniform()` 仍會被 Bandit 視為 B311 LOW。
   - 目前用途都是 jitter / delay，偏向工具噪音與一致性議題，不列為本輪高價值修補目標。

## 本輪已驗證結論

### 已確認不再列為待修

1. `src/services/web_searcher.py:13`
   - `chardet` 相依已由 `requirements.txt` 明確宣告，這項不再列為阻塞問題。

2. `src/services/web_searcher.py:76`
   - Brotli 相依已由 `requirements.txt` 明確宣告。

3. `src/services/go_bridge.py`
   - 掃描呼叫透過 `_run_command()` 執行，預設 timeout 為 60 秒，「掃描永久掛起」不再是目前狀態。

## 本輪已修正

### 0. 從 detached worktree 回收 scraper 修正，補齊 HTTP 失敗判定與共用背景資源

- 位置：
  - `src/scrapers/async_scraper.py`
  - `src/scrapers/base_scraper.py`
  - `src/scrapers/cache_manager.py`
  - `tests/test_code_review_regressions.py`
- 類型：一致性 / 穩定性 / 效能
- 問題：
  - 先前有三個 detached worktree 殘留未提交修正，其中 scraper 相關兩批內容尚未整併到 `main`。
  - `AsyncWebScraper._make_request()` 會把 HTTP 4xx/5xx 回應當成成功，導致統計與上層行為失真，且 404 這類明確 client error 仍會重試。
  - `BaseScraper`、`AsyncWebScraper` 與 `CacheManager` 預設會重複建立快取管理器與健康檢查器，長時間執行下容易累積重複背景執行緒 / task。
- 修正：
  - 將 `AsyncWebScraper` 改為正確回傳 HTTP 錯誤結果，並新增 `_should_retry_result()`，只對暫時性失敗重試。
  - 新增 `get_global_cache_manager()` 與 `get_global_health_checker()`，改為共用快取、健康檢查與限流器實例。
  - 全域共用物件建立流程補上 `RLock`，避免多執行緒下重複初始化。
  - 補上回歸測試，覆蓋 404 不重試與 scraper 共用背景資源兩個情境。

### 1. `SafeJAVDBSearcher` session 重建會遺留舊連線，且隨機來源與 `SafeSearcher` 不一致

- 位置：
  - `src/services/safe_javdb_searcher.py`
  - `tests/test_safe_javdb_searcher.py`
- 類型：資安一致性 / 資源管理 / 效能穩定性
- 問題：
  - `create_session()` 在達到 session 請求上限或遇到 403 時會重建 `httpx.Client`，但原本直接覆蓋 `self.session`，沒有先關閉舊 client。
  - 長時間執行下會累積未主動釋放的連線資源，屬於低風險但明確可優化的穩定性問題。
  - 同檔案仍使用 `random.choice` / `random.uniform`，與先前已修正為 `secrets` 來源的 `SafeSearcher` 不一致，也會持續被 Bandit 列出低風險告警。
- 修正：
  - 新增 `_random_delay()`，統一使用 `secrets.randbelow` 產生延遲秒數。
  - `create_session()` 改用 `secrets.choice` 選擇 User-Agent，可選標頭改用 `randbelow(2)`。
  - 重建 session 前，若舊物件支援 `close()`，會先顯式關閉舊 client。
  - `__del__()` 的清理錯誤改記錄 debug log，移除 `except: pass`。
  - 補上回歸測試，確認重試等待上限行為未退化，且重建 session 時會關閉舊 client。

### 2. JAVDB 429 `Retry-After` 沒有導入 limiter

- 位置：
  - `src/scrapers/sources/javdb_scraper.py`
  - `src/scrapers/base_scraper.py`
- 類型：資安 / 穩定性 / 反封鎖策略
- 問題：
  - `javdb_scraper.py` 在 429 時雖讀取 `Retry-After`，但沒有解析並傳回 `RateLimiter`。
  - `BaseScraper._scrape_with_protection()` 的失敗紀錄路徑也沒有傳遞 `status_code` / `retry_after` metadata。
- 修正：
  - `ScrapingException` 新增 `retry_after` 欄位。
  - `JAVDBScraper` 解析 `Retry-After` 秒數並寫入 `ScrapingException`。
  - `BaseScraper` 在失敗紀錄時將 `status_code` 與 `retry_after` 傳給 `RateLimiter.record_request(...)`。
- 驗證：
  - `tests/test_code_review_regressions.py::test_safe_scrape_records_retry_after_on_rate_limit`
  - `python -m pytest tests/test_code_review_regressions.py -q -p no:cacheprovider`

### 3. `SafeJAVDBSearcher` 重試路徑會自我死鎖

- 位置：`src/services/safe_javdb_searcher.py`
- 類型：穩定性 / 可用性 / 一致性
- 問題：
  - `safe_request()` 在 `with self._lock:` 內遇到 403 / 429 / timeout 會遞迴呼叫 `self.safe_request(...)`。
  - 原本使用 `threading.Lock()`，重試路徑會嘗試重複取得同一把鎖，造成流程卡死。
- 修正：
  - 將 `_lock` 改為 `threading.RLock()`，讓重試流程可安全重入。
- 補上回歸測試，驗證 403 後可重試並成功返回 response。
- 驗證：
  - `tests/test_safe_javdb_searcher.py`
  - 以 inline Python 驗證：
    - 403 等待超過上限時直接放棄，不進入長時間 sleep。
    - 403 後重入 `safe_request()` 可成功拿到第二次 200 response。

### 4. `go_bridge` 暫存檔清理失敗會造成結果不一致，且重複清理邏輯難追蹤

- 位置：
  - `src/services/go_bridge.py`
  - `src/services/go_bridge_test.py`
- 類型：一致性 / 可觀測性 / 維護性
- 問題：
  - `batch_move()`、`db_update_video()` 各自吞掉 `os.unlink()` 失敗，`identify_studios_batch()` 則直接在 `finally` 呼叫 `os.unlink(temp_file)`。
  - 當暫存檔已被外部程序鎖住或權限異常時，`identify_studios_batch()` 會讓清理例外覆蓋原本成功的 CLI 結果，對外錯誤地回傳空陣列。
  - 同類清理邏輯分散三處，日後追查暫存檔殘留問題不易。
- 修正：
  - 新增 `_cleanup_temp_file()` helper，統一處理暫存檔刪除。
  - 將清理失敗改為 warning log，不再覆蓋主流程結果。
  - `batch_move()`、`db_update_video()`、`identify_studios_batch()` 全部改用同一個 helper。
  - 補上回歸測試，確認 unlink 失敗時 `batch_move()` 與 `identify_studios_batch()` 仍保留原本成功結果。

## 本輪未新增待修高優先問題

- 本輪主要增量問題都已直接修補並完成驗證。
- 尚未看到新的高風險資安缺口、明顯冗餘衝突或可立即安全落地的大型效能退化點。
- 全專案 `bandit -r src` 仍有數個 LOW 告警：
  - 多處 jitter / delay 使用一般亂數（`base_scraper.py`、`rate_limiter.py`、`encoding_handler.py`、`retry_utils.py`）
  - 少量 `except ...` 吞錯或 `subprocess` 靜態提醒
  - 目前未見直接可利用風險，建議後續按模組逐步收斂，不必與本輪修正混在同一批大改。

本輪更新：
- 以上結論維持成立。
- 本次重新掃描 `python -m bandit -q -r src`，結果仍為 10 個 LOW、0 個 Medium / High。
- 本輪沒有發現需要立即建立 `codex/automation-review` branch 的安全可提交修補；因此依 automation 規則只更新報告，不建立 branch、不提交程式碼。

## 本輪驗證指令

```text
python -m pytest tests/test_code_review_regressions.py -q -p no:cacheprovider
結果：5 passed
```

```text
python -m bandit -q -r src/services/safe_javdb_searcher.py
結果：No issues identified.
```

```text
python -m bandit -q -r src
結果：10 個 LOW，0 個 Medium / High
重點：
- B311: jitter / delay 使用一般亂數（4 處）
- B110: 吞錯（3 處）
- B404/B603: go_bridge subprocess 靜態提醒（3 處，屬既知低風險）
```

```text
python -m py_compile src/services/safe_javdb_searcher.py src/scrapers/base_scraper.py src/scrapers/sources/javdb_scraper.py tests/test_code_review_regressions.py tests/test_safe_javdb_searcher.py
結果：通過
```

```text
python -m py_compile src/scrapers/async_scraper.py src/scrapers/base_scraper.py src/scrapers/cache_manager.py tests/test_code_review_regressions.py
結果：通過
```

```text
python -m pytest src/services/go_bridge_test.py -q -p no:cacheprovider
結果：24 passed
```

```text
python -m py_compile src/services/go_bridge.py src/services/go_bridge_test.py
結果：通過
```

```text
python -m bandit -q src/services/go_bridge.py
結果：僅剩預期的 subprocess LOW 告警（B404/B603），未新增中高風險問題
```

```text
inline Python 驗證：
- RateLimiter 會記錄 429 的 retry_after
- SafeJAVDBSearcher 在 403 重試時不再自我死鎖
- SafeJAVDBSearcher 重建 session 時會先關閉舊 client
結果：TARGETED_VALIDATION_OK
```

```text
python -m pytest tests/test_safe_javdb_searcher.py tests/test_code_review_regressions.py -q -p no:cacheprovider
結果：測試內容本身通過，但此 Windows 環境的 pytest 暫存目錄清理會觸發 PermissionError；
因此本輪延續使用工作區內 inline Python 做定向驗證，避免環境噪音影響結論。
```

## 後續建議

1. 若下一輪持續收斂 LOW 告警，優先檢查 `base_scraper.py`、`rate_limiter.py`、`retry_utils.py` 的 jitter 是否要統一為 `secrets` 或明確註記非安全用途。
2. 優先補 `src/services/classifier_core.py:443` 的日期解析 fallback，避免資料髒值讓重新搜尋條件失效。
3. 若要清理舊模組技術債，可先處理 `src/scrapers/enhanced/encoding_handler.py:177` 的 session 生命週期，再決定是否保留這組輔助模組。
4. `pytest` 在這台 Windows 環境建立 / 清理暫存目錄時會遇到 `PermissionError`，後續若要擴充測試建議優先沿用工作區內定向驗證腳本。

