# Implementation Plan: Web Scraper Rate Limiter

**Branch**: `001-rate-limiter` | **Date**: 2025-10-12 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/001-rate-limiter/spec.md`

## Summary

本功能實作一個網域獨立的爬蟲速率限制器，使用 token bucket 演算法控制每個資料來源（JAVDB、AV-WIKI、chiba-f）的請求頻率，確保遵守各網站的爬取限制並避免被封鎖。速率限制器必須支援並發安全、基於 context 的取消機制，並提供詳細的請求統計資訊。

**核心價值**: 保護爬蟲系統免於被目標網站封鎖，同時最大化爬取效率。

**技術方法**: 使用 Go 的 goroutines 和 channels 實作並發安全的 token bucket 演算法，每個網域維護獨立的限流器實例。

## Technical Context

**Language/Version**: Go 1.22+ (Go 1.23 preferred)  
**Primary Dependencies**: 
- `golang.org/x/time/rate` - Token bucket 演算法標準實作
- `golang.org/x/sync/errgroup` - 並發錯誤處理和協調
- `go.uber.org/zap` - 結構化日誌

**Storage**: 記憶體中的網域限流器對映表（無持久化需求）  
**Testing**: Go 標準 testing 套件 + `github.com/stretchr/testify`  
**Target Platform**: 跨平台（Windows/Linux/macOS），作為函式庫提供  
**Project Type**: Single library project（純後端函式庫，無 GUI）  
**Performance Goals**: 
- 支援 ≥10 網域並發限流
- 頻率控制精確度 ±50ms
- 記憶體佔用 <10MB（管理 100 個網域）

**Constraints**: 
- 並發安全：支援 100+ 並發 goroutines 無競態條件
- Context 取消響應時間 <100ms
- 初始化時間 <100ms

**Scale/Scope**: 
- 管理 10-100 個網域
- 每個網域處理 100-1000 requests/hour
- 單一程序內運作（非分散式）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### ✅ Compliance Status

#### II. Progressive Migration Strategy
- ✅ **Phase 1 - Backend Core**: Rate limiter 是第一個重構的後端核心模組
- ✅ **獨立性**: 不依賴其他模組，可獨立開發測試
- ✅ **測試要求**: 將達到 ≥70% unit test coverage

#### III. Code Quality Standards
- ✅ **Go 1.22+**: 使用 Go 1.22 或更新版本
- ✅ **Effective Go**: 遵循 Go 官方編碼規範
- ✅ **Clean Code**: 函式簡短、命名清楚
- ✅ **Cognitive Complexity**: 將使用 golangci-lint + gocognit 檢查（≤15）
- ✅ **Error Handling**: 使用 context wrapping，不濫用 panic
- ✅ **Structured Logging**: 使用 zap，繁體中文日誌訊息
- ✅ **Concurrency**: 充分利用 goroutines 和 channels

#### V. Concurrency and Performance
- ✅ **Goroutines**: 使用 goroutines 實作並發限流
- ✅ **Concurrency Control**: 使用 buffered channel 和 mutex 保護共享狀態
- ✅ **Error Group**: 使用 errgroup 協調並發任務
- ✅ **Context Cancellation**: 支援 graceful shutdown
- ✅ **Performance Targets**: 符合記憶體 ≤200MB（實際 <10MB）、啟動 <1s（實際 <100ms）

#### VIII. Dependency Management
- ✅ **Standard Library First**: 優先使用 stdlib，外部相依最小化
- ✅ **Active Maintenance**: 所有相依套件來自 golang.org（官方維護）
- ✅ **No cgo**: 純 Go 實作，無 cgo 相依

### 🚫 No Violations

無需填寫 Complexity Tracking 表格。

## Project Structure

### Documentation (this feature)

```
specs/001-rate-limiter/
├── spec.md              # 功能規格（已完成）
├── plan.md              # 本實作計畫
├── research.md          # Phase 0 研究文件（待生成）
├── data-model.md        # Phase 1 資料模型（待生成）
├── quickstart.md        # Phase 1 快速開始（待生成）
├── contracts/           # Phase 1 API 合約（待生成）
│   └── ratelimiter.go   # Go interface 定義
└── checklists/
    └── requirements.md  # 需求品質檢查表（已完成）
```

### Source Code (repository root)

```
女優分類-go/
├── cmd/
│   └── (CLI tools - Phase 2, not for this feature)
├── internal/
│   └── ratelimit/              # 本功能實作目錄
│       ├── limiter.go          # 主要限流器實作
│       ├── domain_limiter.go   # 單一網域限流器
│       ├── config.go           # 限流配置
│       ├── stats.go            # 統計資訊
│       └── limiter_test.go     # 單元測試
├── pkg/
│   └── (shared utilities - future)
├── tests/
│   └── integration/
│       └── ratelimit_test.go   # 整合測試
├── docs/
│   └── ratelimit/              # 使用文件
│       ├── README.md
│       └── examples/
├── go.mod
├── go.sum
└── Makefile
```

**Structure Decision**: 選擇 Option 1 (Single project)，因為：
1. Rate limiter 是獨立的後端函式庫，無前端元件
2. 將放置於 `internal/ratelimit/` 以示僅供專案內部使用
3. 遵循標準 Go 專案布局（Go Standard Project Layout）

## Phase 0: Research & Technical Decisions

### 研究任務清單

以下研究任務需在 Phase 0 完成，結果記錄於 `research.md`：

#### R1: Token Bucket 演算法實作選擇
**Question**: 使用 `golang.org/x/time/rate` 還是自行實作 token bucket？

**Research Points**:
- `golang.org/x/time/rate.Limiter` 的功能完整性
- 是否支援 burst capacity 配置
- 並發安全性保證
- 效能基準測試結果
- 社群使用案例

**Expected Outcome**: 選定實作方案並說明理由

---

#### R2: 並發安全策略
**Question**: 如何確保多 goroutine 存取網域限流器的並發安全？

**Research Points**:
- Mutex vs RWMutex vs sync.Map
- 鎖粒度選擇（粗粒度 vs 細粒度）
- 無鎖設計的可能性（channels only）
- 效能權衡分析

**Expected Outcome**: 選定並發控制策略

---

#### R3: 配置載入機制
**Question**: 如何從配置檔案載入網域限流規則？

**Research Points**:
- 現有專案的配置管理方式
- INI vs JSON vs YAML 格式支援
- 配置驗證機制
- 預設值處理策略
- 配置範例設計

**Expected Outcome**: 配置格式和載入邏輯設計

---

#### R4: Context 取消實作模式
**Question**: 如何在等待 token 時正確響應 context 取消？

**Research Points**:
- `rate.Limiter.Wait(ctx)` 的 context 支援
- Select statement 的最佳實踐
- 清理邏輯處理
- 錯誤返回規範

**Expected Outcome**: Context 取消實作模式

---

#### R5: 統計資訊收集設計
**Question**: 如何高效收集和查詢限流統計資訊？

**Research Points**:
- Atomic operations vs mutex
- 統計資料結構設計
- 記憶體佔用優化
- 統計查詢 API 設計

**Expected Outcome**: 統計系統設計方案

---

#### R6: 測試策略
**Question**: 如何測試時間敏感的限流邏輯？

**Research Points**:
- Time mocking 技術（fake clock）
- Table-driven tests 設計
- Race detector 使用
- 整合測試場景設計
- Benchmark 測試方法

**Expected Outcome**: 完整測試策略

---

### Research Deliverable

完成後將生成 `research.md`，包含：
- 所有研究問題的決策結果
- 每個決策的理由說明
- 被拒絕的替代方案及原因
- 程式碼範例和參考連結

## Phase 1: Design & Contracts

### Phase 1.1: Data Model

將生成 `data-model.md`，包含：

#### Entity: RateLimiter (主限流器)
- **職責**: 管理所有網域的限流器實例
- **狀態**:
  - `limiters`: 網域 → DomainLimiter 對映
  - `defaultConfig`: 預設限流配置
  - `mu`: 保護對映表的 mutex
- **關鍵方法**:
  - `Wait(ctx, domain)`: 等待獲取 token
  - `GetStats(domain)`: 查詢統計
  - `UpdateConfig(domain, config)`: 更新配置

#### Entity: DomainLimiter (網域限流器)
- **職責**: 單一網域的限流控制
- **狀態**:
  - `domain`: 網域名稱
  - `limiter`: `rate.Limiter` 實例
  - `config`: 限流配置
  - `stats`: 統計資訊
  - `mu`: 保護統計的 mutex
- **關鍵行為**:
  - Token 獲取邏輯
  - 等待時間計算
  - 統計更新

#### Entity: LimitConfig (限流配置)
- **屬性**:
  - `RequestsPerSecond`: 每秒請求數
  - `BurstCapacity`: Burst 容量
- **驗證規則**:
  - RequestsPerSecond > 0
  - BurstCapacity ≥ 1

#### Entity: LimitStats (統計資訊)
- **屬性**:
  - `TotalRequests`: 總請求數
  - `DelayedRequests`: 被延遲的請求數
  - `TotalWaitTime`: 總等待時間
  - `LastRequestTime`: 最後請求時間
- **計算**:
  - `AverageWaitTime`: TotalWaitTime / DelayedRequests

### Phase 1.2: API Contracts

將生成 `contracts/ratelimiter.go`，包含：

```go
// RateLimiter 介面定義
type RateLimiter interface {
    // Wait 等待獲取指定網域的請求許可
    // 如果需要等待，會阻塞直到可以發送請求或 context 被取消
    Wait(ctx context.Context, domain string) error
    
    // WaitN 等待獲取 n 個 token（批次請求）
    WaitN(ctx context.Context, domain string, n int) error
    
    // Allow 非阻塞地檢查是否可以立即發送請求
    Allow(domain string) bool
    
    // GetStats 獲取指定網域的統計資訊
    GetStats(domain string) (*LimitStats, error)
    
    // GetAllStats 獲取所有網域的統計資訊
    GetAllStats() map[string]*LimitStats
    
    // UpdateConfig 更新指定網域的限流配置（可選功能）
    UpdateConfig(domain string, config LimitConfig) error
    
    // Close 關閉限流器，釋放資源
    Close() error
}

// 建構函式
func New(configs map[string]LimitConfig, defaultConfig LimitConfig) *RateLimiter

// 從配置檔案載入
func NewFromConfig(configPath string) (*RateLimiter, error)
```

### Phase 1.3: Quickstart Guide

將生成 `quickstart.md`，包含：

1. **Installation**: 如何在專案中引入 ratelimit 套件
2. **Basic Usage**: 5 分鐘快速上手範例
3. **Configuration**: 配置檔案範例和說明
4. **Common Patterns**: 常見使用模式
5. **Troubleshooting**: 常見問題和解決方法

## Phase 2: Task Breakdown (由 /speckit.tasks 生成)

Phase 2 將生成 `tasks.md`，包含：
- 具體的開發任務清單
- 每個任務的預估時間
- 任務依賴關係
- 測試需求

**注意**: Phase 2 任務由 `/speckit.tasks` 命令生成，不在本計畫範圍內。

## Next Steps

1. ✅ **Phase 0 Complete**: Research tasks完成，已生成 `research.md`
2. ✅ **Phase 1 Complete**: Design完成，已生成 `data-model.md`, `contracts/`, `quickstart.md`
3. ✅ **Constitution Re-check**: 設計符合所有 Constitution 原則
4. **Ready for Tasks**: 準備執行 `/speckit.tasks` 生成任務清單

---

**Status**: � Design Complete (Phase 1) - Ready for Task Breakdown  
**Blocker**: None  
**Next Command**: `/speckit.tasks` to generate detailed implementation tasks

---

## Phase 1 Constitution Re-check

### ✅ 最終符合性驗證

經過 Phase 0 研究和 Phase 1 設計，再次驗證 Constitution 符合性：

#### II. Progressive Migration Strategy ✅
- 速率限制器是第一個重構模組，為後續爬蟲模組提供基礎
- 完全獨立，無外部依賴，符合漸進式策略

#### III. Code Quality Standards ✅
- 資料模型清晰定義，遵循 Clean Code 原則
- API 合約完整，類型安全
- 使用 `golang.org/x/time/rate` 經過驗證的實作
- 錯誤處理使用 context wrapping
- 日誌將使用 zap（已規劃）

#### V. Concurrency and Performance ✅
- 並發模型明確：RWMutex + Atomic + rate.Limiter
- 記憶體佔用估算：<10MB (100 domains)
- 效能目標已在 Success Criteria 定義

#### VIII. Dependency Management ✅
- 僅使用 `golang.org/x/*` 官方套件
- 無 cgo 相依
- 符合最小化外部相依原則

### 🎯 設計品質評估

| 面向 | 狀態 | 說明 |
|------|------|------|
| API 完整性 | ✅ | 所有功能需求都有對應 API |
| 文件完整性 | ✅ | Quickstart + Data Model + Contracts |
| 並發安全 | ✅ | 明確的鎖策略和記憶體模型 |
| 可測試性 | ✅ | 清晰的介面和行為定義 |
| 效能設計 | ✅ | 記憶體和時間複雜度已分析 |

### 📊 Phase 1 產出總結

| 文件 | 狀態 | 行數 | 用途 |
|------|------|------|------|
| `research.md` | ✅ | ~800 | 技術決策記錄 |
| `data-model.md` | ✅ | ~600 | 資料模型設計 |
| `contracts/ratelimiter.go` | ✅ | ~400 | API 合約定義 |
| `quickstart.md` | ✅ | ~700 | 使用者快速開始 |

**Total**: ~2500 行完整設計文件

---

**Phase 1 Complete**: 所有設計文件已生成，準備進入任務分解階段 🎉
