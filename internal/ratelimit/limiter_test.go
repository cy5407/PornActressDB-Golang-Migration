package ratelimit_test

import (
	"context"
	"os"
	"sync"
	"testing"
	"time"

	"actress-classifier/internal/ratelimit"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestNew(t *testing.T) {
	configs := map[string]ratelimit.LimitConfig{
		"javdb.com":   {RequestsPerSecond: 1.0, BurstCapacity: 1},
		"av-wiki.net": {RequestsPerSecond: 2.0, BurstCapacity: 2},
	}

	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)
	require.NotNil(t, limiter)

	// 測試已配置的網域
	err := limiter.Wait(context.Background(), "javdb.com")
	assert.NoError(t, err)
}

func TestNewFromConfig(t *testing.T) {
	// 建立臨時配置檔案
	tmpDir := t.TempDir()
	configPath := tmpDir + "/config.json"

	configJSON := `{
		"version": "1.0",
		"default_config": {
			"requests_per_second": 1.0,
			"burst_capacity": 1
		},
		"domains": {
			"javdb.com": {
				"requests_per_second": 1.0,
				"burst_capacity": 1
			}
		}
	}`

	err := os.WriteFile(configPath, []byte(configJSON), 0644)
	require.NoError(t, err)

	limiter, err := ratelimit.NewFromConfig(configPath)
	require.NoError(t, err)
	require.NotNil(t, limiter)

	// 測試載入的配置
	err = limiter.Wait(context.Background(), "javdb.com")
	assert.NoError(t, err)
}

func TestRateLimiter_SingleDomain(t *testing.T) {
	configs := map[string]ratelimit.LimitConfig{
		"javdb.com": {RequestsPerSecond: 1, BurstCapacity: 1},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)

	start := time.Now()

	// 第 1 個請求（立即）
	err := limiter.Wait(context.Background(), "javdb.com")
	assert.NoError(t, err)

	// 第 2 個請求（延遲 ~1s）
	err = limiter.Wait(context.Background(), "javdb.com")
	assert.NoError(t, err)

	// 第 3 個請求（延遲 ~1s）
	err = limiter.Wait(context.Background(), "javdb.com")
	assert.NoError(t, err)

	elapsed := time.Since(start)

	// 總時間應該約 2 秒（第1個立即，第2、3個各延遲1秒）
	assert.InDelta(t, 2000, elapsed.Milliseconds(), 100, "預期總時間約 2 秒")
}

func TestRateLimiter_MultipleDomains(t *testing.T) {
	configs := map[string]ratelimit.LimitConfig{
		"javdb.com":   {RequestsPerSecond: 1, BurstCapacity: 1},
		"av-wiki.net": {RequestsPerSecond: 2, BurstCapacity: 2},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)

	var wg sync.WaitGroup

	// 並行向兩個網域發送請求
	start := time.Now()

	// JAVDB: 3 個請求，1 req/s，預期 ~2s
	wg.Add(1)
	go func() {
		defer wg.Done()
		for i := 0; i < 3; i++ {
			limiter.Wait(context.Background(), "javdb.com")
		}
	}()

	// AV-WIKI: 4 個請求，2 req/s，預期 ~1.5s
	wg.Add(1)
	go func() {
		defer wg.Done()
		for i := 0; i < 4; i++ {
			limiter.Wait(context.Background(), "av-wiki.net")
		}
	}()

	wg.Wait()
	elapsed := time.Since(start)

	// 並行執行，總時間應該約等於較慢的那個（~2s）
	assert.InDelta(t, 2000, elapsed.Milliseconds(), 200, "並行執行時間應約 2 秒")
}

func TestRateLimiter_DefaultConfigFallback(t *testing.T) {
	limiter := ratelimit.New(map[string]ratelimit.LimitConfig{}, ratelimit.DefaultConfig)

	start := time.Now()

	// 未配置的網域應使用預設配置（1 req/s）
	err := limiter.Wait(context.Background(), "unknown.com")
	assert.NoError(t, err)

	err = limiter.Wait(context.Background(), "unknown.com")
	assert.NoError(t, err)

	elapsed := time.Since(start)

	// 預設 1 req/s，應延遲 ~1s
	assert.InDelta(t, 1000, elapsed.Milliseconds(), 50)
}

func TestRateLimiter_Allow(t *testing.T) {
	configs := map[string]ratelimit.LimitConfig{
		"test.com": {RequestsPerSecond: 1, BurstCapacity: 1},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)

	// 第一個請求應該允許
	allowed := limiter.Allow("test.com")
	assert.True(t, allowed)

	// 立即第二個請求應該被拒絕（因為沒有可用 token）
	allowed = limiter.Allow("test.com")
	assert.False(t, allowed)

	// 等待一段時間後應該允許
	time.Sleep(1100 * time.Millisecond)
	allowed = limiter.Allow("test.com")
	assert.True(t, allowed)
}

func TestRateLimiter_WaitN(t *testing.T) {
	configs := map[string]ratelimit.LimitConfig{
		"test.com": {RequestsPerSecond: 2, BurstCapacity: 5},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)

	start := time.Now()

	// 一次獲取 3 個 token
	err := limiter.WaitN(context.Background(), "test.com", 3)
	assert.NoError(t, err)

	elapsed := time.Since(start)

	// Burst 為 5，第一次可以立即獲取 3 個
	assert.Less(t, elapsed.Milliseconds(), int64(100))
}

func TestRateLimiter_GetStats(t *testing.T) {
	configs := map[string]ratelimit.LimitConfig{
		"test.com": {RequestsPerSecond: 1, BurstCapacity: 1},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)

	// 發送幾個請求
	limiter.Wait(context.Background(), "test.com")
	limiter.Wait(context.Background(), "test.com")

	// 獲取統計
	stats, err := limiter.GetStats("test.com")
	require.NoError(t, err)
	assert.Equal(t, int64(2), stats.TotalRequests)
	assert.Equal(t, int64(1), stats.DelayedRequests)
}

func TestRateLimiter_GetStatsNotFound(t *testing.T) {
	limiter := ratelimit.New(map[string]ratelimit.LimitConfig{}, ratelimit.DefaultConfig)

	// 查詢不存在的網域
	stats, err := limiter.GetStats("nonexistent.com")
	assert.Error(t, err)
	assert.Nil(t, stats)
}

func TestRateLimiter_GetAllStats(t *testing.T) {
	configs := map[string]ratelimit.LimitConfig{
		"test1.com": {RequestsPerSecond: 1, BurstCapacity: 1},
		"test2.com": {RequestsPerSecond: 2, BurstCapacity: 2},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)

	// 向兩個網域發送請求
	limiter.Wait(context.Background(), "test1.com")
	limiter.Wait(context.Background(), "test2.com")

	// 獲取所有統計
	allStats := limiter.GetAllStats()
	assert.Equal(t, 2, len(allStats))
	assert.Contains(t, allStats, "test1.com")
	assert.Contains(t, allStats, "test2.com")
}

func TestRateLimiter_UpdateConfig(t *testing.T) {
	limiter := ratelimit.New(map[string]ratelimit.LimitConfig{}, ratelimit.DefaultConfig)

	// 發送一個請求（使用預設配置 1 req/s）
	limiter.Wait(context.Background(), "test.com")

	// 更新配置為 2 req/s
	newConfig := ratelimit.LimitConfig{
		RequestsPerSecond: 2.0,
		BurstCapacity:     2,
	}
	err := limiter.UpdateConfig("test.com", newConfig)
	assert.NoError(t, err)

	// 新配置應該生效（可以發送更快的請求）
	// 注意：更新配置會建立新的限流器，舊的統計會丟失
}

func TestRateLimiter_Close(t *testing.T) {
	limiter := ratelimit.New(map[string]ratelimit.LimitConfig{}, ratelimit.DefaultConfig)

	// 正常操作
	err := limiter.Wait(context.Background(), "test.com")
	assert.NoError(t, err)

	// 關閉
	err = limiter.Close()
	assert.NoError(t, err)

	// 關閉後應該返回錯誤
	err = limiter.Wait(context.Background(), "test.com")
	assert.ErrorIs(t, err, ratelimit.ErrLimiterClosed)

	// 重複關閉應該是冪等的
	err = limiter.Close()
	assert.NoError(t, err)
}

func TestRateLimiter_Concurrency(t *testing.T) {
	configs := map[string]ratelimit.LimitConfig{
		"test.com": {RequestsPerSecond: 10, BurstCapacity: 10},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)

	const goroutines = 50
	var wg sync.WaitGroup

	// 並發請求
	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			err := limiter.Wait(context.Background(), "test.com")
			assert.NoError(t, err)
		}()
	}

	wg.Wait()

	// 驗證統計
	stats, err := limiter.GetStats("test.com")
	require.NoError(t, err)
	assert.Equal(t, int64(goroutines), stats.TotalRequests)
}

func TestRateLimiter_ContextCancellation(t *testing.T) {
	configs := map[string]ratelimit.LimitConfig{
		"test.com": {RequestsPerSecond: 0.1, BurstCapacity: 1}, // 很慢：每 10 秒 1 個請求
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)

	// 第一個請求（立即）
	err := limiter.Wait(context.Background(), "test.com")
	assert.NoError(t, err)

	// 第二個請求（需要等待 10 秒）
	ctx, cancel := context.WithCancel(context.Background())

	done := make(chan error, 1)
	go func() {
		done <- limiter.Wait(ctx, "test.com")
	}()

	// 等待一小段時間後取消
	time.Sleep(100 * time.Millisecond)
	cancel()

	// 應該立即返回取消錯誤
	select {
	case err := <-done:
		assert.ErrorIs(t, err, context.Canceled)
	case <-time.After(500 * time.Millisecond):
		t.Fatal("context 取消沒有及時響應")
	}
}
