# 搜尋引擎架構

> 來源：`wails-app/backend/app.go`、`src/scrapers/run_search.py`、`src/scrapers/run_batch_search.py`、`src/services/web_searcher.py`、`wails-app/frontend/src/App.tsx`
> 更新：2026-04-24

---

## 搜尋架構總覽

目前的搜尋主流程仍是同一條 Python 搜尋管線，由 Wails backend 依需求用不同 API 入口呼叫：

```text
Wails UI / Backend
   ↓
BatchSearch / BatchSearchAVWiki / BatchSearchJAVDB
   ↓
run_batch_search.py（單一 Python 批次子程序）
   ↓
WebSearcher
   ├─ cascade: search_info()
   ├─ avwiki:  search_avwiki_only()
   └─ javdb:   search_javdb_only()
```

單筆搜尋時，`run_search.py` 也使用同樣的 `source_mode` 概念：
- `cascade`：主線級聯搜尋
- `avwiki`：只跑 AV-WIKI
- `javdb`：只跑 JAVDB

也就是說，來源專用搜尋不是另一套 crawler 架構，而是同一組腳本與 `WebSearcher` 在不同 `source_mode` 下的定向執行方式。

---

## 主線策略：預設 BatchSearch / `search_info()`

### 1. Wails 預設批次 API

`wails-app/backend/app.go` 的：
- `BatchSearch(codes, workers)`

會呼叫：
- `batchSearch(codes, workers, "")`
- 再由 backend 將請求序列化為 `source_mode` 空字串
- Python 端把空字串正規化為 `cascade`

### 2. Python 主線模式

`src/scrapers/run_search.py` 與 `src/scrapers/run_batch_search.py` 都將以下別名正規化到預設模式：
- `""`
- `cascade`
- `all`
- `default`

正規化後會走：
- `WebSearcher.search_info(code, stop_event)`

### 3. 目前 cascade 的實際順序

`src/services/web_searcher.py` 中，`search_info()` 的主線是：

```text
番號
  ↓
AV-WIKI
  ├─ 找到且有 actresses → 回傳成功
  └─ 否則 ↓
JAVDB
  ├─ 找到且有 actresses → 回傳成功
  └─ 否則 → 回傳 None
```

補充：
- `search_info()` 會先建立番號候選（例如特定 `00xxx` alias fallback）。
- AV-WIKI 命中後就不再往下跑 JAVDB。
- 若 AV-WIKI 未命中，才會進入 JAVDB。
- 這就是目前文件中應稱為「主線級聯搜尋」的部分。

### 4. 預設批次 API 的資料庫行為

`BatchSearch` 與來源專用 API 的差異，不只在搜尋來源，也在 DB 快取策略：

- `BatchSearch` 會先查 DB
- 若既有影片 `search_status == "searched_found"`，會直接當作整體快取結果回傳
- 只有未命中的番號才會送進 `run_batch_search.py`
- Python 回傳成功結果後，backend 會更新整體欄位：
  - `search_status = "searched_found"`
  - `search_method`
  - `last_search_date`
  - 以及標題、片商、網址、女優等主資料

因此預設 `BatchSearch` 代表的是「整體搜尋主線」，不是單一來源重跑。

---

## 來源專用 API：補搜 / 定向重跑入口

### Wails backend API

`wails-app/backend/app.go` 另外提供：
- `BatchSearchAVWiki(codes, workers)`
- `BatchSearchJAVDB(codes, workers)`

兩者都仍然進入同一個 `batchSearch(...)`，只是帶入不同 `source`：
- `avwiki`
- `javdb`

backend 會把這個值寫進批次請求的 `source_mode` 欄位，交給 `run_batch_search.py`。

### 這些 API 的定位

這兩個 API 的定位是：
- 針對特定來源補搜
- 針對特定來源重跑
- 更新該來源自己的狀態欄位

它們不是：
- 獨立於主線之外的另一套搜尋架構
- 新增另一條 crawler pipeline

### 與預設 BatchSearch 的關鍵差異

來源專用 API 會刻意略過舊的整體快取捷徑：
- `BatchSearchAVWiki` / `BatchSearchJAVDB` 不使用 `search_status == "searched_found"` 的 legacy cache 直接返回
- 即使 DB 已有整體成功資料，仍會重跑指定來源

這表示它們是主線搜尋之外的「補充性 / 定向 rerun」能力，而不是取代主線。

---

## `source_mode` 對應關係

`run_search.py` 與 `run_batch_search.py` 目前都支援相同的來源模式：

| `source_mode` | Python 實際呼叫 | 用途 |
|---|---|---|
| `cascade` | `search_info()` | 預設主線級聯搜尋 |
| `avwiki` | `search_avwiki_only()` | 只跑 AV-WIKI 的補搜 / 重跑 |
| `javdb` | `search_javdb_only()` | 只跑 JAVDB 的補搜 / 重跑 |

其中：
- `run_search.py` 用於單筆子程序包裝
- `run_batch_search.py` 用於批次子程序包裝
- 兩者都共用 `run_search.py` 內的 `_normalize_source_mode()` 與 `_search_with_mode()`

---

## `WebSearcher` 中各模式的實際行為

### `search_info()`

主線級聯模式：
1. 先嘗試 AV-WIKI
2. AV-WIKI 沒有女優結果時，再嘗試 JAVDB
3. 任一來源成功即回傳

### `search_avwiki_only()`

來源專用模式，直接呼叫：
- `search_japanese_sites(code, stop_event)`

目前這條路徑只做 AV-WIKI 搜尋，不會再串接 JAVDB。

### `search_javdb_only()`

來源專用模式，直接：
- 建立番號候選
- 呼叫 `_search_candidates_in_javdb(...)`

目前這條路徑只做 JAVDB 搜尋，不會回退到 AV-WIKI。

---

## 批次腳本與主流程的關係

### `run_batch_search.py`

`run_batch_search.py` 的角色是：
- 一次接收多個 `codes`
- 啟動單一 Python 子程序
- 在子程序內用 `ThreadPoolExecutor` 平行處理
- 每個 thread 各自建立 `WebSearcher`
- 逐筆輸出 JSON Lines，讓 Go/Wails 即時收到進度與結果

它本身不是另一套搜尋策略；真正的來源選擇仍由 `source_mode` 決定。

### `batch_cascade_search()` 的位置

`WebSearcher.batch_cascade_search()` 仍存在，且語意是：
- 以 AV-WIKI 為主體的批次級聯/別名 fallback 流程
- 主要處理 AV-WIKI 批次併發與 alias fallback

但目前 Wails `BatchSearch` 主流程實際呼叫的是：
- `run_batch_search.py`
- 再由每筆工作依 `source_mode` 進入 `search_info()` / `search_avwiki_only()` / `search_javdb_only()`

因此文件應將 `batch_cascade_search()` 視為 `WebSearcher` 內部仍存在的批次能力，而不是當前 Wails 搜尋 UI 的唯一主入口。

### AV-WIKI 批次併發的效能邊界

AV-WIKI 批次搜尋是目前最適合加速的來源。正確優化方向不是單純把 worker 開大，而是：

- 批次內共用 `aiohttp.ClientSession`
- 透過 `aiohttp.TCPConnector` 控制 connection pool 與 `limit_per_host`
- 以 `asyncio` 分波執行，讓自適應併發的升降載能影響下一波請求
- 對 timeout、429、5xx 等暫時性錯誤降載並退避

這表示「高併發」應該是受控併發，而不是無限制平行請求。若網站開始 server throttling，客戶端應降載而不是持續加壓。

JAVDB 則不適合套用同一組高併發策略。JAVDB 的安全搜尋器包含 session 重建、冷卻與反爬處理，因此應以低併發、快取與錯誤狀態紀錄為主。

---

## 來源專用狀態欄位

目前 source-specific 搜尋會另外維護來源自己的狀態欄位。

### Backend 對應欄位

`wails-app/backend/app.go`：
- `avwiki` → `avwiki_actress_status`, `avwiki_last_search_date`
- `javdb` → `javdb_actress_status`, `javdb_last_search_date`

### 狀態值

backend 會依 `SearchResult` 推導來源狀態：
- `found`
- `not_found`
- `error`

### 寫入規則

來源專用批次搜尋時：
- 成功找到資料：
  - 更新來源專屬狀態欄位
  - 也會同步更新整體資料欄位（title/studio/url/actresses 等）
  - 並把整體 `search_status` 設為 `searched_found`
- 未找到或發生錯誤：
  - 至少會更新該來源的 `*_actress_status` 與 `*_last_search_date`
  - 不會把另一個來源的狀態欄位洗掉

`run_search.py` 也有相同概念：
- `avwiki` 模式更新 `avwiki_*`
- `javdb` 模式更新 `javdb_*`
- `cascade` 模式不走這組來源專屬欄位寫入

這也是來源專用 API 與主線 `BatchSearch` 的重要區別。

---

## Wails UI 的來源專用按鈕

`wails-app/frontend/src/App.tsx` 目前將：
- `BatchSearchAVWiki`
- `BatchSearchJAVDB`

包裝成 UI 上的來源專用搜尋按鈕。

它們的角色應理解為：
- 提供使用者做定向補搜 / rerun
- 後端仍是同一個 batch search API 家族
- 並非代表 UI 另外接了一套 AV-WIKI crawler 或 JAVDB crawler 架構

另外，現有 UI 邏輯在呼叫來源專用搜尋前，會先讀取 DB：
- 若 `avwiki_actress_status` 或 `javdb_actress_status` 任一方已是 found 類狀態，該項目會先被視為已有結果而略過
- 只有尚未被任一來源標記為 found 的項目，才會送去做來源專用搜尋

因此目前 UI 上的來源按鈕更接近「補充搜尋入口」，而不是完全獨立的搜尋模式切換器。

---

## 現行文件應避免的誤解

以下說法已不夠精確，應避免：

- 「搜尋架構只有 AV-WIKI → JAVDB 兩層，沒有其他 API 分流」
  - 不精確，因為現在已有 `BatchSearchAVWiki` / `BatchSearchJAVDB` 這類來源專用 rerun API。

- 「AV-WIKI 與 JAVDB 是兩套彼此分離的 crawler 架構」
  - 不精確，因為目前仍是同一條 Wails → Python wrapper → `WebSearcher` 管線，只是 `source_mode` 不同。

- 「來源專用搜尋只影響整體 `search_status`」
  - 不精確，因為現在也會更新 `avwiki_*` / `javdb_*` 狀態欄位。

---

## 相關檔案

- `wails-app/backend/app.go`
- `src/scrapers/run_search.py`
- `src/scrapers/run_batch_search.py`
- `src/services/web_searcher.py`
- `src/scrapers/sources/avwiki_scraper.py`
- `wails-app/frontend/src/App.tsx`
