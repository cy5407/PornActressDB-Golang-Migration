# 區塊 2：搜尋與爬蟲評估

## 本次檢閱範圍

已檢閱：

- `src/services/web_searcher.py`
- `src/services/safe_searcher.py`
- `src/services/safe_javdb_searcher.py`
- `src/scrapers/base_scraper.py`
- `src/scrapers/cache_manager.py`
- `src/scrapers/rate_limiter.py`
- `src/scrapers/unified_scraper.py`
- `src/scrapers/sources/avwiki_scraper.py`
- `src/scrapers/sources/javdb_scraper.py`
- `src/scrapers/sources/shiroutowiki_scraper.py`
- `src/utils/actress_name_filter.py`

## 這個區塊在做什麼

- 搜尋協調與來源級聯
- HTTP 標頭、重試、快取、rate limit
- 日文網站編碼與 HTML 解析
- 女優名稱過濾
- 搜尋結果整形與欄位標準化

## 現況判斷

這一區塊的 Python 比例很高，而且集中在幾個大檔案：

- `src/services/web_searcher.py` 約 1119 行
- `src/scrapers/sources/avwiki_scraper.py` 約 717 行
- `src/services/safe_javdb_searcher.py` 約 627 行
- `src/services/safe_searcher.py` 約 356 行

這裡是目前 Python 佔比最高、但也最容易受網站變動影響的區塊。

## 是否適合重構成 Golang

**判定：部分非常適合，部分要分段遷移**

### 很適合搬到 Go 的部分

- HTTP client
- 快取
- retry / backoff
- rate limit
- 搜尋候選組裝
- 結果標準化
- 網路錯誤分類

### 不建議一次硬搬的部分

- AV-WIKI / JAVDB 的 HTML selector 與站點特化解析
- 日文名稱過濾細節
- 各站點 fallback 規則

原因：

- 這些解析規則高度依賴網站當下 HTML 結構
- Python + BeautifulSoup 在這種快速修修補補的情境下開發效率很高
- 若一次全部搬到 Go，初期風險會偏高

## 是否適合重構成 Rust

**判定：技術上可行，但不建議作為主路線**

Rust 在 async HTTP、解析、型別模型上當然做得到，但目前專案沒有任何 Rust 基礎設施，導入成本會明顯高於 Go。

如果你的目標是「盡快降低 Python 比例」，Rust 不是這區塊的最佳選擇。

## 建議結論

這一區塊建議採取 **Go 漸進式重構**：

1. 先把 transport 層搬到 Go
2. 再把搜尋協調與結果標準化搬到 Go
3. 最後才逐站點搬 parser

## 建議遷移邊界

### 第 1 批可先搬到 Go

- `safe_searcher.py`
- `cache_manager.py`
- `rate_limiter.py`
- `web_searcher.py` 中與來源無關的通用流程

### 第 2 批再搬

- `avwiki_scraper.py`
- `javdb_scraper.py`
- `shiroutowiki_scraper.py`
- `actress_name_filter.py`

## 遷移風險

- 站點 HTML 經常變動，回歸測試若不夠，Go 版 parser 會變得難修
- 目前部分邏輯混在協調器與解析器中，搬之前最好先拆 pure function
- 這一區塊有不少網站例外處理，必須先建立 fixture 測試樣本

## 建議優先度

**優先度：P2**

價值很高，但應分段，不要一次整塊重寫。

