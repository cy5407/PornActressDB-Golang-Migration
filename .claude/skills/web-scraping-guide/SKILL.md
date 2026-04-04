---
name: web-scraping-guide
description: 網路爬蟲開發指引 - 用於新增爬蟲來源、修改級聯邏輯、處理日文編碼、速率限制與錯誤處理
argument-hint: "[scraper-name]"
---

# 網路爬蟲開發 Skill

## 何時使用此 Skill

當需要：
1. **新增爬蟲來源**（新網站支援）
2. **修改級聯搜尋邏輯**（調整優先順序）
3. **處理編碼問題**（日文網站）
4. **設定速率限制**（避免被封鎖）
5. **修復爬蟲失敗**（網站改版）

## 搜尋順序

```
AV-WIKI (主要)
    ↓ 失敗
JAVDB (最終)
```

> chiba-f.net 已於 2026-03-22 移除。

## 爬蟲架構

```
src/scrapers/
├── sources/
│   ├── avwiki_scraper.py     # AV-WIKI 爬蟲
│   └── javdb_scraper.py      # JAVDB 爬蟲
├── cache_manager.py          # 快取管理
└── unified_scraper.py        # 統一介面
```

## 新增爬蟲來源

### Step 1: 建立爬蟲類別

檔案：`src/scrapers/sources/example_scraper.py`
```python
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class ExampleScraper:
    """Example 網站爬蟲"""
    
    BASE_URL = "https://example.com"
    
    def __init__(self, safe_searcher):
        self.safe_searcher = safe_searcher
    
    async def search(self, code: str) -> Optional[Dict[str, Any]]:
        """搜尋番號"""
        try:
            url = f"{self.BASE_URL}/search?q={code}"
            html = await self.safe_searcher.fetch(url)
            
            if not html:
                return None
            
            soup = BeautifulSoup(html, 'html.parser')
            # 解析邏輯...
            
            return {
                'actresses': [...],
                'title': '...',
                'studio': '...'
            }
        except Exception as e:
            logger.error(f"❌ Example 搜尋失敗 {code}: {e}")
            return None
```

### Step 2: 整合到級聯搜尋

檔案：`src/services/web_searcher.py`
```python
from scrapers.sources.example_scraper import ExampleScraper

class WebSearcher:
    def __init__(self):
        self.example_scraper = ExampleScraper(self.safe_searcher)
    
    async def cascade_search(self, code: str):
        # 1. AV-WIKI
        result = await self.avwiki.search(code)
        if result:
            return result
        
        # 2. Example (新增)
        result = await self.example_scraper.search(code)
        if result:
            return result
        
        # 3. JAVDB (最終)
        return await self.javdb.search(code)
```

## 日文編碼處理

```python
import chardet
from bs4 import BeautifulSoup

# 自動檢測編碼
def decode_japanese_html(content: bytes) -> str:
    detected = chardet.detect(content)
    encoding = detected['encoding']
    
    # 常見日文編碼
    if encoding in ['SHIFT_JIS', 'EUC-JP']:
        return content.decode(encoding, errors='ignore')
    else:
        return content.decode('utf-8', errors='ignore')
```

## 速率限制

```python
# SafeSearcher 自動處理速率限制
from services.safe_searcher import SafeSearcher

searcher = SafeSearcher(
    min_delay=0.5,      # 最小延遲 (秒)
    max_delay=1.5,      # 最大延遲 (秒)
    timeout=20,         # 請求逾時
    max_retries=3       # 重試次數
)
```

## 相關檔案

- `src/scrapers/sources/` - 爬蟲實作
- `src/services/web_searcher.py` - 級聯搜尋協調器
- `src/services/safe_searcher.py` - 安全 HTTP 請求
