# IncrementalJSONDB 架構分析報告

> **分析日期**: 2026-01-12
> **分析目的**: 為 Golang 重構做準備，理解 Python 版本的設計與實作細節
> **分析對象**: `src/models/incremental_json_database.py` (508 行)

---

## 📋 執行摘要

**IncrementalJSONDB** 是一個增量式 JSON 資料庫管理器，透過 **Journal（日誌）機制** 實現 **40x 寫入加速**。

### 核心設計理念

1. **Append-Only Journal**: 寫入操作只追加到 journal 檔案（極快）
2. **延遲合併 (Lazy Compaction)**: 只在必要時才合併 journal 到主檔案
3. **記憶體同步**: Journal 記錄立即套用到記憶體，確保讀取一致性
4. **Dirty Tracking**: 追蹤哪些資料項被修改過

### 效能提升原理

| 操作 | Python JSONDBManager | IncrementalJSONDB | 加速倍數 |
|------|---------------------|-------------------|---------|
| 寫入單一影片 | ~250ms (完整 JSON 重寫) | ~6ms (追加 journal) | **40x** |
| 讀取影片 | ~5ms | ~5ms | 1x (相同) |
| 合併操作 | N/A | ~10s (1000 條記錄) | N/A |

---

## 🏗️ 架構設計

### 檔案結構

```
data/json_db/
├── data.json         # 主資料檔案（完整狀態快照）
├── data.journal      # 增量變更日誌（JSON Lines 格式）
├── data.index        # Dirty keys 索引（加速查找）
└── data.journal.lock # FileLock 鎖定檔案
```

### 核心類別

#### 1. JournalEntry（Journal 記錄項）

```python
class JournalEntry:
    operation: str       # "ADD" | "UPDATE" | "DELETE"
    entity_type: str     # "video" | "actress" | "link"
    entity_id: str       # 實體 ID（如番號 "SONE-123"）
    data: dict | None    # 更新內容（DELETE 時為 None）
    timestamp: str       # ISO 8601 時間戳
```

**JSON 序列化格式**:
```json
{
  "op": "UPDATE",
  "type": "video",
  "id": "SONE-123",
  "data": {"title": "新標題"},
  "ts": "2026-01-12T21:00:00.000000Z"
}
```

#### 2. IncrementalJSONDB（主類別）

**關鍵屬性**:
```python
self.data_dir: Path              # 資料目錄
self.data_file: Path             # data.json
self.journal_file: Path          # data.journal
self.index_file: Path            # data.index
self.journal_lock: FileLock      # 並發鎖

self.base_db: JSONDBManager      # 底層標準資料庫
self.dirty_videos: set[str]      # 記憶體 dirty tracking
self.journal_size: int           # Journal 記錄數
self.journal_created_at: datetime # Journal 建立時間
```

---

## 🔄 核心流程

### 1. 初始化流程

```
__init__()
  │
  ├─> 初始化檔案路徑
  ├─> 建立 FileLock
  ├─> 建立 JSONDBManager (base_db)
  │
  └─> _init_journal()
       │
       ├─> journal 檔案存在？
       │    YES: _load_journal_stats() + _replay_journal()
       │    NO:  建立空 journal + 儲存索引
       │
       └─> 完成初始化
```

**_replay_journal() 重播機制**:
- 逐行讀取 journal 檔案（JSON Lines 格式）
- 解析成 JournalEntry 物件
- 呼叫 `_apply_entry_to_memory()` 套用到記憶體
- **目的**: 啟動時同步 journal 變更到記憶體，確保資料完整性

### 2. 寫入流程（快速路徑）

```
update_video(code, updates)
  │
  ├─> 檢查影片是否存在（base_db.get_video_info）
  ├─> 建立 JournalEntry(UPDATE, "video", code, updates)
  │
  └─> _append_journal(entry)
       │
       ├─> 取得 FileLock（避免並發寫入）
       ├─> 以二進位模式追加寫入 journal 檔案
       ├─> 更新 dirty_videos.add(code)
       ├─> journal_size += 1
       ├─> _save_index() 持久化 dirty tracking
       │
       └─> 立即更新記憶體: base_db.data["videos"][code].update(updates)
```

**關鍵優化點**:
1. **Append-Only**: 只需要 `open("ab") + write()` 操作，極快
2. **無需解析整個 JSON**: 不用讀取或重寫完整 data.json
3. **記憶體同步**: 確保後續讀取看到最新資料

### 3. 讀取流程（透明代理）

```
get_video_info(code)
  │
  └─> base_db.get_video_info(code)
       │
       └─> 返回記憶體中的資料（已包含 journal 變更）
```

**讀取效能**: 與標準 JSONDBManager 相同（~5ms），因為記憶體已同步。

### 4. 合併流程（重型操作）

```
compact()
  │
  ├─> 取得 FileLock
  ├─> 讀取所有 journal 記錄到記憶體 (entries: list[JournalEntry])
  │
  ├─> 逐條套用到記憶體
  │    for entry in entries:
  │        _apply_entry_to_memory(entry)
  │
  ├─> base_db._save_all_data() - 寫入完整 data.json（慢）
  │
  ├─> 清空 journal 檔案
  ├─> 重設統計資訊
  └─> 更新索引檔案
```

**合併觸發條件** (`compact_if_needed()`):
```python
JOURNAL_SIZE_THRESHOLD = 1000  # 記錄數超過 1000 條
JOURNAL_AGE_THRESHOLD = 3600   # 年齡超過 1 小時（秒）
```

---

## 📐 JSON 格式定義

### data.json（主檔案）

```json
{
  "schema_version": "1.0.0",
  "videos": {
    "SONE-123": {
      "code": "SONE-123",
      "title": "影片標題",
      "studio": "S1",
      "release_date": "2025-12-01",
      "url": "https://example.com",
      "actresses": ["女優A", "女優B"],
      "search_status": "success",
      "last_search_date": "2025-12-21T10:00:00Z",
      "created_at": "2025-12-01T00:00:00Z",
      "updated_at": "2025-12-21T10:30:00Z",
      "metadata": {
        "source": "avwiki",
        "confidence": 0.95
      }
    }
  },
  "actresses": {},
  "video_actress_links": []
}
```

### data.journal（增量日誌，JSON Lines 格式）

```jsonl
{"op":"ADD","type":"video","id":"SONE-123","data":{...},"ts":"2025-12-21T10:00:00Z"}
{"op":"UPDATE","type":"video","id":"SONE-123","data":{"title":"新標題"},"ts":"2025-12-21T10:30:00Z"}
{"op":"DELETE","type":"video","id":"OLD-999","data":null,"ts":"2025-12-21T11:00:00Z"}
```

**重要**: 每行必須是獨立的有效 JSON 物件（JSON Lines 標準）

### data.index（Dirty Tracking 索引）

```json
{
  "videos": ["SONE-123", "MIDV-456"],
  "actresses": [],
  "links": [],
  "journal_size": 42,
  "created_at": "2025-12-21T10:00:00Z"
}
```

---

## 🔐 並發控制機制

### FileLock 鎖定策略

```python
self.journal_lock = FileLock(self.journal_lock_file, timeout=10)

with self.journal_lock:
    # 寫入 journal 或合併操作
    ...
```

**鎖定範圍**:
- ✅ `_append_journal()` - 寫入時鎖定
- ✅ `compact()` - 合併時鎖定
- ❌ 讀取操作 - 不需鎖定（讀取記憶體）

**多程序安全性**:
- FileLock 使用作業系統級鎖（flock/lockf）
- 支援多程序並發讀，單程序寫入
- Timeout 10 秒後拋出異常

---

## 🎯 Go 實作設計建議

### Phase 1: 核心資料結構

```go
package database

import (
    "sync"
    "time"
)

// JournalEntry - Journal 記錄項
type JournalEntry struct {
    Operation  string                 `json:"op"`    // "ADD" | "UPDATE" | "DELETE"
    EntityType string                 `json:"type"`  // "video" | "actress" | "link"
    EntityID   string                 `json:"id"`
    Data       map[string]interface{} `json:"data,omitempty"`
    Timestamp  time.Time              `json:"ts"`
}

// IncrementalDB - 增量資料庫
type IncrementalDB struct {
    dataDir    string
    dataFile   string
    journalFile string
    indexFile  string

    // 並發控制
    mu         sync.RWMutex  // 保護記憶體資料
    fileMu     sync.Mutex    // 保護檔案寫入

    // 記憶體資料（從 base_db 載入）
    videos     map[string]map[string]interface{}

    // Dirty tracking
    dirtyVideos map[string]bool

    // Journal 統計
    journalSize      int
    journalCreatedAt time.Time
}
```

### Phase 2: 關鍵方法實作

```go
// UpdateVideo - 更新影片（快速操作）
func (db *IncrementalDB) UpdateVideo(code string, updates map[string]interface{}) error {
    // 1. 檢查影片是否存在
    db.mu.RLock()
    video, exists := db.videos[code]
    db.mu.RUnlock()

    if !exists {
        return fmt.Errorf("影片不存在: %s", code)
    }

    // 2. 建立 journal 記錄
    entry := JournalEntry{
        Operation:  "UPDATE",
        EntityType: "video",
        EntityID:   code,
        Data:       updates,
        Timestamp:  time.Now(),
    }

    // 3. 追加到 journal（鎖定檔案）
    if err := db.appendJournal(entry); err != nil {
        return err
    }

    // 4. 立即更新記憶體
    db.mu.Lock()
    for k, v := range updates {
        video[k] = v
    }
    db.videos[code] = video
    db.dirtyVideos[code] = true
    db.mu.Unlock()

    return nil
}

// appendJournal - 追加 journal（檔案寫入）
func (db *IncrementalDB) appendJournal(entry JournalEntry) error {
    db.fileMu.Lock()
    defer db.fileMu.Unlock()

    // 1. 序列化為 JSON
    data, err := json.Marshal(entry)
    if err != nil {
        return err
    }

    // 2. 追加寫入 journal 檔案
    f, err := os.OpenFile(db.journalFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
    if err != nil {
        return err
    }
    defer f.Close()

    if _, err := f.Write(data); err != nil {
        return err
    }
    if _, err := f.Write([]byte("\n")); err != nil {
        return err
    }

    // 3. 更新統計
    db.journalSize++

    // 4. 儲存索引
    return db.saveIndex()
}

// Compact - 合併 journal 到主檔案
func (db *IncrementalDB) Compact() error {
    db.mu.Lock()
    defer db.mu.Unlock()

    db.fileMu.Lock()
    defer db.fileMu.Unlock()

    // 1. 讀取所有 journal 記錄
    entries, err := db.loadJournalEntries()
    if err != nil {
        return err
    }

    // 2. 套用到記憶體（已在記憶體中，跳過）

    // 3. 寫入完整 data.json
    if err := db.saveDataFile(); err != nil {
        return err
    }

    // 4. 清空 journal
    if err := os.Truncate(db.journalFile, 0); err != nil {
        return err
    }

    // 5. 重設統計
    db.journalSize = 0
    db.journalCreatedAt = time.Now()
    db.dirtyVideos = make(map[string]bool)

    // 6. 更新索引
    return db.saveIndex()
}
```

### Phase 3: CLI 命令設計

```bash
# 更新影片
classifier.exe db update SONE-123 '{"title":"新標題"}'

# 查詢影片
classifier.exe db get SONE-123

# 強制合併
classifier.exe db compact

# 統計資訊
classifier.exe db stats
# 輸出: {"journal_size":42,"dirty_videos":3,"needs_compact":false}
```

### Phase 4: Python 橋接整合

```python
# src/services/go_bridge.py

def db_update_video(self, code: str, updates: dict) -> bool:
    """更新影片（Go 加速）"""
    if not self.is_available:
        return False

    result = subprocess.run(
        [self.exe_path, "db", "update", code, json.dumps(updates)],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise GoBridgeError(f"更新失敗: {result.stderr}")

    return True

def db_compact(self) -> dict:
    """合併 journal"""
    result = subprocess.run(
        [self.exe_path, "db", "compact"],
        capture_output=True,
        text=True
    )

    return json.loads(result.stdout)
```

---

## ⚠️ 潛在問題與解決方案

### 問題 1: Journal 無限增長

**現象**: 如果從未執行 compact，journal 檔案會無限增長。

**解決方案**:
- 實作自動合併閾值檢查
- 建議在程式啟動時檢查 `compact_if_needed()`
- CLI 提供手動 `compact` 命令

### 問題 2: 並發寫入衝突

**現象**: 多個程序同時寫入 journal 可能導致資料損壞。

**解決方案**:
- 使用 FileLock（Python）或 flock（Go）
- Timeout 機制避免死鎖
- 寫入失敗時拋出明確錯誤

### 問題 3: Journal 損壞恢復

**現象**: journal 檔案中某行 JSON 格式錯誤。

**現行策略**:
```python
try:
    entry_dict = orjson.loads(line)
except Exception as e:
    logger.warning(f"跳過損壞的 journal 記錄: {line}")
    continue  # 跳過該記錄
```

**Go 實作建議**: 相同策略，記錄警告但繼續處理。

### 問題 4: 記憶體同步一致性

**現象**: Journal 寫入成功但記憶體更新失敗。

**現行保證**:
```python
# 先寫 journal，再更新記憶體
self._append_journal(entry)  # 持久化
video.update(updates)        # 記憶體同步
```

**Go 實作**: 相同順序，確保持久性優先。

---

## 📊 效能特性分析

### 時間複雜度

| 操作 | Python 版本 | 預期 Go 版本 | 備註 |
|------|------------|-------------|------|
| UpdateVideo | O(1) | O(1) | Journal 追加寫入 |
| GetVideo | O(1) | O(1) | 雜湊表查找 |
| Compact | O(n) | O(n) | n = journal 記錄數 |
| ReplayJournal | O(n) | O(n) | 啟動時重播 |

### 空間複雜度

- **記憶體**: O(m) - m = 影片總數（完整資料載入記憶體）
- **磁碟 journal**: O(n) - n = journal 記錄數（定期合併清空）
- **磁碟 data.json**: O(m) - 完整資料備份

### 預期效能提升（Python → Go）

| 操作 | Python | Go 目標 | 提升倍數 |
|------|--------|---------|---------|
| UpdateVideo | ~6ms | **~0.5ms** | **12x** |
| Compact (1000 條) | ~10s | **~1s** | **10x** |
| ReplayJournal (1000 條) | ~2s | **~0.2s** | **10x** |

**關鍵提升來源**:
1. Go 無 GIL，真正的並發處理
2. Go JSON 序列化比 Python orjson 略快
3. Go 檔案 I/O 更高效

---

## 🔍 相依性分析

### 內部相依

```
IncrementalJSONDB
  └─> JSONDBManager (base_db)
       ├─> get_video_info()      # 查詢影片
       ├─> get_all_videos()      # 列出所有影片
       └─> _save_all_data()      # 儲存完整資料
```

**Go 實作策略**:
- Phase 1: 先實作 IncrementalDB 獨立版本（不依賴 JSONDBManager）
- Phase 2: 如需要，實作簡化版 BaseDB 提供基礎功能

### 外部依賴

| Python 套件 | 功能 | Go 替代方案 |
|------------|------|-----------|
| `orjson` | 快速 JSON 序列化 | `encoding/json` (標準庫) |
| `filelock` | 檔案鎖定 | `syscall.Flock()` (Unix) / `LockFileEx()` (Windows) |
| `pathlib` | 路徑處理 | `path/filepath` (標準庫) |

---

## ✅ 重構檢查清單

### Phase 1: 分析與設計 ✅
- [x] 理解 Journal 增量機制
- [x] 理解 Compact 合併邏輯
- [x] 記錄 JSON 格式定義
- [x] 識別並發控制機制
- [x] 分析效能瓶頸

### Phase 2: Go 實作（待執行）
- [ ] 建立 `pkg/database/` 套件
- [ ] 實作 JournalEntry struct
- [ ] 實作 IncrementalDB struct
- [ ] 實作 UpdateVideo/AddVideo/DeleteVideo
- [ ] 實作 appendJournal（檔案寫入）
- [ ] 實作 Compact/CompactIfNeeded
- [ ] 實作並發控制（Mutex + FileLock）
- [ ] 撰寫單元測試（80%+ 覆蓋率）

### Phase 3: CLI 整合（待執行）
- [ ] 新增 `db update` 命令
- [ ] 新增 `db get` 命令
- [ ] 新增 `db compact` 命令
- [ ] 新增 `db stats` 命令
- [ ] JSON 輸出格式驗證

### Phase 4: Python 橋接（待執行）
- [ ] 更新 `go_bridge.py` 新增資料庫方法
- [ ] 實作 fallback 機制
- [ ] 撰寫整合測試
- [ ] 效能基準測試（目標 10x+）

### Phase 5: 文件與驗證（待執行）
- [ ] 更新 CLAUDE.md 架構說明
- [ ] 更新 GO_MIGRATION_TODO.md 標記進度
- [ ] 撰寫遷移指南
- [ ] 回歸測試確保 Python 功能正常

---

## 📝 結論

IncrementalJSONDB 是一個設計精良的增量儲存系統，核心思想清晰：

1. **Append-Only Journal** 提供極快的寫入速度
2. **記憶體同步** 確保讀取一致性
3. **延遲合併** 平衡效能與磁碟空間
4. **FileLock** 確保並發安全

Go 重構可預期獲得 **10-12x 效能提升**，特別是在：
- 高頻率更新場景（UpdateVideo）
- Journal 合併操作（Compact）
- 大規模 Journal 重播（ReplayJournal）

**建議下一步**: 開始實作 `pkg/database/database.go` 核心結構。
