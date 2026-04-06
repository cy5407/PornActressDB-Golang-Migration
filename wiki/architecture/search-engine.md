# 搜尋引擎架構

> 來源：`src/scrapers/sources/avwiki_scraper.py`、`README.md`  
> 更新：2026-04-06

---

## 搜尋策略：AV-WIKI → JAVDB 級聯

```
番號列表
   ↓
【第一層：AV-WIKI】
   ├─ 找到 → 儲存，標記 search_method: "AV-WIKI"
   └─ 未找到 ↓
【第二層：JAVDB】
   ├─ 找到 → 儲存，標記 search_method: "JAVDB"
   └─ 未找到 → 標記 searched_not_found
```

> ⚠️ chiba-f.net 已從搜尋來源移除（歷史資料中的 `chiba-f.net` search_method 仍保留）

---

## WebSearcher

**位置**：`src/services/web_searcher.py`

核心方法：

```python
# 批次級聯搜尋
result = web_searcher.batch_cascade_search(
    codes,           # 番號列表
    stop_event,      # threading.Event，可中斷
    progress_callback,
    enable_javdb=True
)
```

---

## AV-WIKI 爬蟲

**位置**：`src/scrapers/sources/avwiki_scraper.py`  
**基底**：`BaseScraper`  
**協定**：非同步 `aiohttp`

### Headers 設定

```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",  # 日語優先
    "Accept-Encoding": "gzip, deflate, br",          # 不用 identity，支援壓縮
}
```

### 高併發支援

```python
# AV-WIKI 支援高併發（config.ini）
avwiki_concurrent_enabled = true
avwiki_max_concurrent = 15   # 最大同時請求數
```

---

## JAVDB 爬蟲

**位置**：`src/scrapers/sources/javdb_scraper.py`  
**專用搜尋器**：`src/services/safe_javdb_searcher.py`  
**協定**：同步 requests（SafeSearcher 封裝）

### False Positive 防護

**關鍵邏輯**（2026-04 修正）：

```python
# ❌ 舊邏輯（Issue 12）：無精確匹配時取第一筆
if not best_match_url:
    best_match_url = video_links[0].get("href")  # 產生 false positive

# ✅ 新邏輯：無精確匹配直接回傳 None
if not best_match_url:
    logger.debug(f"🔍 JAVDB 未找到 {video_id} 精確匹配，視為未找到")
    return None
```

**詳情頁二次驗證**：

```python
# 從標題提取番號，與搜尋目標比對
if page_code != video_id.upper():
    logger.warning(f"⚠️ 詳情頁番號不符: {video_id} vs {page_code}")
    return None
```

→ 詳見 [pitfalls/javdb-false-positive.md](../pitfalls/javdb-false-positive.md)

---

## SafeSearcher

**位置**：`src/services/safe_searcher.py`

特性：
- 速率限制（配置化延遲）
- 重試機制（指數退避）
- 快取（避免重複請求）

**JAVDB 專用設定**（`config.ini`）：

```ini
[search]
batch_size = 10
thread_count = 5
batch_delay = 2.0
request_timeout = 20
```

---

## 零女優二次搜尋

當第一輪搜尋結果女優列表為空（零女優）時，自動進行第二輪：

1. 清除該番號的 JAVDB 快取（`clear_cache_for_code()`）
2. 重新搜尋
3. 找到則覆寫資料庫，標記 `search_method: "JAVDB (二次搜尋)"`

**提升效果**：搜尋成功率 +3-5%，零女優番號處理率 +10-15%

→ 詳見 [patterns/zero-actress-retry.md](../patterns/zero-actress-retry.md)

---

## 編碼處理

日文網站需要特別處理編碼：

```python
from ..encoding_utils import create_safe_soup

# 自動偵測 Shift_JIS / EUC-JP / UTF-8
soup, encoding = create_safe_soup(content_bytes)
```

JAVDB 使用 `Accept-Encoding: identity`（明確拒絕 Brotli 壓縮）。

---

## 快取管理

**位置**：`src/scrapers/cache_manager.py`  
**Go 加速**：Phase 4A 後 get/set/delete 委派 Go CLI

```bash
classifier.exe cache stats
classifier.exe cache prune -ttl-days 7
classifier.exe cache clear -confirm
```

---

## 相關頁面

- [wiki/pitfalls/javdb-false-positive.md](../pitfalls/javdb-false-positive.md)
- [wiki/patterns/zero-actress-retry.md](../patterns/zero-actress-retry.md)
