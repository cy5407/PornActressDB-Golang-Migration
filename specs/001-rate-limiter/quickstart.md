# Quick Start Guide: Web Scraper Rate Limiter

**功能**: 網域獨立速率限制器  
**版本**: 1.0  
**更新日期**: 2025-10-12

## 目錄

1. [5 分鐘快速上手](#5-分鐘快速上手)
2. [安裝](#安裝)
3. [基本使用](#基本使用)
4. [配置管理](#配置管理)
5. [進階使用](#進階使用)
6. [常見問題](#常見問題)
7. [最佳實踐](#最佳實踐)

---

## 5 分鐘快速上手

### 步驟 1: 建立限流器

```go
package main

import (
    "context"
    "log"
    "net/http"
    
    "actress-classifier/internal/ratelimit"
)

func main() {
    // 建立限流器，配置各網域的速率
    limiter := ratelimit.New(map[string]ratelimit.LimitConfig{
        "javdb.com":   {RequestsPerSecond: 1, BurstCapacity: 1},
        "av-wiki.net": {RequestsPerSecond: 2, BurstCapacity: 2},
    }, ratelimit.DefaultConfig)
    
    defer limiter.Close()
    
    // 使用限流器
    ctx := context.Background()
    
    // 等待獲取許可
    if err := limiter.Wait(ctx, "javdb.com"); err != nil {
        log.Fatal(err)
    }
    
    // 現在可以安全地發送請求
    resp, err := http.Get("https://javdb.com/search?q=test")
    if err != nil {
        log.Fatal(err)
    }
    defer resp.Body.Close()
    
    log.Println("請求成功！")
}
```

### 步驟 2: 查看統計

```go
// 獲取特定網域的統計
stats, err := limiter.GetStats("javdb.com")
if err != nil {
    log.Fatal(err)
}

log.Printf("JAVDB 統計:")
log.Printf("  總請求: %d", stats.TotalRequests)
log.Printf("  延遲請求: %d", stats.DelayedRequests)
log.Printf("  延遲率: %.2f%%", stats.DelayRate*100)
log.Printf("  平均等待時間: %v", stats.AverageWaitTime)

// 獲取所有網域的統計
allStats := limiter.GetAllStats()
for domain, s := range allStats {
    log.Printf("%s: %d 個請求", domain, s.TotalRequests)
}
```

**就是這麼簡單！** 🎉

---

## 安裝

### 前置需求

- Go 1.22 或更新版本
- 網路連線（下載相依套件）

### 下載相依套件

速率限制器使用以下相依套件（會自動下載）：

```bash
go get golang.org/x/time/rate
go get golang.org/x/sync/errgroup
go get go.uber.org/zap
```

### 驗證安裝

```bash
cd internal/ratelimit
go test -v
```

如果看到 `PASS`，表示安裝成功！

---

## 基本使用

### 方式 1: 程式碼建構（適合簡單場景）

```go
import "actress-classifier/internal/ratelimit"

// 建立限流器
limiter := ratelimit.New(
    map[string]ratelimit.LimitConfig{
        "javdb.com": {
            RequestsPerSecond: 1.0,  // 每秒 1 個請求
            BurstCapacity:     1,     // Burst 容量 1
        },
        "av-wiki.net": {
            RequestsPerSecond: 2.0,  // 每秒 2 個請求
            BurstCapacity:     3,     // Burst 容量 3
        },
    },
    ratelimit.DefaultConfig,  // 未配置網域的預設值
)
defer limiter.Close()
```

### 方式 2: 從配置檔案載入（適合生產環境）

**步驟 1**: 建立配置檔案 `config/ratelimit.json`

```json
{
  "version": "1.0",
  "default_config": {
    "requests_per_second": 1.0,
    "burst_capacity": 1
  },
  "domains": {
    "javdb.com": {
      "requests_per_second": 1.0,
      "burst_capacity": 1
    },
    "av-wiki.net": {
      "requests_per_second": 2.0,
      "burst_capacity": 2
    },
    "chiba-f.com": {
      "requests_per_second": 1.0,
      "burst_capacity": 1
    }
  }
}
```

**步驟 2**: 載入配置

```go
limiter, err := ratelimit.NewFromConfig("config/ratelimit.json")
if err != nil {
    log.Fatalf("載入配置失敗: %v", err)
}
defer limiter.Close()
```

---

## 配置管理

### 配置參數說明

#### RequestsPerSecond (每秒請求數)

- **類型**: `float64`
- **必須**: 大於 0
- **說明**: 控制每秒允許的請求數量

| 值 | 含義 | 使用場景 |
|----|------|---------|
| 0.5 | 每 2 秒 1 個請求 | 極保守限流 |
| 1.0 | 每秒 1 個請求 | 一般限流（推薦） |
| 2.0 | 每秒 2 個請求 | 寬鬆限流 |
| 10.0 | 每秒 10 個請求 | 高頻爬取 |

#### BurstCapacity (Burst 容量)

- **類型**: `int`
- **必須**: 至少為 1
- **說明**: 允許短時間內累積的請求數

| 值 | 含義 | 使用場景 |
|----|------|---------|
| 1 | 無 burst，嚴格限流 | 保守策略 |
| 2-3 | 適度 burst | 一般場景 |
| 5-10 | 較大 burst | 允許短時間爆發 |

**建議組合**:

```go
// 保守配置（JAVDB）
LimitConfig{
    RequestsPerSecond: 1.0,
    BurstCapacity:     1,
}

// 一般配置（AV-WIKI）
LimitConfig{
    RequestsPerSecond: 2.0,
    BurstCapacity:     2,
}

// 寬鬆配置（內部 API）
LimitConfig{
    RequestsPerSecond: 10.0,
    BurstCapacity:     20,
}
```

### 預設配置

```go
// 使用內建預設配置
limiter := ratelimit.New(nil, ratelimit.DefaultConfig)

// 或使用預設的網域配置
limiter := ratelimit.New(ratelimit.PresetConfigs, ratelimit.DefaultConfig)
```

**PresetConfigs 內容**:

| 網域 | 請求/秒 | Burst |
|-----|---------|-------|
| javdb.com | 1.0 | 1 |
| av-wiki.net | 2.0 | 2 |
| chiba-f.com | 1.0 | 1 |
| minnano-av.com | 1.0 | 1 |

---

## 進階使用

### 1. Context 控制

#### 超時控制

```go
// 設定 5 秒超時
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()

err := limiter.Wait(ctx, "javdb.com")
if err != nil {
    if errors.Is(err, context.DeadlineExceeded) {
        log.Println("等待超時，網站可能回應過慢")
    }
    return err
}
```

#### 取消控制

```go
ctx, cancel := context.WithCancel(context.Background())

// 在另一個 goroutine 中處理取消
go func() {
    <-stopSignal
    cancel()  // 取消所有等待中的請求
}()

err := limiter.Wait(ctx, "javdb.com")
if err != nil {
    if errors.Is(err, context.Canceled) {
        log.Println("使用者取消請求")
    }
    return err
}
```

### 2. 非阻塞檢查

```go
// 立即檢查是否可以發送請求，不等待
if limiter.Allow("javdb.com") {
    // 可以立即發送
    resp, err := http.Get("https://javdb.com/...")
    // ...
} else {
    // 無法立即發送，稍後重試或跳過
    log.Warn("速率限制中，跳過此請求")
}
```

**使用場景**:
- 可選的背景任務
- 「盡力而為」的爬取
- UI 回應性要求高的場景

### 3. 批次請求

```go
// 預留 5 個 token 用於批次請求
ctx := context.Background()
if err := limiter.WaitN(ctx, "javdb.com", 5); err != nil {
    return err
}

// 現在可以連續發送 5 個請求
for i := 0; i < 5; i++ {
    url := fmt.Sprintf("https://javdb.com/page/%d", i+1)
    resp, err := http.Get(url)
    // 處理回應...
}
```

### 4. 並發爬取

```go
package main

import (
    "context"
    "log"
    "sync"
    
    "actress-classifier/internal/ratelimit"
    "golang.org/x/sync/errgroup"
)

func main() {
    limiter := ratelimit.NewFromConfig("config/ratelimit.json")
    defer limiter.Close()
    
    urls := []string{
        "https://javdb.com/page/1",
        "https://javdb.com/page/2",
        "https://javdb.com/page/3",
        // ... 更多 URL
    }
    
    // 使用 errgroup 協調並發
    g, ctx := errgroup.WithContext(context.Background())
    
    for _, url := range urls {
        url := url  // 捕獲變數
        g.Go(func() error {
            // 等待限流許可
            if err := limiter.Wait(ctx, "javdb.com"); err != nil {
                return err
            }
            
            // 發送請求
            return fetchURL(url)
        })
    }
    
    // 等待所有請求完成
    if err := g.Wait(); err != nil {
        log.Fatalf("爬取失敗: %v", err)
    }
    
    // 顯示統計
    stats, _ := limiter.GetStats("javdb.com")
    log.Printf("完成！總請求: %d, 平均等待: %v", 
        stats.TotalRequests, stats.AverageWaitTime)
}

func fetchURL(url string) error {
    // 實作 HTTP 請求邏輯
    return nil
}
```

### 5. 動態調整配置（可選功能）

```go
// 注意：此功能可能在 MVP 版本中不可用

// 提高 JAVDB 的速率限制
newConfig := ratelimit.LimitConfig{
    RequestsPerSecond: 2.0,  // 從 1.0 提高到 2.0
    BurstCapacity:     3,
}

if err := limiter.UpdateConfig("javdb.com", newConfig); err != nil {
    log.Printf("更新配置失敗: %v", err)
}
```

---

## 常見問題

### Q1: 為什麼第一個請求很快，後續請求變慢？

**A**: 這是 burst capacity 的作用。如果 `BurstCapacity > 1`，前幾個請求可以快速執行（使用累積的 token），之後需要等待 token 恢復。

**解決方案**:
- 如果希望速率更平穩，設定 `BurstCapacity = 1`
- 如果希望允許短時間爆發，保持 `BurstCapacity > 1`

---

### Q2: 如何知道是否被限流了？

**A**: 查看統計資訊的 `DelayRate`：

```go
stats, _ := limiter.GetStats("javdb.com")
if stats.DelayRate > 0.5 {
    log.Printf("警告：%s 的 50%% 請求被延遲", domain)
}
```

---

### Q3: 可以動態新增網域嗎？

**A**: 可以！限流器會自動為新網域使用預設配置：

```go
// 首次請求 "new-site.com"，自動建立限流器
err := limiter.Wait(ctx, "new-site.com")  // 使用 defaultConfig
```

---

### Q4: 如何處理請求失敗和重試？

**A**: 結合限流器和重試邏輯：

```go
func fetchWithRetry(ctx context.Context, limiter ratelimit.RateLimiter, url string) error {
    maxRetries := 3
    
    for i := 0; i < maxRetries; i++ {
        // 等待限流許可
        if err := limiter.Wait(ctx, extractDomain(url)); err != nil {
            return err
        }
        
        // 發送請求
        resp, err := http.Get(url)
        if err == nil {
            return nil  // 成功
        }
        
        // 檢查是否應該重試
        if !isRetryable(err) {
            return err  // 永久性錯誤，不重試
        }
        
        log.Printf("請求失敗 (嘗試 %d/%d): %v", i+1, maxRetries, err)
        time.Sleep(time.Second * time.Duration(i+1))  // 指數退避
    }
    
    return fmt.Errorf("重試 %d 次後仍失敗", maxRetries)
}
```

---

### Q5: 限流器的記憶體佔用有多大？

**A**: 非常小！

- 每個網域: ~200 bytes
- 100 個網域: ~20 KB
- 1000 個網域: ~200 KB

---

### Q6: 如何在測試中使用限流器？

**A**: 使用高速率配置：

```go
func TestMyFunction(t *testing.T) {
    // 測試環境使用極高速率，避免減慢測試
    limiter := ratelimit.New(nil, ratelimit.LimitConfig{
        RequestsPerSecond: 1000,  // 非常快
        BurstCapacity:     100,
    })
    defer limiter.Close()
    
    // 使用 limiter 進行測試...
}
```

---

## 最佳實踐

### ✅ 建議做法

#### 1. 全域單例模式

```go
// 在應用程式啟動時建立一次
var globalLimiter ratelimit.RateLimiter

func init() {
    var err error
    globalLimiter, err = ratelimit.NewFromConfig("config/ratelimit.json")
    if err != nil {
        log.Fatal(err)
    }
}

// 在各處使用
func fetchData(url string) error {
    ctx := context.Background()
    if err := globalLimiter.Wait(ctx, extractDomain(url)); err != nil {
        return err
    }
    // ...
}
```

#### 2. 總是使用 Context

```go
// ✅ 好
func fetch(ctx context.Context) error {
    if err := limiter.Wait(ctx, domain); err != nil {
        return err
    }
    // ...
}

// ❌ 不好（無法取消）
func fetch() error {
    if err := limiter.Wait(context.Background(), domain); err != nil {
        return err
    }
    // ...
}
```

#### 3. 記得關閉限流器

```go
func main() {
    limiter, err := ratelimit.NewFromConfig("config.json")
    if err != nil {
        log.Fatal(err)
    }
    defer limiter.Close()  // ✅ 總是 defer Close
    
    // 使用 limiter...
}
```

#### 4. 記錄統計資訊

```go
// 定期記錄統計
func logStats(limiter ratelimit.RateLimiter) {
    ticker := time.NewTicker(5 * time.Minute)
    defer ticker.Stop()
    
    for range ticker.C {
        stats := limiter.GetAllStats()
        for domain, s := range stats {
            log.Printf("[統計] %s: %d 請求, %.2f%% 延遲", 
                domain, s.TotalRequests, s.DelayRate*100)
        }
    }
}
```

### ❌ 避免的做法

#### 1. 不要在迴圈中建立限流器

```go
// ❌ 錯誤
for _, url := range urls {
    limiter := ratelimit.New(...)  // 每次都建立新的
    limiter.Wait(ctx, domain)
}

// ✅ 正確
limiter := ratelimit.New(...)
defer limiter.Close()
for _, url := range urls {
    limiter.Wait(ctx, domain)
}
```

#### 2. 不要忽略錯誤

```go
// ❌ 錯誤
limiter.Wait(ctx, domain)  // 忽略錯誤
http.Get(url)

// ✅ 正確
if err := limiter.Wait(ctx, domain); err != nil {
    return err
}
```

#### 3. 不要使用過小的超時

```go
// ❌ 可能有問題
ctx, cancel := context.WithTimeout(ctx, 10*time.Millisecond)  // 太短

// ✅ 合理
ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
```

---

## 範例程式碼

### 完整爬蟲範例

```go
package main

import (
    "context"
    "fmt"
    "log"
    "net/http"
    "time"
    
    "actress-classifier/internal/ratelimit"
    "golang.org/x/sync/errgroup"
)

func main() {
    // 1. 建立限流器
    limiter, err := ratelimit.NewFromConfig("config/ratelimit.json")
    if err != nil {
        log.Fatalf("載入配置失敗: %v", err)
    }
    defer limiter.Close()
    
    // 2. 準備要爬取的 URL
    urls := []string{
        "https://javdb.com/search?q=actress1",
        "https://javdb.com/search?q=actress2",
        "https://av-wiki.net/search?q=actress1",
        // ...
    }
    
    // 3. 並發爬取
    g, ctx := errgroup.WithContext(context.Background())
    g.SetLimit(10)  // 限制最大並發數
    
    for _, url := range urls {
        url := url
        g.Go(func() error {
            return fetchURL(ctx, limiter, url)
        })
    }
    
    // 4. 等待完成
    if err := g.Wait(); err != nil {
        log.Fatalf("爬取失敗: %v", err)
    }
    
    // 5. 顯示統計
    printStats(limiter)
}

func fetchURL(ctx context.Context, limiter ratelimit.RateLimiter, url string) error {
    domain := extractDomain(url)
    
    // 等待限流許可
    if err := limiter.Wait(ctx, domain); err != nil {
        return fmt.Errorf("等待限流失敗 (%s): %w", domain, err)
    }
    
    // 發送請求
    resp, err := http.Get(url)
    if err != nil {
        return fmt.Errorf("HTTP 請求失敗 (%s): %w", url, err)
    }
    defer resp.Body.Close()
    
    log.Printf("✓ 成功: %s (狀態: %d)", url, resp.StatusCode)
    return nil
}

func extractDomain(url string) string {
    // 簡化版本，實際應使用 net/url 解析
    if len(url) > 8 && url[:8] == "https://" {
        url = url[8:]
    }
    for i, c := range url {
        if c == '/' {
            return url[:i]
        }
    }
    return url
}

func printStats(limiter ratelimit.RateLimiter) {
    fmt.Println("\n=== 爬取統計 ===")
    stats := limiter.GetAllStats()
    for domain, s := range stats {
        fmt.Printf("\n網域: %s\n", domain)
        fmt.Printf("  總請求數: %d\n", s.TotalRequests)
        fmt.Printf("  延遲請求數: %d\n", s.DelayedRequests)
        fmt.Printf("  延遲率: %.2f%%\n", s.DelayRate*100)
        fmt.Printf("  平均等待時間: %v\n", s.AverageWaitTime)
        fmt.Printf("  最後請求時間: %v\n", s.LastRequestTime.Format(time.RFC3339))
    }
}
```

---

## 下一步

- 📖 閱讀 [data-model.md](./data-model.md) 了解內部設計
- 🔧 查看 [contracts/ratelimiter.go](./contracts/ratelimiter.go) 了解完整 API
- 🧪 參考測試檔案了解更多使用範例
- 📝 查看 [plan.md](./plan.md) 了解實作計畫

---

**需要幫助？** 查看專案文件或提交 Issue！ 🚀
