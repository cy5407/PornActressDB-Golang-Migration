# 專案程式碼巡檢持續追蹤報告

最後更新：2026-04-01 10:42 (Asia/Taipei)
基準提交：`8612d25` `review: harden fallback and record tracking report`

## 本輪檢查範圍

- 先讀取既有報告：
  - `security_reports/manual_fix_progress_2026-03-31.md`
  - `security_reports/one_time_fix_schedule_2026-03-31.md`
  - `security_reports/security_fix_summary_2026-03-31.md`
- 先比對最近提交：
  - `8612d25`、`7651546`、`8148592`、`a35e965` 起的最近 20 筆 commit
- 針對三類問題做增量巡檢：
  - 資安 / 安全性
  - 程式碼冗餘 / 一致性衝突
  - 明顯低效可優化寫法

## 本輪已驗證結論

### 已確認不再列為待修

1. `src/services/web_searcher.py:13`
   - `chardet` 相依已由 `requirements.txt` 明確宣告，這項不再列為阻塞問題。

2. `src/services/web_searcher.py:76`
   - Brotli 相依已由 `requirements.txt` 明確宣告。

3. `src/services/go_bridge.py`
   - 掃描呼叫透過 `_run_command()` 執行，預設 timeout 為 60 秒，「掃描永久掛起」不再是目前狀態。

## 本輪已修正

### 1. JAVDB 429 `Retry-After` 沒有導入 limiter

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

### 2. `SafeJAVDBSearcher` 重試路徑會自我死鎖

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

## 本輪未新增待修高優先問題

- 本輪主要增量問題都已直接修補並完成驗證。
- 尚未看到新的高風險資安缺口、明顯冗餘衝突或可立即安全落地的大型效能退化點。

## 本輪驗證指令

```text
python -m pytest tests/test_code_review_regressions.py -q -p no:cacheprovider
結果：3 passed
```

```text
python -m py_compile src/services/safe_javdb_searcher.py src/scrapers/base_scraper.py src/scrapers/sources/javdb_scraper.py tests/test_code_review_regressions.py tests/test_safe_javdb_searcher.py
結果：通過
```

```text
inline Python 驗證：
- RateLimiter 會記錄 429 的 retry_after
- SafeJAVDBSearcher 在 403 重試時不再自我死鎖
結果：TARGETED_VALIDATION_OK
```

## 後續建議

1. 若下一輪持續巡檢爬蟲穩定性，可檢查 `avwiki_scraper.py` 是否也需要支援 `Retry-After` 傳遞。
2. 若要擴大效能盤點，可檢查 `WebSearcher` 其他批次流程是否還有重複 JSON / HTML 解析。
3. `pytest` 在這台 Windows 環境建立 / 清理暫存目錄時會遇到 `PermissionError`，後續若要擴充測試建議優先沿用工作區內定向驗證腳本。
