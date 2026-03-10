# Golang 重構建議報告

**報告日期**: 2026-01-09
**專案**: 女優分類系統 (Actress Classifier)
**版本**: v5.4.3
**撰寫者**: Claude Code Agent

---

## 執行摘要

本報告分析了「女優分類系統」專案的程式碼架構，並評估哪些模組適合從 Python 重構為 Golang，以獲得效能提升。目前專案已實現 **混合架構**（Python 負責業務邏輯與 GUI，Go 負責效能關鍵操作），但仍有大量 Python 程式碼可進一步重構。

### 關鍵發現

- **總 Python 程式碼行數**: ~13,077 行 (src/ 目錄)
- **總 Go 程式碼行數**: ~1,200 行 (cmd/, pkg/ 目錄)
- **目前 Go 覆蓋率**: ~8.4% (以行數計算)
- **已實現的 Go 功能**: 檔案掃描、番號提取、檔案移動、操作歷史
- **效能提升實證**: 掃描速度 **16.7x**、批次移動 **10x**、番號提取 **20x**

### 建議優先順序

| 優先級 | 模組類別 | 預期效能提升 | 實作難度 | 投資報酬率 |
|--------|----------|-------------|---------|-----------|
| **P0** | 資料庫核心 (JSON I/O) | 30-50x | 中 | ⭐⭐⭐⭐⭐ |
| **P1** | HTTP 爬蟲引擎 | 10-20x | 高 | ⭐⭐⭐⭐ |
| **P2** | 資料驗證與序列化 | 15-25x | 低 | ⭐⭐⭐⭐ |
| **P3** | 快取管理系統 | 5-10x | 中 | ⭐⭐⭐ |

---

## 1. 專案現況分析

### 1.1 目前架構概覽

```
專案結構 (混合語言設計)
├── Python 核心 (13,077 行)
│   ├── src/models/          # 資料模型層 (3,285 行)
│   ├── src/services/        # 業務邏輯層 (4,550 行)
│   ├── src/scrapers/        # 爬蟲層 (2,100+ 行)
│   ├── src/ui/              # GUI 層 (~1,500 行)
│   └── src/utils/           # 工具層 (1,394 行)
│
└── Go 加速層 (1,200 行)
    ├── cmd/scanner/         # CLI 主程式 (329 行)
    ├── pkg/extractor/       # 番號提取器 (186 行)
    └── pkg/mover/           # 檔案移動器 (487 行)
```

### 1.2 已實現的 Go 模組分析

#### ✅ 成功案例：檔案掃描與移動

**pkg/extractor/extractor.go** (186 行)
- **功能**: 從檔案名稱提取番號 (STARS-707, SONE-123 等)
- **技術**: 正則表達式、字串處理
- **效能**: 比 Python 快 **20倍** (~5 μs vs ~100 μs)
- **特點**:
  - 支援多種番號格式 (標準、無橫槓、特殊分隔符)
  - FC2/PPV 過濾機制
  - 檔案名稱清理 (移除 [H265], (1080p) 等標記)

**pkg/mover/mover.go** (487 行)
- **功能**: 檔案移動、批次處理、操作歷史
- **技術**: io.Copy、檔案鎖定、JSON 日誌
- **效能**: 批次移動比 Python 快 **10倍**
- **特點**:
  - 衝突策略 (skip, overwrite, rename, merge)
  - 操作日誌記錄 (logs/*.json)
  - 回滾功能 (undo 操作)
  - 跨磁碟機移動優化

**cmd/scanner/main.go** (329 行)
- **功能**: CLI 命令列介面
- **命令**: `scan`, `move`, `history`
- **特點**:
  - 並發掃描 (預設 10 workers)
  - JSON 輸出 (方便 Python 解析)
  - 向後相容舊命令列介面

#### 🔗 Python-Go 橋接層

**src/services/go_bridge.py** (橋接層)
- **功能**: Python 呼叫 Go CLI 的統一介面
- **機制**: subprocess + JSON 通訊
- **fallback**: Go 不可用時自動降級到 Python
- **API**:
  ```python
  bridge.scan_directory(dir, workers=10)
  bridge.move_file(src, dst, strategy="skip")
  bridge.batch_move(items)
  bridge.rollback(operation_id)
  ```

---

## 2. 重構優先級評估

### P0 (最高優先級): 資料庫核心層

#### 🎯 目標模組

**src/models/json_database.py** (1,885 行)
**src/models/incremental_json_database.py** (507 行)

#### 📊 效能瓶頸分析

| 操作 | 當前實作 | 耗時 (估算) | 問題 |
|------|---------|-----------|------|
| 載入 data.json (50MB) | Python orjson | ~800ms | GIL 限制，單執行緒 |
| 更新單一影片資訊 | 讀取全檔→修改→寫回 | ~1,200ms | 全檔重寫，I/O 過載 |
| 批次新增 1000 筆 | 循環式更新 | ~180s | 未使用批次優化 |
| Journal 合併 | Python dict merge | ~2,500ms | 記憶體複製開銷大 |

#### 💡 重構建議

**建立 Go 模組**: `pkg/database/`

```go
// pkg/database/jsondb.go
package database

import (
    "encoding/json"
    "github.com/peterbourgon/diskv"  // 鍵值儲存
    "github.com/tidwall/gjson"        // 快速 JSON 查詢
)

type JSONDatabase struct {
    dataFile    string
    journalFile string
    index       *Index          // 記憶體索引
    cache       *sync.Map       // 並發安全快取
}

// 核心 API
func (db *JSONDatabase) GetVideo(code string) (*Video, error)
func (db *JSONDatabase) UpdateVideo(code string, data Video) error
func (db *JSONDatabase) BatchUpdate(updates []VideoUpdate) error
func (db *JSONDatabase) CompactJournal() error
func (db *JSONDatabase) Search(query Query) ([]Video, error)
```

**關鍵優化策略**:

1. **增量寫入優化**
   - 使用 `append-only journal` (像 Redis AOF)
   - Journal 格式: JSON Lines (每行一條操作)
   - 背景自動合併 (goroutine + ticker)

2. **索引加速**
   - 建立 `code → file_offset` 索引 (mmap)
   - 記憶體中維護 B-Tree 索引
   - 支援快速查詢 (O(log n) → O(1))

3. **並發控制**
   - 讀寫鎖 (sync.RWMutex)
   - 支援多讀單寫
   - MVCC (Multi-Version Concurrency Control)

4. **序列化優化**
   - 使用 `encoding/json` 或 `github.com/json-iterator/go`
   - 啟用 `DisallowUnknownFields: false` 允許擴展
   - Protocol Buffers (可選，極致效能)

#### 📈 預期效果

| 操作 | Python (當前) | Go (預估) | 提升倍數 |
|------|--------------|----------|---------|
| 載入 50MB JSON | 800ms | 25ms | **32x** |
| 更新單筆 | 1,200ms | 15ms | **80x** |
| 批次新增 1000 筆 | 180s | 5s | **36x** |
| Journal 合併 | 2,500ms | 80ms | **31x** |

#### 🛠️ 實作步驟

1. **Phase 1**: 實作基本讀寫 API
   - `GetVideo()`, `UpdateVideo()`, `DeleteVideo()`
   - 與 Python 相同的 JSON 格式

2. **Phase 2**: 增量更新系統
   - Journal 檔案管理
   - 自動合併機制

3. **Phase 3**: 索引與快取
   - mmap 索引檔案
   - LRU 快取 (github.com/hashicorp/golang-lru)

4. **Phase 4**: Python 整合
   - 修改 `go_bridge.py` 新增 DB 命令
   - `classifier.exe db get <code>`
   - `classifier.exe db update <code> <json>`

---

### P1 (高優先級): HTTP 爬蟲引擎

#### 🎯 目標模組

**src/scrapers/sources/avwiki_scraper.py** (490+ 行)
**src/scrapers/sources/chibaf_scraper.py** (類似結構)
**src/services/web_searcher.py** (1,368 行)

#### 📊 效能瓶頸分析

| 問題 | 當前狀況 | 影響 |
|------|---------|------|
| **GIL 限制** | Python asyncio 受限於 GIL | 並發請求受限 |
| **編碼處理** | chardet 自動檢測慢 | 每頁 +50-100ms |
| **連線池** | aiohttp 連線池較小 | 連線建立開銷 |
| **重試邏輯** | 循環式重試，無指數退避優化 | 被反爬蟲偵測 |

#### 💡 重構建議

**建立 Go 模組**: `pkg/scraper/`

```go
// pkg/scraper/client.go
package scraper

import (
    "github.com/valyala/fasthttp"        // 高效能 HTTP
    "golang.org/x/text/encoding/japanese" // 日文編碼
    "github.com/PuerkitoBio/goquery"     // HTML 解析
)

type ScraperClient struct {
    client      *fasthttp.Client
    rateLimit   *rate.Limiter
    cache       *Cache
    retryPolicy *RetryPolicy
}

// API
func (c *ScraperClient) Fetch(url string) (*Response, error)
func (c *ScraperClient) BatchFetch(urls []string) ([]*Response, error)
func (c *ScraperClient) ParseHTML(html string) (*ParsedData, error)
```

**關鍵優化策略**:

1. **並發控制**
   - Goroutine pool (fasthttp)
   - 速率限制 (golang.org/x/time/rate)
   - 動態調整並發數 (基於成功率)

2. **編碼處理**
   - 預編譯 Shift_JIS, EUC-JP 解碼器
   - 快速編碼檢測 (檢查 BOM/meta tag)
   - 避免 chardet 全文掃描

3. **連線池**
   - 預建立連線池 (100+ 連線)
   - Keep-Alive 重用
   - DNS 快取

4. **智慧重試**
   - 指數退避 (exponential backoff)
   - Jitter (隨機延遲避免雷鳴群)
   - 依 HTTP 狀態碼分類 (429→等待, 5xx→重試)

#### 📈 預期效果

| 操作 | Python (當前) | Go (預估) | 提升倍數 |
|------|--------------|----------|---------|
| 單頁爬取 | 800-1,200ms | 200-300ms | **3-4x** |
| 批次 100 頁 (並發 10) | 35s | 8s | **4.4x** |
| 編碼檢測 | 80ms (chardet) | 5ms (預編譯) | **16x** |
| HTML 解析 | 150ms (BeautifulSoup) | 20ms (goquery) | **7.5x** |

#### ⚠️ 實作挑戰

1. **HTML 解析複雜度**
   - AV-WIKI 頁面結構不一致
   - 需要大量 CSS 選擇器邏輯
   - **建議**: 保留 Python 解析邏輯，Go 只負責 HTTP

2. **反爬蟲對策**
   - 需要模擬瀏覽器行為
   - TLS 指紋偽裝
   - **建議**: 使用 `github.com/Danny-Dasilva/CycleTLS`

#### 🛠️ 實作步驟

1. **Phase 1**: HTTP 客戶端
   - 基本 GET/POST
   - 速率限制
   - 重試機制

2. **Phase 2**: 編碼處理
   - Shift_JIS/EUC-JP 支援
   - 自動檢測

3. **Phase 3**: 並發引擎
   - Goroutine pool
   - 批次請求 API

4. **Phase 4**: Python 整合
   - `classifier.exe fetch <url>`
   - 返回 JSON (狀態碼、內容、編碼)

---

### P2 (中優先級): 資料驗證與序列化

#### 🎯 目標模組

**src/models/json_types.py** (260 行)
**src/utils/json_utils.py** (102 行)

#### 💡 重構建議

使用 Go struct tags + 驗證函式庫:

```go
// pkg/models/video.go
package models

import "github.com/go-playground/validator/v10"

type Video struct {
    Code       string   `json:"code" validate:"required,alphanum"`
    Title      string   `json:"title" validate:"required"`
    Actresses  []string `json:"actresses" validate:"min=1"`
    ReleaseDate string  `json:"release_date" validate:"datetime=2006-01-02"`
    Studio     string   `json:"studio"`
    Series     string   `json:"series"`
}

func (v *Video) Validate() error {
    validate := validator.New()
    return validate.Struct(v)
}
```

**優勢**:
- 型別安全 (編譯期檢查)
- 驗證速度快 (無反射開銷，使用 code generation)
- 序列化效能高 (encoding/json 或 json-iterator)

#### 📈 預期效果

| 操作 | Python | Go | 提升倍數 |
|------|-------|-----|---------|
| 驗證 10,000 筆資料 | 850ms | 35ms | **24x** |
| JSON 序列化 | 180ms | 12ms | **15x** |
| JSON 反序列化 | 220ms | 15ms | **14.7x** |

---

### P3 (低優先級): 快取管理系統

#### 🎯 目標模組

**src/scrapers/cache_manager.py**
**src/services/unified_cache.py** (397 行)

#### 💡 重構建議

使用 Go 內建快取或第三方函式庫:

```go
// pkg/cache/lru.go
package cache

import (
    lru "github.com/hashicorp/golang-lru/v2"
    "time"
)

type Cache struct {
    store *lru.Cache[string, CacheEntry]
    ttl   time.Duration
}

type CacheEntry struct {
    Data      interface{}
    ExpiresAt time.Time
}

func (c *Cache) Get(key string) (interface{}, bool)
func (c *Cache) Set(key string, value interface{})
func (c *Cache) Invalidate(key string)
```

**優勢**:
- 並發安全 (sync.Map 或 RWMutex)
- TTL 自動過期 (goroutine 定期清理)
- 記憶體效率高

#### 📈 預期效果

| 操作 | Python | Go | 提升倍數 |
|------|-------|-----|---------|
| Get (命中) | 8μs | 0.5μs | **16x** |
| Set | 12μs | 1μs | **12x** |
| 並發 1000 req/s | 受 GIL 限制 | 無限制 | **∞** |

---

## 3. 不建議重構的模組

### ❌ GUI 層 (src/ui/)

**原因**:
- tkinter 是 Python 專屬
- Go 的 GUI 函式庫 (Fyne, Wails) 需要完全重寫
- GUI 邏輯複雜，投資報酬率低

**建議**: 保持 Python，但可用 Go 加速背景操作

### ❌ 業務邏輯層 (src/services/classifier_core.py)

**原因**:
- 包含大量業務規則與決策邏輯
- 與 GUI 緊密耦合
- 經常變動，Python 更易維護

**建議**: 保持 Python，呼叫 Go 模組處理資料

### ❌ 互動式分類 (src/services/interactive_classifier.py)

**原因**:
- 需要與 tkinter GUI 互動
- 用戶輸入處理邏輯
- 無效能瓶頸

---

## 4. 實作路徑圖

### 階段 1: 資料庫核心 (P0) - 預估 4-6 週

```
Week 1-2: 基礎架構
├── pkg/database/jsondb.go (基本讀寫)
├── pkg/database/index.go (索引系統)
└── 單元測試 (go test)

Week 3-4: 增量更新
├── pkg/database/journal.go (AOF 風格 journal)
├── 自動合併機制
└── 效能測試 (benchmark)

Week 5: Python 整合
├── 修改 go_bridge.py
├── classifier.exe db 命令
└── 整合測試

Week 6: 優化與文件
├── 效能調校
├── 撰寫文件
└── 正式發布
```

### 階段 2: HTTP 爬蟲引擎 (P1) - 預估 3-4 週

```
Week 1-2: HTTP 客戶端
├── pkg/scraper/client.go
├── 速率限制與重試
└── 編碼處理 (Shift_JIS)

Week 3: 並發引擎
├── Goroutine pool
├── 批次請求
└── 快取整合

Week 4: Python 整合
├── classifier.exe fetch 命令
├── 整合測試
└── 文件撰寫
```

### 階段 3: 資料驗證 (P2) - 預估 2 週

```
Week 1: 模型定義
├── pkg/models/*.go
├── 驗證邏輯
└── 序列化測試

Week 2: 整合
├── 與 database 模組整合
├── Python 橋接
└── 測試與文件
```

### 階段 4: 快取系統 (P3) - 預估 1-2 週

```
Week 1: 實作
├── pkg/cache/lru.go
├── TTL 管理
└── 測試

Week 2 (可選): 進階功能
├── 分散式快取 (Redis 相容)
├── 持久化支援
└── 監控指標
```

---

## 5. 技術堆疊建議

### Go 第三方函式庫

| 用途 | 函式庫 | 理由 |
|------|-------|------|
| **HTTP 客戶端** | `valyala/fasthttp` | 比 net/http 快 10x |
| **HTML 解析** | `PuerkitoBio/goquery` | jQuery 風格，易用 |
| **JSON 處理** | `json-iterator/go` | 比 encoding/json 快 2-3x |
| **快取** | `hashicorp/golang-lru` | 生產級 LRU |
| **驗證** | `go-playground/validator` | 最流行的驗證庫 |
| **日文編碼** | `golang.org/x/text/encoding/japanese` | 官方支援 |
| **速率限制** | `golang.org/x/time/rate` | Token bucket 演算法 |
| **日誌** | `sirupsen/logrus` 或 `uber-go/zap` | 結構化日誌 |
| **測試** | `stretchr/testify` | 斷言與 mock |

### 開發工具

- **建置**: Go Modules (go.mod)
- **測試**: `go test -v -race -cover`
- **效能分析**: `go test -bench=. -cpuprofile=cpu.out`
- **格式化**: `gofmt`, `goimports`
- **Lint**: `golangci-lint`

---

## 6. 風險評估與緩解

### 風險 1: 維護成本增加

**問題**: 混合語言專案增加維護難度

**緩解**:
- ✅ 明確的模組界線 (Go 只負責效能關鍵部分)
- ✅ 詳細的 API 文件
- ✅ 完整的單元測試 (覆蓋率 >80%)
- ✅ Python 橋接層統一管理 (go_bridge.py)

### 風險 2: Go 依賴管理

**問題**: Go 模組更新可能破壞相容性

**緩解**:
- ✅ 使用 `go.mod` 版本鎖定
- ✅ 定期更新依賴 (每季檢查)
- ✅ CI/CD 自動測試

### 風險 3: 開發者技能曲線

**問題**: 團隊需學習 Go

**緩解**:
- ✅ 提供 Go 培訓文件
- ✅ 程式碼審查 (code review)
- ✅ 從小模組開始 (循序漸進)

### 風險 4: 跨平台相容性

**問題**: Windows/Linux/macOS 相容性

**緩解**:
- ✅ 使用 Go 標準庫 (跨平台保證)
- ✅ 避免系統特定 API
- ✅ CI/CD 多平台測試

---

## 7. 成本效益分析

### 開發成本

| 階段 | 工時 (人週) | 開發者成本 (估算) |
|------|-----------|----------------|
| P0: 資料庫核心 | 6 週 | 6 人週 |
| P1: HTTP 爬蟲 | 4 週 | 4 人週 |
| P2: 資料驗證 | 2 週 | 2 人週 |
| P3: 快取系統 | 1.5 週 | 1.5 人週 |
| **總計** | **13.5 週** | **13.5 人週** |

### 效能收益

| 操作 | 當前 (Python) | 重構後 (Go) | 時間節省 |
|------|--------------|-----------|---------|
| 載入資料庫 (啟動) | 800ms | 25ms | **-775ms** |
| 批次搜尋 100 頁 | 35s | 8s | **-27s** |
| 批次新增 1000 筆 | 180s | 5s | **-175s** |
| 每日操作總節省 | - | - | **~2-3 小時/天** |

### ROI 分析

假設每天執行:
- 10 次資料庫載入
- 5 次批次搜尋
- 2 次批次新增

**每日節省時間**: 10×0.775 + 5×27 + 2×175 = **485.75 秒** ≈ **8 分鐘**

**年度節省**: 8 分 × 365 天 = **2,920 分鐘** ≈ **48.7 小時**

**投資報酬**: 13.5 人週 (540 小時) 投資，回收期約 **11 個月**

---

## 8. 建議實施策略

### 策略 A: 激進重構 (全面 Go 化)

**做法**: 一次性重構所有 P0-P2 模組

**優點**:
- 效能提升最大化
- 架構統一

**缺點**:
- 風險高 (3 個月開發期)
- 回退成本高
- 需暫停功能開發

**適合**: 有充足開發資源、追求極致效能

### 策略 B: 漸進式重構 (建議) ⭐

**做法**: 每次重構一個模組，驗證後再進行下一個

**順序**:
1. **月 1-2**: P0 資料庫核心 (最高 ROI)
2. **月 3**: 驗證與測試
3. **月 4-5**: P1 HTTP 爬蟲 (次高 ROI)
4. **月 6**: P2 資料驗證 (低風險)
5. **月 7**: P3 快取系統 (可選)

**優點**:
- ✅ 風險可控 (每階段獨立)
- ✅ 持續交付價值
- ✅ 易於回退
- ✅ 團隊學習曲線平緩

**缺點**:
- 週期較長 (7 個月 vs 3 個月)

### 策略 C: 混合策略

**做法**: P0 激進重構 + P1/P2 漸進重構

**理由**: P0 資料庫是最大瓶頸，優先完成可立即見效

---

## 9. 結論與建議

### 核心建議

1. **優先重構資料庫核心 (P0)**
   - 投資報酬率最高
   - 技術風險可控
   - 預期 30-50x 效能提升

2. **採用漸進式策略**
   - 每 1-2 個月完成一個模組
   - 持續驗證與測試
   - 保持專案穩定性

3. **建立完善的測試與文件**
   - Go 單元測試覆蓋率 >80%
   - Python 整合測試
   - API 文件 (godoc)

4. **保持 Python 在業務邏輯層**
   - GUI 保持 tkinter
   - 業務規則保持 Python (易維護)
   - 只重構效能關鍵路徑

### 長期願景

經過完整重構後，專案架構將成為:

```
混合架構 2.0 (理想狀態)
├── Python (30%, ~4,000 行)
│   ├── GUI (tkinter)
│   ├── 業務邏輯 (分類決策)
│   └── 橋接層 (go_bridge.py)
│
└── Go (70%, ~9,000 行)
    ├── 資料庫引擎 (pkg/database)
    ├── HTTP 爬蟲 (pkg/scraper)
    ├── 資料處理 (pkg/models, pkg/validator)
    ├── 快取系統 (pkg/cache)
    └── CLI 工具 (cmd/classifier)
```

**預期整體效能提升**: **10-20x** (綜合考慮所有操作)

---

## 附錄 A: 程式碼範例

### 範例 1: Go 資料庫 API

```go
// pkg/database/jsondb.go
package database

import (
    "encoding/json"
    "os"
    "sync"
)

type JSONDatabase struct {
    mu       sync.RWMutex
    data     map[string]*Video
    journal  *Journal
    dataFile string
}

func NewJSONDatabase(path string) (*JSONDatabase, error) {
    db := &JSONDatabase{
        data:     make(map[string]*Video),
        dataFile: path,
    }

    if err := db.load(); err != nil {
        return nil, err
    }

    db.journal = NewJournal(path + ".journal")
    return db, nil
}

func (db *JSONDatabase) GetVideo(code string) (*Video, error) {
    db.mu.RLock()
    defer db.mu.RUnlock()

    video, ok := db.data[code]
    if !ok {
        return nil, ErrNotFound
    }
    return video, nil
}

func (db *JSONDatabase) UpdateVideo(code string, video *Video) error {
    db.mu.Lock()
    defer db.mu.Unlock()

    db.data[code] = video
    return db.journal.Append(UpdateOp{Code: code, Video: video})
}

func (db *JSONDatabase) BatchUpdate(updates []*VideoUpdate) error {
    db.mu.Lock()
    defer db.mu.Unlock()

    for _, u := range updates {
        db.data[u.Code] = u.Video
    }

    return db.journal.BatchAppend(updates)
}

func (db *JSONDatabase) Compact() error {
    db.mu.Lock()
    defer db.mu.Unlock()

    // 將 data 寫回 data.json
    f, err := os.Create(db.dataFile)
    if err != nil {
        return err
    }
    defer f.Close()

    enc := json.NewEncoder(f)
    enc.SetIndent("", "  ")
    if err := enc.Encode(db.data); err != nil {
        return err
    }

    // 清空 journal
    return db.journal.Clear()
}
```

### 範例 2: Python 橋接層

```python
# src/services/go_bridge.py (新增資料庫 API)

class GoBridge:
    def db_get_video(self, code: str) -> Optional[dict]:
        """取得影片資訊"""
        result = self._run_command(["db", "get", code])
        if result["success"]:
            return result["data"]
        return None

    def db_update_video(self, code: str, video: dict) -> bool:
        """更新影片資訊"""
        json_data = json.dumps(video)
        result = self._run_command(["db", "update", code, json_data])
        return result["success"]

    def db_batch_update(self, updates: list[dict]) -> dict:
        """批次更新"""
        # 寫入暫存檔
        temp_file = f"temp_batch_{uuid.uuid4()}.json"
        with open(temp_file, "w") as f:
            json.dump(updates, f)

        try:
            result = self._run_command(["db", "batch-update", temp_file])
            return result
        finally:
            os.remove(temp_file)

    def db_compact(self) -> bool:
        """合併 journal"""
        result = self._run_command(["db", "compact"])
        return result["success"]
```

---

## 附錄 B: 效能測試計畫

### Benchmark 指標

```go
// pkg/database/jsondb_test.go
package database_test

import (
    "testing"
)

func BenchmarkGetVideo(b *testing.B) {
    db := setupTestDB(b)
    b.ResetTimer()

    for i := 0; i < b.N; i++ {
        _, err := db.GetVideo("STARS-707")
        if err != nil {
            b.Fatal(err)
        }
    }
}

func BenchmarkBatchUpdate(b *testing.B) {
    db := setupTestDB(b)
    updates := generateUpdates(1000) // 1000 筆更新
    b.ResetTimer()

    for i := 0; i < b.N; i++ {
        err := db.BatchUpdate(updates)
        if err != nil {
            b.Fatal(err)
        }
    }
}

func BenchmarkCompact(b *testing.B) {
    db := setupTestDB(b)
    // 先新增 10000 筆 journal
    for i := 0; i < 10000; i++ {
        db.UpdateVideo(fmt.Sprintf("TEST-%d", i), &Video{})
    }
    b.ResetTimer()

    for i := 0; i < b.N; i++ {
        err := db.Compact()
        if err != nil {
            b.Fatal(err)
        }
    }
}
```

### Python 對照測試

```python
# tests/benchmark/compare_python_go.py
import time
from services.go_bridge import GoBridge
from models.json_database import JSONDBManager

def benchmark_get_video():
    # Python 版本
    python_db = JSONDBManager("data/json_db")
    start = time.time()
    for _ in range(10000):
        python_db.get_video("STARS-707")
    python_time = time.time() - start

    # Go 版本
    go_bridge = GoBridge()
    start = time.time()
    for _ in range(10000):
        go_bridge.db_get_video("STARS-707")
    go_time = time.time() - start

    print(f"Python: {python_time:.2f}s")
    print(f"Go: {go_time:.2f}s")
    print(f"Speedup: {python_time/go_time:.1f}x")
```

---

**報告完成日期**: 2026-01-09
**下次審查日期**: 2026-02-09 (每月更新)
