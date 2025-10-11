package ratelimit_test

import (
	"context"
	"testing"
	"time"

	"actress-classifier/internal/ratelimit"

	"github.com/stretchr/testify/assert"
)

// assertRequestTiming 驗證請求時間間隔是否在預期範圍內
// expectedMs: 預期延遲時間（毫秒）
// toleranceMs: 容忍誤差（毫秒）
func assertRequestTiming(t *testing.T, start time.Time, expectedMs int, toleranceMs int) {
	t.Helper()
	elapsed := time.Since(start).Milliseconds()
	assert.InDelta(t, float64(expectedMs), float64(elapsed), float64(toleranceMs),
		"請求延遲時間不符預期：期望 %dms ±%dms，實際 %dms",
		expectedMs, toleranceMs, elapsed)
}

// createTestLimiter 建立測試用的限流器
func createTestLimiter(configs map[string]ratelimit.LimitConfig, defaultConfig ratelimit.LimitConfig) ratelimit.RateLimiter {
	return ratelimit.New(configs, defaultConfig)
}

// waitForDuration 精確等待指定時間
func waitForDuration(d time.Duration) {
	time.Sleep(d)
}

// executeWithTimeout 在指定超時時間內執行函式
func executeWithTimeout(t *testing.T, timeout time.Duration, fn func(ctx context.Context) error) error {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	return fn(ctx)
}

// measureExecutionTime 測量函式執行時間
func measureExecutionTime(fn func()) time.Duration {
	start := time.Now()
	fn()
	return time.Since(start)
}
