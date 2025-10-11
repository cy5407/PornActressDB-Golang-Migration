# 女優分類系統 - Go 版本快速開始

> **⚠️ 注意**: 這是 Go 重構版本的快速開始指南。Python 原版請參考主 README.md

## 📋 前置需求

- **Go 1.22+**: [下載安裝](https://go.dev/dl/)
- **Git**: 版本控制
- **Make**: 建構工具（Windows 使用者可選）

驗證安裝：
```bash
go version    # 應顯示 go1.22 或更高
git --version
```

---

## 🚀 階段一：後端核心邏輯（當前狀態）

### 1. 建立專案結構

```bash
# 建立新的 Go 專案目錄
mkdir actress-classifier-go
cd actress-classifier-go

# 初始化 Go module
go mod init github.com/你的使用者名稱/actress-classifier-go

# 建立標準目錄結構
mkdir -p cmd/cli cmd/server
mkdir -p internal/scraper/client internal/scraper/parser internal/scraper/ratelimit
mkdir -p internal/scraper/cache internal/scraper/sources
mkdir -p internal/classifier internal/database internal/models internal/config
mkdir -p pkg/retry pkg/logger
mkdir -p test/integration test/testdata
mkdir -p data cache docs scripts
```

### 2. 安裝核心相依套件

```bash
# HTTP 與 HTML 解析
go get github.com/PuerkitoBio/goquery

# 編碼處理（日文網站）
go get golang.org/x/text/encoding

# 並發控制
go get golang.org/x/sync/errgroup
go get golang.org/x/time/rate

# 日誌
go get go.uber.org/zap

# 設定管理
go get github.com/spf13/viper

# 測試工具
go get github.com/stretchr/testify
```

### 3. 建立第一個模組：HTTP 客戶端

**檔案**: `internal/scraper/client/client.go`

```go
package client

import (
    "context"
    "net/http"
    "time"
)

// Config HTTP 客戶端設定
type Config struct {
    MaxConcurrent  int
    RequestTimeout time.Duration
    UserAgents     []string
}

// Client HTTP 客戶端
type Client struct {
    httpClient *http.Client
    config     Config
    semaphore  chan struct{}
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

// Get 執行 GET 請求（帶並發控制）
func (c *Client) Get(ctx context.Context, url string) (*http.Response, error) {
    // 取得信號量（限制並發）
    select {
    case c.semaphore <- struct{}{}:
        defer func() { <-c.semaphore }()
    case <-ctx.Done():
        return nil, ctx.Err()
    }
    
    req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
    if err != nil {
        return nil, err
    }
    
    // 設定 User-Agent
    if len(c.config.UserAgents) > 0 {
        req.Header.Set("User-Agent", c.config.UserAgents[0])
    }
    
    return c.httpClient.Do(req)
}
```

### 4. 建立測試

**檔案**: `internal/scraper/client/client_test.go`

```go
package client

import (
    "context"
    "net/http"
    "net/http/httptest"
    "testing"
    "time"
)

func TestClient_Get(t *testing.T) {
    // 建立測試伺服器
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
    
    if err != nil {
        t.Fatalf("Expected no error, got %v", err)
    }
    if resp.StatusCode != http.StatusOK {
        t.Fatalf("Expected 200, got %d", resp.StatusCode)
    }
}
```

### 5. 執行測試

```bash
# 執行所有測試
go test ./...

# 執行測試並顯示覆蓋率
go test -cover ./...

# 產生覆蓋率報告
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out -o coverage.html

# 檢查競態條件
go test -race ./...
```

### 6. 建立 Makefile（簡化命令）

**檔案**: `Makefile`

```makefile
.PHONY: all build test clean

# 預設目標
all: test build

# 建構執行檔
build:
	go build -o bin/actress-classifier ./cmd/cli

# 執行測試
test:
	go test -v -race -cover ./...

# 測試覆蓋率
coverage:
	go test -coverprofile=coverage.out ./...
	go tool cover -html=coverage.out -o coverage.html
	@echo "Coverage report: coverage.html"

# 程式碼檢查
lint:
	golangci-lint run

# 清理建構產物
clean:
	rm -rf bin/
	rm -f coverage.out coverage.html

# 安裝開發工具
install-tools:
	go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest

# 執行（開發模式）
run:
	go run ./cmd/cli
```

使用方式：
```bash
make test       # 執行測試
make build      # 建構執行檔
make coverage   # 產生覆蓋率報告
make lint       # 程式碼檢查
```

---

## 📊 進度追蹤

### ✅ 已完成

- [x] 專案結構建立
- [x] Go module 初始化
- [x] HTTP 客戶端基礎實作
- [x] 測試框架設定

### 🔄 進行中（建議優先順序）

1. **頻率限制器** (`internal/scraper/ratelimit/`)
   - 每個網域獨立限流
   - Token bucket 演算法
   - 測試覆蓋率 ≥ 70%

2. **編碼檢測器** (`internal/scraper/parser/encoding.go`)
   - UTF-8 檢測
   - Shift-JIS 轉換
   - EUC-JP 轉換

3. **HTML 解析器** (`internal/scraper/parser/html.go`)
   - 使用 goquery
   - 封裝常用選擇器操作

4. **快取系統** (`internal/scraper/cache/`)
   - 記憶體快取（sync.Map）
   - 檔案快取（JSON）
   - TTL 機制

5. **JAVDB 爬蟲** (`internal/scraper/sources/javdb.go`)
   - 搜尋功能
   - 資料解析
   - 錯誤處理

### ⏳ 待開始

- [ ] AV-WIKI 爬蟲
- [ ] chiba-f 爬蟲
- [ ] JSON 資料庫
- [ ] 分類邏輯
- [ ] CLI 工具（階段二）
- [ ] GUI（階段三）

---

## 🔧 開發工作流程

### 日常開發循環

```bash
# 1. 建立功能分支
git checkout -b feature/rate-limiter

# 2. 開發功能
# 編輯 internal/scraper/ratelimit/limiter.go

# 3. 執行測試
make test

# 4. 檢查程式碼品質
make lint

# 5. 提交變更
git add .
git commit -m "feat: 實作頻率限制器"

# 6. 推送到遠端
git push origin feature/rate-limiter
```

### 測試驅動開發（TDD）

```bash
# 1. 先寫測試
# 編輯 internal/scraper/ratelimit/limiter_test.go

# 2. 執行測試（應該失敗）
go test ./internal/scraper/ratelimit/

# 3. 實作功能
# 編輯 internal/scraper/ratelimit/limiter.go

# 4. 再次執行測試（應該通過）
go test ./internal/scraper/ratelimit/

# 5. 重構（保持測試通過）
```

---

## 📖 學習資源

### 必讀文件

1. **Go 基礎**
   - [A Tour of Go](https://go.dev/tour/) - 互動式教學
   - [Effective Go](https://go.dev/doc/effective_go) - 官方最佳實踐

2. **並發模式**
   - [Go Concurrency Patterns](https://go.dev/blog/pipelines)
   - [Context 使用指南](https://go.dev/blog/context)

3. **測試**
   - [Table Driven Tests](https://go.dev/wiki/TableDrivenTests)
   - [Testing Techniques](https://go.dev/blog/examples)

### 推薦套件文件

- [goquery](https://pkg.go.dev/github.com/PuerkitoBio/goquery) - HTML 解析
- [golang.org/x/time/rate](https://pkg.go.dev/golang.org/x/time/rate) - 頻率限制
- [zap](https://pkg.go.dev/go.uber.org/zap) - 結構化日誌

---

## 💡 常見問題

### Q: 如何除錯 Go 程式？

**A**: 使用 Delve 除錯器

```bash
# 安裝 Delve
go install github.com/go-delve/delve/cmd/dlv@latest

# 除錯測試
dlv test ./internal/scraper/client

# 除錯程式
dlv debug ./cmd/cli
```

VS Code 設定（`.vscode/launch.json`）:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Launch Package",
      "type": "go",
      "request": "launch",
      "mode": "debug",
      "program": "${workspaceFolder}/cmd/cli"
    }
  ]
}
```

---

### Q: 如何處理相依套件版本？

**A**: 使用 Go modules 管理

```bash
# 檢視所有相依套件
go list -m all

# 檢視可更新的套件
go list -u -m all

# 更新特定套件
go get github.com/PuerkitoBio/goquery@latest

# 更新所有套件（謹慎使用）
go get -u ./...

# 清理未使用的相依
go mod tidy

# 驗證相依套件
go mod verify
```

---

### Q: 如何組織測試資料？

**A**: 使用 `testdata` 目錄

```
internal/scraper/sources/
├── javdb.go
├── javdb_test.go
└── testdata/
    ├── javdb_search_response.html
    ├── javdb_detail_response.html
    └── expected_result.json
```

在測試中讀取：
```go
func TestJAVDBParser(t *testing.T) {
    // 讀取測試資料
    htmlBytes, err := os.ReadFile("testdata/javdb_search_response.html")
    if err != nil {
        t.Fatal(err)
    }
    
    // 測試解析邏輯
    result, err := ParseJAVDBResponse(htmlBytes)
    // ...
}
```

---

### Q: 如何效能分析？

**A**: 使用內建 profiling 工具

```bash
# CPU 分析
go test -cpuprofile=cpu.prof -bench=.
go tool pprof cpu.prof

# 記憶體分析
go test -memprofile=mem.prof -bench=.
go tool pprof mem.prof

# 產生視覺化圖表
go tool pprof -http=:8080 cpu.prof
```

---

## 🎯 下一步

完成階段一後，請參考：

1. **[Go 重構指南](./go-重構指南.md)** - 完整技術文件
2. **[Constitution](../.specify/memory/constitution.md)** - 開發規範
3. **階段二：CLI 工具** - 開始建立命令列介面

---

**需要協助？**

- 查看 [GitHub Issues](https://github.com/你的repo/issues)
- 閱讀 [Go 重構指南](./go-重構指南.md)
- 參考 Python 原版程式碼：`src/scrapers/`

---

**版本**: 1.0.0  
**最後更新**: 2025-10-12  
**維護者**: 女優分類系統開發團隊
