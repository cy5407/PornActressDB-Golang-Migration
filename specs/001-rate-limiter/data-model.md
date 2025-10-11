# Data Model: Web Scraper Rate Limiter

**Feature**: Web Scraper Rate Limiter  
**Date**: 2025-10-12  
**Phase**: Phase 1 - Design  
**Status**: Completed

## Overview

本文件定義速率限制器的資料模型，包括所有實體（entities）、它們的屬性、關係和行為。資料模型設計遵循 Clean Architecture 原則，確保高內聚低耦合。

---

## Entity Relationships

```
┌─────────────────┐
│   RateLimiter   │  (1)
└────────┬────────┘
         │ manages
         │ 1:N
         ▼
┌─────────────────┐
│ DomainLimiter   │  (N)
└────────┬────────┘
         │ contains
         │ 1:1
         ▼
┌─────────────────┐         ┌─────────────────┐
│  LimitConfig    │         │   LimitStats    │
└─────────────────┘         └─────────────────┘
```

---

## Entity 1: RateLimiter (主限流器)

### 職責
- 管理所有網域的限流器實例
- 提供統一的限流 API 介面
- 處理網域限流器的建立和生命週期

### 屬性

| 屬性名稱 | 類型 | 說明 | 可見性 |
|---------|------|------|--------|
| `limiters` | `map[string]*DomainLimiter` | 網域名稱到限流器的對映 | private |
| `defaultConfig` | `LimitConfig` | 未配置網域的預設限流配置 | private |
| `mu` | `sync.RWMutex` | 保護 limiters map 的讀寫鎖 | private |

### 不變條件 (Invariants)
- `limiters` 永不為 nil
- `defaultConfig` 必須通過驗證（`RequestsPerSecond > 0`）
- 對 `limiters` 的所有存取必須在鎖保護下進行

### 關鍵行為

#### 1. Wait(ctx Context, domain string) error
**語義**: 等待獲取指定網域的請求許可

**前置條件**:
- `ctx` 不為 nil
- `domain` 不為空字串

**後置條件**:
- 成功：token 已消耗，可以發送請求
- 失敗：返回錯誤（context 取消或超時）

**副作用**:
- 如果網域首次出現，建立新的 `DomainLimiter`
- 更新該網域的統計資訊

**並發安全**: 是（使用 RWMutex）

---

#### 2. Allow(domain string) bool
**語義**: 非阻塞地檢查是否可以立即發送請求

**前置條件**:
- `domain` 不為空字串

**後置條件**:
- 返回 true：可以立即發送請求，token 已消耗
- 返回 false：當前無可用 token，請稍後重試

**副作用**:
- 如果返回 true，消耗一個 token 並更新統計
- 如果網域首次出現，建立新的 `DomainLimiter`

**並發安全**: 是

---

#### 3. GetStats(domain string) (*LimitStats, error)
**語義**: 獲取指定網域的統計資訊快照

**前置條件**:
- `domain` 不為空字串

**後置條件**:
- 成功：返回統計資訊副本
- 失敗：網域不存在，返回錯誤

**副作用**: 無（只讀操作）

**並發安全**: 是（返回副本，不持有鎖）

---

#### 4. GetAllStats() map[string]*LimitStats
**語義**: 獲取所有網域的統計資訊

**前置條件**: 無

**後置條件**: 返回所有網域的統計資訊對映（副本）

**副作用**: 無

**並發安全**: 是（需要遍歷 map，使用讀鎖）

---

## Entity 2: DomainLimiter (網域限流器)

### 職責
- 執行單一網域的 token bucket 演算法
- 維護該網域的限流狀態和統計資訊
- 處理 context 取消和超時

### 屬性

| 屬性名稱 | 類型 | 說明 | 可見性 |
|---------|------|------|--------|
| `domain` | `string` | 網域名稱 | private |
| `limiter` | `*rate.Limiter` | Token bucket 實作 | private |
| `config` | `LimitConfig` | 限流配置 | private |
| `stats` | `*LimitStats` | 統計資訊 | private |

### 不變條件
- `domain` 永不為空
- `limiter` 永不為 nil
- `config` 必須通過驗證
- `stats` 永不為 nil

### 生命週期

```
┌─────────┐   newDomainLimiter()   ┌─────────┐
│ Created │ ────────────────────►  │  Active │
└─────────┘                        └────┬────┘
                                        │
                                        │ Wait() / Allow()
                                        │ (可重複呼叫)
                                        │
                                        ▼
                                   ┌─────────┐
                                   │ Closed  │
                                   └─────────┘
                                   (無明確 Close，由 GC 回收)
```

### 關鍵行為

#### 1. Wait(ctx Context) error
**語義**: 等待獲取 token

**實作細節**:
```go
func (dl *DomainLimiter) Wait(ctx context.Context) error {
    start := time.Now()
    
    // 呼叫 rate.Limiter.Wait（內建 context 支援）
    err := dl.limiter.Wait(ctx)
    
    waitTime := time.Since(start)
    
    if err != nil {
        // Context 取消或超時
        dl.updateStatsCanceled(waitTime)
        return err
    }
    
    // 成功獲取 token
    delayed := waitTime > 10*time.Millisecond
    dl.updateStatsSuccess(waitTime, delayed)
    
    return nil
}
```

**時間語義**:
- 如果有可用 token：立即返回（< 1ms）
- 如果無可用 token：等待直到下一個 token 恢復
- 如果 context 取消：立即返回錯誤（< 1ms）

---

#### 2. Allow() bool
**語義**: 非阻塞檢查

**實作細節**:
```go
func (dl *DomainLimiter) Allow() bool {
    allowed := dl.limiter.Allow()
    
    if allowed {
        dl.updateStatsSuccess(0, false) // 未延遲
    }
    
    return allowed
}
```

---

#### 3. updateStatsSuccess(waitTime Duration, delayed bool)
**語義**: 更新成功請求的統計

**並發安全**: 是（使用 atomic 和 mutex）

---

#### 4. GetStats() LimitStats
**語義**: 獲取統計快照

**並發安全**: 是（返回副本）

---

## Entity 3: LimitConfig (限流配置)

### 職責
- 定義單一網域的限流參數
- 提供配置驗證邏輯

### 屬性

| 屬性名稱 | 類型 | 說明 | 驗證規則 |
|---------|------|------|---------|
| `RequestsPerSecond` | `float64` | 每秒允許的請求數 | 必須 > 0 |
| `BurstCapacity` | `int` | Burst 容量（可累積的 token 數） | 必須 ≥ 1 |

### 範例配置

```go
// 保守配置（JAVDB）
LimitConfig{
    RequestsPerSecond: 1.0,
    BurstCapacity:     1,
}

// 寬鬆配置（AV-WIKI）
LimitConfig{
    RequestsPerSecond: 2.0,
    BurstCapacity:     3,  // 允許短時間爆發 3 個請求
}
```

### 關鍵行為

#### Validate() error
**語義**: 驗證配置有效性

```go
func (c LimitConfig) Validate() error {
    if c.RequestsPerSecond <= 0 {
        return fmt.Errorf("RequestsPerSecond 必須大於 0，當前值: %.2f", c.RequestsPerSecond)
    }
    if c.BurstCapacity < 1 {
        return fmt.Errorf("BurstCapacity 必須至少為 1，當前值: %d", c.BurstCapacity)
    }
    return nil
}
```

### 配置範例（JSON）

```json
{
  "requests_per_second": 1.0,
  "burst_capacity": 1
}
```

---

## Entity 4: LimitStats (統計資訊)

### 職責
- 記錄網域的請求統計資訊
- 提供統計查詢和計算

### 屬性

| 屬性名稱 | 類型 | 說明 | 更新方式 |
|---------|------|------|---------|
| `TotalRequests` | `int64` | 總請求數 | Atomic increment |
| `DelayedRequests` | `int64` | 被延遲的請求數 | Atomic increment |
| `TotalWaitTime` | `time.Duration` | 總等待時間 | Mutex 保護 |
| `LastRequestTime` | `time.Time` | 最後請求時間 | Mutex 保護 |

### 衍生欄位（計算得出）

| 欄位名稱 | 計算方式 | 說明 |
|---------|---------|------|
| `AverageWaitTime` | `TotalWaitTime / DelayedRequests` | 平均等待時間 |
| `DelayRate` | `DelayedRequests / TotalRequests` | 延遲比例 |

### 內部結構（實作細節）

```go
type LimitStats struct {
    // Atomic 欄位（高頻更新）
    totalRequests   atomic.Int64
    delayedRequests atomic.Int64
    
    // Mutex 保護欄位（低頻更新）
    mu              sync.Mutex
    totalWaitTime   time.Duration
    lastRequestTime time.Time
}
```

### 關鍵行為

#### 1. Snapshot() StatsSnapshot
**語義**: 獲取統計資訊的一致性快照

```go
type StatsSnapshot struct {
    TotalRequests    int64
    DelayedRequests  int64
    TotalWaitTime    time.Duration
    AverageWaitTime  time.Duration
    LastRequestTime  time.Time
    DelayRate        float64
}

func (s *LimitStats) Snapshot() StatsSnapshot {
    total := s.totalRequests.Load()
    delayed := s.delayedRequests.Load()
    
    s.mu.Lock()
    waitTime := s.totalWaitTime
    lastTime := s.lastRequestTime
    s.mu.Unlock()
    
    var avgWait time.Duration
    if delayed > 0 {
        avgWait = waitTime / time.Duration(delayed)
    }
    
    var delayRate float64
    if total > 0 {
        delayRate = float64(delayed) / float64(total)
    }
    
    return StatsSnapshot{
        TotalRequests:    total,
        DelayedRequests:  delayed,
        TotalWaitTime:    waitTime,
        AverageWaitTime:  avgWait,
        LastRequestTime:  lastTime,
        DelayRate:        delayRate,
    }
}
```

#### 2. Reset()
**語義**: 重置統計資訊

```go
func (s *LimitStats) Reset() {
    s.totalRequests.Store(0)
    s.delayedRequests.Store(0)
    
    s.mu.Lock()
    s.totalWaitTime = 0
    s.lastRequestTime = time.Time{}
    s.mu.Unlock()
}
```

---

## Data Flow

### 1. Wait 操作流程

```
使用者程式碼
    │
    ▼
RateLimiter.Wait(ctx, domain)
    │
    ├─ [讀鎖] 查找 DomainLimiter
    │   └─ 未找到？[寫鎖] 建立新 DomainLimiter
    │
    ▼
DomainLimiter.Wait(ctx)
    │
    ├─ rate.Limiter.Wait(ctx)  ← Token Bucket 演算法
    │   │
    │   ├─ 有 token？立即返回
    │   └─ 無 token？等待或 context 取消
    │
    ▼
更新 LimitStats
    ├─ Atomic: totalRequests++
    ├─ Atomic: delayedRequests++ (如果延遲)
    └─ Mutex: totalWaitTime += waitTime
```

### 2. 統計查詢流程

```
使用者程式碼
    │
    ▼
RateLimiter.GetStats(domain)
    │
    ├─ [讀鎖] 查找 DomainLimiter
    │
    ▼
DomainLimiter.GetStats()
    │
    ├─ Atomic: Load totalRequests
    ├─ Atomic: Load delayedRequests
    └─ Mutex: 讀取 totalWaitTime, lastRequestTime
    │
    ▼
計算衍生欄位
    ├─ AverageWaitTime
    └─ DelayRate
    │
    ▼
返回 StatsSnapshot（副本）
```

---

## Memory Layout

### 單個 DomainLimiter 的記憶體佔用估算

```
DomainLimiter:
├─ domain (string):           ~24 bytes (header) + len(domain)
├─ limiter (*rate.Limiter):   ~8 bytes (pointer) + ~64 bytes (結構)
├─ config (LimitConfig):      ~16 bytes
└─ stats (*LimitStats):       ~8 bytes (pointer) + ~80 bytes (結構)
                              ────────────────────────────────
                              Total: ~200 bytes per domain

100 個網域: ~20 KB
1000 個網域: ~200 KB
```

✅ **符合需求**: < 10MB (100 domains)

---

## Validation Rules

### LimitConfig 驗證
- ✅ `RequestsPerSecond > 0`
- ✅ `BurstCapacity >= 1`
- ✅ `BurstCapacity` 應 ≤ `RequestsPerSecond * 60` (合理範圍)

### RateLimiter 驗證
- ✅ `defaultConfig` 必須通過 `Validate()`
- ✅ 所有 `domains` 配置必須通過 `Validate()`

### Domain 名稱驗證
- ✅ 不為空字串
- ✅ 建議：使用小寫，無協定前綴（如 "javdb.com" 而非 "https://javdb.com"）

---

## State Transitions

### DomainLimiter Token State

```
狀態: [可用 Token 數]

初始: [BurstCapacity]
    │
    ▼
[BurstCapacity - N] ← Allow/Wait 消耗 token
    │
    │ (時間流逝，token 恢復)
    │ 恢復速率: RequestsPerSecond
    │
    ▼
[0] ← 無可用 token
    │
    │ Allow() → false
    │ Wait() → 阻塞
    │
    ▼
[1+] ← Token 恢復
    │
    │ Allow() → true
    │ Wait() → 立即返回
    │
    └─ 循環
```

---

## Concurrency Model

### 鎖層次結構

```
Level 1: RateLimiter.mu (RWMutex)
    │
    └─ 保護 limiters map
        │
        ▼
Level 2: rate.Limiter (內部 mutex)
    │
    └─ 保護 token bucket 狀態
        │
        ▼
Level 3: LimitStats.mu (Mutex)
    │
    └─ 保護時間相關統計
```

**死鎖預防**: 鎖定順序從外到內，永不反向

---

## JSON Serialization

### ConfigFile 結構

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
    }
  }
}
```

### StatsSnapshot JSON

```json
{
  "domain": "javdb.com",
  "total_requests": 100,
  "delayed_requests": 30,
  "total_wait_time_ms": 3000,
  "average_wait_time_ms": 100,
  "last_request_time": "2025-10-12T10:30:45Z",
  "delay_rate": 0.30
}
```

---

## Summary

| Entity | 職責 | 關鍵屬性 | 並發模型 |
|--------|------|---------|---------|
| **RateLimiter** | 管理所有網域限流器 | limiters (map), defaultConfig | RWMutex |
| **DomainLimiter** | 執行限流邏輯 | limiter, config, stats | Mutex + Atomic |
| **LimitConfig** | 定義限流參數 | RequestsPerSecond, BurstCapacity | Immutable |
| **LimitStats** | 記錄統計資訊 | totalRequests, delayedRequests | Atomic + Mutex |

---

**Approved By**: AI Agent (Copilot)  
**Date**: 2025-10-12  
**Status**: ✅ Ready for Contract Generation
