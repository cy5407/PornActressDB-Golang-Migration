// Package ratelimit 提供網域獨立的爬蟲速率限制功能
//
// 本套件實作基於 token bucket 演算法的速率限制器，支援：
// - 每個網域獨立的限流配置
// - 並發安全的請求控制
// - Context-based 取消機制
// - 詳細的請求統計資訊
//
// 基本使用範例：
//
//	import "actress-classifier/internal/ratelimit"
//
//	// 建立限流器
//	limiter := ratelimit.New(map[string]ratelimit.LimitConfig{
//	    "javdb.com": {RequestsPerSecond: 1, BurstCapacity: 1},
//	    "av-wiki.net": {RequestsPerSecond: 2, BurstCapacity: 2},
//	}, ratelimit.DefaultConfig)
//
//	// 使用限流器
//	ctx := context.Background()
//	if err := limiter.Wait(ctx, "javdb.com"); err != nil {
//	    log.Fatal(err)
//	}
//	// 現在可以安全地發送請求
//	resp, err := http.Get("https://javdb.com/...")
package ratelimit

import (
	"context"
	"time"
)

// RateLimiter 介面定義了速率限制器的核心功能
//
// RateLimiter 管理多個網域的限流狀態，每個網域有獨立的限流配置和統計資訊。
// 所有方法都是並發安全的。
type RateLimiter interface {
	// Wait 等待獲取指定網域的請求許可
	//
	// 如果當前有可用的 token，Wait 會立即返回。
	// 如果沒有可用 token，Wait 會阻塞直到：
	// 1. 有 token 可用（根據配置的速率恢復）
	// 2. context 被取消（返回 context.Canceled）
	// 3. context 超時（返回 context.DeadlineExceeded）
	//
	// 參數：
	//   ctx: 用於取消等待的 context
	//   domain: 目標網域名稱（如 "javdb.com"）
	//
	// 返回：
	//   nil: 成功獲取 token，可以發送請求
	//   error: context 取消、超時或其他錯誤
	//
	// 範例：
	//   ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	//   defer cancel()
	//   if err := limiter.Wait(ctx, "javdb.com"); err != nil {
	//       // 處理錯誤：可能是超時或被取消
	//       return err
	//   }
	//   // 發送請求
	Wait(ctx context.Context, domain string) error

	// WaitN 等待獲取 n 個 token（用於批次請求）
	//
	// 類似 Wait，但一次性獲取多個 token。
	// 當需要連續發送多個請求時，可以使用此方法一次性預留。
	//
	// 參數：
	//   ctx: 用於取消等待的 context
	//   domain: 目標網域名稱
	//   n: 需要獲取的 token 數量（必須 >= 1）
	//
	// 返回：
	//   nil: 成功獲取 n 個 token
	//   error: context 取消、n 無效或其他錯誤
	//
	// 範例：
	//   // 預留 5 個 token 用於批次請求
	//   if err := limiter.WaitN(ctx, "javdb.com", 5); err != nil {
	//       return err
	//   }
	//   // 現在可以連續發送 5 個請求
	WaitN(ctx context.Context, domain string, n int) error

	// Allow 非阻塞地檢查是否可以立即發送請求
	//
	// Allow 不會等待，立即返回當前是否有可用 token。
	// 如果返回 true，token 會被消耗；如果返回 false，不會消耗 token。
	//
	// 使用場景：
	// - 需要立即知道結果，不能等待
	// - 實作「盡力而為」的限流（允許偶爾失敗）
	// - 與其他非阻塞邏輯整合
	//
	// 參數：
	//   domain: 目標網域名稱
	//
	// 返回：
	//   true: 有可用 token，已消耗，可以立即發送請求
	//   false: 無可用 token，請稍後重試
	//
	// 範例：
	//   if limiter.Allow("javdb.com") {
	//       // 發送請求
	//   } else {
	//       // 稍後重試或跳過
	//       log.Warn("速率限制中，跳過請求")
	//   }
	Allow(domain string) bool

	// GetStats 獲取指定網域的統計資訊
	//
	// 返回該網域的請求統計快照，包括總請求數、延遲數、等待時間等。
	// 返回的結構是副本，可以安全地使用而不會影響內部狀態。
	//
	// 參數：
	//   domain: 目標網域名稱
	//
	// 返回：
	//   *StatsSnapshot: 統計資訊快照
	//   error: 網域不存在或其他錯誤
	//
	// 範例：
	//   stats, err := limiter.GetStats("javdb.com")
	//   if err != nil {
	//       return err
	//   }
	//   fmt.Printf("總請求: %d, 延遲率: %.2f%%\n",
	//       stats.TotalRequests, stats.DelayRate*100)
	GetStats(domain string) (*StatsSnapshot, error)

	// GetAllStats 獲取所有網域的統計資訊
	//
	// 返回一個 map，key 是網域名稱，value 是統計資訊。
	// 只包含已經有請求的網域（未使用的網域不會出現）。
	//
	// 返回：
	//   map[string]*StatsSnapshot: 所有網域的統計資訊
	//
	// 範例：
	//   allStats := limiter.GetAllStats()
	//   for domain, stats := range allStats {
	//       fmt.Printf("%s: %d 個請求\n", domain, stats.TotalRequests)
	//   }
	GetAllStats() map[string]*StatsSnapshot

	// UpdateConfig 動態更新指定網域的限流配置
	//
	// 注意：此功能為可選（Optional），在 MVP 版本中可能不實作。
	// 如果實作，更新會立即生效，但不影響正在等待的請求。
	//
	// 參數：
	//   domain: 目標網域名稱
	//   config: 新的限流配置
	//
	// 返回：
	//   nil: 成功更新
	//   error: 配置無效或其他錯誤
	//
	// 範例：
	//   newConfig := ratelimit.LimitConfig{
	//       RequestsPerSecond: 3,  // 提高速率
	//       BurstCapacity: 5,
	//   }
	//   if err := limiter.UpdateConfig("javdb.com", newConfig); err != nil {
	//       return err
	//   }
	UpdateConfig(domain string, config LimitConfig) error

	// Close 關閉限流器，釋放資源
	//
	// Close 會等待所有正在執行的 Wait 操作完成。
	// 關閉後，後續的 Wait/Allow 呼叫會返回錯誤。
	//
	// 返回：
	//   nil: 成功關閉
	//   error: 關閉失敗（通常不會發生）
	//
	// 範例：
	//   defer limiter.Close()
	Close() error
}

// LimitConfig 定義單一網域的限流配置
type LimitConfig struct {
	// RequestsPerSecond 指定每秒允許的請求數
	//
	// 必須大於 0。可以是小數（如 0.5 表示每 2 秒 1 個請求）。
	//
	// 範例：
	//   1.0  -> 每秒 1 個請求
	//   2.0  -> 每秒 2 個請求
	//   0.5  -> 每 2 秒 1 個請求
	//   10.0 -> 每秒 10 個請求
	RequestsPerSecond float64 `json:"requests_per_second"`

	// BurstCapacity 指定 burst 容量（可累積的 token 數）
	//
	// 必須至少為 1。較高的 burst 容量允許短時間內發送更多請求。
	//
	// 範例：
	//   BurstCapacity=1: 嚴格限流，無 burst
	//   BurstCapacity=5: 允許短時間內發送 5 個請求
	//
	// 建議：
	//   - 保守配置：BurstCapacity = 1
	//   - 一般配置：BurstCapacity = RequestsPerSecond * 2
	//   - 寬鬆配置：BurstCapacity = RequestsPerSecond * 5
	BurstCapacity int `json:"burst_capacity"`
}

// Validate 驗證配置的有效性
//
// 返回：
//
//	nil: 配置有效
//	error: 配置無效，包含具體錯誤訊息
func (c LimitConfig) Validate() error

// StatsSnapshot 表示某一時刻的統計資訊快照
type StatsSnapshot struct {
	// Domain 網域名稱
	Domain string `json:"domain"`

	// TotalRequests 總請求數（包含成功和取消的）
	TotalRequests int64 `json:"total_requests"`

	// DelayedRequests 被延遲的請求數（等待時間 > 10ms）
	DelayedRequests int64 `json:"delayed_requests"`

	// TotalWaitTime 總等待時間
	TotalWaitTime time.Duration `json:"total_wait_time"`

	// AverageWaitTime 平均等待時間（僅計算被延遲的請求）
	//
	// 計算公式：TotalWaitTime / DelayedRequests
	// 如果 DelayedRequests = 0，則為 0
	AverageWaitTime time.Duration `json:"average_wait_time"`

	// LastRequestTime 最後一次請求的時間
	LastRequestTime time.Time `json:"last_request_time"`

	// DelayRate 延遲比例（0.0 - 1.0）
	//
	// 計算公式：DelayedRequests / TotalRequests
	// 如果 TotalRequests = 0，則為 0
	//
	// 範例：
	//   0.0  -> 所有請求都立即執行
	//   0.3  -> 30% 的請求被延遲
	//   1.0  -> 所有請求都被延遲
	DelayRate float64 `json:"delay_rate"`
}

// ConfigFile 表示配置檔案的結構
//
// JSON 範例：
//
//	{
//	  "version": "1.0",
//	  "default_config": {
//	    "requests_per_second": 1.0,
//	    "burst_capacity": 1
//	  },
//	  "domains": {
//	    "javdb.com": {
//	      "requests_per_second": 1.0,
//	      "burst_capacity": 1
//	    },
//	    "av-wiki.net": {
//	      "requests_per_second": 2.0,
//	      "burst_capacity": 2
//	    }
//	  }
//	}
type ConfigFile struct {
	// Version 配置檔案版本（用於未來相容性）
	Version string `json:"version"`

	// DefaultConfig 未明確配置的網域使用的預設配置
	DefaultConfig LimitConfig `json:"default_config"`

	// Domains 每個網域的特定配置
	Domains map[string]LimitConfig `json:"domains"`
}

// Validate 驗證整個配置檔案的有效性
func (cf ConfigFile) Validate() error

// New 建立一個新的 RateLimiter
//
// 參數：
//
//	configs: 每個網域的限流配置（可以為 nil 或空 map）
//	defaultConfig: 未配置網域使用的預設配置
//
// 返回：
//
//	RateLimiter: 新建立的限流器實例
//
// 範例：
//
//	limiter := ratelimit.New(map[string]ratelimit.LimitConfig{
//	    "javdb.com": {RequestsPerSecond: 1, BurstCapacity: 1},
//	    "av-wiki.net": {RequestsPerSecond: 2, BurstCapacity: 2},
//	}, ratelimit.LimitConfig{
//	    RequestsPerSecond: 1, // 預設：每秒 1 個請求
//	    BurstCapacity: 1,
//	})
func New(configs map[string]LimitConfig, defaultConfig LimitConfig) RateLimiter

// NewFromConfig 從配置檔案建立 RateLimiter
//
// 參數：
//
//	configPath: 配置檔案路徑（JSON 格式）
//
// 返回：
//
//	RateLimiter: 新建立的限流器實例
//	error: 檔案讀取、解析或驗證失敗
//
// 範例：
//
//	limiter, err := ratelimit.NewFromConfig("config/ratelimit.json")
//	if err != nil {
//	    log.Fatalf("載入配置失敗: %v", err)
//	}
//	defer limiter.Close()
func NewFromConfig(configPath string) (RateLimiter, error)

// DefaultConfig 提供一個保守的預設配置
//
// 預設配置：每秒 1 個請求，burst 容量為 1
var DefaultConfig = LimitConfig{
	RequestsPerSecond: 1.0,
	BurstCapacity:     1,
}

// PresetConfigs 提供預設的網域配置
//
// 包含常見資料來源的建議配置
var PresetConfigs = map[string]LimitConfig{
	"javdb.com":      {RequestsPerSecond: 1.0, BurstCapacity: 1},
	"av-wiki.net":    {RequestsPerSecond: 2.0, BurstCapacity: 2},
	"chiba-f.com":    {RequestsPerSecond: 1.0, BurstCapacity: 1},
	"minnano-av.com": {RequestsPerSecond: 1.0, BurstCapacity: 1},
}

// Errors 定義套件專用的錯誤類型

// ErrInvalidDomain 表示提供的網域名稱無效
var ErrInvalidDomain error

// ErrInvalidConfig 表示配置無效
var ErrInvalidConfig error

// ErrLimiterClosed 表示限流器已關閉
var ErrLimiterClosed error

// ErrDomainNotFound 表示網域不存在（GetStats 時）
var ErrDomainNotFound error
