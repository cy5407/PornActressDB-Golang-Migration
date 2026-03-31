# 專案程式碼巡檢持續追蹤報告

最後更新：2026-03-31 23:43 (Asia/Taipei)
基準提交：`7651546` `docs: add agent guidance and ignore local security archives`

## 本輪檢查範圍

- 先讀取既有報告：
  - `security_reports/manual_fix_progress_2026-03-31.md`
  - `security_reports/one_time_fix_schedule_2026-03-31.md`
  - `security_reports/security_fix_summary_2026-03-31.md`
- 先比對最近提交：
  - `7651546`、`8148592`、`a35e965` 起的最近 20 筆 commit
- 針對三類問題做增量巡檢：
  - 資安 / 安全性
  - 程式碼冗餘 / 一致性衝突
  - 明顯低效可優化寫法

## 本輪已驗證結論

### 已確認不再列為待修

1. `src/services/web_searcher.py:13`
   - 先前待驗證的 `chardet` 依賴問題已確認不是目前阻塞。
   - `requirements.txt` 已明確宣告 `chardet>=5.2.0`。

2. `src/services/web_searcher.py:76`
   - 先前待驗證的 Brotli 風險本輪確認已有依賴基礎。
   - `requirements.txt` 已明確宣告 `brotli>=1.0.0`。
   - 但是否完整處理所有 `429/Retry-After` 退避仍需另行追蹤，見下方未解決項目。

3. `src/services/go_bridge.py:316`
   - 「掃描操作無 timeout」本輪確認已不是現況問題。
   - `scan_directory()` 透過 `_run_command()` 執行，預設 timeout 為 60 秒。

## 本輪已修正

### 1. 初始化降級缺口

- 位置：`src/services/classifier_core.py:27`
- 類型：穩定性 / 可用性
- 問題：
  - `IncrementalJSONDB` 初始化失敗時，整個核心物件會直接在建構期崩潰。
  - 這會把資料檔或 journal 問題放大成 GUI / 流程全面不可用。
- 修正：
  - 加入 `try/except`。
  - 當 `IncrementalJSONDB` 初始化失敗時，自動降級到 `JSONDBManager`，並留下 warning 日誌。
- 驗證：
  - `tests/test_code_review_regressions.py::test_classifier_core_falls_back_to_json_db`

### 2. 片商代碼查找的重複磁碟 I/O

- 位置：`src/services/web_searcher.py:732`
- 類型：效能
- 問題：
  - `_get_studio_name_by_code()` 原本每次呼叫都重新讀取 `studios.json`。
  - 批次搜尋情境下，這會造成大量重複磁碟讀取與 JSON 解析。
- 修正：
  - 啟動時一次載入片商代碼映射為 `self._studio_code_mapping`。
  - 查詢改為記憶體字典存取。
- 附帶修正：
  - 補上該段實作實際使用但缺失的 `Path` 匯入，避免觸發 `NameError`。

### 3. AV-WIKI 搜尋 API 重複實作

- 位置：
  - `src/services/web_searcher.py:813`
  - `src/services/web_searcher.py:880`
- 類型：冗餘 / 一致性
- 問題：
  - `search_japanese_sites_only()` 與 `search_japanese_sites()` 幾乎是重複邏輯。
  - 後續若只修其中一支，容易造成行為分歧。
- 修正：
  - `search_japanese_sites_only()` 改為委派到 `search_japanese_sites()`，保留舊 API 但消除雙份邏輯。
- 驗證：
  - `tests/test_code_review_regressions.py::test_search_japanese_sites_only_delegates_to_unified_method`

### 4. Go 快取註解與實作現況不一致

- 位置：`pkg/cache/types.go:5`
- 類型：一致性
- 問題：
  - 註解仍寫「因 pickle 序列化」，與 2026-03-31 已完成的 JSON 快取修復不符。
- 修正：
  - 更新註解為目前的 JSON 載荷格式描述。

## 本輪新發現且尚未修正

### P2: `Retry-After` 標頭被讀取但沒有導入退避控制

- 位置：`src/scrapers/sources/javdb_scraper.py:63`
- 類型：資安 / 穩定性 / 反封鎖策略
- 問題：
  - 429 時只讀取 `response.headers.get("Retry-After")`，但值沒有被保存、解析或回傳到 `RateLimiter`。
  - 實際效果等同忽略伺服器要求的冷卻時間，容易造成重試過快、封鎖延長，甚至被視為惡意流量。
- 影響：
  - 會削弱目前 `rate_limiter.py` 已具備的 `Retry-After` 支援設計。
  - 屬於「安全爬取」策略缺口，而非單純功能小問題。
- 建議：
  - 擴充 `ScrapingException` 或 `safe_scrape` 流程，讓 429 的 `Retry-After` 可傳遞到 rate limiter。
  - 修正後補一個 429 單元測試，驗證 limiter 有記錄冷卻時間。

## 本輪驗證指令

```text
python -m pytest tests/test_code_review_regressions.py -q -p no:cacheprovider
結果：2 passed
```

```text
python -m py_compile src/services/web_searcher.py src/services/classifier_core.py tests/test_code_review_regressions.py
結果：通過
```

```text
$env:GOCACHE=(Join-Path (Get-Location) '.gocache'); go test ./pkg/...
結果：通過
```

```text
$env:GOCACHE=(Join-Path (Get-Location) '.gocache'); go build -o classifier.exe ./cmd/scanner
./classifier.exe help
結果：通過
```

```text
以接近 run.py 的流程建立 Tk / ttkbootstrap / UnifiedActressClassifierGUI
結果：GUI_STARTUP_OK UnifiedActressClassifierGUI
```

## 建議下一輪優先順序

1. 修補 `javdb_scraper.py` 的 `Retry-After` 傳遞與退避整合。
2. 若要延伸安全巡檢，可再檢查 `safe_javdb_searcher.py` 與 `async_scraper.py` 是否也有同類 429 行為不一致。
3. 若要延伸效能巡檢，可盤點 `WebSearcher` 其餘批次流程中是否仍有重複的 JSON / HTML 解析路徑。
