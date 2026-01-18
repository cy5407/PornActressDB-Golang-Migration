# CacheManager 架構分析報告

> 分析日期: 2026-01-19
> 分析師: Ralph AI Agent
> 目標: 評估 Go 重構可行性與設計方案

---

## 1. 概述

`src/scrapers/cache_manager.py` 實作了一個多層級智慧快取管理系統，用於快取爬蟲結果。

### 1.1 核心特性

| 特性 | 說明 |
|------|------|
| 多層級快取 | 記憶體 (L1) + 磁碟 (L2) |
| TTL 支援 | 可配置的過期時間 |
| 壓縮儲存 | 使用 gzip 壓縮大型資料 |
| LRU 策略 | 記憶體快取清理 |
| 非同步介面 | async/await 支援 |
| 背景清理 | 定時清理過期快取 |

---

## 2. 核心資料結構

### 2.1 CacheConfig (配置類)

```python
@dataclass
class CacheConfig:
    cache_dir: str = "cache"           # 快取目錄
    index_file: str = "cache_index.json"  # JSON 索引檔案
    default_ttl_hours: int = 24        # 預設 TTL (小時)
    max_memory_entries: int = 1000     # 記憶體最大條目數
    enable_compression: bool = True    # 啟用壓縮
    enable_memory_cache: bool = True   # 啟用記憶體快取
    enable_disk_cache: bool = True     # 啟用磁碟快取
    cleanup_interval_hours: int = 6    # 清理間隔
    max_file_size_mb: int = 10         # 單檔最大大小
```

### 2.2 CacheEntry (快取條目)

```python
@dataclass
class CacheEntry:
    key: str              # SHA256 雜湊鍵值
    value: Any            # 快取值 (Python 物件)
    created_at: float     # 建立時間戳
    ttl_seconds: int      # 過期秒數
    access_count: int     # 存取次數
    last_accessed: float  # 最後存取時間
    compressed: bool      # 是否壓縮
    size_bytes: int       # 大小 (bytes)
```

### 2.3 JSON 索引格式

```json
{
  "_metadata": {
    "version": "1.0",
    "created_at": 1737123456.789
  },
  "entries": {
    "a1b2c3d4...": {
      "file_path": "cache/a1/b2/a1b2c3d4....cache",
      "created_at": 1737123456.789,
      "ttl_seconds": 86400,
      "last_accessed": 1737123500.123,
      "access_count": 5,
      "compressed": true,
      "size_bytes": 1024
    }
  }
}
```

---

## 3. 檔案結構

```
cache/
├── cache_index.json        # JSON 索引檔案
├── a1/                     # 第一層目錄 (雜湊前2字元)
│   └── b2/                 # 第二層目錄 (雜湊第3-4字元)
│       └── a1b2c3d4....cache  # 快取檔案
├── c3/
│   └── d4/
│       └── c3d4e5f6....cache
...
```

**設計原理**: 使用兩層目錄結構避免單目錄檔案過多，提高檔案系統效能。

---

## 4. 核心操作流程

### 4.1 Set (寫入快取)

```
1. 生成 SHA256 雜湊鍵值
2. 序列化值 (pickle)
3. 選擇性壓縮 (>1KB 且壓縮率 >10%)
4. 檢查檔案大小限制
5. 寫入記憶體快取 (LRU 清理)
6. 寫入磁碟檔案
7. 更新 JSON 索引
```

### 4.2 Get (讀取快取)

```
1. 生成 SHA256 雜湊鍵值
2. 嘗試記憶體快取
   - 命中: 更新存取統計，返回
   - 過期: 移除，繼續
3. 嘗試磁碟快取
   - 查詢 JSON 索引
   - 檢查過期
   - 讀取檔案
   - 反序列化 (解壓縮)
   - 載入到記憶體快取
   - 更新存取統計
4. 未命中: 返回 None
```

### 4.3 Prune (清理快取)

兩種清理策略:

**過期清理 (TTL)**:
```
1. 遍歷索引
2. 檢查 created_at + ttl_seconds < now
3. 刪除過期檔案
4. 更新索引
```

**大小清理 (LRU)**:
```
1. 計算總大小
2. 如果超過限制
3. 按 last_accessed 排序
4. 刪除最舊的直到符合限制
5. 更新索引
```

---

## 5. 序列化格式

### 5.1 快取檔案 (.cache)

- 格式: Python pickle + 可選 gzip 壓縮
- 優點: 支援任意 Python 物件
- 缺點: **Python 專用，Go 無法直接讀取**

### 5.2 JSON 索引

- 格式: 標準 JSON
- 優點: Go 可直接讀寫
- 用途: 元數據管理 (不含實際快取值)

---

## 6. Go 重構可行性評估

### 6.1 挑戰

| 挑戰 | 嚴重度 | 說明 |
|------|--------|------|
| pickle 格式 | 🔴 高 | Go 無法反序列化 Python pickle |
| 動態類型 | 🟡 中 | Python `Any` 需要明確類型定義 |
| gzip 壓縮 | 🟢 低 | Go 原生支援 |
| JSON 索引 | 🟢 低 | Go 原生支援 |

### 6.2 解決方案

**方案 A: 純 Go 實作 (推薦)**

優點:
- 效能最佳
- 完全獨立

實作方式:
- 使用 JSON 或 MessagePack 取代 pickle
- 僅支援 Go 產生的新快取
- 舊 pickle 快取由 Python fallback 處理

**方案 B: 混合模式**

優點:
- 完全相容現有快取

實作方式:
- Go 處理索引操作 (stats, prune)
- Python 處理讀寫操作

**建議**: 採用方案 A，但保留 Python fallback

### 6.3 Go 可加速的操作

| 操作 | 效能提升預估 | 原因 |
|------|-------------|------|
| get_stats() | 10x+ | 純 JSON 解析 |
| cleanup_expired() | 5x+ | 檔案遍歷+刪除 |
| cleanup_by_size() | 5x+ | 排序+批次刪除 |
| clear_all() | 3x+ | 批次檔案刪除 |
| set/get | 1x | pickle 需 Python |

---

## 7. Go 套件設計建議

### 7.1 pkg/cache/ 結構

```
pkg/cache/
├── cache.go          # CacheManager 主結構
├── config.go         # CacheConfig 配置
├── entry.go          # CacheEntry 條目
├── index.go          # JSON 索引管理
├── prune.go          # 清理邏輯
└── cache_test.go     # 單元測試
```

### 7.2 Go 結構定義

```go
// CacheConfig 快取配置
type CacheConfig struct {
    CacheDir            string `json:"cache_dir"`
    IndexFile           string `json:"index_file"`
    DefaultTTLHours     int    `json:"default_ttl_hours"`
    MaxMemoryEntries    int    `json:"max_memory_entries"`
    EnableCompression   bool   `json:"enable_compression"`
    CleanupIntervalHours int   `json:"cleanup_interval_hours"`
    MaxFileSizeMB       int    `json:"max_file_size_mb"`
}

// IndexEntry 索引條目
type IndexEntry struct {
    FilePath     string  `json:"file_path"`
    CreatedAt    float64 `json:"created_at"`
    TTLSeconds   int     `json:"ttl_seconds"`
    LastAccessed float64 `json:"last_accessed"`
    AccessCount  int     `json:"access_count"`
    Compressed   bool    `json:"compressed"`
    SizeBytes    int     `json:"size_bytes"`
}

// CacheIndex 快取索引
type CacheIndex struct {
    Metadata struct {
        Version   string  `json:"version"`
        CreatedAt float64 `json:"created_at"`
    } `json:"_metadata"`
    Entries map[string]IndexEntry `json:"entries"`
}
```

### 7.3 CLI 命令設計

```bash
# 統計資訊
classifier.exe cache stats

# 清理過期快取
classifier.exe cache prune --ttl-days 7

# 清理至指定大小
classifier.exe cache prune --max-size 500

# 清空所有快取
classifier.exe cache clear --confirm
```

---

## 8. 實作優先順序

### Phase 1: 索引操作 (快速完成)

1. `GetStats()` - 讀取索引，計算統計
2. `CleanupExpired()` - 刪除過期條目
3. `CleanupBySize()` - LRU 清理
4. `ClearAll()` - 清空快取

### Phase 2: CLI 整合

1. `cache stats` 命令
2. `cache prune` 命令
3. `cache clear` 命令

### Phase 3: Python 橋接

1. 更新 `go_bridge.py`
2. 實作 `GoAcceleratedCacheManager`
3. Fallback 機制

---

## 9. 效能預估

| 操作 | Python | Go (預估) | 提升 |
|------|--------|----------|------|
| stats | ~50ms | ~5ms | 10x |
| prune (1000 files) | ~2s | ~0.4s | 5x |
| clear (1000 files) | ~1.5s | ~0.5s | 3x |

---

## 10. 風險評估

| 風險 | 機率 | 影響 | 緩解措施 |
|------|------|------|----------|
| pickle 相容性 | 高 | 低 | 僅處理索引操作 |
| 索引損壞 | 低 | 中 | 備份+修復機制 |
| 檔案鎖衝突 | 低 | 中 | 使用 filelock |

---

## 11. 結論

### 建議實作範圍

✅ **適合 Go 實作**:
- `GetStats()` - 純 JSON 操作
- `CleanupExpired()` - 檔案刪除
- `CleanupBySize()` - 排序+刪除
- `ClearAll()` - 批次刪除

❌ **保留 Python 實作**:
- `Set()` - 需要 pickle 序列化
- `Get()` - 需要 pickle 反序列化
- 非同步操作

### 預估工時

| 階段 | 工時 |
|------|------|
| Go 索引操作 | 2 小時 |
| CLI 整合 | 1 小時 |
| Python 橋接 | 1 小時 |
| 測試 | 1 小時 |
| **總計** | **5 小時** |

---

*報告結束*
