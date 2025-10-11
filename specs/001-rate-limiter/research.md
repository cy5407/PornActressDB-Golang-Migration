# Research Document: Web Scraper Rate Limiter

**Feature**: Web Scraper Rate Limiter  
**Date**: 2025-10-12  
**Phase**: Phase 0 - Technical Research  
**Status**: Completed

## Executive Summary

本研究文件記錄了速率限制器實作的所有技術決策，包括演算法選擇、並發控制策略、配置管理、context 處理和測試方法。所有決策均基於 Go 生態系統最佳實踐和專案 Constitution 要求。

---

## R1: Token Bucket 演算法實作選擇

### Decision
**使用 `golang.org/x/time/rate.Limiter`** 作為 token bucket 演算法的實作基礎。

### Rationale

1. **官方維護**: 由 Go 官方團隊維護，品質和穩定性有保證
2. **功能完整**: 
   - 支援 burst capacity 配置
   - 提供 `Wait(ctx)`, `Allow()`, `Reserve()` 等多種 API
   - 內建 context 支援，可優雅取消
3. **並發安全**: 內部使用 mutex 保護，經過充分測試
4. **效能優異**: 使用高效的時間窗口演算法，記憶體佔用極小
5. **社群驗證**: 被大量 Go 專案使用，包括 gRPC、Kubernetes 等

### Implementation Details

```go
import "golang.org/x/time/rate"

// 建立限流器：每秒 1 個請求，burst 容量 1
limiter := rate.NewLimiter(rate.Limit(1.0), 1)

// 等待獲取 token（支援 context 取消）
err := limiter.Wait(ctx)
if err != nil {
    // context 被取消或超時
    return err
}

// 非阻塞檢查
if limiter.Allow() {
    // 可以立即執行請求
}

// 獲取預約（可提前知道需要等待多久）
reservation := limiter.Reserve()
if !reservation.OK() {
    // 無法在合理時間內獲取 token
    return ErrRateLimitExceeded
}
time.Sleep(reservation.Delay())
```

### Alternatives Considered

#### Alternative 1: 自行實作 Token Bucket
- **優點**: 完全客製化，可調整演算法細節
- **缺點**: 
  - 需要大量測試確保正確性
  - 並發安全需要仔細處理
  - 維護成本高
- **拒絕原因**: Constitution 要求「優先使用標準函式庫」，且 `x/time/rate` 已經提供完整功能

#### Alternative 2: 使用第三方套件（如 `uber-go/ratelimit`）
- **優點**: 更簡潔的 API
- **缺點**: 
  - 不支援 burst capacity
  - 不支援 context 取消
  - 額外的外部相依
- **拒絕原因**: 功能不完整，且違反「最小化外部相依」原則

### References
- [golang.org/x/time/rate Documentation](https://pkg.go.dev/golang.org/x/time/rate)
- [Token Bucket Algorithm Explanation](https://en.wikipedia.org/wiki/Token_bucket)

---

## R2: 並發安全策略

### Decision
**使用 `sync.RWMutex` 保護網域限流器對映表，每個 `DomainLimiter` 使用 `sync.Mutex` 保護統計資訊**。

### Rationale

1. **分層鎖設計**:
   - **外層 RWMutex**: 保護 `map[string]*DomainLimiter`
   - **內層 Mutex**: 保護每個網域的統計資訊
   - 優點：細粒度鎖定，減少競爭

2. **讀寫分離**:
   - `Wait()` 操作：讀鎖獲取 DomainLimiter，寫鎖僅在建立新網域時使用
   - `GetStats()` 操作：讀鎖獲取 limiter，每個網域內部用 mutex 保護統計更新

3. **效能考量**:
   - 大部分操作是讀取現有 limiter（高並發讀）
   - 建立新網域的操作很少（偶爾寫入）
   - RWMutex 在讀多寫少場景下效能優於 Mutex

### Implementation Pattern

```go
type RateLimiter struct {
    limiters      map[string]*DomainLimiter
    defaultConfig LimitConfig
    mu            sync.RWMutex // 保護 limiters map
}

type DomainLimiter struct {
    domain  string
    limiter *rate.Limiter
    config  LimitConfig
    stats   *LimitStats
    statsMu sync.Mutex // 保護 stats
}

// Wait 方法實作
func (rl *RateLimiter) Wait(ctx context.Context, domain string) error {
    // 讀鎖獲取 limiter
    rl.mu.RLock()
    dl, exists := rl.limiters[domain]
    rl.mu.RUnlock()
    
    if !exists {
        // 寫鎖建立新 limiter
        rl.mu.Lock()
        // Double-check pattern
        dl, exists = rl.limiters[domain]
        if !exists {
            dl = newDomainLimiter(domain, rl.defaultConfig)
            rl.limiters[domain] = dl
        }
        rl.mu.Unlock()
    }
    
    // 等待 token（rate.Limiter 內部已並發安全）
    if err := dl.limiter.Wait(ctx); err != nil {
        return err
    }
    
    // 更新統計（需要鎖定）
    dl.updateStats(0) // 未被延遲
    return nil
}
```

### Alternatives Considered

#### Alternative 1: sync.Map
- **優點**: 無需手動加鎖，Go 最佳化的並發 map
- **缺點**: 
  - 不支援範圍遍歷（GetAllStats 會困難）
  - 類型安全性較差（需要類型斷言）
  - Store/Load 操作有記憶體分配開銷
- **拒絕原因**: 功能需求包含 `GetAllStats()`，需要遍歷所有網域

#### Alternative 2: Channels Only (無鎖設計)
- **優點**: 符合「用 channels 通訊而非共享記憶體」哲學
- **缺點**: 
  - 需要額外的 goroutine 管理
  - Channel 本身有效能開銷
  - 複雜度高，難以維護
- **拒絕原因**: 過度設計，mutex 足以滿足需求且更簡單

#### Alternative 3: 粗粒度鎖（單一 Mutex 保護所有）
- **優點**: 實作最簡單
- **缺點**: 
  - 所有網域共用一個鎖，並發效能差
  - 違反「高並發」要求（100+ goroutines）
- **拒絕原因**: 效能不符合需求

### References
- [Effective Go - Concurrency](https://go.dev/doc/effective_go#concurrency)
- [Go sync Package](https://pkg.go.dev/sync)

---

## R3: 配置載入機制

### Decision
**支援 JSON 格式配置檔案，並提供程式碼建構函式**。

### Rationale

1. **格式選擇 - JSON**:
   - Constitution 中現有專案使用 JSON 資料庫（actresses.json, studios.json）
   - Go 標準函式庫原生支援（encoding/json）
   - 結構化、易於驗證
   - 支援註解（使用 `// ...` 非標準但工具支援）

2. **雙重介面**:
   ```go
   // 方式 1: 從配置檔案載入
   limiter, err := ratelimit.NewFromConfig("config/ratelimit.json")
   
   // 方式 2: 程式碼建構（用於測試或動態配置）
   limiter := ratelimit.New(map[string]LimitConfig{
       "javdb.com": {RequestsPerSecond: 1, BurstCapacity: 1},
       "av-wiki.net": {RequestsPerSecond: 2, BurstCapacity: 2},
   }, defaultConfig)
   ```

3. **配置驗證**:
   - RequestsPerSecond 必須 > 0
   - BurstCapacity 必須 ≥ 1
   - 配置載入時立即驗證，失敗則返回錯誤

### Configuration File Format

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

### Implementation

```go
type ConfigFile struct {
    Version       string                  `json:"version"`
    DefaultConfig LimitConfig             `json:"default_config"`
    Domains       map[string]LimitConfig  `json:"domains"`
}

func NewFromConfig(configPath string) (*RateLimiter, error) {
    data, err := os.ReadFile(configPath)
    if err != nil {
        return nil, fmt.Errorf("讀取配置檔案失敗: %w", err)
    }
    
    var cfg ConfigFile
    if err := json.Unmarshal(data, &cfg); err != nil {
        return nil, fmt.Errorf("解析配置檔案失敗: %w", err)
    }
    
    // 驗證配置
    if err := cfg.DefaultConfig.Validate(); err != nil {
        return nil, fmt.Errorf("預設配置無效: %w", err)
    }
    
    for domain, config := range cfg.Domains {
        if err := config.Validate(); err != nil {
            return nil, fmt.Errorf("網域 %s 配置無效: %w", domain, err)
        }
    }
    
    return New(cfg.Domains, cfg.DefaultConfig), nil
}
```

### Alternatives Considered

#### Alternative 1: INI 格式
- **優點**: 簡單、人類可讀
- **缺點**: 
  - 不支援巢狀結構
  - 需要第三方解析套件（如 `gopkg.in/ini.v1`）
- **拒絕原因**: 專案已使用 JSON，保持一致性

#### Alternative 2: YAML 格式
- **優點**: 更易讀、支援註解
- **缺點**: 
  - 需要第三方套件（`gopkg.in/yaml.v3`）
  - 解析效能略低於 JSON
  - 增加外部相依
- **拒絕原因**: Constitution 要求「最小化外部相依」

#### Alternative 3: 僅支援程式碼配置（無檔案）
- **優點**: 無需檔案 I/O，類型安全
- **缺點**: 
  - 不便於運維調整配置
  - 違反「配置與程式碼分離」原則
- **拒絕原因**: 靈活性不足

### References
- [Go JSON Package](https://pkg.go.dev/encoding/json)
- [JSON Schema Validation](https://json-schema.org/)

---

## R4: Context 取消實作模式

### Decision
**直接使用 `rate.Limiter.Wait(ctx)` 的內建 context 支援，無需額外處理**。

### Rationale

1. **原生支援**: `rate.Limiter.Wait(ctx)` 已經正確實作 context 取消
2. **錯誤處理**:
   ```go
   err := limiter.Wait(ctx)
   if err != nil {
       if errors.Is(err, context.Canceled) {
           // 使用者主動取消
           return err
       }
       if errors.Is(err, context.DeadlineExceeded) {
           // 超時
           return err
       }
       // 其他錯誤
       return err
   }
   ```

3. **響應時間**: `Wait()` 使用內部 timer + select，context 取消會立即響應（通常 <1ms）

### Implementation Pattern

```go
func (rl *RateLimiter) Wait(ctx context.Context, domain string) error {
    dl := rl.getOrCreateDomainLimiter(domain)
    
    // 記錄開始時間
    start := time.Now()
    
    // 等待 token（內建 context 支援）
    err := dl.limiter.Wait(ctx)
    
    // 計算等待時間
    waitTime := time.Since(start)
    
    if err != nil {
        // Context 被取消，更新統計但不計入成功請求
        dl.updateStatsCanceled(waitTime)
        return fmt.Errorf("等待 token 失敗 (%s): %w", domain, err)
    }
    
    // 成功獲取 token，更新統計
    delayed := waitTime > 10*time.Millisecond // 超過 10ms 視為被延遲
    dl.updateStatsSuccess(waitTime, delayed)
    
    return nil
}
```

### Testing Context Cancellation

```go
func TestRateLimiter_Wait_ContextCanceled(t *testing.T) {
    limiter := New(map[string]LimitConfig{
        "test.com": {RequestsPerSecond: 0.1, BurstCapacity: 1}, // 極慢速率
    }, defaultConfig)
    
    // 第一個請求立即成功（使用 burst）
    ctx1 := context.Background()
    assert.NoError(t, limiter.Wait(ctx1, "test.com"))
    
    // 第二個請求需要等待，但我們立即取消
    ctx2, cancel := context.WithCancel(context.Background())
    
    go func() {
        time.Sleep(50 * time.Millisecond)
        cancel() // 50ms 後取消
    }()
    
    start := time.Now()
    err := limiter.Wait(ctx2, "test.com")
    elapsed := time.Since(start)
    
    // 驗證：應該在約 50ms 時取消，而非等待完整的 10 秒
    assert.Error(t, err)
    assert.True(t, errors.Is(err, context.Canceled))
    assert.Less(t, elapsed, 100*time.Millisecond) // 遠小於需要的等待時間
}
```

### Alternatives Considered

#### Alternative 1: 自行實作 Select Statement
```go
// 不建議
select {
case <-ctx.Done():
    return ctx.Err()
case <-time.After(waitDuration):
    // 執行請求
}
```
- **缺點**: 
  - 重複造輪子
  - 無法利用 token bucket 的動態調整
  - 效能較差
- **拒絕原因**: `rate.Limiter.Wait()` 已提供此功能

#### Alternative 2: 使用 Timeout 而非 Context
- **缺點**: 
  - 無法支援使用者主動取消
  - 不符合 Go 的 context 最佳實踐
- **拒絕原因**: Constitution 要求「context-based cancellation」

### References
- [Go Context Package](https://pkg.go.dev/context)
- [Context Best Practices](https://go.dev/blog/context)

---

## R5: 統計資訊收集設計

### Decision
**使用 `sync/atomic` 操作更新統計計數器，用 `sync.Mutex` 保護時間戳記**。

### Rationale

1. **混合策略**:
   - **Atomic**: 高頻操作（TotalRequests, DelayedRequests）
   - **Mutex**: 低頻操作（TotalWaitTime, LastRequestTime）

2. **效能優勢**:
   - Atomic 操作無鎖，極低開銷
   - 只在需要時間同步時使用 mutex

3. **記憶體對齊**: 確保 64-bit atomic 操作在 32-bit 平台上正確

### Implementation

```go
type LimitStats struct {
    totalRequests   atomic.Int64  // 使用 atomic
    delayedRequests atomic.Int64  // 使用 atomic
    
    mu              sync.Mutex
    totalWaitTime   time.Duration // 需要 mutex 保護
    lastRequestTime time.Time     // 需要 mutex 保護
}

// 更新統計（成功請求）
func (dl *DomainLimiter) updateStatsSuccess(waitTime time.Duration, delayed bool) {
    dl.stats.totalRequests.Add(1)
    
    if delayed {
        dl.stats.delayedRequests.Add(1)
    }
    
    // 更新時間相關統計（需要鎖定）
    dl.stats.mu.Lock()
    dl.stats.totalWaitTime += waitTime
    dl.stats.lastRequestTime = time.Now()
    dl.stats.mu.Unlock()
}

// 獲取統計快照（返回副本，不持有鎖）
func (dl *DomainLimiter) GetStats() LimitStats {
    total := dl.stats.totalRequests.Load()
    delayed := dl.stats.delayedRequests.Load()
    
    dl.stats.mu.Lock()
    waitTime := dl.stats.totalWaitTime
    lastTime := dl.stats.lastRequestTime
    dl.stats.mu.Unlock()
    
    var avgWaitTime time.Duration
    if delayed > 0 {
        avgWaitTime = waitTime / time.Duration(delayed)
    }
    
    return LimitStats{
        TotalRequests:    total,
        DelayedRequests:  delayed,
        TotalWaitTime:    waitTime,
        AverageWaitTime:  avgWaitTime,
        LastRequestTime:  lastTime,
    }
}
```

### Memory Layout Consideration

```go
// 確保 64-bit 對齊（在 32-bit 平台上重要）
type LimitStats struct {
    // 64-bit 欄位放在前面
    totalRequests   atomic.Int64
    delayedRequests atomic.Int64
    
    // 其他欄位
    mu              sync.Mutex
    totalWaitTime   time.Duration
    lastRequestTime time.Time
}
```

### Alternatives Considered

#### Alternative 1: 全部使用 Mutex
- **優點**: 實作最簡單，一致性最強
- **缺點**: 
  - 每次統計更新都需要加鎖
  - 高並發下效能瓶頸
- **拒絕原因**: 不符合效能要求（100+ 並發）

#### Alternative 2: 全部使用 Atomic
- **缺點**: 
  - `time.Duration` 和 `time.Time` 不適合 atomic 操作
  - 複雜的結構需要 atomic.Value，效能反而更差
- **拒絕原因**: 技術上困難，且不必要

#### Alternative 3: 無統計功能
- **缺點**: 違反功能需求 FR-007
- **拒絕原因**: 統計是 P3 功能但仍需實作

### References
- [Go Atomic Package](https://pkg.go.dev/sync/atomic)
- [Atomic Operations Best Practices](https://go101.org/article/concurrent-atomic-operation.html)

---

## R6: 測試策略

### Decision
**使用實際時間測試搭配寬鬆斷言，加上 race detector 和 benchmark 測試**。

### Rationale

1. **不使用 Fake Clock**: 
   - `rate.Limiter` 使用系統時間，mock 困難
   - 實際時間測試更真實
   - 使用寬鬆的時間斷言（±50ms）

2. **測試分層**:
   - **Unit Tests**: 測試單一網域限流器
   - **Integration Tests**: 測試多網域並發場景
   - **Race Tests**: 使用 `-race` 檢測競態條件
   - **Benchmark Tests**: 測試效能指標

### Test Structure

```go
// 單元測試：基本限流功能
func TestDomainLimiter_BasicRateLimit(t *testing.T) {
    config := LimitConfig{RequestsPerSecond: 10, BurstCapacity: 1}
    dl := newDomainLimiter("test.com", config)
    
    ctx := context.Background()
    
    // 第一個請求應該立即成功（使用 burst）
    start := time.Now()
    err := dl.Wait(ctx)
    elapsed := time.Since(start)
    
    assert.NoError(t, err)
    assert.Less(t, elapsed, 10*time.Millisecond)
    
    // 第二個請求應該等待約 100ms（1/10 秒）
    start = time.Now()
    err = dl.Wait(ctx)
    elapsed = time.Since(start)
    
    assert.NoError(t, err)
    // 寬鬆斷言：90ms - 150ms 之間都可接受
    assert.Greater(t, elapsed, 90*time.Millisecond)
    assert.Less(t, elapsed, 150*time.Millisecond)
}

// 整合測試：多網域並發
func TestRateLimiter_ConcurrentMultipleDomains(t *testing.T) {
    limiter := New(map[string]LimitConfig{
        "fast.com":   {RequestsPerSecond: 10, BurstCapacity: 5},
        "medium.com": {RequestsPerSecond: 2, BurstCapacity: 2},
        "slow.com":   {RequestsPerSecond: 1, BurstCapacity: 1},
    }, defaultConfig)
    
    var wg sync.WaitGroup
    errors := make(chan error, 300)
    
    // 每個網域 100 個並發請求
    for _, domain := range []string{"fast.com", "medium.com", "slow.com"} {
        for i := 0; i < 100; i++ {
            wg.Add(1)
            go func(d string) {
                defer wg.Done()
                ctx := context.Background()
                if err := limiter.Wait(ctx, d); err != nil {
                    errors <- err
                }
            }(domain)
        }
    }
    
    wg.Wait()
    close(errors)
    
    // 驗證沒有錯誤
    assert.Empty(t, errors)
    
    // 驗證統計
    stats := limiter.GetAllStats()
    assert.Len(t, stats, 3)
    for domain, stat := range stats {
        assert.Equal(t, int64(100), stat.TotalRequests, "domain: %s", domain)
    }
}

// Race 測試
func TestRateLimiter_Race(t *testing.T) {
    // 使用 go test -race 執行
    limiter := New(nil, LimitConfig{RequestsPerSecond: 100, BurstCapacity: 10})
    
    var wg sync.WaitGroup
    for i := 0; i < 100; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            _ = limiter.Wait(context.Background(), "test.com")
            _ = limiter.GetStats("test.com")
        }()
    }
    wg.Wait()
}

// Benchmark 測試
func BenchmarkRateLimiter_Wait(b *testing.B) {
    limiter := New(nil, LimitConfig{RequestsPerSecond: 1000, BurstCapacity: 100})
    ctx := context.Background()
    
    b.ResetTimer()
    b.RunParallel(func(pb *testing.PB) {
        for pb.Next() {
            _ = limiter.Wait(ctx, "test.com")
        }
    })
}
```

### Test Coverage Goals

- **Unit Tests**: ≥80% coverage
- **Integration Tests**: 涵蓋所有 user scenarios
- **Edge Cases**: 所有 spec 中列出的 edge cases
- **Performance**: Benchmark 驗證效能目標

### CI/CD Integration

```makefile
# Makefile 測試命令
.PHONY: test
test:
	go test -v -race -coverprofile=coverage.out ./internal/ratelimit/...
	go tool cover -html=coverage.out -o coverage.html

.PHONY: test-integration
test-integration:
	go test -v -tags=integration ./tests/integration/...

.PHONY: bench
bench:
	go test -bench=. -benchmem ./internal/ratelimit/...
```

### Alternatives Considered

#### Alternative 1: Fake Clock / Time Mocking
- **優點**: 測試速度快，完全可控
- **缺點**: 
  - `rate.Limiter` 使用系統時間，無法 mock
  - 需要修改實作以支援可注入的時間源
  - 測試與實際行為可能不一致
- **拒絕原因**: 增加複雜度，收益不明顯

#### Alternative 2: 只測試介面，不測試時間
- **缺點**: 無法驗證限流是否真正生效
- **拒絕原因**: 時間是限流的核心，必須測試

### References
- [Testing in Go](https://go.dev/doc/tutorial/add-a-test)
- [Table Driven Tests](https://go.dev/wiki/TableDrivenTests)
- [Go Race Detector](https://go.dev/doc/articles/race_detector)

---

## Summary of Decisions

| Research Area | Decision | Key Rationale |
|--------------|----------|---------------|
| **R1: Token Bucket 實作** | 使用 `golang.org/x/time/rate.Limiter` | 官方維護、功能完整、並發安全 |
| **R2: 並發安全** | RWMutex (map) + Mutex (stats) | 分層鎖定、讀寫分離、效能最佳 |
| **R3: 配置格式** | JSON + 程式碼建構 | 與專案一致、標準函式庫支援 |
| **R4: Context 取消** | 使用 `Wait(ctx)` 內建支援 | 簡單、可靠、無需額外處理 |
| **R5: 統計收集** | Atomic (計數) + Mutex (時間) | 混合策略、效能最佳 |
| **R6: 測試策略** | 實際時間 + 寬鬆斷言 + Race | 真實、可靠、全面覆蓋 |

---

## Next Steps

✅ **Phase 0 Complete**: 所有技術決策已完成  
➡️ **Phase 1**: 生成 data-model.md, contracts/, quickstart.md  
➡️ **Constitution Re-check**: 驗證設計符合所有原則

---

**Approved By**: AI Agent (Copilot)  
**Date**: 2025-10-12  
**Status**: ✅ Ready for Phase 1
