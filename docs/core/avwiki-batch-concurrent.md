# AV-WIKI 批次併發搜尋功能說明

## 功能概述

已成功整合 AV-WIKI 批次併發搜尋功能到片商分類系統中。此功能可大幅提升搜尋效能，特別是在處理大量番號時。

## 效能提升

- **傳統循序搜尋**: ~2 秒/番號
- **批次併發搜尋**: ~0.17 秒/番號 (5.95 請求/秒)
- **提升倍數**: 約 11.7 倍

## 配置選項

在 `config.ini` 中添加了以下配置：

```ini
[search]
# AV-WIKI 批次併發搜尋配置
avwiki_concurrent_enabled = true   # 是否啟用批次併發搜尋
avwiki_max_concurrent = 15          # 最大併發數
```

### 建議配置

- **最大併發數**: 15 (已測試最佳值)
- **啟用狀態**: true (預設啟用)

## 使用方式

### 1. 使用 GUI 介面

直接使用原有的片商分類功能，系統會自動使用批次併發搜尋：

1. 開啟 GUI: `python run.py`
2. 選擇「日文網站搜尋」或「完整搜尋」
3. 系統會自動使用 AV-WIKI 批次併發進行搜尋

### 2. 程式碼範例

```python
from services.classifier_core import UnifiedClassifierCore
from models.config import ConfigManager
import threading

# 初始化
config = ConfigManager('config.ini')
core = UnifiedClassifierCore(config)

# 使用批次併發搜尋（預設啟用）
stop_event = threading.Event()
result = core.process_and_search_japanese_sites(
    folder_path='path/to/folder',
    stop_event=stop_event,
    progress_callback=print,
    use_avwiki_concurrent=True  # 啟用批次併發
)

# 關閉批次併發，使用傳統搜尋
result = core.process_and_search_japanese_sites(
    folder_path='path/to/folder',
    stop_event=stop_event,
    progress_callback=print,
    use_avwiki_concurrent=False  # 關閉批次併發
)
```

### 3. 單獨使用批次搜尋

```python
from services.web_searcher import WebSearcher
from models.config import ConfigManager
import threading

config = ConfigManager('config.ini')
searcher = WebSearcher(config)

codes = ['STARS-123', 'SSIS-456', 'IPX-789']
stop_event = threading.Event()

results = searcher.batch_search_avwiki_concurrent(
    codes,
    stop_event,
    progress_callback=print
)

for code, info in results.items():
    if info and info.get('actresses'):
        print(f"{code}: {', '.join(info['actresses'])}")
```

## 技術細節

### 實作原理

1. **併發控制**: 使用 `asyncio.Semaphore(15)` 限制最大併發數
2. **繞過速率限制**: 直接呼叫 `scrape_url()` 避免觸發速率限制保護
3. **快取機制**: 自動快取搜尋結果，避免重複搜尋
4. **異步轉同步**: 使用 `asyncio.run()` 在同步環境中執行異步操作

### 流程圖

```
用戶請求
    ↓
WebSearcher.batch_search_avwiki_concurrent()
    ↓
檢查快取 → 已快取 → 直接返回
    ↓
未快取
    ↓
asyncio.run(run_batch_search())
    ↓
AVWikiScraper.search_batch_concurrent()
    ↓
15 個併發請求 (asyncio.Semaphore)
    ↓
合併結果 + 更新快取
    ↓
返回結果
```

## 測試結果

### 小批次測試 (5 個番號)

- 耗時: 0.84 秒
- 速率: 5.95 請求/秒
- 成功率: 100% (5/5)

### 大批次測試 (30 個番號)

- 耗時: 4.87 秒
- 速率: 6.16 請求/秒
- 成功率: 100% (30/30)

## 注意事項

1. **只針對 AV-WIKI**: 此批次併發功能僅適用於 AV-WIKI，其他網站仍使用傳統搜尋
2. **網路環境**: 效能受網路環境影響，建議在穩定的網路環境下使用
3. **記憶體使用**: 併發搜尋會同時載入多個網頁，記憶體使用會稍高
4. **Brotli 依賴**: 需要安裝 `brotli` 套件支援壓縮編碼

## 相依套件

確保已安裝以下套件：

```bash
pip install brotli httpx beautifulsoup4
```

## 疑難排解

### 問題: RuntimeError: no running event loop

**原因**: AVWikiScraper 在非異步環境中初始化

**解決方法**: 已在 `batch_search_avwiki_concurrent` 中使用 `asyncio.run()` 包裝，無需手動處理

### 問題: 進度回調錯誤

**原因**: 進度回調函式參數不匹配

**解決方法**: 進度回調接收 3 個參數：`(current, total, code)`

```python
def progress_callback(current, total, code):
    print(f"[{current}/{total}] 搜尋 {code}")
```

## 更新日誌

### 2025-01-XX

- ✅ 實作 AV-WIKI 批次併發搜尋功能
- ✅ 整合到 WebSearcher 和 UnifiedClassifierCore
- ✅ 添加配置選項到 config.ini
- ✅ 修正 Brotli 壓縮支援
- ✅ 修正速率限制器衝突問題
- ✅ 完成整合測試

## 未來改進

- [ ] 支援其他網站的批次併發搜尋
- [ ] 動態調整併發數根據網路狀態
- [ ] 添加搜尋結果品質評分
- [ ] 支援斷點續傳
