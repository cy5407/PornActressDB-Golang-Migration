# Go 資料庫模組設計文件

> **分析來源**: `src/models/incremental_json_database.py`
> **目標套件**: `pkg/database/`
> **分析日期**: 2026-01-12
> **效能目標**: 40x 寫入加速

---

## 📋 Python 原始架構分析

### 核心機制：增量儲存 (Incremental Storage)

**設計理念**：
將頻繁的小規模更新（新增/修改單一影片）從完整 JSON 重寫改為 append-only journal 記錄，實現 **40x 寫入加速**。

**三層檔案結構**：

```
data/json_db/
├── data.json          # 主資料檔案（完整狀態快照）
├── data.journal       # 增量變更日誌（JSON Lines 格式）
└── data.index         # Dirty keys 索引（快速查找）
```

### Journal 機制詳解

#### 1. Journal 檔案格式（JSON Lines）

每行一條 JSON 記錄，包含操作類型和資料：

```json
{"op": "ADD", "type": "video", "id": "SONE-123", "data": {...}, "ts": "2026-01-12T10:00:00Z"}
{"op": "UPDATE", "type": "video", "id": "SONE-123", "data": {"title": "新標題"}, "ts": "2026-01-12T10:01:00Z"}
{"op": "DELETE", "type": "video", "id": "SONE-123", "data": null, "ts": "2026-01-12T10:02:00Z"}
```

**欄位說明**：
- `op`: 操作類型（`ADD`, `UPDATE`, `DELETE`）
- `type`: 實體類型（`video`, `actress`, `link`）
- `id`: 實體識別符（影片番號、女優 ID）
- `data`: 操作資料（`UPDATE` 僅包含變更欄位，`DELETE` 為 null）
- `ts`: 時間戳（ISO 8601 格式）

#### 2. Dirty Index 格式

追蹤被修改的實體，用於快速查找和合併判斷：

```json
{
  "videos": ["SONE-123", "MIDV-456"],
  "actresses": [],
  "links": [],
  "journal_size": 15,
  "created_at": "2026-01-12T10:00:00Z"
}
```

### 讀寫流程

#### 讀取流程（Read）

```
1. 載入 data.json 到記憶體
2. 重播 data.journal 所有記錄
3. 套用變更到記憶體
4. 返回最新狀態
```

**時間複雜度**: O(n + m)，其中 n = 主檔案大小，m = journal 記錄數

#### 寫入流程（Write）

```
1. 驗證操作（如檢查影片是否存在）
2. 建立 JournalEntry
3. Append 到 data.journal（O(1) 操作）
4. 更新 dirty index
5. 立即更新記憶體狀態（確保讀取一致性）
```

**時間複雜度**: O(1)（純 append 操作）

#### 合併流程（Compact）

```
1. 讀取所有 journal 記錄
2. 套用到記憶體中的主資料
3. 寫回 data.json（完整重寫）
4. 清空 data.journal
5. 重設 dirty index
```

**觸發條件**（兩者其一）：
- Journal 記錄數 ≥ 1000 條
- Journal 年齡 ≥ 1 小時（3600 秒）

### 並發控制

使用 `filelock.FileLock` 保護 journal 寫入：

```python
self.journal_lock = FileLock(self.data_dir / "data.journal.lock", timeout=10)

with self.journal_lock:
    # 原子性寫入 journal
    f.write(orjson.dumps(entry.to_dict()))
    f.write(b"\n")
```

**鎖定範圍**: 僅鎖定 journal 寫入（不影響讀取）

### 資料一致性保證

1. **記憶體同步**: 寫入 journal 後立即更新記憶體中的 `base_db.data`
2. **原子操作**: 每條 journal 記錄獨立，失敗不影響其他記錄
3. **WAL 機制**: Journal 類似 Write-Ahead Log，crash 後可重播恢復

---

## 🏗️ Go 實作設計

### 套件結構

```
pkg/database/
├── database.go           # IncrementalDB 主邏輯
├── journal.go            # Journal 管理
├── types.go              # 資料結構定義
├── compact.go            # 合併邏輯
├── database_test.go      # 單元測試
└── benchmark_test.go     # 效能測試
```

### 核心資料結構

```go
// IncrementalDB - 增量資料庫
type IncrementalDB struct {
    dataDir       string
    dataFile      string
    journalFile   string
    indexFile     string

    // 鎖定機制
    journalMu     sync.RWMutex

    // 記憶體快取
    data          *DatabaseData

    // Dirty tracking
    dirtyVideos   map[string]bool
    dirtyActresses map[string]bool
    dirtyLinks    map[string]bool

    // Journal 統計
    journalSize   int
    journalCreatedAt time.Time
}

// DatabaseData - 主資料結構
type DatabaseData struct {
    SchemaVersion string                `json:"schema_version"`
    Videos        map[string]*VideoData `json:"videos"`
    Actresses     map[string]*ActressData `json:"actresses"`
    Links         []*VideoActressLink   `json:"links"`
    UpdatedAt     string                `json:"updated_at"`
}

// JournalEntry - Journal 記錄項
type JournalEntry struct {
    Op        string          `json:"op"`    // ADD, UPDATE, DELETE
    Type      string          `json:"type"`  // video, actress, link
    ID        string          `json:"id"`
    Data      json.RawMessage `json:"data"`  // 原始 JSON（延遲解析）
    Timestamp string          `json:"ts"`
}

// VideoData - 影片資料（與 Python VideoDict 相容）
type VideoData struct {
    Code          string   `json:"code"`
    Title         string   `json:"title"`
    Studio        string   `json:"studio"`
    ReleaseDate   string   `json:"release_date"`
    URL           string   `json:"url"`
    Actresses     []string `json:"actresses"`
    SearchStatus  string   `json:"search_status"`
    LastSearchDate string  `json:"last_search_date"`
    CreatedAt     string   `json:"created_at"`
    UpdatedAt     string   `json:"updated_at"`
}
```

### 核心 API 設計

```go
// New - 建立增量資料庫
func New(dataDir string) (*IncrementalDB, error)

// UpdateVideo - 更新影片（快速操作）
func (db *IncrementalDB) UpdateVideo(code string, updates map[string]interface{}) error

// AddVideo - 新增影片（快速操作）
func (db *IncrementalDB) AddVideo(video *VideoData) error

// DeleteVideo - 刪除影片（快速操作）
func (db *IncrementalDB) DeleteVideo(code string) error

// GetVideo - 查詢影片
func (db *IncrementalDB) GetVideo(code string) (*VideoData, error)

// GetAllVideos - 取得所有影片
func (db *IncrementalDB) GetAllVideos() ([]*VideoData, error)

// CompactIfNeeded - 自動判斷是否合併
func (db *IncrementalDB) CompactIfNeeded() (bool, error)

// Compact - 強制合併
func (db *IncrementalDB) Compact() error

// GetStats - 取得統計資訊
func (db *IncrementalDB) GetStats() (*Stats, error)
```

### Journal 管理邏輯

```go
// appendJournal - 追加 journal 記錄（核心加速邏輯）
func (db *IncrementalDB) appendJournal(entry *JournalEntry) error {
    db.journalMu.Lock()
    defer db.journalMu.Unlock()

    // 1. 序列化 entry
    data, err := json.Marshal(entry)
    if err != nil {
        return fmt.Errorf("marshal journal entry: %w", err)
    }

    // 2. Append 到檔案（O(1) 操作）
    f, err := os.OpenFile(db.journalFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
    if err != nil {
        return fmt.Errorf("open journal file: %w", err)
    }
    defer f.close()

    if _, err := f.Write(append(data, '\n')); err != nil {
        return fmt.Errorf("write journal: %w", err)
    }

    // 3. 更新統計
    db.journalSize++

    // 4. 更新 dirty tracking
    switch entry.Type {
    case "video":
        db.dirtyVideos[entry.ID] = true
    case "actress":
        db.dirtyActresses[entry.ID] = true
    }

    // 5. 儲存索引
    return db.saveIndex()
}

// replayJournal - 重播 journal 到記憶體
func (db *IncrementalDB) replayJournal() error {
    f, err := os.Open(db.journalFile)
    if err != nil {
        if os.IsNotExist(err) {
            return nil // journal 不存在，正常情況
        }
        return fmt.Errorf("open journal: %w", err)
    }
    defer f.Close()

    scanner := bufio.NewScanner(f)
    count := 0

    for scanner.Scan() {
        var entry JournalEntry
        if err := json.Unmarshal(scanner.Bytes(), &entry); err != nil {
            log.Printf("⚠️ 跳過無效 journal 記錄: %v", err)
            continue
        }

        if err := db.applyEntry(&entry); err != nil {
            log.Printf("❌ 套用 journal 失敗: %v", err)
            continue
        }

        count++
    }

    log.Printf("✅ 重播 %d 條 journal 記錄", count)
    return scanner.Err()
}
```

### 合併邏輯

```go
// Compact - 合併 journal 到主檔案
func (db *IncrementalDB) Compact() error {
    db.journalMu.Lock()
    defer db.journalMu.Unlock()

    log.Printf("🔄 開始合併 %d 條 journal 記錄...", db.journalSize)

    // 1. 重播所有 journal（確保記憶體狀態最新）
    if err := db.replayJournal(); err != nil {
        return fmt.Errorf("replay journal: %w", err)
    }

    // 2. 序列化記憶體資料
    data, err := json.MarshalIndent(db.data, "", "  ")
    if err != nil {
        return fmt.Errorf("marshal data: %w", err)
    }

    // 3. 寫入主檔案（原子性寫入 - 先寫 temp 再 rename）
    tempFile := db.dataFile + ".tmp"
    if err := os.WriteFile(tempFile, data, 0644); err != nil {
        return fmt.Errorf("write temp file: %w", err)
    }

    if err := os.Rename(tempFile, db.dataFile); err != nil {
        return fmt.Errorf("rename file: %w", err)
    }

    // 4. 清空 journal
    if err := os.Truncate(db.journalFile, 0); err != nil {
        return fmt.Errorf("truncate journal: %w", err)
    }

    // 5. 重設統計
    db.journalSize = 0
    db.journalCreatedAt = time.Now()
    db.dirtyVideos = make(map[string]bool)
    db.dirtyActresses = make(map[string]bool)
    db.dirtyLinks = make(map[string]bool)

    // 6. 更新索引
    if err := db.saveIndex(); err != nil {
        return fmt.Errorf("save index: %w", err)
    }

    log.Printf("✅ 合併完成")
    return nil
}

// CompactIfNeeded - 自動判斷是否需要合併
func (db *IncrementalDB) CompactIfNeeded() (bool, error) {
    // 檢查大小閾值
    if db.journalSize >= 1000 {
        log.Printf("📊 Journal 超過大小閾值，開始合併...")
        return true, db.Compact()
    }

    // 檢查時間閾值
    age := time.Since(db.journalCreatedAt)
    if age >= time.Hour {
        log.Printf("⏰ Journal 超過時間閾值，開始合併...")
        return true, db.Compact()
    }

    return false, nil
}
```

---

## 🧪 測試策略

### 單元測試案例

```go
func TestIncrementalDB_UpdateVideo(t *testing.T) {
    // 測試快速更新
}

func TestIncrementalDB_AddVideo(t *testing.T) {
    // 測試新增影片
}

func TestIncrementalDB_Journal_Replay(t *testing.T) {
    // 測試 journal 重播
}

func TestIncrementalDB_Compact(t *testing.T) {
    // 測試合併邏輯
}

func TestIncrementalDB_CompactIfNeeded(t *testing.T) {
    // 測試自動合併觸發
}

func TestIncrementalDB_Concurrent(t *testing.T) {
    // 測試並發安全
}

func TestIncrementalDB_Crash_Recovery(t *testing.T) {
    // 測試 crash 後恢復
}
```

### 基準測試

```go
func BenchmarkIncrementalDB_UpdateVideo(b *testing.B) {
    // 測試單次更新效能
}

func BenchmarkIncrementalDB_BatchUpdate(b *testing.B) {
    // 測試批次更新效能
}

func BenchmarkIncrementalDB_Compact(b *testing.B) {
    // 測試合併效能
}
```

**效能目標**：
- 單次更新: < 1ms（Python: ~40ms）
- 批次更新 100 筆: < 50ms（Python: ~2000ms）
- 合併 1000 筆: < 500ms

---

## 🔗 Python-Go 整合

### CLI 命令設計

```bash
# 更新影片
classifier.exe db update SONE-123 '{"title": "新標題"}'

# 新增影片
classifier.exe db add '{"code": "SONE-123", "title": "...", ...}'

# 刪除影片
classifier.exe db delete SONE-123

# 查詢影片
classifier.exe db get SONE-123

# 統計資訊
classifier.exe db stats

# 手動合併
classifier.exe db compact

# 批次更新（讀取 JSON 檔案）
classifier.exe db batch-update updates.json
```

**JSON 輸出格式**（與 Python 完全相容）：

```json
{
  "success": true,
  "data": {
    "code": "SONE-123",
    "title": "新標題",
    ...
  },
  "error": null
}
```

### GoBridge 整合

```python
# src/services/go_bridge.py

class GoBridge:
    def update_video(self, code: str, updates: dict) -> dict:
        """更新影片（使用 Go 加速）"""
        result = self._run_command([
            self.exe_path, "db", "update",
            code,
            json.dumps(updates)
        ])
        return json.loads(result.stdout)

    def add_video(self, video: dict) -> dict:
        """新增影片（使用 Go 加速）"""
        result = self._run_command([
            self.exe_path, "db", "add",
            json.dumps(video)
        ])
        return json.loads(result.stdout)

    def compact_database(self) -> dict:
        """合併資料庫"""
        result = self._run_command([
            self.exe_path, "db", "compact"
        ])
        return json.loads(result.stdout)
```

### Fallback 機制

```python
# src/models/incremental_json_database.py

class IncrementalJSONDB:
    def __init__(self, data_dir: str):
        self.go_bridge = get_bridge()
        self.use_go = self.go_bridge.is_available

        if self.use_go:
            logger.info("✅ 使用 Go 加速資料庫")
        else:
            logger.warning("⚠️ Go CLI 不可用，使用 Python 實作")

    def update_video(self, code: str, updates: dict):
        if self.use_go:
            try:
                result = self.go_bridge.update_video(code, updates)
                if result['success']:
                    return
            except Exception as e:
                logger.warning(f"Go 更新失敗，降級到 Python: {e}")
                self.use_go = False

        # Python fallback
        self._update_video_python(code, updates)
```

---

## 📊 效能預估

| 操作 | Python (現況) | Go (目標) | 提升倍數 |
|------|--------------|-----------|---------|
| 單次更新 | ~40ms | <1ms | **40x** |
| 批次更新 100 筆 | ~2000ms | <50ms | **40x** |
| 合併 1000 筆 | ~5000ms | <500ms | **10x** |
| Journal 重播 | ~500ms | <50ms | **10x** |

**瓶頸分析**：
- Python: `orjson.dumps()` + 檔案 I/O + GIL 鎖定
- Go: 原生 JSON 編碼 + buffered I/O + goroutine 並發

---

## ⚠️ 實作注意事項

1. **JSON 相容性**: 確保 Go struct tags 與 Python dict keys 完全一致
2. **時間格式**: 統一使用 ISO 8601 格式 (`2026-01-12T10:00:00Z`)
3. **錯誤處理**: 使用 `fmt.Errorf("...: %w", err)` 包裝錯誤
4. **並發安全**: 使用 `sync.RWMutex` 保護共享資源
5. **原子寫入**: 使用 temp file + rename 確保資料完整性
6. **記憶體管理**: 避免一次載入過大 JSON（考慮串流處理）

---

## 📝 下一步

1. ✅ 完成設計文件（當前步驟）
2. ⬜ 實作 `pkg/database/types.go` - 資料結構定義
3. ⬜ 實作 `pkg/database/journal.go` - Journal 管理
4. ⬜ 實作 `pkg/database/database.go` - 核心邏輯
5. ⬜ 實作 `pkg/database/compact.go` - 合併邏輯
6. ⬜ 撰寫單元測試 `database_test.go`
7. ⬜ 整合到 CLI (`cmd/scanner/main.go`)
8. ⬜ 更新 `go_bridge.py`
9. ⬜ 效能基準測試
10. ⬜ 更新文件

---

**設計完成日期**: 2026-01-12
**預計實作時間**: 2-3 個工作循環
**預期效能提升**: 40x 寫入加速
