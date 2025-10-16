package ratelimit

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"

	"go.uber.org/zap"
)

// RateLimiter 速率限制器介面
type RateLimiter interface {
	Wait(ctx context.Context, domain string) error
	WaitN(ctx context.Context, domain string, n int) error
	Allow(domain string) bool
	GetStats(domain string) (*StatsSnapshot, error)
	GetAllStats() map[string]*StatsSnapshot
	UpdateConfig(domain string, config LimitConfig) error
	Close() error
}

// rateLimiter 實作 RateLimiter 介面
type rateLimiter struct {
	limiters      map[string]*DomainLimiter
	defaultConfig LimitConfig
	mu            sync.RWMutex
	closed        atomic.Bool
	logger        *zap.Logger
}

// New 建立新的限流器
func New(configs map[string]LimitConfig, defaultConfig LimitConfig) RateLimiter {
	if configs == nil {
		configs = make(map[string]LimitConfig)
	}

	// 驗證預設配置
	if err := defaultConfig.Validate(); err != nil {
		// 如果預設配置無效，使用內建預設值
		defaultConfig = DefaultConfig
	}

	// 初始化 zap logger
	logger, err := zap.NewProduction()
	if err != nil {
		// 如果初始化失敗，使用無操作 logger
		logger = zap.NewNop()
	}

	rl := &rateLimiter{
		limiters:      make(map[string]*DomainLimiter),
		defaultConfig: defaultConfig,
		logger:        logger,
	}

	logger.Info("初始化速率限制器",
		zap.Int("已配置網域數", len(configs)),
		zap.Float64("預設速率", defaultConfig.RequestsPerSecond),
		zap.Int("預設爆發容量", defaultConfig.BurstCapacity),
	)

	// 預先建立已配置的網域限流器
	for domain, config := range configs {
		if limiter, err := newDomainLimiter(domain, config); err == nil {
			rl.limiters[domain] = limiter
			logger.Debug("預先建立網域限流器",
				zap.String("domain", domain),
				zap.Float64("speed_per_second", config.RequestsPerSecond),
				zap.Int("burst_capacity", config.BurstCapacity),
			)
		} else {
			logger.Error("建立網域限流器失敗",
				zap.String("domain", domain),
				zap.Error(err),
			)
		}
	}

	return rl
}

// NewFromConfig 從配置檔案建立限流器
func NewFromConfig(configPath string) (RateLimiter, error) {
	configFile, err := LoadConfigFromFile(configPath)
	if err != nil {
		return nil, err
	}

	return New(configFile.Domains, configFile.DefaultConfig), nil
}

// getOrCreateLimiter 取得或建立網域限流器（double-check locking）
func (r *rateLimiter) getOrCreateLimiter(domain string) (*DomainLimiter, error) {
	if r.closed.Load() {
		r.logger.Error("嘗試存取已關閉的限流器",
			zap.String("domain", domain),
		)
		return nil, ErrLimiterClosed
	}

	if domain == "" {
		r.logger.Warn("網域名稱為空",
			zap.Error(ErrInvalidDomain),
		)
		return nil, fmt.Errorf("%w: 網域名稱不能為空", ErrInvalidDomain)
	}

	// 先使用讀鎖檢查
	r.mu.RLock()
	limiter, exists := r.limiters[domain]
	r.mu.RUnlock()

	if exists {
		return limiter, nil
	}

	// 使用寫鎖建立新限流器
	r.mu.Lock()
	defer r.mu.Unlock()

	// 再次檢查（double-check）
	if limiter, exists := r.limiters[domain]; exists {
		return limiter, nil
	}

	// 建立新的限流器（使用預設配置）
	limiter, err := newDomainLimiter(domain, r.defaultConfig)
	if err != nil {
		r.logger.Error("建立網域限流器失敗",
			zap.String("domain", domain),
			zap.Error(err),
		)
		return nil, err
	}

	r.limiters[domain] = limiter
	r.logger.Info("建立新網域限流器",
		zap.String("domain", domain),
		zap.Float64("speed_per_second", r.defaultConfig.RequestsPerSecond),
		zap.Int("burst_capacity", r.defaultConfig.BurstCapacity),
	)

	return limiter, nil
}

// Wait 等待獲取指定網域的請求許可
func (r *rateLimiter) Wait(ctx context.Context, domain string) error {
	limiter, err := r.getOrCreateLimiter(domain)
	if err != nil {
		return err
	}

	return limiter.Wait(ctx)
}

// WaitN 等待獲取 n 個 token
func (r *rateLimiter) WaitN(ctx context.Context, domain string, n int) error {
	limiter, err := r.getOrCreateLimiter(domain)
	if err != nil {
		return err
	}

	return limiter.WaitN(ctx, n)
}

// Allow 非阻塞地檢查是否可以立即發送請求
func (r *rateLimiter) Allow(domain string) bool {
	limiter, err := r.getOrCreateLimiter(domain)
	if err != nil {
		return false
	}

	return limiter.Allow()
}

// GetStats 獲取指定網域的統計資訊
func (r *rateLimiter) GetStats(domain string) (*StatsSnapshot, error) {
	if r.closed.Load() {
		return nil, ErrLimiterClosed
	}

	r.mu.RLock()
	limiter, exists := r.limiters[domain]
	r.mu.RUnlock()

	if !exists {
		return nil, fmt.Errorf("%w: %s", ErrDomainNotFound, domain)
	}

	return limiter.Stats(), nil
}

// GetAllStats 獲取所有網域的統計資訊
func (r *rateLimiter) GetAllStats() map[string]*StatsSnapshot {
	if r.closed.Load() {
		return make(map[string]*StatsSnapshot)
	}

	r.mu.RLock()
	defer r.mu.RUnlock()

	stats := make(map[string]*StatsSnapshot, len(r.limiters))
	for domain, limiter := range r.limiters {
		stats[domain] = limiter.Stats()
	}

	return stats
}

// UpdateConfig 動態更新指定網域的限流配置
func (r *rateLimiter) UpdateConfig(domain string, config LimitConfig) error {
	if r.closed.Load() {
		r.logger.Warn("嘗試更新已關閉限流器的配置",
			zap.String("domain", domain),
		)
		return ErrLimiterClosed
	}

	if err := config.Validate(); err != nil {
		r.logger.Error("配置驗證失敗",
			zap.String("domain", domain),
			zap.Error(err),
		)
		return err
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	// 建立新的限流器替換舊的
	limiter, err := newDomainLimiter(domain, config)
	if err != nil {
		r.logger.Error("建立新網域限流器失敗",
			zap.String("domain", domain),
			zap.Error(err),
		)
		return err
	}

	r.limiters[domain] = limiter
	r.logger.Info("更新網域限流配置",
		zap.String("domain", domain),
		zap.Float64("new_speed_per_second", config.RequestsPerSecond),
		zap.Int("new_burst_capacity", config.BurstCapacity),
	)

	return nil
}

// Close 關閉限流器，釋放資源
func (r *rateLimiter) Close() error {
	// 冪等關閉
	if r.closed.Swap(true) {
		r.logger.Debug("限流器已經關閉")
		return nil // 已經關閉
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	// 清空限流器
	r.limiters = make(map[string]*DomainLimiter)

	r.logger.Info("關閉限流器", zap.Int("釋放網域數", 0))

	// 同步 logger
	_ = r.logger.Sync()

	return nil
}
