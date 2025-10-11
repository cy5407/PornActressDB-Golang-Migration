# Tasks Breakdown: Web Scraper Rate Limiter

**Feature**: Web Scraper Rate Limiter  
**Branch**: `001-rate-limiter`  
**Date**: 2025-10-12  
**Status**: Ready for Implementation

---

## Task Overview

本文件將功能實作分解為可執行的任務序列，每個任務都有明確的輸入、輸出和驗證標準。任務組織按 User Story 優先級進行，並標註可並行執行的任務。

**總任務數**: 28 tasks  
**預估總工時**: 16-20 小時  
**MVP 範圍**: Phase 1-4 (Tasks T001-T018) - 實作 US1 和 US2 (P1)

---

## Phase 1: Setup 專案初始化

### T001: 建立 Go 模組和專案結構 [P]
**Prerequisites**: 無  
**User Story**: 基礎設施  
**Priority**: P0 (Blocking)

**Description**:
建立 Go 專案的基本結構，包括 go.mod 初始化和目錄結構建立。

**Acceptance Criteria**:
- [X] `go.mod` 存在且模組路徑為 `actress-classifier`
- [X] Go 版本宣告為 1.22 或更高
- [X] 建立目錄結構：
  - `internal/ratelimit/`
  - `tests/integration/`
  - `docs/ratelimit/examples/`
- [X] 執行 `go mod tidy` 無錯誤

**Output Files**:
- `go.mod`
- `go.sum` (初始為空)
- 目錄結構

**Validation**:
```bash
go version  # 確認 >= 1.22
go mod verify
tree internal/ratelimit
```

**Estimated Time**: 15 分鐘

---

### T002: 安裝核心相依套件 [P]
**Prerequisites**: T001  
**User Story**: 基礎設施  
**Priority**: P0 (Blocking)

**Description**:
安裝專案需要的外部相依套件，包括 rate limiter、testing 和 logging。

**Acceptance Criteria**:
- [X] `golang.org/x/time` 已安裝並記錄在 go.mod
- [X] `golang.org/x/sync` 已安裝
- [X] `go.uber.org/zap` 已安裝
- [X] `github.com/stretchr/testify` 已安裝（測試用）
- [X] 所有相依套件版本已鎖定在 go.sum

**Output Files**:
- 更新的 `go.mod`
- 更新的 `go.sum`

**Validation**:
```bash
go mod graph | grep -E "(golang.org/x/time|golang.org/x/sync|go.uber.org/zap)"
go list -m all
```

**Estimated Time**: 10 分鐘

---

### T003: 建立測試基礎設施 [P]
**Prerequisites**: T001, T002  
**User Story**: 基礎設施  
**Priority**: P0 (Blocking)

**Description**:
建立測試輔助函式和共用測試資料，為後續單元測試和整合測試打基礎。

**Acceptance Criteria**:
- [X] `internal/ratelimit/testing_utils_test.go` 包含：
  - `assertRequestTiming()` - 驗證請求時間間隔
  - `createTestLimiter()` - 建立測試用限流器
  - `waitForDuration()` - 精確等待計時
- [X] 測試檔案使用 `package ratelimit_test` (黑盒測試)
- [X] 執行 `go test ./internal/ratelimit -run=^$` 無錯誤（空測試）

**Output Files**:
- `internal/ratelimit/testing_utils_test.go`

**Validation**:
```bash
go test ./internal/ratelimit -v -run=^$
```

**Estimated Time**: 30 分鐘

---

## Phase 2: Foundational Components 基礎元件

_此 phase 無任務，因為 rate limiter 無阻塞性前置相依。_

---

## Phase 3: User Story 1 - 基本速率限制保護 (P1)

### T004: 實作 LimitConfig 結構和驗證
**Prerequisites**: T001  
**User Story**: US1 - 基本速率限制保護  
**Priority**: P1

**Description**:
實作限流配置結構（LimitConfig），包括參數驗證和預設值定義。

**Acceptance Criteria**:
- [X] `internal/ratelimit/config.go` 包含：
  - `LimitConfig` struct（RequestsPerSecond, BurstCapacity）
  - `Validate()` 方法驗證參數合法性（RPS > 0, Burst >= 1）
  - `DefaultConfig` 預設配置（1 req/s, burst 1）
  - `PresetConfigs` map（JAVDB: 1/s, AV-WIKI: 2/s, chiba-f: 1/s）
- [X] 單元測試涵蓋：
  - 合法配置驗證通過
  - 非法配置（RPS ≤ 0, Burst < 1）驗證失敗
  - 預設配置驗證通過

**Output Files**:
- `internal/ratelimit/config.go`
- `internal/ratelimit/config_test.go`

**Validation**:
```bash
go test ./internal/ratelimit -run=TestLimitConfig -v
go test ./internal/ratelimit -cover  # 期望此檔案 >90% coverage
```

**Estimated Time**: 45 分鐘

**Independent Test**:
```go
func TestLimitConfig_Validation(t *testing.T) {
    valid := LimitConfig{RequestsPerSecond: 1.0, BurstCapacity: 1}
    assert.NoError(t, valid.Validate())
    
    invalid := LimitConfig{RequestsPerSecond: 0, BurstCapacity: 1}
    assert.Error(t, invalid.Validate())
}
```

---

### T005: 實作 LimitStats 統計結構 [P]
**Prerequisites**: T001  
**User Story**: US1 - 基本速率限制保護（部分）, US4 - 限流統計（全部）  
**Priority**: P1

**Description**:
實作統計資訊結構（LimitStats），支援原子操作和執行緒安全更新。

**Acceptance Criteria**:
- [X] `internal/ratelimit/stats.go` 包含：
  - `LimitStats` struct（atomic counters + mutex for timestamps）
  - `IncrementTotal()` - 原子遞增總請求數
  - `RecordDelay(duration)` - 記錄延遲時間（需 mutex）
  - `Snapshot()` - 返回統計快照（StatsSnapshot struct）
  - 計算衍生指標：DelayRate, AvgWaitTime
- [X] StatsSnapshot 包含所有欄位（只讀）
- [X] 單元測試驗證並發安全性（使用 race detector）

**Output Files**:
- `internal/ratelimit/stats.go`
- `internal/ratelimit/stats_test.go`

**Validation**:
```bash
go test ./internal/ratelimit -run=TestLimitStats -race -v
go test ./internal/ratelimit -cover
```

**Estimated Time**: 1 小時

**Independent Test**:
```go
func TestLimitStats_Concurrency(t *testing.T) {
    stats := NewLimitStats()
    var wg sync.WaitGroup
    for i := 0; i < 100; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            stats.IncrementTotal()
            stats.RecordDelay(10 * time.Millisecond)
        }()
    }
    wg.Wait()
    snapshot := stats.Snapshot()
    assert.Equal(t, int64(100), snapshot.TotalRequests)
}
```

---

### T006: 實作 DomainLimiter 核心邏輯
**Prerequisites**: T004, T005  
**User Story**: US1 - 基本速率限制保護  
**Priority**: P1

**Description**:
實作單一網域的限流器（DomainLimiter），封裝 rate.Limiter 並整合統計功能。

**Acceptance Criteria**:
- [X] `internal/ratelimit/domain_limiter.go` 包含：
  - `DomainLimiter` struct（包含 rate.Limiter, config, stats）
  - `newDomainLimiter(domain, config)` 建構函式
  - `Wait(ctx)` 方法（呼叫 rate.Limiter.Wait，記錄統計）
  - `WaitN(ctx, n)` 方法（批次 token 獲取）
  - `Allow()` 方法（非阻塞檢查）
  - `Stats()` 方法（返回統計快照）
- [X] 正確計算等待時間並記錄到統計
- [X] Context 取消時立即返回錯誤

**Output Files**:
- `internal/ratelimit/domain_limiter.go`
- `internal/ratelimit/domain_limiter_test.go`

**Validation**:
```bash
go test ./internal/ratelimit -run=TestDomainLimiter -v
```

**Estimated Time**: 1.5 小時

**Independent Test**:
```go
func TestDomainLimiter_BasicRateControl(t *testing.T) {
    config := LimitConfig{RequestsPerSecond: 1, BurstCapacity: 1}
    limiter := newDomainLimiter("test.com", config)
    
    start := time.Now()
    limiter.Wait(context.Background())  // 第 1 個請求
    limiter.Wait(context.Background())  // 第 2 個請求（應延遲 ~1s）
    elapsed := time.Since(start)
    
    assert.InDelta(t, 1000, elapsed.Milliseconds(), 50)  // ±50ms
}
```

---

### T007: 實作 RateLimiter 主介面
**Prerequisites**: T006  
**User Story**: US1 - 基本速率限制保護  
**Priority**: P1

**Description**:
實作主限流器（RateLimiter），管理多個 DomainLimiter 實例。

**Acceptance Criteria**:
- [X] `internal/ratelimit/limiter.go` 包含：
  - `RateLimiter` struct（包含 map[string]*DomainLimiter, defaultConfig, RWMutex）
  - `New(configs, defaultConfig)` 建構函式
  - `Wait(ctx, domain)` 方法（取得或建立 DomainLimiter）
  - `WaitN(ctx, domain, n)` 方法
  - `Allow(domain)` 方法
  - 懶載入機制：首次存取網域時建立 DomainLimiter
- [X] 並發安全：使用 RWMutex 保護 map
- [X] 未配置網域使用 defaultConfig

**Output Files**:
- `internal/ratelimit/limiter.go`
- `internal/ratelimit/limiter_test.go`

**Validation**:
```bash
go test ./internal/ratelimit -run=TestRateLimiter -race -v
```

**Estimated Time**: 2 小時

**Independent Test**:
```go
func TestRateLimiter_SingleDomain(t *testing.T) {
    configs := map[string]LimitConfig{
        "javdb.com": {RequestsPerSecond: 1, BurstCapacity: 1},
    }
    limiter := New(configs, DefaultConfig)
    
    start := time.Now()
    limiter.Wait(context.Background(), "javdb.com")
    limiter.Wait(context.Background(), "javdb.com")
    limiter.Wait(context.Background(), "javdb.com")
    elapsed := time.Since(start)
    
    // 3 個請求 = 0s + 1s + 1s = ~2s
    assert.InDelta(t, 2000, elapsed.Milliseconds(), 100)
}
```

---

### T008: US1 整合測試 - 基本限流驗證
**Prerequisites**: T007  
**User Story**: US1 - 基本速率限制保護  
**Priority**: P1

**Description**:
建立整合測試，驗證 US1 的 Acceptance Scenarios。

**Acceptance Criteria**:
- [X] `tests/integration/ratelimit_test.go` 包含：
  - Scenario 1: 1 秒內 3 個請求到 JAVDB，驗證延遲時間
  - Scenario 2: 並行請求到 JAVDB 和 AV-WIKI，驗證獨立限流
- [X] 使用真實時間測試（不使用 fake clock）
- [X] 容忍 ±50ms 時間誤差
- [X] 所有測試通過

**Output Files**:
- `tests/integration/ratelimit_test.go`

**Validation**:
```bash
go test ./tests/integration -run=TestUS1 -v
```

**Estimated Time**: 1 小時

**Independent Test**: 直接執行整合測試驗證 US1 完整功能。

---

## Phase 4: User Story 2 - 網域獨立限流管理 (P1)

### T009: 實作配置檔案載入 (JSON)
**Prerequisites**: T004  
**User Story**: US2 - 網域獨立限流管理  
**Priority**: P1

**Description**:
實作從 JSON 配置檔案載入限流規則的功能。

**Acceptance Criteria**:
- [X] `internal/ratelimit/config.go` 新增：
  - `ConfigFile` struct（包含 Version, DefaultConfig, Domains map）
  - `LoadConfigFromFile(path)` 函式
  - `LoadConfigFromJSON(data)` 函式
  - JSON schema 驗證（version 必填，configs 合法）
- [X] 配置範例檔案：`docs/ratelimit/examples/config.json`
- [X] 單元測試涵蓋：
  - 合法 JSON 載入成功
  - 非法 JSON 返回錯誤（格式錯誤、缺少欄位、非法值）
  - 檔案不存在返回錯誤

**Output Files**:
- 更新 `internal/ratelimit/config.go`
- 更新 `internal/ratelimit/config_test.go`
- `docs/ratelimit/examples/config.json`

**Validation**:
```bash
go test ./internal/ratelimit -run=TestLoadConfig -v
```

**Estimated Time**: 1 小時

**Independent Test**:
```go
func TestLoadConfigFromFile_Valid(t *testing.T) {
    tmpfile := createTempConfigFile(t, `{
        "version": "1.0",
        "default_config": {"requests_per_second": 1, "burst_capacity": 1},
        "domains": {
            "javdb.com": {"requests_per_second": 1, "burst_capacity": 1}
        }
    }`)
    defer os.Remove(tmpfile)
    
    cfg, err := LoadConfigFromFile(tmpfile)
    assert.NoError(t, err)
    assert.Equal(t, "1.0", cfg.Version)
}
```

---

### T010: 新增 NewFromConfig 建構函式
**Prerequisites**: T007, T009  
**User Story**: US2 - 網域獨立限流管理  
**Priority**: P1

**Description**:
新增從配置檔案建立 RateLimiter 的便利建構函式。

**Acceptance Criteria**:
- [X] `internal/ratelimit/limiter.go` 新增：
  - `NewFromConfig(configPath)` 函式
  - 內部呼叫 `LoadConfigFromFile` 和 `New`
  - 錯誤處理：檔案讀取失敗、配置驗證失敗
- [X] 單元測試驗證：
  - 使用合法配置檔案建立成功
  - 使用非法配置檔案返回錯誤
  - 建立的限流器行為正確

**Output Files**:
- 更新 `internal/ratelimit/limiter.go`
- 更新 `internal/ratelimit/limiter_test.go`

**Validation**:
```bash
go test ./internal/ratelimit -run=TestNewFromConfig -v
```

**Estimated Time**: 30 分鐘

---

### T011: 實作預設配置回退機制
**Prerequisites**: T007  
**User Story**: US2 - 網域獨立限流管理  
**Priority**: P1

**Description**:
確保未配置的網域自動使用預設限流規則（1 req/s）。

**Acceptance Criteria**:
- [X] `RateLimiter.getOrCreateLimiter(domain)` 內部方法：
  - 檢查 domain 是否已配置
  - 若未配置，使用 `defaultConfig` 建立 DomainLimiter
  - 執行緒安全：使用 double-check locking 或 sync.Map
- [X] 單元測試驗證：
  - 請求未配置網域使用預設配置
  - 預設配置正確限流（1 req/s）
  - 並發請求到未配置網域不會建立重複 limiter

**Output Files**:
- 更新 `internal/ratelimit/limiter.go`
- 更新 `internal/ratelimit/limiter_test.go`

**Validation**:
```bash
go test ./internal/ratelimit -run=TestDefaultConfigFallback -race -v
```

**Estimated Time**: 45 分鐘

**Independent Test**:
```go
func TestRateLimiter_UnknownDomainUsesDefault(t *testing.T) {
    limiter := New(map[string]LimitConfig{}, DefaultConfig)
    
    start := time.Now()
    limiter.Wait(context.Background(), "unknown.com")
    limiter.Wait(context.Background(), "unknown.com")
    elapsed := time.Since(start)
    
    // 預設 1 req/s，應延遲 ~1s
    assert.InDelta(t, 1000, elapsed.Milliseconds(), 50)
}
```

---

### T012: US2 整合測試 - 多網域並行限流
**Prerequisites**: T010, T011  
**User Story**: US2 - 網域獨立限流管理  
**Priority**: P1

**Description**:
建立整合測試，驗證 US2 的 Acceptance Scenarios。

**Acceptance Criteria**:
- [X] `tests/integration/ratelimit_test.go` 新增：
  - Scenario 1: 三個網域不同配置，並行發送請求，驗證總時間
  - Scenario 2: 未配置網域使用預設規則
- [X] 使用 errgroup 並行執行請求
- [X] 驗證每個網域獨立計時
- [X] 所有測試通過

**Output Files**:
- 更新 `tests/integration/ratelimit_test.go`

**Validation**:
```bash
go test ./tests/integration -run=TestUS2 -v
```

**Estimated Time**: 1 小時

**Independent Test**: 直接執行整合測試驗證 US2 完整功能。

---

## Phase 5: User Story 3 - 爬蟲任務可控中斷 (P2)

### T013: 實作 Context 取消傳播
**Prerequisites**: T007  
**User Story**: US3 - 爬蟲任務可控中斷  
**Priority**: P2

**Description**:
確保 Context 取消信號正確傳播到所有等待中的請求。

**Acceptance Criteria**:
- [X] `DomainLimiter.Wait(ctx)` 正確處理 ctx.Done()
- [X] `rate.Limiter.Wait(ctx)` 的錯誤正確返回
- [X] 單元測試驗證：
  - Context 取消時立即返回 context.Canceled
  - Context 超時返回 context.DeadlineExceeded
  - 響應時間 <100ms

**Output Files**:
- 更新 `internal/ratelimit/domain_limiter_test.go`

**Validation**:
```bash
go test ./internal/ratelimit -run=TestContextCancellation -v
```

**Estimated Time**: 45 分鐘

**Independent Test**:
```go
func TestDomainLimiter_ContextCancellation(t *testing.T) {
    config := LimitConfig{RequestsPerSecond: 0.1, BurstCapacity: 1}  // 很慢
    limiter := newDomainLimiter("test.com", config)
    
    ctx, cancel := context.WithCancel(context.Background())
    
    var err error
    done := make(chan struct{})
    go func() {
        limiter.Wait(ctx)  // 第 1 個請求（立即）
        err = limiter.Wait(ctx)  // 第 2 個請求（需等待 10s）
        close(done)
    }()
    
    time.Sleep(100 * time.Millisecond)
    cancel()  // 取消 context
    
    <-done
    assert.ErrorIs(t, err, context.Canceled)
}
```

---

### T014: 實作 Close 方法和資源清理
**Prerequisites**: T007  
**User Story**: US3 - 爬蟲任務可控中斷  
**Priority**: P2

**Description**:
實作 RateLimiter.Close() 方法，確保資源正確釋放。

**Acceptance Criteria**:
- [X] `internal/ratelimit/limiter.go` 新增：
  - `Close()` 方法
  - 內部標記為 closed（使用 atomic bool 或 closed channel）
  - 後續 Wait/Allow 呼叫返回 ErrLimiterClosed
- [X] 單元測試驗證：
  - Close 後無法再使用
  - Close 是冪等的（重複呼叫無副作用）
  - 正在等待的請求正確完成或取消

**Output Files**:
- 更新 `internal/ratelimit/limiter.go`
- 更新 `internal/ratelimit/limiter_test.go`

**Validation**:
```bash
go test ./internal/ratelimit -run=TestClose -v
```

**Estimated Time**: 1 小時

**Independent Test**:
```go
func TestRateLimiter_CloseIdempotent(t *testing.T) {
    limiter := New(map[string]LimitConfig{}, DefaultConfig)
    
    err1 := limiter.Close()
    err2 := limiter.Close()
    
    assert.NoError(t, err1)
    assert.NoError(t, err2)
    
    err := limiter.Wait(context.Background(), "test.com")
    assert.ErrorIs(t, err, ErrLimiterClosed)
}
```

---

### T015: US3 整合測試 - 優雅停止
**Prerequisites**: T013, T014  
**User Story**: US3 - 爬蟲任務可控中斷  
**Priority**: P2

**Description**:
建立整合測試，驗證 US3 的 Acceptance Scenarios。

**Acceptance Criteria**:
- [X] `tests/integration/ratelimit_test.go` 新增：
  - Scenario 1: 排隊 50 個請求，中途取消，驗證停止行為
  - Scenario 2: Close 後重新建立限流器，驗證狀態重置
- [X] 使用 errgroup + context 模擬真實爬蟲場景
- [X] 所有測試通過

**Output Files**:
- 更新 `tests/integration/ratelimit_test.go`

**Validation**:
```bash
go test ./tests/integration -run=TestUS3 -v
```

**Estimated Time**: 1 小時

---

## Phase 6: User Story 4 - 限流統計和監控 (P3)

### T016: 實作 GetStats 方法
**Prerequisites**: T007, T005  
**User Story**: US4 - 限流統計和監控  
**Priority**: P3

**Description**:
實作統計資訊查詢介面。

**Acceptance Criteria**:
- [ ] `internal/ratelimit/limiter.go` 新增：
  - `GetStats(domain)` 方法（返回 StatsSnapshot 或錯誤）
  - `GetAllStats()` 方法（返回 map[string]*StatsSnapshot）
  - 網域不存在時返回 ErrDomainNotFound
- [ ] 單元測試驗證：
  - 查詢已存在網域返回正確統計
  - 查詢不存在網域返回錯誤
  - 並發查詢統計不會出現競態條件

**Output Files**:
- 更新 `internal/ratelimit/limiter.go`
- 更新 `internal/ratelimit/limiter_test.go`

**Validation**:
```bash
go test ./internal/ratelimit -run=TestGetStats -race -v
```

**Estimated Time**: 45 分鐘

**Independent Test**:
```go
func TestRateLimiter_GetStats(t *testing.T) {
    limiter := New(map[string]LimitConfig{
        "test.com": {RequestsPerSecond: 1, BurstCapacity: 1},
    }, DefaultConfig)
    
    limiter.Wait(context.Background(), "test.com")
    limiter.Wait(context.Background(), "test.com")
    
    stats, err := limiter.GetStats("test.com")
    assert.NoError(t, err)
    assert.Equal(t, int64(2), stats.TotalRequests)
    assert.Equal(t, int64(1), stats.DelayedRequests)
}
```

---

### T017: 增強統計資訊計算精度
**Prerequisites**: T005, T016  
**User Story**: US4 - 限流統計和監控  
**Priority**: P3

**Description**:
完善統計指標的計算邏輯，確保準確性。

**Acceptance Criteria**:
- [ ] `LimitStats` 正確計算：
  - DelayRate = DelayedRequests / TotalRequests
  - AvgWaitTime = TotalWaitTime / DelayedRequests
  - 處理邊界情況（除以零）
- [ ] `StatsSnapshot` 包含所有衍生指標
- [ ] 單元測試驗證計算準確性（100% 準確率）

**Output Files**:
- 更新 `internal/ratelimit/stats.go`
- 更新 `internal/ratelimit/stats_test.go`

**Validation**:
```bash
go test ./internal/ratelimit -run=TestStatsCalculation -v
```

**Estimated Time**: 30 分鐘

---

### T018: US4 整合測試 - 統計準確性驗證
**Prerequisites**: T016, T017  
**User Story**: US4 - 限流統計和監控  
**Priority**: P3

**Description**:
建立整合測試，驗證 US4 的 Acceptance Scenarios。

**Acceptance Criteria**:
- [ ] `tests/integration/ratelimit_test.go` 新增：
  - Scenario 1: 執行 50 個請求，驗證統計準確性
  - Scenario 2: 多網域統計獨立性
- [ ] 驗證統計資訊 100% 準確（請求數、延遲數、等待時間）
- [ ] 所有測試通過

**Output Files**:
- 更新 `tests/integration/ratelimit_test.go`

**Validation**:
```bash
go test ./tests/integration -run=TestUS4 -v
```

**Estimated Time**: 1 小時

---

## Phase 7: Polish & Integration 完善與整合

### T019: 實作錯誤類型定義 [P]
**Prerequisites**: T001  
**User Story**: 基礎設施  
**Priority**: P2

**Description**:
定義專案的錯誤類型常數，提供清晰的錯誤語義。

**Acceptance Criteria**:
- [ ] `internal/ratelimit/errors.go` 包含：
  - `ErrInvalidConfig` - 配置無效
  - `ErrInvalidDomain` - 網域名稱無效
  - `ErrLimiterClosed` - 限流器已關閉
  - `ErrDomainNotFound` - 網域不存在
- [ ] 所有錯誤使用繁體中文訊息
- [ ] 使用 `errors.New()` 定義錯誤常數

**Output Files**:
- `internal/ratelimit/errors.go`

**Validation**:
```bash
go build ./internal/ratelimit
```

**Estimated Time**: 20 分鐘

---

### T020: 新增結構化日誌記錄 [P]
**Prerequisites**: T007  
**User Story**: 基礎設施  
**Priority**: P2

**Description**:
整合 zap logger，記錄關鍵事件（網域建立、統計更新、錯誤）。

**Acceptance Criteria**:
- [ ] `internal/ratelimit/limiter.go` 新增：
  - 初始化 zap.Logger（development mode）
  - 記錄事件：
    - 建立新網域限流器（Info）
    - 請求被延遲（Debug）
    - 錯誤發生（Error）
- [ ] 所有日誌訊息使用繁體中文
- [ ] 日誌包含結構化欄位（domain, config, duration 等）

**Output Files**:
- 更新 `internal/ratelimit/limiter.go`

**Validation**:
```bash
go test ./internal/ratelimit -v  # 檢查日誌輸出
```

**Estimated Time**: 45 分鐘

---

### T021: 撰寫 API 參考文件 [P]
**Prerequisites**: T007, T016  
**User Story**: 文件  
**Priority**: P2

**Description**:
撰寫完整的 API 參考文件，包含所有公開介面和範例。

**Acceptance Criteria**:
- [ ] `docs/ratelimit/README.md` 包含：
  - 安裝指南
  - 快速開始（3 分鐘範例）
  - API 參考（所有方法）
  - 配置參數說明
  - 常見問題 Q&A
- [ ] 所有文件使用繁體中文
- [ ] 程式碼範例可直接執行

**Output Files**:
- `docs/ratelimit/README.md`

**Validation**:
手動檢閱文件完整性

**Estimated Time**: 2 小時

---

### T022: 建立使用範例集合 [P]
**Prerequisites**: T007, T010, T016  
**User Story**: 文件  
**Priority**: P3

**Description**:
建立多個實際使用範例，展示不同場景的用法。

**Acceptance Criteria**:
- [ ] `docs/ratelimit/examples/` 包含：
  - `basic.go` - 基本使用
  - `config_file.go` - 從配置檔案載入
  - `context_control.go` - Context 取消控制
  - `statistics.go` - 統計資訊查詢
  - `crawler.go` - 完整爬蟲範例（~100 行）
- [ ] 所有範例可獨立執行（`go run example.go`）
- [ ] 範例註解使用繁體中文

**Output Files**:
- `docs/ratelimit/examples/basic.go`
- `docs/ratelimit/examples/config_file.go`
- `docs/ratelimit/examples/context_control.go`
- `docs/ratelimit/examples/statistics.go`
- `docs/ratelimit/examples/crawler.go`

**Validation**:
```bash
cd docs/ratelimit/examples
go run basic.go
go run config_file.go
# ... 其他範例
```

**Estimated Time**: 2 小時

---

### T023: 新增效能基準測試 [P]
**Prerequisites**: T007  
**User Story**: 測試  
**Priority**: P2

**Description**:
建立效能基準測試，驗證記憶體和效能指標。

**Acceptance Criteria**:
- [ ] `internal/ratelimit/limiter_bench_test.go` 包含：
  - `BenchmarkWait_SingleDomain` - 單一網域效能
  - `BenchmarkWait_MultipleDomains` - 多網域效能
  - `BenchmarkAllow` - Allow 方法效能
  - `BenchmarkGetStats` - 統計查詢效能
- [ ] 記憶體基準測試（100 網域 <10MB）
- [ ] 執行 `go test -bench=. -benchmem`

**Output Files**:
- `internal/ratelimit/limiter_bench_test.go`

**Validation**:
```bash
go test ./internal/ratelimit -bench=. -benchmem
```

**Estimated Time**: 1.5 小時

---

### T024: 執行 Race Detector 完整掃描
**Prerequisites**: T007, T013, T014, T016  
**User Story**: 測試  
**Priority**: P1

**Description**:
使用 Go Race Detector 掃描所有並發程式碼，確保無競態條件。

**Acceptance Criteria**:
- [ ] 執行 `go test ./... -race` 無錯誤
- [ ] 執行整合測試 `go test ./tests/integration -race` 無錯誤
- [ ] 至少測試 1000 次並發操作

**Output Files**:
無（驗證測試）

**Validation**:
```bash
go test ./internal/ratelimit -race -count=10
go test ./tests/integration -race -count=10
```

**Estimated Time**: 30 分鐘

---

### T025: 測試覆蓋率驗證（≥70%）
**Prerequisites**: T004-T018  
**User Story**: 測試  
**Priority**: P1

**Description**:
驗證測試覆蓋率達到專案要求（≥70%），補充缺失測試。

**Acceptance Criteria**:
- [ ] 執行 `go test ./internal/ratelimit -cover`
- [ ] 總覆蓋率 ≥70%
- [ ] 核心模組（limiter.go, domain_limiter.go）覆蓋率 ≥80%
- [ ] 生成覆蓋率報告 `coverage.html`

**Output Files**:
- `coverage.out`
- `coverage.html`

**Validation**:
```bash
go test ./internal/ratelimit -coverprofile=coverage.out
go tool cover -html=coverage.out -o coverage.html
go tool cover -func=coverage.out | grep total
```

**Estimated Time**: 1 小時（可能需要補充測試）

---

### T026: 執行 golangci-lint 靜態分析
**Prerequisites**: All implementation tasks (T004-T018)  
**User Story**: 程式碼品質  
**Priority**: P1

**Description**:
使用 golangci-lint 執行靜態分析，確保程式碼品質符合 Constitution 標準。

**Acceptance Criteria**:
- [ ] 安裝並配置 golangci-lint
- [ ] 建立 `.golangci.yml` 配置檔案：
  - 啟用 gocognit（complexity ≤15）
  - 啟用 gofmt、goimports
  - 啟用 errcheck、govet、staticcheck
- [ ] 執行 `golangci-lint run ./...` 無錯誤
- [ ] 修復所有 warnings

**Output Files**:
- `.golangci.yml`
- 更新程式碼（如有需要）

**Validation**:
```bash
golangci-lint run ./internal/ratelimit
```

**Estimated Time**: 1 小時

---

### T027: 建立 Makefile 自動化指令 [P]
**Prerequisites**: T001, T023, T024, T025, T026  
**User Story**: 基礎設施  
**Priority**: P2

**Description**:
建立 Makefile 提供常用開發指令。

**Acceptance Criteria**:
- [ ] `Makefile` 包含 targets：
  - `make test` - 執行所有測試
  - `make test-race` - Race detector 測試
  - `make test-cover` - 覆蓋率測試
  - `make bench` - 效能基準測試
  - `make lint` - 靜態分析
  - `make fmt` - 格式化程式碼
  - `make clean` - 清理產物
- [ ] 所有 target 正常執行

**Output Files**:
- `Makefile`

**Validation**:
```bash
make test
make lint
make bench
```

**Estimated Time**: 30 分鐘

---

### T028: 最終整合驗證和 MVP 發布
**Prerequisites**: T001-T027  
**User Story**: 整合驗證  
**Priority**: P0

**Description**:
執行完整的整合驗證，確保所有功能正常運作，準備發布 MVP。

**Acceptance Criteria**:
- [ ] 所有單元測試通過（`make test`）
- [ ] 所有整合測試通過（US1-US4）
- [ ] Race detector 無錯誤（`make test-race`）
- [ ] 測試覆蓋率 ≥70%（`make test-cover`）
- [ ] 靜態分析無錯誤（`make lint`）
- [ ] 效能基準達標（`make bench`）
- [ ] 文件完整且範例可執行
- [ ] Success Criteria SC-001 到 SC-008 全部驗證通過

**Output Files**:
- 驗證報告（手動記錄）

**Validation**:
```bash
make test
make test-race
make test-cover
make lint
make bench
cd docs/ratelimit/examples && go run crawler.go
```

**Estimated Time**: 1 小時

---

## Parallelization Opportunities

以下任務可並行執行（標記 [P]）：

### Phase 1: Setup
- T001, T002, T003 - 可依序執行（快速）

### Phase 3: US1
- T005 (LimitStats) 可與 T004 (LimitConfig) 並行

### Phase 7: Polish
- T019 (Errors), T020 (Logging), T021 (Docs), T022 (Examples), T023 (Benchmarks) 完全獨立，可同時進行

**建議並行策略**:
- 核心實作（T004-T018）按順序執行（相依性強）
- Polish 階段（T019-T027）盡可能並行（相依性弱）

---

## MVP Definition (Minimum Viable Product)

**MVP 範圍**: Phase 1-4 (Tasks T001-T012)

**包含功能**:
- ✅ US1: 基本速率限制保護
- ✅ US2: 網域獨立限流管理
- ❌ US3: 爬蟲任務可控中斷（延後）
- ❌ US4: 限流統計和監控（延後）

**MVP 驗證標準**:
1. 單一網域限流精確度 ±50ms (SC-001)
2. 支援 ≥10 網域並發限流 (SC-002)
3. 100 並發請求無競態條件 (SC-003)
4. 記憶體佔用 <10MB for 100 domains (SC-004)
5. 初始化時間 <100ms (SC-005)

**MVP 交付物**:
- 完整程式碼（`internal/ratelimit/`）
- 單元測試（覆蓋率 ≥60%）
- 整合測試（US1 + US2）
- 基本文件（API 參考）

---

## Task Dependencies Visualization

```
Phase 1: Setup
T001 → T002 → T003

Phase 3: US1
T001 → T004 → T006 → T007 → T008
       T004 → T005 ↗

Phase 4: US2
T004 → T009 → T010 → T012
T007 → T011 → T012
T010 + T011 → T012

Phase 5: US3
T007 → T013 → T015
T007 → T014 → T015

Phase 6: US4
T005 + T007 → T016 → T018
T005 + T016 → T017 → T018

Phase 7: Polish
[T019, T020, T021, T022, T023] (並行) → T024 → T025 → T026 → T027 → T028
```

---

## Risk Mitigation

### 高風險任務
1. **T006 (DomainLimiter)**: 核心演算法實作
   - 緩解：先寫測試，參考 golang.org/x/time/rate 範例
   
2. **T007 (RateLimiter)**: 並發安全設計
   - 緩解：使用 race detector，參考 sync.Map 或 double-check locking 模式
   
3. **T024 (Race Detector)**: 可能發現未預期的競態條件
   - 緩解：在每個任務完成時立即執行 race detector，及早發現問題

### 時間風險
- 若時間有限，優先完成 MVP（T001-T012）
- US3 和 US4 可在後續迭代中補充

---

## Success Metrics Mapping

| Task | Success Criteria | Validation Method |
|------|------------------|-------------------|
| T006 | SC-001 (±50ms 精度) | 整合測試 + time.Since() |
| T007 | SC-002 (≥10 網域), SC-003 (100 並發) | 整合測試 + race detector |
| T023 | SC-004 (<10MB), SC-005 (<100ms init) | 效能基準測試 |
| T013 | SC-006 (<100ms 取消響應) | 單元測試 + context.WithTimeout |
| T017 | SC-007 (100% 統計準確率) | 整合測試 + 精確驗證 |
| T012 | SC-008 (1000 請求誤差 ±5%) | 整合測試 + 長時間執行 |

---

## 總結

**總任務數**: 28 tasks  
**核心任務** (P1): 18 tasks  
**支援任務** (P2): 8 tasks  
**可選任務** (P3): 2 tasks  
**預估總工時**: 16-20 小時  
**MVP 工時**: 8-10 小時（T001-T012）

**下一步**:
1. 建立 Git branch: `git checkout -b 001-rate-limiter`
2. 開始執行 Phase 1: Setup (T001-T003)
3. 每完成一個任務，立即執行測試和 race detector
4. 定期 commit，遵循 Conventional Commits 格式
5. MVP 完成後進行完整驗證，再繼續 Phase 5-7

**建議工作流程**:
- Day 1-2: Phase 1-4 (MVP 核心功能)
- Day 3: Phase 5 (US3)
- Day 4: Phase 6 (US4) + Phase 7 (前半)
- Day 5: Phase 7 (後半) + 最終驗證
