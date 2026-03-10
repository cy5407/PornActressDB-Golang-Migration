# 女優分類系統 - 功能改善實作計畫

> 📅 建立日期：2025-11-25  
> 🎯 目標版本：v5.5.0  
> 📊 目前版本：v6.0.0

---

## 📋 目錄

1. [快取過期清理](#1-快取過期清理)
2. [多來源級聯搜尋](#2-多來源級聯搜尋)
3. [進度顯示優化](#3-進度顯示優化)
4. [GUI 非同步優化](#4-gui-非同步優化)
5. [搜尋結果預覽](#5-搜尋結果預覽)
6. [實作順序與時程](#6-實作順序與時程)

---

## 1. 快取過期清理

### 1.1 現狀分析

**問題描述**：
- `cache/` 目錄累積大量快取檔案
- 沒有自動清理機制，會逐漸佔滿硬碟空間
- 快取檔案使用 SHA256 雜湊命名，難以人工判斷內容

**現有架構**：
```
cache/
├── cache_index.json    # 快取索引檔
├── search_cache.json   # 搜尋快取
├── 04/8f/xxx.cache     # 雜湊分片儲存
├── 06/67/xxx.cache
└── ...
```

**相關程式碼**：
- `src/scrapers/cache_manager.py` - `CacheManager` 類別
- `src/ui/main_gui.py` - `on_closing()` 方法

### 1.2 實作目標

1. 自動清理超過 TTL（存活時間）的快取檔案
2. 限制快取總大小，超過時清理最舊的檔案
3. 提供手動清理功能
4. 在程式關閉時自動執行清理

### 1.3 技術設計

#### 1.3.1 設定檔擴充 (`config.ini`)

```ini
[cache]
# 快取保留天數（預設 7 天）
ttl_days = 7

# 快取最大容量 MB（預設 500MB）
max_size_mb = 500

# 是否在關閉程式時自動清理
auto_cleanup_on_exit = true

# 清理時保留的最小檔案數（避免全部清空）
min_keep_entries = 100
```

#### 1.3.2 新增方法 (`src/scrapers/cache_manager.py`)

```python
def cleanup_expired(self, ttl_days: int = 7) -> Dict[str, int]:
    """
    清理過期的快取檔案
    
    Args:
        ttl_days: 快取保留天數
        
    Returns:
        {
            'deleted_files': 刪除的檔案數,
            'freed_bytes': 釋放的空間（位元組）,
            'remaining_files': 剩餘檔案數
        }
    """
    pass

def cleanup_by_size(self, max_size_mb: int = 500) -> Dict[str, int]:
    """
    根據大小限制清理快取（LRU 策略：刪除最久未存取的）
    
    Args:
        max_size_mb: 最大快取大小 MB
        
    Returns:
        清理結果統計
    """
    pass

def get_cache_stats(self) -> Dict[str, Any]:
    """
    取得快取統計資訊
    
    Returns:
        {
            'total_files': 總檔案數,
            'total_size_mb': 總大小 MB,
            'oldest_entry': 最舊的快取時間,
            'newest_entry': 最新的快取時間,
            'index_entries': 索引中的條目數
        }
    """
    pass

def clear_all(self, confirm: bool = False) -> bool:
    """
    清除所有快取（需要確認）
    
    Args:
        confirm: 必須為 True 才會執行
        
    Returns:
        是否成功
    """
    pass
```

#### 1.3.3 清理邏輯流程

```
[程式關閉觸發] 或 [手動觸發]
        ↓
[讀取 cache_index.json]
        ↓
[檢查每個條目的 created_at]
        ↓
[過期？] ─是→ [加入刪除清單]
   ↓否
[檢查總大小是否超過限制]
        ↓
[超過？] ─是→ [按 last_accessed 排序，刪除最舊的]
   ↓否
[執行批次刪除]
        ↓
[更新 cache_index.json]
        ↓
[回報清理結果]
```

#### 1.3.4 整合到 GUI (`src/ui/main_gui.py`)

```python
def on_closing(self):
    """程式關閉時的處理"""
    self.is_running = False
    self.stop_event.set()
    
    # 1. 合併增量資料庫
    try:
        if hasattr(self.core, 'db_manager'):
            self.core.db_manager.compact_if_needed()
    except Exception as e:
        print(f"資料庫合併失敗: {e}")
    
    # 2. 清理過期快取（新增）
    try:
        from scrapers.cache_manager import CacheManager
        cache_mgr = CacheManager()
        
        # 讀取設定
        ttl_days = self.config_manager.getint('cache', 'ttl_days', fallback=7)
        auto_cleanup = self.config_manager.getboolean('cache', 'auto_cleanup_on_exit', fallback=True)
        
        if auto_cleanup:
            result = cache_mgr.cleanup_expired(ttl_days)
            if result['deleted_files'] > 0:
                print(f"已清理 {result['deleted_files']} 個過期快取，釋放 {result['freed_bytes'] / 1024 / 1024:.1f} MB")
    except Exception as e:
        print(f"快取清理失敗: {e}")
    
    self.root.destroy()
```

### 1.4 測試計畫

| 測試案例 | 預期結果 |
|---------|---------|
| TTL = 7 天，有 30 天前的快取 | 該快取被刪除 |
| max_size = 100MB，目前 150MB | 刪除 50MB 最舊的快取 |
| min_keep_entries = 100，但只有 50 個快取 | 不刪除任何檔案 |
| cache_index.json 損壞 | 重建索引，不報錯 |

---

## 2. 多來源級聯搜尋

### 2.1 現狀分析

**問題描述**：
- 目前「日文網站搜尋」只使用 AV-WIKI
- AV-WIKI 找不到時，需要手動再執行 JAVDB 搜尋
- 部分冷門番號只有特定網站有資料

**現有搜尋來源**：
| 來源 | 特性 | 速率限制 |
|------|------|----------|
| AV-WIKI | 主要來源，支援批次併發 | 無 (15 併發) |
| chiba-f.net | 備援來源，資料較舊 | 未測試 |
| JAVDB | 資料最全，但有封鎖風險 | 嚴格 (1 req/2s) |

### 2.2 實作目標

1. 自動級聯搜尋：AV-WIKI → chiba-f → JAVDB
2. 可設定是否啟用級聯
3. 可設定級聯深度（只到 chiba-f 或完整三層）
4. 顯示每個來源的搜尋結果

### 2.3 技術設計

#### 2.3.1 設定檔擴充 (`config.ini`)

```ini
[search]
# 是否啟用級聯搜尋
cascade_enabled = true

# 級聯搜尋的來源順序（逗號分隔）
cascade_sources = avwiki,chibaf,javdb

# 級聯搜尋時是否跳過已知無結果的來源
skip_known_empty = true

# JAVDB 搜尋延遲（秒）
javdb_delay = 2.0
```

#### 2.3.2 新增資料結構

```python
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

class SearchSource(Enum):
    AVWIKI = "avwiki"
    CHIBAF = "chibaf"
    JAVDB = "javdb"

@dataclass
class CascadeSearchResult:
    """級聯搜尋結果"""
    code: str
    actresses: List[str]
    source: SearchSource          # 最終成功的來源
    tried_sources: List[str]      # 嘗試過的來源
    studio: Optional[str] = None
    search_time_ms: float = 0.0
    
@dataclass
class CascadeSearchSummary:
    """級聯搜尋總結"""
    total: int
    success: int
    failed: int
    by_source: Dict[str, int]  # {'avwiki': 35, 'chibaf': 5, 'javdb': 3}
    failed_codes: List[str]
```

#### 2.3.3 新增方法 (`src/services/web_searcher.py`)

```python
async def cascade_search_single(
    self, 
    code: str, 
    sources: List[SearchSource] = None
) -> CascadeSearchResult:
    """
    對單一番號執行級聯搜尋
    
    Args:
        code: 影片番號
        sources: 搜尋來源順序，預設 [AVWIKI, CHIBAF, JAVDB]
        
    Returns:
        CascadeSearchResult
    """
    sources = sources or [SearchSource.AVWIKI, SearchSource.CHIBAF, SearchSource.JAVDB]
    tried = []
    
    for source in sources:
        tried.append(source.value)
        
        try:
            if source == SearchSource.AVWIKI:
                result = await self.avwiki_scraper.search_video(code)
            elif source == SearchSource.CHIBAF:
                result = await self.chibaf_scraper.search_video(code)
            elif source == SearchSource.JAVDB:
                await asyncio.sleep(self.javdb_delay)  # 速率限制
                result = await self.javdb_scraper.search_video(code)
            
            if result and result.get('actresses'):
                return CascadeSearchResult(
                    code=code,
                    actresses=result['actresses'],
                    source=source,
                    tried_sources=tried,
                    studio=result.get('studio')
                )
        except Exception as e:
            logger.warning(f"[級聯搜尋] {code} 在 {source.value} 失敗: {e}")
            continue
    
    # 全部失敗
    return CascadeSearchResult(
        code=code,
        actresses=[],
        source=None,
        tried_sources=tried
    )

def batch_cascade_search(
    self,
    codes: List[str],
    stop_event: threading.Event,
    progress_callback: callable = None
) -> Dict[str, CascadeSearchResult]:
    """
    批次級聯搜尋
    
    策略：
    1. 先用 AV-WIKI 批次併發搜尋所有番號
    2. 收集失敗的番號
    3. 對失敗番號逐一嘗試 chiba-f
    4. 再對仍失敗的嘗試 JAVDB
    """
    pass
```

#### 2.3.4 搜尋流程圖

```
┌─────────────────────────────────────────────────────────┐
│                    批次級聯搜尋流程                       │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │  第一階段：AV-WIKI 批次  │
              │  (15 併發，無速率限制)   │
              └─────────────────────────┘
                           │
           ┌───────────────┴───────────────┐
           ▼                               ▼
    ┌─────────────┐                 ┌─────────────┐
    │ 成功：39 個  │                 │ 失敗：12 個  │
    │ → 儲存結果   │                 │ → 進入第二階│
    └─────────────┘                 └─────────────┘
                                           │
                                           ▼
                          ┌─────────────────────────┐
                          │  第二階段：chiba-f 逐筆  │
                          │  (無併發，間隔 0.5s)    │
                          └─────────────────────────┘
                                           │
                           ┌───────────────┴───────────────┐
                           ▼                               ▼
                    ┌─────────────┐                 ┌─────────────┐
                    │ 成功：5 個   │                 │ 失敗：7 個   │
                    │ → 儲存結果   │                 │ → 進入第三階│
                    └─────────────┘                 └─────────────┘
                                                           │
                                                           ▼
                                          ┌─────────────────────────┐
                                          │  第三階段：JAVDB 逐筆    │
                                          │  (無併發，間隔 2.0s)    │
                                          └─────────────────────────┘
                                                           │
                                           ┌───────────────┴───────────────┐
                                           ▼                               ▼
                                    ┌─────────────┐                 ┌─────────────┐
                                    │ 成功：3 個   │                 │ 失敗：4 個   │
                                    │ → 儲存結果   │                 │ → 標記失敗  │
                                    └─────────────┘                 └─────────────┘
                                                           
                        ┌─────────────────────────────────────────┐
                        │           最終結果統計                   │
                        │  總計：51 | 成功：47 | 失敗：4           │
                        │  AV-WIKI：39 | chiba-f：5 | JAVDB：3    │
                        └─────────────────────────────────────────┘
```

#### 2.3.5 整合到核心類別 (`src/services/classifier_core.py`)

```python
def process_and_search_cascade(
    self, 
    folder_path: str, 
    stop_event: threading.Event, 
    progress_callback=None
):
    """
    使用級聯策略搜尋（日文網站 + JAVDB 自動備援）
    """
    # ... 檔案掃描邏輯 ...
    
    if progress_callback:
        progress_callback("🔄 使用級聯搜尋策略 (AV-WIKI → chiba-f → JAVDB)...\n")
    
    # 執行級聯搜尋
    results = self.web_searcher.batch_cascade_search(
        codes=list(new_code_file_map.keys()),
        stop_event=stop_event,
        progress_callback=progress_callback
    )
    
    # 儲存結果
    for code, result in results.items():
        if result.actresses:
            # ... 儲存到資料庫 ...
            pass
    
    # 回傳詳細結果
    return {
        'status': 'success',
        'total': len(results),
        'success': sum(1 for r in results.values() if r.actresses),
        'by_source': self._count_by_source(results),
        'details': results  # 供搜尋結果預覽使用
    }
```

### 2.4 UI 整合

在 GUI 新增選項：

```python
# 在功能按鈕區新增
self.cascade_var = tk.BooleanVar(value=True)
cascade_check = ttk.Checkbutton(
    options_frame, 
    text="🔄 啟用級聯搜尋 (找不到時自動嘗試其他來源)",
    variable=self.cascade_var
)
```

### 2.5 測試計畫

| 測試案例 | 預期結果 |
|---------|---------|
| AV-WIKI 有資料的番號 | 直接返回，不查詢其他來源 |
| AV-WIKI 無、chiba-f 有 | 從 chiba-f 返回結果 |
| 只有 JAVDB 有的番號 | 從 JAVDB 返回結果 |
| 全部來源都沒有 | 標記為 failed，tried_sources 包含三個來源 |
| 中途按下停止 | 立即中止，已完成的結果正常儲存 |

---

## 3. 進度顯示優化

### 3.1 現狀分析

**問題描述**：
- 目前只顯示簡單的 `[1/51] 搜尋 XXX`
- 無法預估剩餘時間
- 不知道目前成功率

### 3.2 實作目標

1. 顯示預估剩餘時間
2. 顯示即時成功率
3. 顯示搜尋速度
4. 顯示當前搜尋來源（配合級聯搜尋）

### 3.3 技術設計

#### 3.3.1 進度資料結構

```python
from dataclasses import dataclass, field
from typing import Optional
import time

@dataclass
class SearchProgressInfo:
    """搜尋進度資訊"""
    # 基本進度
    current: int = 0
    total: int = 0
    current_code: str = ""
    
    # 統計資訊
    success: int = 0
    failed: int = 0
    
    # 時間追蹤
    start_time: float = field(default_factory=time.time)
    
    # 級聯搜尋資訊
    current_source: str = "AV-WIKI"
    source_stats: Dict[str, int] = field(default_factory=dict)
    
    @property
    def elapsed_seconds(self) -> float:
        """已經過的時間（秒）"""
        return time.time() - self.start_time
    
    @property
    def items_per_second(self) -> float:
        """每秒處理數量"""
        if self.elapsed_seconds == 0:
            return 0
        return self.current / self.elapsed_seconds
    
    @property
    def estimated_remaining_seconds(self) -> float:
        """預估剩餘時間（秒）"""
        if self.items_per_second == 0:
            return 0
        remaining_items = self.total - self.current
        return remaining_items / self.items_per_second
    
    @property
    def success_rate(self) -> float:
        """成功率（0-100）"""
        if self.current == 0:
            return 0
        return (self.success / self.current) * 100
    
    def format_time(self, seconds: float) -> str:
        """格式化時間顯示"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}:{secs:02d}"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours}:{mins:02d}:00"
    
    def format_progress(self) -> str:
        """
        格式化進度顯示
        
        範例輸出：
        [15/51] 搜尋 STARS-707 | ✅ 12 ❌ 3 (80.0%) | ⏱️ 剩餘 2:30 | 🚀 5.2/s | 📡 AV-WIKI
        """
        parts = [
            f"[{self.current}/{self.total}]",
            f"搜尋 {self.current_code}",
            f"| ✅ {self.success} ❌ {self.failed} ({self.success_rate:.1f}%)",
            f"| ⏱️ 剩餘 {self.format_time(self.estimated_remaining_seconds)}",
            f"| 🚀 {self.items_per_second:.1f}/s",
        ]
        
        if self.current_source:
            parts.append(f"| 📡 {self.current_source}")
        
        return " ".join(parts)
```

#### 3.3.2 修改搜尋方法

```python
# src/services/web_searcher.py

def batch_search_avwiki_concurrent(
    self,
    codes: List[str],
    stop_event: threading.Event,
    progress_callback: callable = None
) -> Dict[str, Any]:
    """批次併發搜尋（優化進度顯示）"""
    
    # 初始化進度追蹤
    progress = SearchProgressInfo(total=len(codes))
    
    def update_progress(code: str, success: bool, source: str = "AV-WIKI"):
        """更新進度並回報"""
        progress.current += 1
        progress.current_code = code
        progress.current_source = source
        
        if success:
            progress.success += 1
        else:
            progress.failed += 1
        
        # 更新來源統計
        if source not in progress.source_stats:
            progress.source_stats[source] = 0
        if success:
            progress.source_stats[source] += 1
        
        # 回報進度
        if progress_callback:
            progress_callback(progress.format_progress() + "\n")
    
    # ... 搜尋邏輯 ...
```

#### 3.3.3 進度顯示範例

**搜尋中**：
```
🚀 使用 AV-WIKI 批次併發搜尋 (併發數: 15)...

[5/51] 搜尋 MIFD-543 | ✅ 4 ❌ 1 (80.0%) | ⏱️ 剩餘 1:45 | 🚀 2.8/s | 📡 AV-WIKI
[6/51] 搜尋 SDJS-038 | ✅ 5 ❌ 1 (83.3%) | ⏱️ 剩餘 1:35 | 🚀 3.0/s | 📡 AV-WIKI
...
```

**級聯搜尋**：
```
🔄 進入第二階段：chiba-f 備援搜尋 (12 個番號)

[40/51] 搜尋 VRTM-427 | ✅ 39 ❌ 1 (97.5%) | ⏱️ 剩餘 0:22 | 🚀 1.8/s | 📡 chiba-f
[41/51] 搜尋 KAGP-070 | ✅ 40 ❌ 1 (97.6%) | ⏱️ 剩餘 0:18 | 🚀 1.9/s | 📡 chiba-f
...
```

**完成摘要**：
```
============================================================
📊 搜尋完成摘要

  ⏱️ 總耗時: 3:45
  📁 總番號: 51
  ✅ 成功: 47 (92.2%)
  ❌ 失敗: 4 (7.8%)

  📡 各來源貢獻:
     • AV-WIKI: 39 個 (83.0%)
     • chiba-f: 5 個 (10.6%)
     • JAVDB: 3 個 (6.4%)

  🚀 平均速度: 0.23 個/秒
============================================================
```

### 3.4 測試計畫

| 測試案例 | 預期結果 |
|---------|---------|
| 搜尋開始時 | 顯示 [0/N]，剩餘時間為 "--" |
| 搜尋進行中 | 剩餘時間逐漸減少且合理 |
| 快速搜尋（AV-WIKI） | 速度顯示約 5-10/s |
| 慢速搜尋（JAVDB） | 速度顯示約 0.5/s |
| 搜尋完成 | 顯示完整摘要 |

---

## 4. GUI 非同步優化

### 4.1 現狀分析

**問題描述**：
- 長時間操作時 GUI 可能無回應
- 需確認所有按鈕都有正確的背景執行緒處理

**現有機制**：
- ✅ 使用 `threading.Thread` 執行搜尋任務
- ✅ 有 `stop_event` 支援中止操作
- ⚠️ 進度更新可能造成 GUI 卡頓（大量文字更新）

### 4.2 實作目標

1. 確保所有長時間操作都在背景執行緒
2. 優化進度文字更新機制
3. 新增載入指示器
4. 改善「中止」按鈕的回饋

### 4.3 技術設計

#### 4.3.1 背景執行緒裝飾器

```python
# src/ui/utils.py (新檔案)

import threading
import functools
from typing import Callable

def run_in_background(func: Callable) -> Callable:
    """
    裝飾器：將函式放到背景執行緒執行
    
    使用方式：
        @run_in_background
        def long_running_task(self):
            ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
        thread.start()
        return thread
    return wrapper
```

#### 4.3.2 進度更新節流

```python
# src/ui/main_gui.py

class ProgressThrottler:
    """進度更新節流器，避免過於頻繁的 GUI 更新"""
    
    def __init__(self, min_interval_ms: int = 50):
        self.min_interval = min_interval_ms / 1000
        self.last_update = 0
        self.pending_message = None
        self.lock = threading.Lock()
    
    def update(self, message: str, force: bool = False) -> bool:
        """
        嘗試更新進度
        
        Args:
            message: 進度訊息
            force: 是否強制更新（用於重要訊息）
            
        Returns:
            是否成功更新
        """
        current_time = time.time()
        
        with self.lock:
            if force or (current_time - self.last_update) >= self.min_interval:
                self.last_update = current_time
                self.pending_message = None
                return True
            else:
                self.pending_message = message
                return False
    
    def flush(self) -> Optional[str]:
        """取得待處理的訊息（如果有）"""
        with self.lock:
            msg = self.pending_message
            self.pending_message = None
            return msg

class UnifiedActressClassifierGUI:
    def __init__(self, root):
        # ... 現有初始化 ...
        
        # 新增進度節流器
        self.progress_throttler = ProgressThrottler(min_interval_ms=100)
    
    def update_progress(self, message: str):
        """更新進度顯示（有節流機制）"""
        # 重要訊息強制更新
        force = any(keyword in message for keyword in ['完成', '錯誤', '開始', '===='])
        
        if self.progress_throttler.update(message, force):
            if self.is_running and self.result_text.winfo_exists():
                self.result_text.insert(tk.END, message)
                self.result_text.see(tk.END)
```

#### 4.3.3 載入指示器

```python
class LoadingIndicator:
    """載入指示器（在狀態列顯示旋轉動畫）"""
    
    FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    
    def __init__(self, status_var: tk.StringVar, base_text: str = "處理中"):
        self.status_var = status_var
        self.base_text = base_text
        self.running = False
        self.frame_index = 0
    
    def start(self, text: str = None):
        """開始動畫"""
        self.base_text = text or self.base_text
        self.running = True
        self._animate()
    
    def stop(self, final_text: str = "就緒"):
        """停止動畫"""
        self.running = False
        self.status_var.set(final_text)
    
    def _animate(self):
        """動畫循環"""
        if self.running:
            frame = self.FRAMES[self.frame_index % len(self.FRAMES)]
            self.status_var.set(f"{frame} {self.base_text}")
            self.frame_index += 1
            # 每 100ms 更新一次
            # 需要在主執行緒呼叫
```

#### 4.3.4 改善中止回饋

```python
def stop_task(self):
    """中止當前任務"""
    if not self.stop_event.is_set():
        self.stop_event.set()
        
        # 更新 UI 回饋
        self.status_var.set("🛑 正在中止任務...")
        self.stop_btn.config(state="disabled")
        
        # 顯示中止訊息
        self.update_progress("\n⚠️ 使用者要求中止，正在等待當前操作完成...\n")
```

### 4.4 需要審計的按鈕事件

| 按鈕 | 當前狀態 | 需要修改 |
|------|---------|---------|
| 日文網站搜尋 | ✅ 使用背景執行緒 | 無 |
| JAVDB 搜尋 | ✅ 使用背景執行緒 | 無 |
| 互動式移動 | ✅ 使用背景執行緒 | 無 |
| 標準移動 | ✅ 使用背景執行緒 | 無 |
| 智慧搜尋並分類 | ✅ 使用背景執行緒 | 無 |
| 片商分類 | ✅ 使用背景執行緒 | 無 |
| 瀏覽資料夾 | ⚠️ 主執行緒 | 無需修改（快速操作） |
| 偏好設定 | ⚠️ 主執行緒 | 無需修改（對話框） |

---

## 5. 搜尋結果預覽

### 5.1 現狀分析

**問題描述**：
- 搜尋完成後只顯示統計數字
- 無法看到每個番號的搜尋結果
- 無法匯出結果

### 5.2 實作目標

1. 彈出式視窗顯示搜尋結果表格
2. 支援排序（按番號、女優數、來源）
3. 支援匯出 CSV
4. 支援點擊查看詳細資訊

### 5.3 技術設計

#### 5.3.1 對話框類別

```python
# src/ui/search_result_dialog.py (新檔案)

import tkinter as tk
from tkinter import ttk, filedialog
import csv
from typing import Dict, List, Any
from dataclasses import dataclass

@dataclass
class SearchResultItem:
    """搜尋結果項目"""
    code: str
    actresses: List[str]
    source: str
    status: str  # 'success', 'failed', 'not_found'
    studio: str = ""

class SearchResultDialog:
    """搜尋結果預覽對話框"""
    
    def __init__(self, parent, results: Dict[str, SearchResultItem], title: str = "搜尋結果預覽"):
        self.parent = parent
        self.results = results
        self.title = title
        
        # 建立對話框
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("800x600")
        self.dialog.transient(parent)
        
        self._setup_ui()
        self._populate_data()
    
    def _setup_ui(self):
        """建立 UI 元件"""
        # 標題區
        header_frame = ttk.Frame(self.dialog, padding="10")
        header_frame.pack(fill="x")
        
        ttk.Label(
            header_frame, 
            text="🔍 搜尋結果預覽", 
            font=("Arial", 14, "bold")
        ).pack(side="left")
        
        # 統計資訊
        success_count = sum(1 for r in self.results.values() if r.status == 'success')
        total_count = len(self.results)
        
        ttk.Label(
            header_frame,
            text=f"✅ {success_count} / {total_count} ({success_count/total_count*100:.1f}%)",
            font=("Arial", 12)
        ).pack(side="right")
        
        # 表格區
        table_frame = ttk.Frame(self.dialog)
        table_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 建立 Treeview
        columns = ("code", "actresses", "source", "studio", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        
        # 設定欄位
        self.tree.heading("code", text="番號", command=lambda: self._sort_by("code"))
        self.tree.heading("actresses", text="女優", command=lambda: self._sort_by("actresses"))
        self.tree.heading("source", text="來源", command=lambda: self._sort_by("source"))
        self.tree.heading("studio", text="片商", command=lambda: self._sort_by("studio"))
        self.tree.heading("status", text="狀態", command=lambda: self._sort_by("status"))
        
        # 設定欄寬
        self.tree.column("code", width=100)
        self.tree.column("actresses", width=300)
        self.tree.column("source", width=80)
        self.tree.column("studio", width=100)
        self.tree.column("status", width=80)
        
        # 捲軸
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 按鈕區
        button_frame = ttk.Frame(self.dialog, padding="10")
        button_frame.pack(fill="x")
        
        ttk.Button(button_frame, text="📥 匯出 CSV", command=self._export_csv).pack(side="left", padx=5)
        ttk.Button(button_frame, text="📋 複製失敗番號", command=self._copy_failed).pack(side="left", padx=5)
        ttk.Button(button_frame, text="關閉", command=self.dialog.destroy).pack(side="right", padx=5)
    
    def _populate_data(self):
        """填充資料"""
        for code, result in self.results.items():
            # 格式化女優列表
            if result.actresses:
                if len(result.actresses) > 3:
                    actresses_str = ", ".join(result.actresses[:3]) + f" (+{len(result.actresses)-3})"
                else:
                    actresses_str = ", ".join(result.actresses)
            else:
                actresses_str = "❌ 未找到"
            
            # 狀態顯示
            status_display = {
                'success': '✅ 成功',
                'failed': '❌ 失敗',
                'not_found': '⚠️ 無資料'
            }.get(result.status, result.status)
            
            self.tree.insert("", "end", values=(
                code,
                actresses_str,
                result.source or "-",
                result.studio or "-",
                status_display
            ))
    
    def _sort_by(self, column: str):
        """按欄位排序"""
        items = [(self.tree.set(item, column), item) for item in self.tree.get_children("")]
        items.sort()
        for index, (_, item) in enumerate(items):
            self.tree.move(item, "", index)
    
    def _export_csv(self):
        """匯出為 CSV"""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 檔案", "*.csv")],
            title="匯出搜尋結果"
        )
        
        if filepath:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(["番號", "女優", "來源", "片商", "狀態"])
                
                for code, result in self.results.items():
                    writer.writerow([
                        code,
                        " # ".join(result.actresses) if result.actresses else "",
                        result.source or "",
                        result.studio or "",
                        result.status
                    ])
            
            tk.messagebox.showinfo("匯出成功", f"已匯出至:\n{filepath}")
    
    def _copy_failed(self):
        """複製失敗的番號到剪貼簿"""
        failed_codes = [code for code, r in self.results.items() if r.status != 'success']
        
        if failed_codes:
            self.dialog.clipboard_clear()
            self.dialog.clipboard_append("\n".join(failed_codes))
            tk.messagebox.showinfo("已複製", f"已複製 {len(failed_codes)} 個失敗番號到剪貼簿")
        else:
            tk.messagebox.showinfo("無失敗", "沒有失敗的番號")
```

#### 5.3.2 整合到 GUI

```python
# src/ui/main_gui.py

from ui.search_result_dialog import SearchResultDialog, SearchResultItem

def _japanese_search_worker(self, path):
    """日文網站搜尋工作執行緒（修改版）"""
    self.status_var.set("執行中：日文網站搜尋...")
    
    # 呼叫核心搜尋
    result = self.core.process_and_search_japanese_sites(
        path, 
        self.stop_event, 
        self.update_progress
    )
    
    if self.is_running:
        if result.get('status') == 'success':
            # 顯示結果摘要
            summary = f"\n{'='*60}\n🇯🇵 日文網站搜尋完成！\n\n"
            summary += f"  📁 掃描檔案: {result.get('total_files', 0)}\n"
            summary += f"  🆕 新番號: {result.get('new_codes', 0)}\n"
            summary += f"  ✅ 搜尋成功: {result.get('success', 0)}\n"
            self.update_progress(summary)
            
            # 詢問是否查看詳細結果
            if result.get('details') and result.get('new_codes', 0) > 0:
                if tk.messagebox.askyesno("搜尋完成", "是否查看詳細搜尋結果？"):
                    # 轉換結果格式
                    search_results = {}
                    for code, detail in result.get('details', {}).items():
                        search_results[code] = SearchResultItem(
                            code=code,
                            actresses=detail.get('actresses', []),
                            source=detail.get('source', ''),
                            status='success' if detail.get('actresses') else 'not_found',
                            studio=detail.get('studio', '')
                        )
                    
                    # 顯示結果對話框
                    SearchResultDialog(self.root, search_results)
            
            self.status_var.set("就緒")
        else:
            self.update_progress(f"\n💥 錯誤: {result.get('message', '未知錯誤')}\n")
            self.status_var.set(f"錯誤: {result.get('message', '未知錯誤')}")
```

### 5.4 UI 預覽

```
┌──────────────────────────────────────────────────────────────────┐
│ 🔍 搜尋結果預覽                                    ✅ 47 / 51 (92.2%) │
├──────────────────────────────────────────────────────────────────┤
│ 番號      │ 女優                        │ 來源    │ 片商    │ 狀態   │
├───────────┼─────────────────────────────┼─────────┼─────────┼────────┤
│ STARS-707 │ 天神羽衣                    │ AV-WIKI │ SOD     │ ✅ 成功│
│ MIFD-543  │ 星月えむ                    │ AV-WIKI │ MOODYZ  │ ✅ 成功│
│ SDJS-038  │ 星咲凛, 雪美千夏 (+8)       │ AV-WIKI │ SOD     │ ✅ 成功│
│ VRTM-427  │ ❌ 未找到                   │ -       │ -       │ ⚠️ 無資料│
│ KAGP-070  │ あけみみう                  │ chiba-f │ UNKNOWN │ ✅ 成功│
│ ...       │ ...                         │ ...     │ ...     │ ...    │
├──────────────────────────────────────────────────────────────────┤
│ [📥 匯出 CSV]  [📋 複製失敗番號]                          [關閉] │
└──────────────────────────────────────────────────────────────────┘
```

---

## 6. 實作順序與時程

### 6.1 建議實作順序

```
Phase 1: 基礎改善 (Day 1)
├── #3 進度顯示優化 ─────────── 30 分鐘
└── #4 GUI 非同步優化 ────────── 30 分鐘

Phase 2: 核心功能 (Day 1-2)
├── #2 多來源級聯搜尋 ────────── 2 小時
└── #5 搜尋結果預覽 ─────────── 1 小時

Phase 3: 維護功能 (Day 2)
└── #1 快取過期清理 ─────────── 1 小時

總預估時間：5 小時
```

### 6.2 依賴關係

```
#3 進度顯示優化
      │
      ▼
#2 多來源級聯搜尋 ──────► #5 搜尋結果預覽
                              │
                              ▼
                        需要 #2 的詳細結果

#4 GUI 非同步優化 ───────► 獨立，可並行
#1 快取過期清理 ─────────► 獨立，可並行
```

### 6.3 測試檢查清單

- [ ] #1 快取清理後，舊快取已刪除
- [ ] #2 級聯搜尋能正確切換來源
- [ ] #2 JAVDB 搜尋有正確的延遲
- [ ] #3 剩餘時間預估合理
- [ ] #4 長時間操作時 GUI 不卡頓
- [ ] #5 CSV 匯出格式正確
- [ ] #5 複製失敗番號功能正常

---

## 附錄：設定檔範例

完整的 `config.ini` 設定：

```ini
[paths]
default_input_dir = .

[cache]
ttl_days = 7
max_size_mb = 500
auto_cleanup_on_exit = true
min_keep_entries = 100

[search]
cascade_enabled = true
cascade_sources = avwiki,chibaf,javdb
skip_known_empty = true
javdb_delay = 2.0
avwiki_max_concurrent = 15

[ui]
progress_throttle_ms = 100
show_loading_indicator = true
auto_show_results = false
```
