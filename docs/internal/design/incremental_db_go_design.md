# Go IncrementalDB 設計文件

> 基於 Python `IncrementalJSONDB` 的 Go 實作設計
> 建立日期: 2026-01-15

## 1. Python 架構分析摘要

### 1.1 核心組件

**IncrementalJSONDB 類別** (`src/models/incremental_json_database.py`)
- 提供 40x 寫入加速的增量儲存機制
- 基於 Journal 的 append-only 寫入
- 延遲合併 (lazy compaction) 策略

### 1.2 檔案結構

```
data/json_db/
├── data.json        # 主資料檔案 (完整狀態)
├── data.journal     # 增量變更日誌 (JSON Lines 格式)
├── data.index       # Dirty keys 索引
├── data.journal.lock # Journal 鎖定檔案
└── db.lock          # 主資料庫鎖定檔案
```

### 1.3 Journal 記錄格式 (JSON Lines)

```json
{"op":"ADD","type":"video","id":"STARS-707","data":{...},"ts":"2026-01-15T10:30:00+00:00"}
{"op":"UPDATE","type":"video","id":"STARS-707","data":{"title":"新標題"},"ts":"2026-01-15T10:31:00+00:00"}
{"op":"DELETE","type":"video","id":"STARS-707","data":null,"ts":"2026-01-15T10:32:00+00:00"}
```

**操作類型**:
- `ADD`: 新增實體
- `UPDATE`: 更新實體 (僅包含變更欄位)
- `DELETE`: 刪除實體

**實體類型**:
- `video`: 影片
- `actress`: 女優
- `link`: 影片-女優關聯

### 1.4 Index 檔案格式

```json
{
  "videos": ["STARS-707", "SONE-860"],
  "actresses": [],
  "links": [],
  "journal_size": 2,
  "created_at": "2026-01-15T10:30:00+00:00"
}
```

### 1.5 主資料庫結構 (data.json)

```json
{
  "schema_version": "1.0.0",
  "metadata": {
    "description": "Python 女優分類系統 JSON 資料庫",
    "encoding": "UTF-8"
  },
  "data_hash": "sha256...",
  "created_at": "2025-10-16T16:19:46Z",
  "updated_at": "2026-01-13T14:32:55Z",
  "videos": {
    "STARS-707": {
      "code": "STARS-707",
      "title": "...",
      "studio": "SOD",
      "release_date": "",
      "url": "",
      "actresses": ["女優名"],
      "search_status": "success",
      "last_search_date": "2025-11-16T00:43:06Z",
      "created_at": "2025-11-15T16:43:06Z",
      "updated_at": "2025-11-15T17:01:50Z",
      "metadata": {
        "source": "",
        "confidence": 0.0
      },
      "original_filename": "STARS-707.mp4",
      "file_path": "C:\\...",
      "search_method": "AV-WIKI"
    }
  },
  "actresses": {},
  "links": [],
  "statistics": {}
}
```

### 1.6 合併閾值

```python
JOURNAL_SIZE_THRESHOLD = 1000   # 條記錄
JOURNAL_AGE_THRESHOLD = 3600    # 秒 (1小時)
```

## 2. Go 套件設計

### 2.1 套件結構

```
pkg/database/
├── database.go        # 核心介面和常數
├── journal.go         # JournalEntry 和 Journal 操作
├── index.go           # Index 管理
├── incremental.go     # IncrementalDB 主實作
├── types.go           # 型別定義
└── database_test.go   # 單元測試
```

### 2.2 核心介面

```go
// Database 定義資料庫操作介面
type Database interface {
    // 影片操作
    GetVideo(code string) (*Video, error)
    AddVideo(video *Video) error
    UpdateVideo(code string, updates map[string]any) error
    DeleteVideo(code string) error
    GetAllVideos(filter *VideoFilter) ([]*Video, error)

    // 統計
    GetStats() (*Stats, error)

    // 合併
    CompactIfNeeded() (bool, error)
    Compact() error

    // 生命週期
    Close() error
}
```

### 2.3 型別定義

```go
// Video 影片資料結構
type Video struct {
    Code            string            `json:"code"`
    Title           string            `json:"title"`
    Studio          string            `json:"studio"`
    ReleaseDate     string            `json:"release_date"`
    URL             string            `json:"url"`
    Actresses       []string          `json:"actresses"`
    SearchStatus    string            `json:"search_status"`
    LastSearchDate  string            `json:"last_search_date"`
    CreatedAt       string            `json:"created_at"`
    UpdatedAt       string            `json:"updated_at"`
    Metadata        *VideoMetadata    `json:"metadata"`
    OriginalFilename string           `json:"original_filename,omitempty"`
    FilePath        string            `json:"file_path,omitempty"`
    SearchMethod    string            `json:"search_method,omitempty"`
    ID              string            `json:"id,omitempty"` // 舊欄位相容
}

// JournalEntry Journal 記錄項
type JournalEntry struct {
    Operation   string         `json:"op"`
    EntityType  string         `json:"type"`
    EntityID    string         `json:"id"`
    Data        map[string]any `json:"data,omitempty"`
    Timestamp   string         `json:"ts"`
}

// Index Dirty keys 索引
type Index struct {
    Videos      []string `json:"videos"`
    Actresses   []string `json:"actresses"`
    Links       []string `json:"links"`
    JournalSize int      `json:"journal_size"`
    CreatedAt   string   `json:"created_at"`
}
```

### 2.4 IncrementalDB 實作

```go
type IncrementalDB struct {
    dataDir      string
    dataFile     string
    journalFile  string
    indexFile    string

    // 鎖定
    journalLock  *sync.Mutex
    dataLock     *sync.RWMutex

    // 記憶體狀態
    data         *DatabaseData
    dirtyVideos  map[string]bool

    // Journal 統計
    journalSize  int
    journalCreatedAt time.Time
}
```

### 2.5 CLI 命令設計

```bash
# 查詢影片
classifier.exe db get <code>

# 更新影片
classifier.exe db update <code> -field title -value "新標題"

# 合併 Journal
classifier.exe db compact

# 統計資訊
classifier.exe db stats
```

**JSON 輸出格式**:
```json
{
  "success": true,
  "operation": "get",
  "data": {...},
  "error": null
}
```

## 3. 實作計畫

### Phase 1: 核心型別和檔案操作
1. 定義 Go 型別 (types.go)
2. 實作 JSON 讀寫 (使用 encoding/json)
3. 實作檔案鎖定 (使用 flock)

### Phase 2: Journal 機制
1. 實作 JournalEntry 序列化/反序列化
2. 實作 Journal 追加寫入
3. 實作 Journal 重播

### Phase 3: CRUD 操作
1. GetVideo / GetAllVideos
2. AddVideo / UpdateVideo / DeleteVideo
3. 自動同步記憶體狀態

### Phase 4: 合併和統計
1. CompactIfNeeded 閾值判斷
2. Compact 強制合併
3. GetStats 統計查詢

### Phase 5: CLI 整合
1. db get 命令
2. db update 命令
3. db compact 命令
4. db stats 命令

### Phase 6: Python 橋接
1. 更新 go_bridge.py
2. 實作 fallback 機制
3. 整合測試

## 4. 相容性考量

### 4.1 JSON 格式相容
- 必須與 Python orjson 輸出完全一致
- 支援舊有 `id` 欄位 (等同於 `code`)
- 保持 schema_version = "1.0.0"

### 4.2 時間戳格式
- ISO 8601 格式: `2026-01-15T10:30:00Z`
- 支援帶時區: `2026-01-15T10:30:00+00:00`

### 4.3 編碼
- 一律使用 UTF-8
- 支援日文字元

### 4.4 並發安全
- Journal 寫入需要鎖定
- 讀取操作可並發
- 合併操作需要獨佔鎖

## 5. 效能目標

| 操作 | Python 基準 | Go 目標 | 目標倍數 |
|------|------------|---------|---------|
| 單筆更新 | ~25ms | <1ms | 25x |
| 批次更新 (100筆) | ~2.5s | <10ms | 250x |
| 合併 (1000條 Journal) | ~5s | <100ms | 50x |
| 讀取單筆 | ~1ms | <0.1ms | 10x |

## 6. 測試策略

### 單元測試
- Journal 讀寫測試
- CRUD 操作測試
- 合併邏輯測試
- 並發安全測試

### 整合測試
- Python 產生的資料相容性
- CLI 命令測試
- GoBridge 整合測試

### 效能測試
- 批次寫入基準測試
- 合併效能基準測試
- 記憶體使用量監控
