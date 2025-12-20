# Go 遷移 Todo List

> 最後更新：2025-12-21

## ✅ 已完成

- [x] **番號提取器** - `pkg/extractor/extractor.go`
  - 14 個測試案例全通過
  - 支援多種番號格式（標準、無橫槓、數字格式）
  - 自動跳過 FC2/PPV

- [x] **CLI 掃描器** - `cmd/scanner/main.go`
  - 支援並發處理（`-workers` 參數）
  - JSON 輸出格式
  - 編譯產出：`classifier.exe`

- [x] **Python 整合** - `tools/integration/go_integration.py`
  - subprocess 呼叫 Go CLI
  - JSON 結果解析

- [x] **檔案移動器** - `pkg/mover/mover.go` ⭐ 新完成
  - 11 個測試案例全通過
  - 支援 4 種衝突策略（skip, overwrite, rename, merge）
  - 批次移動、操作日誌、回滾功能
  - CLI 整合：`classifier.exe move`、`classifier.exe history`

---

## 📋 待實作

### Phase 1: 檔案移動器 ✅ 已完成

#### Python 原始程式碼分析

檔案移動功能分散在多個檔案中：

| 檔案 | 函式 | 說明 |
|------|------|------|
| `src/services/classifier_core.py` | `move_files()` | 智慧移動（單人自動，多人互動） |
| `src/services/classifier_core.py` | `interactive_move_files()` | 互動式移動（使用者選擇） |
| `src/services/classifier_core.py` | `smart_search_and_move()` | 搜尋 + 移動一體化 |
| `src/services/studio_classifier.py` | `_move_actresses_by_studio()` | 按片商移動女優資料夾 |
| `src/services/studio_classifier.py` | `_merge_actress_folders()` | 資料夾合併（處理同名） |

#### 相依性分析

```
檔案移動器
├── 核心依賴
│   ├── shutil.move()              # 檔案移動 API
│   ├── pathlib.Path               # 路徑處理
│   └── os (mkdir, exists, etc.)   # 檔案系統操作
│
├── 資料依賴
│   ├── db_manager.get_video_info()     # 查詢番號對應女優
│   ├── code_extractor.extract_code()   # 從檔名提取番號 ✅ Go 已實作
│   └── studio_identifier.identify()    # 識別片商
│
├── 邏輯依賴
│   ├── preference_manager               # 取得使用者設定（單體企劃資料夾名等）
│   ├── _parse_actresses_list()          # 解析女優列表（判斷單人/多人）
│   └── _is_actress_folder()             # 判斷是否為女優資料夾
│
└── UI 依賴（不需遷移）
    ├── progress_callback               # 進度回報
    └── interactive_classifier          # 互動選擇對話框（GUI）
```

#### Go 實作範圍

**適合 Go 實作（純 I/O 操作）**：
- [ ] 單檔移動
- [ ] 批次移動（並發）
- [ ] 資料夾合併（處理同名檔案）
- [ ] Dry-run 預覽模式
- [ ] 進度回報（JSON stdout）

**保留在 Python（需要互動或複雜邏輯）**：
- 互動式選擇（GUI 對話框）
- 智慧搜尋 + 移動（涉及網路爬蟲）
- 複雜的分類邏輯判斷

#### 實作清單

- [ ] `pkg/mover/mover.go` - 核心移動邏輯
  - [ ] `MoveFile(src, dst string) error` - 單檔移動
  - [ ] `MoveFiles(items []MoveItem, workers int) []MoveResult` - 批次移動
  - [ ] `MergeFolder(src, dst string) MergeResult` - 資料夾合併
  - [ ] 衝突處理策略（重命名 `_1`, `_2`...）
  - [ ] Dry-run 模式

- [ ] `pkg/mover/mover_test.go` - 單元測試
  - [ ] 基本移動測試
  - [ ] 衝突處理測試
  - [ ] 並發安全測試
  - [ ] 錯誤處理測試

- [ ] `cmd/mover/main.go` - CLI 介面
  ```bash
  classifier.exe move -src "A" -dst "B"              # 單檔/資料夾移動
  classifier.exe move -batch moves.json             # 批次移動（讀取 JSON）
  classifier.exe move -src "A" -dst "B" -dry-run    # 預覽模式
  classifier.exe move -src "A" -dst "B" -merge      # 合併模式
  ```

- [ ] Python 整合
  - [ ] `tools/integration/go_mover.py` - 呼叫 Go CLI
  - [ ] 修改 `classifier_core.py` - 替換 `shutil.move`

#### 資料結構定義

```go
// MoveItem - 單次移動任務
type MoveItem struct {
    Src string `json:"src"`           // 來源路徑
    Dst string `json:"dst"`           // 目標路徑
}

// MoveResult - 移動結果
type MoveResult struct {
    Src      string `json:"src"`
    Dst      string `json:"dst"`
    Success  bool   `json:"success"`
    Error    string `json:"error,omitempty"`
    Action   string `json:"action"`   // "moved", "merged", "skipped", "renamed"
    NewName  string `json:"new_name,omitempty"` // 若重命名，記錄新名稱
}

// MergeResult - 合併結果
type MergeResult struct {
    Success      bool   `json:"success"`
    FilesMoved   int    `json:"files_moved"`
    FilesSkipped int    `json:"files_skipped"`
    FilesFailed  int    `json:"files_failed"`
    Error        string `json:"error,omitempty"`
}

// BatchResult - 批次操作結果
type BatchResult struct {
    Total     int           `json:"total"`
    Success   int           `json:"success"`
    Failed    int           `json:"failed"`
    Skipped   int           `json:"skipped"`
    Results   []MoveResult  `json:"results"`
}
```

#### 錯誤處理策略

| 錯誤類型 | 處理方式 | 回傳 |
|---------|---------|------|
| 來源不存在 | 跳過 | `Action: "skipped"` |
| 目標已存在 | 重命名 `_1`, `_2`... | `Action: "renamed"` |
| 權限不足 | 跳過並記錄 | `Success: false, Error: "..."` |
| 磁碟空間不足 | 中止整批操作 | 立即回傳錯誤 |
| 跨磁碟移動 | 複製 + 刪除 | 正常處理 |
| 路徑過長 (Windows) | 使用 `\\?\` 前綴 | 正常處理 |

---

### Phase 2: 片商識別器 ⭐⭐⭐⭐

#### Python 原始程式碼位置

| 檔案 | 說明 |
|------|------|
| `src/models/studio.py` | `StudioIdentifier` 類別 |
| `studios.json` | 片商對應表 |

#### 相依性分析

```
片商識別器
├── 輸入
│   └── 番號字串 (如 "SONE-123")
│
├── 資料依賴
│   └── studios.json - 片商對應表
│       ├── prefix -> studio_name 對應
│       └── 大片商 vs 小片商分類
│
└── 輸出
    └── 片商名稱 (如 "S1")
```

#### 實作清單

- [ ] `pkg/studio/identifier.go` - 識別邏輯
  - [ ] 載入 `studios.json`
  - [ ] 番號前綴匹配
  - [ ] 大片商判斷

- [ ] `pkg/studio/identifier_test.go` - 測試

- [ ] 整合到 CLI
  ```bash
  classifier.exe identify SONE-123    # 輸出: S1
  classifier.exe identify -batch codes.txt
  ```

#### `studios.json` 結構說明

```json
{
  "S1": ["SSIS", "SSNI", "SONE", "ONEZ", "OFJE", "SNOS"],
  "MOODYZ": ["MIRD", "MIDD", "MIDV", "MIDE", "MIAB"],
  "PREMIUM": ["IPX", "IPZ", "IPZZ", "IDEA", "PRED"],
  ...
}
```

**格式**：`片商名稱 -> [番號前綴列表]`

#### 大片商清單

以下片商會被分類到專屬資料夾（其他歸入「單體企劃女優」）：

```go
var MajorStudios = map[string]bool{
    "S1":        true,
    "MOODYZ":    true,
    "PREMIUM":   true,
    "FALENO":    true,
    "KAWAII":    true,
    "ATTACKERS": true,
    "E-BODY":    true,
    "SOD":       true,
    "PRESTIGE":  true,
    "MADONNA":   true,
    "OPPAI":     true,
    "FITCH":     true,
    "WANZ":      true,
}
```

#### 片商別名對照

```go
var StudioAliases = map[string]string{
    "MOODYZ DIVA":     "MOODYZ",
    "S1 NO.1 STYLE":   "S1",
    "エスワン":          "S1",
    "FALENO star":     "FALENO",
    "FALENO TUBE":     "FALENO",
    "Premium":         "PREMIUM",
}

---

### Phase 3: 快取管理器 ⭐⭐⭐

#### Python 原始程式碼位置

| 檔案 | 說明 |
|------|------|
| `src/scrapers/cache_manager.py` | 快取管理 |
| `src/services/unified_cache.py` | 統一快取介面 |
| `cache/` | 快取目錄 |

#### 相依性分析

```
快取管理器
├── 儲存
│   ├── cache/cache_index.json - 索引檔
│   └── cache/{hash}/ - 分片儲存
│
├── 功能
│   ├── Get(key) -> value
│   ├── Set(key, value, ttl)
│   ├── Delete(key)
│   └── Prune() - 清理過期/超量
│
└── 設定
    ├── TTL (預設 7 天)
    └── 最大大小 (預設 500 MB)
```

#### 實作清單

- [ ] `pkg/cache/manager.go`
- [ ] `pkg/cache/manager_test.go`
- [ ] CLI 命令
  ```bash
  classifier.exe cache stats    # 統計
  classifier.exe cache prune    # 清理
  classifier.exe cache get KEY  # 查詢
  ```

#### 快取目錄結構

```
cache/
├── cache_index.json           # 索引檔（key -> hash 對應）
├── search_cache.json          # 搜尋快取
└── {hash[0:2]}/
    └── {hash[2:4]}/
        └── {hash}.json        # 快取內容
```

#### 快取索引格式 (`cache_index.json`)

```json
{
  "entries": {
    "avwiki:SONE-123": {
      "hash": "a1b2c3d4...",
      "created_at": "2025-12-21T10:00:00Z",
      "expires_at": "2025-12-28T10:00:00Z",
      "size": 1234
    }
  },
  "total_size": 52428800,
  "last_prune": "2025-12-21T00:00:00Z"
}
```

#### 快取內容格式

```json
{
  "key": "avwiki:SONE-123",
  "value": { ... },
  "created_at": "2025-12-21T10:00:00Z",
  "ttl_seconds": 604800
}
```

---

### Phase 4: 統一 CLI ⭐⭐

- [ ] 合併所有功能到單一執行檔
  ```bash
  classifier.exe scan -dir "D:\Videos"
  classifier.exe move -src "A" -dst "B"
  classifier.exe identify -code "SONE-123"
  classifier.exe cache stats
  ```

- [ ] 加入進度條顯示（可選）

---

## 🔗 相依檔案對照表

| Go 模組 | 對應 Python 檔案 | 相依資料 |
|--------|-----------------|---------|
| `pkg/extractor` ✅ | `src/models/extractor.py` | - |
| `pkg/mover` | `src/services/classifier_core.py` | - |
| `pkg/studio` | `src/models/studio.py` | `studios.json` |
| `pkg/cache` | `src/scrapers/cache_manager.py` | `cache/` 目錄 |

---

## 🚫 不遷移到 Go

| 項目 | 原因 |
|------|------|
| GUI 介面 | Go GUI 生態不成熟 |
| HTML 解析/爬蟲 | Python BeautifulSoup 更完整 |
| 互動式分類 | 需要 GUI 對話框 |
| 複雜分類邏輯 | 需要頻繁調整，Python 更靈活 |
| 資料庫操作 | 與 Python 程式緊密整合 |

---

## 📊 效能目標

| 操作 | Python 現況 | Go 目標 |
|------|------------|---------|
| 掃描 1000 檔案 | ~5s | <1s |
| 移動 100 檔案 | ~10s | <2s |
| 片商識別 | ~1ms | <0.1ms |

---

## 🔗 相關文件

- [GO_MVP_STATUS.md](GO_MVP_STATUS.md) - MVP 完成狀態
- [docs/CLASSIFICATION_LOGIC_PROPOSAL.md](docs/CLASSIFICATION_LOGIC_PROPOSAL.md) - 分類邏輯提案

---

## 🧪 整合測試計畫

### 單元測試需求

| 模組 | 測試案例 | 預期覆蓋率 |
|------|---------|-----------|
| `pkg/mover` | 單檔移動、批次移動、衝突處理、權限錯誤、回滾 | ≥ 85% |
| `pkg/studio` | 前綴匹配、別名解析、大片商判斷、未知片商 | ≥ 90% |
| `pkg/cache` | 讀寫、TTL 過期、LRU 清理、容量限制 | ≥ 80% |

### 整合測試場景

#### 場景 1：檔案移動整合

```bash
# 測試腳本
1. 建立測試目錄結構
   temp_test/
   ├── source/
   │   ├── SONE-123.mp4
   │   ├── MIDV-456.mp4
   │   └── ABC-789.mp4 (無效番號)
   └── dest/
       └── S1/

2. 執行批次移動
3. 驗證結果：
   - SONE-123.mp4 → dest/S1/
   - MIDV-456.mp4 → dest/MOODYZ/
   - ABC-789.mp4 → 保持原位
```

#### 場景 2：與 Python 程式互通

```bash
# 驗證 Go CLI 輸出能被 Python 正確解析
1. Go CLI 執行 scan 產生 JSON
2. Python 讀取 JSON 執行分類邏輯
3. Go CLI 執行 move 完成移動
```

### 測試資料準備

```
tests/fixtures/
├── studios.json.test      # 測試用片商設定
├── sample_videos/         # 測試用空檔案 (0 bytes)
│   ├── SONE-001.mp4
│   ├── MIDV-002.mp4
│   └── IPX-003.mp4
└── expected_results/      # 預期結果
    └── move_batch_1.json
```

---

## 🔄 回滾/復原機制

### Phase 1：檔案移動回滾

#### 設計原則

1. **操作日誌**：每次批次操作前記錄完整狀態
2. **原子性**：單一移動失敗不影響其他檔案
3. **可追溯**：保留 30 天操作歷史

#### 操作日誌格式

```go
type OperationLog struct {
    ID        string    `json:"id"`         // UUID
    Timestamp time.Time `json:"timestamp"`
    Type      string    `json:"type"`       // "move_batch", "merge"
    Items     []MoveLog `json:"items"`
    Status    string    `json:"status"`     // "started", "completed", "partial", "failed"
}

type MoveLog struct {
    Source      string `json:"source"`
    Destination string `json:"destination"`
    Status      string `json:"status"`     // "pending", "success", "failed", "rolled_back"
    Error       string `json:"error,omitempty"`
}
```

#### 日誌儲存位置

```
logs/
└── operations/
    ├── 2025-12-21_143022_abc123.json
    └── 2025-12-21_150530_def456.json
```

#### 回滾 CLI 命令

```bash
# 查看操作歷史
classifier.exe history list

# 查看特定操作詳情
classifier.exe history show abc123

# 回滾特定操作
classifier.exe history rollback abc123

# 回滾最近一次操作
classifier.exe history rollback --last
```

#### 回滾流程

```
1. 讀取操作日誌
2. 篩選狀態為 "success" 的項目
3. 逆向執行移動（dest → source）
4. 更新日誌狀態為 "rolled_back"
5. 輸出回滾報告
```

---

## 📝 備註

- Go 版本：1.21+
- 編譯命令：`go build -o classifier.exe ./cmd/scanner`
- 測試命令：`go test ./pkg/... -v`
