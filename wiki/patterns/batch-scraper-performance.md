# 批次爬蟲效能模式

> 來源：`src/scrapers/sources/avwiki_scraper.py`、`src/scrapers/run_batch_search.py`、`src/services/web_searcher.py`
> 更新：2026-04-24

---

## 適用情境

當爬蟲任務是大量番號查詢時，主要瓶頸通常是 HTTP I/O、網站限速與 Python 子程序啟動成本，不是 Python CPU 執行速度。此時應先優化批次管線與連線重用，再評估是否需要 Go 化。

---

## 正確做法

### 1. 批次搜尋只啟動一次 Python

Wails backend 應透過 `run_batch_search.py` 一次送入多個番號，並用 JSON Lines 串流結果。不要對每個番號各啟動一次 Python，否則 import 與初始化成本會放大成主要瓶頸。

### 2. AV-WIKI 使用 async 批次與共享連線池

AV-WIKI 屬於相對適合併發的來源，批次搜尋應使用：

- `aiohttp.ClientSession`
- `aiohttp.TCPConnector(limit=..., limit_per_host=..., ttl_dns_cache=...)`
- `asyncio.gather`
- 受控的批次併發數

重點是同一批次共用 `ClientSession`，讓 keep-alive、DNS cache 與 connection pool 生效。不要在每一筆請求都建立新的 `ClientSession`。

### 3. 自適應併發必須影響實際排程

只更新一個 `current_concurrency` 數字但仍用固定 `Semaphore(max_concurrent)`，不算真正的自適應併發。正確模式是：

1. 依目前併發值取出下一波任務。
2. 執行該波請求。
3. 依成功/失敗回報調整併發控制器。
4. 下一波使用新的併發值。

這樣遇到 429、timeout、暫時性連線錯誤時，降載會真正減少後續同時請求數。

### 4. JAVDB 保守處理

JAVDB 反爬風險較高，應優先使用低併發、快取、錯誤狀態紀錄與避免重查。不要套用 AV-WIKI 的高併發假設。

---

## Go 與 Python 的分工

Go 適合負責：

- Wails backend 調度
- 子程序生命週期
- JSON Lines 串流讀取
- DB 快取過濾與結果持久化
- 長期若需要，可做 worker pool 與全域 rate limiter

Python 適合保留：

- 站點解析
- 日文編碼處理
- BeautifulSoup 解析規則
- 來源差異與反爬細節

在爬蟲仍是 I/O-bound 的前提下，先把 Python async 管線與批次策略做好，通常比完整 Go 重寫更划算。

---

## 實測參考

2026-04-24 實測 `test-file` 批次 AV-WIKI 搜尋：

| 指標 | 數值 |
|------|------|
| 批次番號 | 262 筆 |
| 結果 | 262 成功 / 0 失敗 |
| 後段吞吐 | 第 163-262 筆約 49 秒 |
| 估算速度 | 約 2 req/s |

此速度屬於單機桌面工具對第三方網站的受控中高併發。商業大規模爬蟲通常會再加入任務佇列、多機 worker、代理池、per-domain rate limit、錯誤率監控與合規策略；本專案目前優先維持穩定、低錯誤率與可恢復性，不追求無限制加壓。

---

## 相關檔案

| 功能 | 位置 |
|------|------|
| AV-WIKI async 批次搜尋 | `src/scrapers/sources/avwiki_scraper.py::batch_search_concurrent()` |
| Wails 批次子程序 | `src/scrapers/run_batch_search.py` |
| 搜尋協調器 | `src/services/web_searcher.py` |
| Wails backend 串流讀取 | `wails-app/backend/app.go::batchSearch()` |

---

## 相關頁面

- [搜尋引擎架構](../architecture/search-engine.md)
- [Wails 搜尋效能優化](../pitfalls/wails-search-perf.md)
