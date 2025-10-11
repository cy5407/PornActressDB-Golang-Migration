# 女優分類系統 - Go 重構實施指南

> **文件版本**: 1.0.0  
> **建立日期**: 2025-10-12  
> **重構策略**: 漸進式三階段遷移  
> **目標**: 從 Python 3.8+ 遷移至 Go 1.22+

## 📋 目錄
- [重構目標與動機](#重構目標與動機)
- [技術選型比較](#技術選型比較)
- [階段一：後端核心邏輯](#階段一後端核心邏輯)
- [階段二：CLI 工具](#階段二cli-工具)
- [階段三：GUI 開發](#階段三gui-開發)
- [遷移檢查清單](#遷移檢查清單)
- [常見問題](#常見問題)

---

## 🎯 重構目標與動機

### 為什麼選擇 Go？

#### ✅ 優勢
1. **並發效能**：goroutines 和 channels 原生支援，效能優於 Python asyncio
2. **類型安全**：編譯時類型檢查，減少執行期錯誤
3. **編譯為原生執行檔**：無需 Python 環境，部署簡單
4. **記憶體效率**：記憶體佔用通常低於 Python
5. **跨平台建構**：一次建構，可產生多平台執行檔
6. **標準函式庫完善**：HTTP、JSON、並發等基礎功能無需外部相依

#### ⚠️ 挑戰
1. **GUI 生態較弱**：不如 Python tkinter 成熟（但有替代方案）
2. **學習曲線**：團隊需要學習 Go 語法和慣例
3. **初期開發速度**：靜態類型可能降低快速原型開發速度
4. **社群資源**：爬蟲相關套件不如 Python 豐富

### 漸進式遷移策略

```
┌─────────────────────────────────────────────────────────────┐
│ 階段一：後端核心邏輯（2-3 週）                              │
│ ✓ 爬蟲引擎（並發、限流、重試）                              │
│ ✓ 資料處理（JSON 資料庫）                                   │
│ ✓ 編碼處理（日文網站）                                      │
│ ✓ 單元測試（≥70% 覆蓋率）                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 階段二：CLI 工具（1-2 週）                                  │
│ ✓ Cobra CLI 框架                                            │
│ ✓ 搜尋、分類、統計命令                                      │
│ ✓ 互動模式                                                  │
│ ✓ 跨平台建構                                                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 階段三：GUI 開發（2-4 週）                                  │
│ ✓ 技術選型（Fyne/Wails/混合架構）                           │
│ ✓ UI 原型                                                   │
│ ✓ 整合後端 API                                              │
│ ✓ 使用者測試                                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 技術選型比較

### 爬蟲引擎

| 功能 | Python 現況 | Go 方案 | 備註 |
|------|------------|---------|------|
| HTTP 客戶端 | httpx, aiohttp, requests | `net/http` (標準庫) | Go 原生支援 HTTP/2 |
| HTML 解析 | BeautifulSoup4 | `goquery` | 語法類似 jQuery |
| 並發模型 | asyncio | goroutines + channels | Go 效能更優 |
| 編碼檢測 | chardet | `golang.org/x/text/encoding` | 支援 Shift-JIS, EUC-JP |
| 頻率限制 | 自建 RateLimiter | `golang.org/x/time/rate` | Token bucket 演算法 |
| 快取 | 自建 CacheManager | `encoding/json` + 檔案系統 | 可搭配 sync.Map |

### 資料儲存

| 方案 | Python 現況 | Go 方案 | 優勢 | 劣勢 |
|------|------------|---------|------|------|
| SQLite | ✓ 使用中 | ❌ 不使用 | 關聯式查詢強大 | 需要 cgo, 部署複雜 |
| JSON 檔案 | ❌ 未使用 | ✓ **採用** | 無需外部相依, 人類可讀 | 大量資料效能較差 |
| 嵌入式 DB | ❌ 未使用 | BoltDB/BadgerDB (可選) | 效能佳, 純 Go | 學習成本 |

**決策：使用 JSON 檔案**
- 理由：符合憲法「不用額外安裝套件或軟體」要求
- 適用場景：影片資料量 < 100,000 筆
- 優化策略：索引檔案、分片儲存、記憶體快取

### GUI 技術選型

| 方案 | 技術棧 | 優勢 | 劣勢 | 適用場景 | 推薦度 |
|------|--------|------|------|----------|--------|
| **Fyne** | 純 Go | 跨平台, 簡單, Material Design | 客製化有限 | 標準 UI 需求 | ⭐⭐⭐⭐ |
| **Wails** | Go + Web | 現代化 UI, 支援 Vue/React | 需前端知識, 體積較大 | 複雜 UI 需求 | ⭐⭐⭐⭐⭐ |
| **Gio** | 純 Go | 效能極佳, 輕量 | 低階 API, 開發複雜 | 追求極致效能 | ⭐⭐⭐ |
| **混合架構** | Python GUI + Go API | 風險最低, 漸進式 | 維護兩種語言 | 快速遷移 | ⭐⭐⭐⭐⭐ |

**建議決策流程**：
```
是否需要立即遷移 GUI？
├─ 否 → 使用混合架構（Python GUI + Go REST API）
└─ 是 → 團隊是否有前端經驗？
    ├─ 是 → 使用 Wails（現代化 UI）
    └─ 否 → 使用 Fyne（純 Go, 簡單）
```

---

## 📦 階段一：後端核心邏輯

### 目標
將 Python 爬蟲引擎和資料處理邏輯遷移至 Go，建立穩定可測試的核心函式庫。

### 專案結構

```
actress-classifier-go/
├── cmd/
│   └── (暫時為空，階段二建立)
├── internal/
│   ├── scraper/
│   │   ├── client/
│   │   │   ├── client.go           # HTTP 客戶端 (對應 async_scraper.py)
│   │   │   ├── pool.go             # 連線池管理
│   │   │   └── client_test.go
│   │   ├── parser/
│   │   │   ├── html.go             # HTML 解析 (對應 base_scraper.py)
│   │   │   ├── encoding.go         # 編碼檢測 (對應 encoding_utils.py)
│   │   │   └── parser_test.go
│   │   ├── ratelimit/
│   │   │   ├── limiter.go          # 頻率限制器 (對應 rate_limiter.py)
│   │   │   ├── domain.go           # 每網域限流
│   │   │   └── limiter_test.go
│   │   ├── cache/
│   │   │   ├── cache.go            # 快取管理 (對應 cache_manager.py)
│   │   │   ├── memory.go           # 記憶體快取
│   │   │   ├── file.go             # 檔案快取
│   │   │   └── cache_test.go
│   │   └── sources/
│   │       ├── javdb.go            # JAVDB 爬蟲 (對應 javdb_scraper.py)
│   │       ├── avwiki.go           # AV-WIKI 爬蟲 (對應 avwiki_scraper.py)
│   │       ├── chibaf.go           # chiba-f 爬蟲 (對應 chibaf_scraper.py)
│   │       └── sources_test.go
│   ├── classifier/
│   │   ├── classifier.go           # 分類邏輯 (對應 classifier_core.py)
│   │   ├── studio.go               # 片商分類 (對應 studio_classifier.py)
│   │   └── classifier_test.go
│   ├── database/
│   │   ├── db.go                   # JSON 資料庫管理
│   │   ├── video.go                # 影片資料 CRUD
│   │   ├── actress.go              # 女優資料 CRUD
│   │   ├── studio.go               # 片商資料 CRUD
│   │   └── db_test.go
│   ├── models/
│   │   ├── video.go                # 影片資料模型
│   │   ├── actress.go              # 女優資料模型
│   │   ├── studio.go               # 片商資料模型
│   │   └── search.go               # 搜尋結果模型
│   └── config/
│       ├── config.go               # 設定管理 (對應 config.py)
│       └── config_test.go
├── pkg/                            # 可重用公開套件
│   ├── retry/
│   │   ├── retry.go                # 重試機制
│   │   └── retry_test.go
│   └── logger/
│       └── logger.go               # 日誌工具
├── test/
│   ├── integration/                # 整合測試
│   └── testdata/                   # 測試資料
├── go.mod
├── go.sum
├── Makefile
└── README.md
```

### 核心模組實作指南

#### 1. HTTP 客戶端 (`internal/scraper/client/`)

**Python 對應**: `src/scrapers/async_scraper.py`

```go
// client.go
package client

import (
    "context"
    "net/http"
    "time"
)

// Config HTTP 客戶端設定
type Config struct {
    MaxConcurrent   int           // 最大並發數 (對應 Python max_concurrent)
    RequestTimeout  time.Duration // 請求逾時 (對應 Python request_timeout)
    MaxRetries      int           // 最大重試次數 (對應 Python max_retries)
    UserAgents      []string      // User-Agent 池
}

// Client HTTP 客戶端封裝
type Client struct {
    httpClient *http.Client
    config     Config
    semaphore  chan struct{} // 控制並發數
}

// NewClient 建立新的 HTTP 客戶端
func NewClient(config Config) *Client {
    return &Client{
        httpClient: &http.Client{
            Timeout: config.RequestTimeout,
            Transport: &http.Transport{
                MaxIdleConns:        100,
                MaxIdleConnsPerHost: 10,
                IdleConnTimeout:     90 * time.Second,
            },
        },
        config:    config,
        semaphore: make(chan struct{}, config.MaxConcurrent),
    }
}

// Get 執行 GET 請求 (帶並發控制)
func (c *Client) Get(ctx context.Context, url string) (*http.Response, error) {
    // 取得信號量
    c.semaphore <- struct{}{}
    defer func() { <-c.semaphore }()
    
    req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
    if err != nil {
        return nil, err
    }
    
    // 設定 User-Agent (對應 Python _get_headers())
    req.Header.Set("User-Agent", c.getRandomUA())
    
    return c.httpClient.Do(req)
}

func (c *Client) getRandomUA() string {
    // TODO: 實作 User-Agent 輪替
    return c.config.UserAgents[0]
}
```

**重點對應**：
- Python `AsyncWebScraper` → Go `Client`
- Python `asyncio.Semaphore` → Go `chan struct{}`
- Python `aiohttp.ClientSession` → Go `http.Client` + `http.Transport`

#### 2. 頻率限制器 (`internal/scraper/ratelimit/`)

**Python 對應**: `src/scrapers/rate_limiter.py`

```go
// limiter.go
package ratelimit

import (
    "context"
    "sync"
    "time"
    "golang.org/x/time/rate"
)

// DomainLimiter 單一網域的限流器 (對應 Python DomainLimiter)
type DomainLimiter struct {
    limiter       *rate.Limiter
    requestsPerMin int
    minInterval   time.Duration
    lastRequest   time.Time
    mu            sync.Mutex
}

// Limiter 多網域限流器 (對應 Python RateLimiter)
type Limiter struct {
    domains map[string]*DomainLimiter
    mu      sync.RWMutex
}

// NewLimiter 建立新的限流器
func NewLimiter() *Limiter {
    return &Limiter{
        domains: make(map[string]*DomainLimiter),
    }
}

// Wait 等待直到可以發送請求 (對應 Python wait_if_needed_async)
func (l *Limiter) Wait(ctx context.Context, domain string) error {
    dl := l.getDomainLimiter(domain)
    
    dl.mu.Lock()
    defer dl.mu.Unlock()
    
    // 檢查最小間隔
    elapsed := time.Since(dl.lastRequest)
    if elapsed < dl.minInterval {
        select {
        case <-time.After(dl.minInterval - elapsed):
        case <-ctx.Done():
            return ctx.Err()
        }
    }
    
    // 使用 token bucket 限流
    if err := dl.limiter.Wait(ctx); err != nil {
        return err
    }
    
    dl.lastRequest = time.Now()
    return nil
}

func (l *Limiter) getDomainLimiter(domain string) *DomainLimiter {
    l.mu.Lock()
    defer l.mu.Unlock()
    
    if dl, ok := l.domains[domain]; ok {
        return dl
    }
    
    // 預設設定 (對應 Python domain_configs)
    dl := &DomainLimiter{
        limiter:       rate.NewLimiter(rate.Every(3*time.Second), 5), // 每3秒1次,突發5次
        requestsPerMin: 20,
        minInterval:   time.Second,
        lastRequest:   time.Time{},
    }
    l.domains[domain] = dl
    return dl
}
```

**重點對應**：
- Python `RateLimiter` → Go `Limiter`
- Python `asyncio.sleep()` → Go `time.After()` + `select`
- Python token bucket 自建 → Go `golang.org/x/time/rate`

#### 3. JSON 資料庫 (`internal/database/`)

**Python 對應**: `src/models/database.py` (SQLite)

```go
// db.go
package database

import (
    "encoding/json"
    "os"
    "sync"
)

// Database JSON 資料庫管理器
type Database struct {
    dataDir   string
    mu        sync.RWMutex // 讀寫鎖
    videos    map[string]*Video
    actresses map[string]*Actress
    studios   map[string]*Studio
}

// NewDatabase 建立新的資料庫實例
func NewDatabase(dataDir string) (*Database, error) {
    db := &Database{
        dataDir:   dataDir,
        videos:    make(map[string]*Video),
        actresses: make(map[string]*Actress),
        studios:   make(map[string]*Studio),
    }
    
    // 載入現有資料
    if err := db.Load(); err != nil {
        return nil, err
    }
    
    return db, nil
}

// Load 從 JSON 檔案載入資料
func (db *Database) Load() error {
    db.mu.Lock()
    defer db.mu.Unlock()
    
    // 載入影片資料
    if err := db.loadJSON("videos.json", &db.videos); err != nil {
        return err
    }
    
    // 載入女優資料
    if err := db.loadJSON("actresses.json", &db.actresses); err != nil {
        return err
    }
    
    // 載入片商資料
    if err := db.loadJSON("studios.json", &db.studios); err != nil {
        return err
    }
    
    return nil
}

// Save 原子性儲存資料 (對應 Python 需求)
func (db *Database) Save() error {
    db.mu.RLock()
    defer db.mu.RUnlock()
    
    // 先寫入臨時檔案
    if err := db.saveJSON("videos.json.tmp", db.videos); err != nil {
        return err
    }
    
    // 原子性重新命名 (atomic write)
    if err := os.Rename(
        db.dataDir+"/videos.json.tmp",
        db.dataDir+"/videos.json",
    ); err != nil {
        return err
    }
    
    // 同樣處理其他檔案...
    return nil
}

func (db *Database) loadJSON(filename string, target interface{}) error {
    path := db.dataDir + "/" + filename
    data, err := os.ReadFile(path)
    if err != nil {
        if os.IsNotExist(err) {
            return nil // 檔案不存在不算錯誤
        }
        return err
    }
    return json.Unmarshal(data, target)
}

func (db *Database) saveJSON(filename string, data interface{}) error {
    path := db.dataDir + "/" + filename
    content, err := json.MarshalIndent(data, "", "  ")
    if err != nil {
        return err
    }
    return os.WriteFile(path, content, 0644)
}
```

**重點對應**：
- Python SQLite CRUD → Go JSON 檔案 + 記憶體 map
- Python `sqlite3.connect()` → Go `os.ReadFile()` + `json.Unmarshal()`
- Python transaction → Go atomic write (temp file + rename)
- Python 自動遷移 schema → Go 版本化 JSON schema

#### 4. 編碼檢測 (`internal/scraper/parser/`)

**Python 對應**: `src/scrapers/encoding_utils.py`

```go
// encoding.go
package parser

import (
    "bytes"
    "golang.org/x/text/encoding"
    "golang.org/x/text/encoding/japanese"
    "golang.org/x/text/encoding/unicode"
    "golang.org/x/text/transform"
    "io"
)

// DetectEncoding 檢測並轉換編碼 (對應 Python EncodingDetector)
func DetectEncoding(rawHTML []byte) (string, error) {
    // 嘗試順序: UTF-8 → Shift-JIS → EUC-JP
    encodings := []encoding.Encoding{
        unicode.UTF8,
        japanese.ShiftJIS,
        japanese.EUCJP,
    }
    
    for _, enc := range encodings {
        decoder := enc.NewDecoder()
        reader := transform.NewReader(bytes.NewReader(rawHTML), decoder)
        decoded, err := io.ReadAll(reader)
        
        if err == nil {
            return string(decoded), nil
        }
    }
    
    // 降級使用 UTF-8 並忽略錯誤
    return string(rawHTML), nil
}
```

**重點對應**：
- Python `chardet.detect()` → Go `golang.org/x/text/encoding`
- Python 多編碼嘗試 → Go 同樣策略，但使用 Transform API

### 測試策略

#### 單元測試範例

```go
// client_test.go
package client

import (
    "context"
    "net/http"
    "net/http/httptest"
    "testing"
    "time"
)

func TestClient_Get(t *testing.T) {
    // 建立測試伺服器 (對應 Python httptest)
    server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.WriteHeader(http.StatusOK)
        w.Write([]byte("test response"))
    }))
    defer server.Close()
    
    // 建立客戶端
    client := NewClient(Config{
        MaxConcurrent:  3,
        RequestTimeout: 5 * time.Second,
        UserAgents:     []string{"TestAgent/1.0"},
    })
    
    // 執行請求
    ctx := context.Background()
    resp, err := client.Get(ctx, server.URL)
    
    // 斷言
    if err != nil {
        t.Fatalf("Expected no error, got %v", err)
    }
    if resp.StatusCode != http.StatusOK {
        t.Fatalf("Expected 200, got %d", resp.StatusCode)
    }
}

// 表格驅動測試 (對應憲法要求)
func TestDetectEncoding(t *testing.T) {
    tests := []struct {
        name     string
        input    []byte
        expected string
    }{
        {"UTF-8", []byte("日本語テスト"), "日本語テスト"},
        {"Shift-JIS", []byte{0x93, 0xfa, 0x96, 0x7b, 0x8c, 0xea}, "日本語"},
        // 更多測試案例...
    }
    
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            result, err := DetectEncoding(tt.input)
            if err != nil {
                t.Fatalf("Unexpected error: %v", err)
            }
            if result != tt.expected {
                t.Errorf("Expected %s, got %s", tt.expected, result)
            }
        })
    }
}
```

### 建構與執行

**Makefile**:
```makefile
# 建構相關
.PHONY: build test lint

build:
	go build -o bin/actress-classifier ./cmd/cli

test:
	go test -v -race -cover ./...

test-coverage:
	go test -v -race -coverprofile=coverage.out ./...
	go tool cover -html=coverage.out -o coverage.html

lint:
	golangci-lint run

# 開發工具
.PHONY: install-tools
install-tools:
	go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
	go install golang.org/x/tools/cmd/goimports@latest
```

---

## 🖥️ 階段二：CLI 工具

### 目標
使用 Cobra 框架建立命令列工具，驗證階段一開發的核心函式庫。

### CLI 架構

```
actress-classifier search javdb --code "SSIS-001"
actress-classifier search avwiki --actress "三上悠亞"
actress-classifier classify --dir "/path/to/videos" --interactive
actress-classifier stats --show actresses
actress-classifier config set search.timeout 30s
```

### 實作範例

```go
// cmd/cli/main.go
package main

import (
    "github.com/spf13/cobra"
)

func main() {
    rootCmd := &cobra.Command{
        Use:   "actress-classifier",
        Short: "女優影片分類系統",
        Long:  "智慧影片管理工具，支援多源搜尋與自動分類",
    }
    
    // 新增子命令
    rootCmd.AddCommand(searchCmd())
    rootCmd.AddCommand(classifyCmd())
    rootCmd.AddCommand(statsCmd())
    rootCmd.AddCommand(configCmd())
    
    if err := rootCmd.Execute(); err != nil {
        os.Exit(1)
    }
}

// cmd/cli/search.go
func searchCmd() *cobra.Command {
    cmd := &cobra.Command{
        Use:   "search",
        Short: "搜尋影片資訊",
    }
    
    cmd.AddCommand(searchJavdbCmd())
    cmd.AddCommand(searchAvwikiCmd())
    
    return cmd
}

func searchJavdbCmd() *cobra.Command {
    return &cobra.Command{
        Use:   "javdb",
        Short: "從 JAVDB 搜尋",
        RunE: func(cmd *cobra.Command, args []string) error {
            code, _ := cmd.Flags().GetString("code")
            // 呼叫 internal/scraper/sources/javdb.go
            return performJavdbSearch(code)
        },
    }
}
```

---

## 🎨 階段三：GUI 開發

### 方案一：Fyne (純 Go GUI)

**安裝**:
```bash
go get fyne.io/fyne/v2
```

**基本範例**:
```go
// cmd/gui/main.go
package main

import (
    "fyne.io/fyne/v2/app"
    "fyne.io/fyne/v2/container"
    "fyne.io/fyne/v2/widget"
)

func main() {
    myApp := app.New()
    myWindow := myApp.NewWindow("女優分類系統")
    
    // 搜尋介面
    searchEntry := widget.NewEntry()
    searchEntry.SetPlaceHolder("輸入影片編號...")
    
    searchBtn := widget.NewButton("搜尋", func() {
        code := searchEntry.Text
        // 呼叫後端 API
        performSearch(code)
    })
    
    // 結果顯示
    resultList := widget.NewList(
        func() int { return len(searchResults) },
        func() fyne.CanvasObject { return widget.NewLabel("") },
        func(id widget.ListItemID, obj fyne.CanvasObject) {
            obj.(*widget.Label).SetText(searchResults[id])
        },
    )
    
    // 佈局
    content := container.NewBorder(
        container.NewVBox(searchEntry, searchBtn), // 頂部
        nil,                                        // 底部
        nil,                                        // 左側
        nil,                                        // 右側
        resultList,                                 // 中央
    )
    
    myWindow.SetContent(content)
    myWindow.ShowAndRun()
}
```

**優勢**：
- 純 Go，無需前端知識
- 跨平台（Windows, macOS, Linux, iOS, Android）
- Material Design 風格
- 編譯後單一執行檔

**劣勢**：
- UI 客製化能力有限
- 複雜表單較難實作

---

### 方案二：Wails (Go + Web)

**安裝**:
```bash
go install github.com/wailsapp/wails/v2/cmd/wails@latest
wails init -n actress-classifier-gui -t vue
```

**專案結構**:
```
actress-classifier-gui/
├── frontend/              # Vue 3 前端
│   ├── src/
│   │   ├── App.vue
│   │   ├── components/
│   │   └── main.js
│   └── package.json
├── main.go                # Go 後端
└── app.go                 # API 綁定
```

**Go 後端 (app.go)**:
```go
package main

import (
    "context"
    "fmt"
)

type App struct {
    ctx context.Context
}

func NewApp() *App {
    return &App{}
}

func (a *App) startup(ctx context.Context) {
    a.ctx = ctx
}

// SearchVideo 提供給前端呼叫的 API (自動綁定)
func (a *App) SearchVideo(code string) (map[string]interface{}, error) {
    // 呼叫 internal/scraper
    result, err := searchJAVDB(code)
    if err != nil {
        return nil, fmt.Errorf("搜尋失敗: %w", err)
    }
    
    return map[string]interface{}{
        "code":      result.Code,
        "title":     result.Title,
        "actresses": result.Actresses,
        "studio":    result.Studio,
    }, nil
}
```

**Vue 前端 (App.vue)**:
```vue
<template>
  <div id="app">
    <h1>🎬 女優分類系統</h1>
    <input v-model="searchCode" placeholder="輸入影片編號" />
    <button @click="handleSearch">搜尋</button>
    
    <div v-if="result">
      <h2>{{ result.title }}</h2>
      <p>編號: {{ result.code }}</p>
      <p>片商: {{ result.studio }}</p>
      <p>女優: {{ result.actresses.join(', ') }}</p>
    </div>
  </div>
</template>

<script>
import { SearchVideo } from '../wailsjs/go/main/App'

export default {
  data() {
    return {
      searchCode: '',
      result: null
    }
  },
  methods: {
    async handleSearch() {
      try {
        this.result = await SearchVideo(this.searchCode)
      } catch (err) {
        alert('搜尋失敗: ' + err)
      }
    }
  }
}
</script>
```

**優勢**：
- 使用熟悉的 Web 技術 (Vue/React)
- UI 設計彈性極高
- 可重用現有前端元件

**劣勢**：
- 需要前端開發知識
- 打包體積較大 (~50MB)
- 部署需要前端建構步驟

---

### 方案三：混合架構 (Python GUI + Go API)

**架構圖**:
```
┌─────────────────────┐
│  Python tkinter GUI │  (保留現有 UI)
│  (src/ui/main_gui.py)│
└──────────┬──────────┘
           │ HTTP/REST API
           ↓
┌─────────────────────┐
│   Go REST API       │  (新建)
│   (使用 Gin 框架)   │
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│  Go 核心邏輯         │  (階段一完成)
│  (爬蟲、分類、資料庫)│
└─────────────────────┘
```

**Go API 伺服器 (cmd/server/main.go)**:
```go
package main

import (
    "github.com/gin-gonic/gin"
    "actress-classifier/internal/scraper"
)

func main() {
    r := gin.Default()
    
    // 搜尋 API
    r.POST("/api/search/javdb", func(c *gin.Context) {
        var req struct {
            Code string `json:"code"`
        }
        if err := c.ShouldBindJSON(&req); err != nil {
            c.JSON(400, gin.H{"error": err.Error()})
            return
        }
        
        result, err := scraper.SearchJAVDB(req.Code)
        if err != nil {
            c.JSON(500, gin.H{"error": err.Error()})
            return
        }
        
        c.JSON(200, result)
    })
    
    // 分類 API
    r.POST("/api/classify", func(c *gin.Context) {
        // ...
    })
    
    r.Run(":8080")
}
```

**Python GUI 調整 (src/ui/main_gui.py)**:
```python
import requests

class UnifiedActressClassifierGUI:
    def __init__(self, root):
        self.api_base = "http://localhost:8080/api"
        # ... 現有初始化程式碼
    
    def start_javdb_search(self):
        """改為呼叫 Go API"""
        code = self.get_video_code()
        
        try:
            response = requests.post(
                f"{self.api_base}/search/javdb",
                json={"code": code},
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            self.display_result(result)
        except requests.RequestException as e:
            messagebox.showerror("錯誤", f"搜尋失敗: {e}")
```

**優勢**：
- 保留現有 UI，使用者體驗不變
- Go 後端獨立部署和測試
- 漸進式遷移，風險最低
- Python 和 Go 可並行開發

**劣勢**：
- 維護兩種語言
- 部署需要同時啟動 API 和 GUI
- 網路通訊增加延遲

---

## ✅ 遷移檢查清單

### 階段一檢查清單

- [ ] 初始化 Go 專案 (`go mod init`)
- [ ] 建立標準目錄結構 (cmd, internal, pkg)
- [ ] 安裝核心相依套件
  - [ ] `github.com/PuerkitoBio/goquery`
  - [ ] `golang.org/x/text/encoding`
  - [ ] `golang.org/x/time/rate`
  - [ ] `go.uber.org/zap`
- [ ] 實作 HTTP 客戶端
  - [ ] 連線池管理
  - [ ] 逾時控制
  - [ ] User-Agent 輪替
- [ ] 實作頻率限制器
  - [ ] 每網域獨立限流
  - [ ] Token bucket 演算法
  - [ ] 支援 context 取消
- [ ] 實作編碼檢測
  - [ ] UTF-8 檢測
  - [ ] Shift-JIS 轉換
  - [ ] EUC-JP 轉換
- [ ] 實作快取系統
  - [ ] 記憶體快取 (sync.Map)
  - [ ] 檔案快取 (JSON)
  - [ ] TTL 機制
- [ ] 實作資料源爬蟲
  - [ ] JAVDB 爬蟲
  - [ ] AV-WIKI 爬蟲
  - [ ] chiba-f 爬蟲
  - [ ] 統一介面
- [ ] 實作 JSON 資料庫
  - [ ] videos.json CRUD
  - [ ] actresses.json CRUD
  - [ ] studios.json CRUD
  - [ ] 原子寫入
  - [ ] 自動備份
- [ ] 實作分類邏輯
  - [ ] 影片編號提取
  - [ ] 女優識別
  - [ ] 片商分類
- [ ] 撰寫單元測試
  - [ ] 測試覆蓋率 ≥ 70%
  - [ ] 表格驅動測試
  - [ ] Race detector 檢查
- [ ] 撰寫整合測試
  - [ ] 真實網路請求測試
  - [ ] 端到端測試
- [ ] 效能測試
  - [ ] Benchmark 測試
  - [ ] 並發壓力測試
  - [ ] 記憶體洩漏檢查
- [ ] 文件撰寫
  - [ ] API 文件
  - [ ] 架構文件
  - [ ] README 更新

### 階段二檢查清單

- [ ] 安裝 Cobra CLI 框架
- [ ] 實作 root 命令
- [ ] 實作 search 命令群組
  - [ ] `search javdb`
  - [ ] `search avwiki`
  - [ ] `search chibaf`
- [ ] 實作 classify 命令
  - [ ] 基本分類
  - [ ] 互動模式
  - [ ] 批次模式
- [ ] 實作 stats 命令
  - [ ] 女優統計
  - [ ] 片商統計
  - [ ] 搜尋統計
- [ ] 實作 config 命令
  - [ ] `config init`
  - [ ] `config set`
  - [ ] `config get`
- [ ] 實作進度顯示
- [ ] 實作日誌等級控制
- [ ] 跨平台建構
  - [ ] Windows (amd64, arm64)
  - [ ] Linux (amd64, arm64)
  - [ ] macOS (amd64, arm64)
- [ ] 建立 Makefile
- [ ] 建立發布流程
- [ ] CLI 使用手冊

### 階段三檢查清單

- [ ] 完成 GUI 技術選型
- [ ] 建立 GUI 專案骨架
- [ ] 實作主視窗
- [ ] 實作搜尋介面
  - [ ] 資料源選擇
  - [ ] 搜尋輸入
  - [ ] 結果顯示
- [ ] 實作分類介面
  - [ ] 資料夾選擇
  - [ ] 分類模式選擇
  - [ ] 進度顯示
- [ ] 實作設定介面
  - [ ] 偏好設定
  - [ ] 資料源設定
  - [ ] 快取設定
- [ ] 實作統計介面
  - [ ] 女優排行
  - [ ] 片商分佈
  - [ ] 圖表視覺化
- [ ] 實作通知系統
  - [ ] 成功通知
  - [ ] 錯誤提示
  - [ ] 進度更新
- [ ] 整合後端 API
- [ ] 錯誤處理
- [ ] 使用者測試
- [ ] 效能優化
- [ ] 打包與安裝程式
- [ ] 使用者手冊

---

## ❓ 常見問題

### Q1: 為什麼不使用 SQLite？

**A**: 雖然 SQLite 功能強大，但在 Go 中使用需要 cgo，這會增加編譯複雜度和跨平台建構難度。JSON 檔案對於本專案的資料量（<100,000 筆）足夠，且符合憲法「不用額外安裝套件」的要求。

**替代方案**：如果未來資料量增長，可考慮：
- BoltDB (純 Go 鍵值資料庫)
- BadgerDB (高效能嵌入式資料庫)
- SQLite + go-sqlite3 (需接受 cgo 依賴)

---

### Q2: Go 的並發模型與 Python asyncio 有何不同？

**對比表**:

| 特性 | Python asyncio | Go goroutines |
|------|----------------|---------------|
| 並發模型 | 協作式（事件循環） | 搶占式（M:N 排程） |
| 語法 | async/await | go keyword |
| 通訊 | 共享記憶體 | channels |
| 效能 | 單核心 | 多核心 |
| 學習曲線 | 較陡峭 | 較平緩 |

**Python 範例**:
```python
async def fetch(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()

results = await asyncio.gather(fetch(url1), fetch(url2))
```

**Go 對應**:
```go
func fetch(url string) (string, error) {
    resp, err := http.Get(url)
    if err != nil {
        return "", err
    }
    defer resp.Body.Close()
    
    body, err := io.ReadAll(resp.Body)
    return string(body), err
}

// 使用 errgroup 併發執行
g, ctx := errgroup.WithContext(context.Background())

var result1, result2 string
g.Go(func() error {
    var err error
    result1, err = fetch(url1)
    return err
})
g.Go(func() error {
    var err error
    result2, err = fetch(url2)
    return err
})

if err := g.Wait(); err != nil {
    // 處理錯誤
}
```

---

### Q3: JSON 資料庫效能如何優化？

**優化策略**:

1. **記憶體快取**:
```go
type Database struct {
    mu        sync.RWMutex
    cache     map[string]*Video // 記憶體快取
    cacheTTL  time.Duration
    lastLoad  time.Time
}

func (db *Database) GetVideo(code string) (*Video, error) {
    db.mu.RLock()
    defer db.mu.RUnlock()
    
    // 檢查快取
    if v, ok := db.cache[code]; ok {
        return v, nil
    }
    
    // 快取未命中，從檔案讀取
    return db.loadFromFile(code)
}
```

2. **分片儲存**:
```
data/
├── videos_A-F.json
├── videos_G-M.json
├── videos_N-S.json
└── videos_T-Z.json
```

3. **索引檔案**:
```json
// index.json
{
  "SSIS-001": {"file": "videos_S.json", "offset": 1234},
  "SSIS-002": {"file": "videos_S.json", "offset": 5678}
}
```

4. **延遲寫入**:
```go
type Database struct {
    dirtyKeys chan string
    flushInterval time.Duration
}

func (db *Database) startFlushWorker() {
    ticker := time.NewTicker(db.flushInterval)
    go func() {
        for range ticker.C {
            db.flushDirtyKeys()
        }
    }()
}
```

---

### Q4: GUI 選型建議？

**決策樹**:

```
你的團隊是否有前端開發經驗？
├─ 有 → 是否需要複雜現代化 UI？
│       ├─ 是 → 使用 Wails (Vue/React)
│       └─ 否 → 使用 Fyne 或混合架構
└─ 無 → 是否能接受學習曲線？
        ├─ 是 → 使用 Fyne (最簡單的純 Go 方案)
        └─ 否 → 使用混合架構 (保留 Python GUI)
```

**我的推薦**:
1. **短期（1-2 個月內上線）**: 混合架構
2. **中期（3-6 個月）**: Wails (如有前端人員) 或 Fyne (純後端團隊)
3. **長期**: 視實際使用情況決定是否需要重構

---

### Q5: 如何處理日文編碼問題？

**完整範例**:

```go
package parser

import (
    "bytes"
    "errors"
    "io"
    
    "golang.org/x/text/encoding"
    "golang.org/x/text/encoding/japanese"
    "golang.org/x/text/encoding/unicode"
    "golang.org/x/text/transform"
)

// EncodingDetector 編碼檢測器
type EncodingDetector struct {
    encodings []encoding.Encoding
}

// NewEncodingDetector 建立新的編碼檢測器
func NewEncodingDetector() *EncodingDetector {
    return &EncodingDetector{
        encodings: []encoding.Encoding{
            unicode.UTF8,       // 最常見
            japanese.ShiftJIS,  // 日文網站常用
            japanese.EUCJP,     // 舊式日文網站
            japanese.ISO2022JP, // 郵件常用
        },
    }
}

// Detect 嘗試多種編碼解碼
func (ed *EncodingDetector) Detect(rawHTML []byte) (string, string, error) {
    for _, enc := range ed.encodings {
        decoded, err := ed.tryDecode(rawHTML, enc)
        if err == nil {
            return decoded, enc.String(), nil
        }
    }
    
    // 所有編碼都失敗，使用 UTF-8 並替換無效字元
    return string(rawHTML), "utf-8-lossy", errors.New("all encodings failed")
}

func (ed *EncodingDetector) tryDecode(data []byte, enc encoding.Encoding) (string, error) {
    decoder := enc.NewDecoder()
    reader := transform.NewReader(bytes.NewReader(data), decoder)
    decoded, err := io.ReadAll(reader)
    if err != nil {
        return "", err
    }
    
    // 檢查解碼結果是否包含過多無效字元
    if invalidCharRatio(decoded) > 0.1 {
        return "", errors.New("too many invalid characters")
    }
    
    return string(decoded), nil
}

func invalidCharRatio(data []byte) float64 {
    invalid := 0
    for _, b := range data {
        if b == 0xFFFD { // Unicode 替換字元
            invalid++
        }
    }
    return float64(invalid) / float64(len(data))
}
```

---

### Q6: 如何測試爬蟲邏輯？

**策略一：使用 httptest 模擬伺服器**

```go
func TestJAVDBScraper_Search(t *testing.T) {
    // 建立模擬伺服器
    server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        // 返回預先準備的 HTML
        w.WriteHeader(http.StatusOK)
        w.Write([]byte(testJAVDBHTML))
    }))
    defer server.Close()
    
    // 建立爬蟲（使用模擬伺服器 URL）
    scraper := NewJAVDBScraper(server.URL)
    result, err := scraper.Search("SSIS-001")
    
    // 斷言
    assert.NoError(t, err)
    assert.Equal(t, "SSIS-001", result.Code)
    assert.Contains(t, result.Actresses, "三上悠亞")
}
```

**策略二：錄製真實請求**

```go
// 使用 go-vcr 套件錄製 HTTP 互動
func TestJAVDBScraper_SearchReal(t *testing.T) {
    if testing.Short() {
        t.Skip("跳過整合測試")
    }
    
    // 第一次執行時會錄製真實請求
    // 後續執行會重播錄製的回應
    r, err := recorder.New("fixtures/javdb_search")
    if err != nil {
        t.Fatal(err)
    }
    defer r.Stop()
    
    client := &http.Client{Transport: r}
    scraper := NewJAVDBScraperWithClient(client)
    
    result, err := scraper.Search("SSIS-001")
    assert.NoError(t, err)
    // ... 斷言
}
```

**策略三：使用真實請求 + 快取**

```go
func TestJAVDBScraper_Integration(t *testing.T) {
    if os.Getenv("INTEGRATION_TEST") != "1" {
        t.Skip("設定 INTEGRATION_TEST=1 執行")
    }
    
    scraper := NewJAVDBScraper()
    result, err := scraper.Search("SSIS-001")
    
    assert.NoError(t, err)
    assert.NotEmpty(t, result.Title)
    
    // 儲存結果供後續測試使用
    saveTestFixture("javdb_ssis001.json", result)
}
```

---

## 📚 參考資源

### Go 學習資源
- [Effective Go](https://go.dev/doc/effective_go) - 官方最佳實踐
- [Go by Example](https://gobyexample.com/) - 實用範例集
- [The Go Blog](https://go.dev/blog/) - 官方部落格

### 並發模式
- [Go Concurrency Patterns](https://go.dev/blog/pipelines) - 管道模式
- [Advanced Go Concurrency](https://go.dev/blog/io2013-talk-concurrency) - 進階並發

### 相關套件文件
- [goquery](https://github.com/PuerkitoBio/goquery) - HTML 解析
- [Cobra](https://github.com/spf13/cobra) - CLI 框架
- [Fyne](https://fyne.io/) - GUI 框架
- [Wails](https://wails.io/) - Go + Web GUI

### 測試相關
- [Table Driven Tests](https://go.dev/wiki/TableDrivenTests) - 表格驅動測試
- [gomock](https://github.com/golang/mock) - Mock 產生器

---

## 📝 版本紀錄

- **v1.0.0** (2025-10-12): 初版發布
  - 完整三階段重構策略
  - 技術選型建議
  - 實作範例與檢查清單

---

**最後更新**: 2025-10-12  
**維護者**: 女優分類系統開發團隊  
**許可證**: MIT
