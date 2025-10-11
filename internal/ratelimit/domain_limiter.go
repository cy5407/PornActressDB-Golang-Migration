package ratelimit

import (
	"context"
	"fmt"
	"time"

	"golang.org/x/time/rate"
)

// DomainLimiter 單一網域的限流器
type DomainLimiter struct {
	domain  string
	limiter *rate.Limiter
	config  LimitConfig
	stats   *LimitStats
}

// newDomainLimiter 建立新的網域限流器
func newDomainLimiter(domain string, config LimitConfig) (*DomainLimiter, error) {
	if domain == "" {
		return nil, fmt.Errorf("%w: 網域名稱不能為空", ErrInvalidDomain)
	}

	if err := config.Validate(); err != nil {
		return nil, err
	}

	// 建立 rate.Limiter
	// Limit 為每秒的速率，Burst 為突發容量
	limiter := rate.NewLimiter(rate.Limit(config.RequestsPerSecond), config.BurstCapacity)

	return &DomainLimiter{
		domain:  domain,
		limiter: limiter,
		config:  config,
		stats:   NewLimitStats(),
	}, nil
}

// Wait 等待獲取請求許可
func (d *DomainLimiter) Wait(ctx context.Context) error {
	if ctx == nil {
		ctx = context.Background()
	}

	start := time.Now()

	// 先檢查是否需要延遲（不消耗 token）
	reservation := d.limiter.Reserve()
	if !reservation.OK() {
		return fmt.Errorf("無法獲取 token")
	}

	delay := reservation.Delay()

	// 取消這個預約（我們只是用來檢查延遲時間）
	reservation.Cancel()

	// 實際等待並消耗 token
	if err := d.limiter.Wait(ctx); err != nil {
		return err
	}

	// 記錄統計
	d.stats.IncrementTotal()
	d.stats.UpdateLastRequestTime(time.Now())

	// 如果有延遲，記錄延遲統計
	if delay > 0 {
		actualWait := time.Since(start)
		d.stats.RecordDelay(actualWait)
	}

	return nil
}

// WaitN 等待獲取 n 個 token
func (d *DomainLimiter) WaitN(ctx context.Context, n int) error {
	if n < 1 {
		return fmt.Errorf("%w: n 必須至少為 1", ErrInvalidConfig)
	}

	if ctx == nil {
		ctx = context.Background()
	}

	start := time.Now()

	// 檢查是否需要延遲
	reservation := d.limiter.ReserveN(time.Now(), n)
	if !reservation.OK() {
		return fmt.Errorf("無法獲取 %d 個 token", n)
	}

	delay := reservation.Delay()
	reservation.Cancel()

	// 實際等待並消耗 token
	if err := d.limiter.WaitN(ctx, n); err != nil {
		return err
	}

	// 記錄統計
	d.stats.IncrementTotal()
	d.stats.UpdateLastRequestTime(time.Now())

	// 如果有延遲，記錄實際等待時間
	if delay > 0 {
		actualWait := time.Since(start)
		d.stats.RecordDelay(actualWait)
	}

	return nil
} // Allow 非阻塞地檢查是否可以立即發送請求
func (d *DomainLimiter) Allow() bool {
	allowed := d.limiter.Allow()

	if allowed {
		// 記錄請求
		d.stats.IncrementTotal()
		d.stats.UpdateLastRequestTime(time.Now())
	}

	return allowed
}

// Stats 返回統計資訊快照
func (d *DomainLimiter) Stats() *StatsSnapshot {
	return d.stats.Snapshot()
}

// Domain 返回網域名稱
func (d *DomainLimiter) Domain() string {
	return d.domain
}

// Config 返回限流配置
func (d *DomainLimiter) Config() LimitConfig {
	return d.config
}
