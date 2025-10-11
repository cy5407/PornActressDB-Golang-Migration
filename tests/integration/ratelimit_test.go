package integration

import (
	"context"
	"sync"
	"testing"
	"time"

	"actress-classifier/internal/ratelimit"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestUS1_Scenario1_JAVDBSequentialRequests 驗證 US1 Scenario 1:
// 1 秒內連續 3 個請求到 JAVDB，驗證延遲時間
func TestUS1_Scenario1_JAVDBSequentialRequests(t *testing.T) {
	// Arrange: 建立限流器，JAVDB 配置為 1 req/s, burst 1
	configs := map[string]ratelimit.LimitConfig{
		"javdb.com": {
			RequestsPerSecond: 1.0,
			BurstCapacity:     1,
		},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)
	defer limiter.Close()

	ctx := context.Background()

	// Act: 連續發送 3 個請求
	start := time.Now()
	requestTimes := make([]time.Duration, 3)

	for i := 0; i < 3; i++ {
		err := limiter.Wait(ctx, "javdb.com")
		require.NoError(t, err, "Wait should not return error")
		requestTimes[i] = time.Since(start)
	}

	totalElapsed := time.Since(start)

	// Assert: 驗證每個請求的時間間隔
	// 第 1 個請求: ~0s (立即通過，使用 burst token)
	assert.InDelta(t, 0, requestTimes[0].Milliseconds(), 50,
		"First request should be immediate (±50ms)")

	// 第 2 個請求: ~1000ms (等待 1 秒後獲得新 token)
	assert.InDelta(t, 1000, requestTimes[1].Milliseconds(), 50,
		"Second request should wait ~1s (±50ms)")

	// 第 3 個請求: ~2000ms (再等待 1 秒)
	assert.InDelta(t, 2000, requestTimes[2].Milliseconds(), 50,
		"Third request should wait ~2s (±50ms)")

	// 總時間應約為 2 秒
	assert.InDelta(t, 2000, totalElapsed.Milliseconds(), 100,
		"Total time for 3 requests should be ~2s (±100ms)")

	// 驗證統計資訊
	stats, err := limiter.GetStats("javdb.com")
	require.NoError(t, err, "GetStats should not return error")
	require.NotNil(t, stats, "Stats should be available")
	assert.Equal(t, int64(3), stats.TotalRequests, "Should record 3 requests")
	assert.Equal(t, int64(2), stats.DelayedRequests, "Should record 2 delayed requests")

	// 延遲率應該是 2/3 = 0.6667 (66.67%)
	assert.InDelta(t, 0.6667, stats.DelayRate, 0.01, "Delay rate should be ~0.6667 (66.67%)")
}

// TestUS1_Scenario2_ParallelDomainsIndependence 驗證 US1 Scenario 2:
// 並行請求到 JAVDB 和 AV-WIKI，驗證獨立限流
func TestUS1_Scenario2_ParallelDomainsIndependence(t *testing.T) {
	// Arrange: 建立限流器
	// JAVDB: 1 req/s (慢)
	// AV-WIKI: 2 req/s (快)
	configs := map[string]ratelimit.LimitConfig{
		"javdb.com": {
			RequestsPerSecond: 1.0,
			BurstCapacity:     1,
		},
		"av-wiki.net": {
			RequestsPerSecond: 2.0,
			BurstCapacity:     1,
		},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)
	defer limiter.Close()

	ctx := context.Background()

	// Act: 並行發送請求到兩個網域
	var wg sync.WaitGroup
	var javdbElapsed, avwikiElapsed time.Duration

	// JAVDB: 3 個請求 (應約 2 秒)
	wg.Add(1)
	go func() {
		defer wg.Done()
		start := time.Now()
		for i := 0; i < 3; i++ {
			err := limiter.Wait(ctx, "javdb.com")
			require.NoError(t, err)
		}
		javdbElapsed = time.Since(start)
	}()

	// AV-WIKI: 3 個請求 (應約 1 秒)
	wg.Add(1)
	go func() {
		defer wg.Done()
		start := time.Now()
		for i := 0; i < 3; i++ {
			err := limiter.Wait(ctx, "av-wiki.net")
			require.NoError(t, err)
		}
		avwikiElapsed = time.Since(start)
	}()

	wg.Wait()

	// Assert: 驗證兩個網域的執行時間
	// JAVDB: 3 個請求 = 0s + 1s + 1s = ~2s
	assert.InDelta(t, 2000, javdbElapsed.Milliseconds(), 100,
		"JAVDB 3 requests should take ~2s (±100ms)")

	// AV-WIKI: 3 個請求 = 0s + 0.5s + 0.5s = ~1s
	assert.InDelta(t, 1000, avwikiElapsed.Milliseconds(), 100,
		"AV-WIKI 3 requests should take ~1s (±100ms)")

	// 關鍵驗證：兩個網域的時間差應明顯 (JAVDB 比 AV-WIKI 慢約 1 秒)
	timeDiff := javdbElapsed - avwikiElapsed
	assert.Greater(t, timeDiff.Milliseconds(), int64(800),
		"JAVDB should be significantly slower than AV-WIKI (>800ms)")

	// 驗證統計資訊
	javdbStats, err := limiter.GetStats("javdb.com")
	require.NoError(t, err, "GetStats for JAVDB should not return error")
	avwikiStats, err := limiter.GetStats("av-wiki.net")
	require.NoError(t, err, "GetStats for AV-WIKI should not return error")

	require.NotNil(t, javdbStats, "JAVDB stats should be available")
	require.NotNil(t, avwikiStats, "AV-WIKI stats should be available")

	assert.Equal(t, int64(3), javdbStats.TotalRequests, "JAVDB should have 3 requests")
	assert.Equal(t, int64(3), avwikiStats.TotalRequests, "AV-WIKI should have 3 requests")
}

// TestUS1_EdgeCase_ContextCancellation 驗證 Context 取消的行為
func TestUS1_EdgeCase_ContextCancellation(t *testing.T) {
	// Arrange: 建立限流器，配置非常慢的速率
	configs := map[string]ratelimit.LimitConfig{
		"slow.com": {
			RequestsPerSecond: 0.1, // 10 秒 1 個請求
			BurstCapacity:     1,
		},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)
	defer limiter.Close()

	// 建立可取消的 context (200ms timeout)
	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	// Act: 第一個請求立即通過（burst token）
	err := limiter.Wait(ctx, "slow.com")
	require.NoError(t, err, "First request should succeed")

	// 第二個請求需要等待 10 秒，但 context 會在 200ms 後 timeout
	// rate.Limiter.Wait() 會立即檢測到無法在 deadline 內完成，所以立即返回錯誤
	start := time.Now()
	err = limiter.Wait(ctx, "slow.com")
	elapsed := time.Since(start)

	// Assert: 驗證返回錯誤
	assert.Error(t, err, "Second request should fail due to context cancellation")
	// 錯誤訊息應該是 context 相關的
	assert.True(t,
		err.Error() == "context deadline exceeded" ||
			err.Error() == "context canceled" ||
			err.Error() == "rate: Wait(n=1) would exceed context deadline",
		"Error should be context-related, got: %v", err)
	
	// rate.Limiter.Wait() 會立即檢測到無法滿足 deadline，所以應該在極短時間內返回
	assert.Less(t, elapsed.Milliseconds(), int64(100),
		"Should fail quickly (<100ms) as rate limiter detects deadline cannot be met")
}

// TestUS1_EdgeCase_BurstCapacity 驗證 burst capacity 的行為
func TestUS1_EdgeCase_BurstCapacity(t *testing.T) {
	// Arrange: 建立限流器，burst capacity = 3
	configs := map[string]ratelimit.LimitConfig{
		"burst.com": {
			RequestsPerSecond: 1.0,
			BurstCapacity:     3, // 允許 burst 3 個請求
		},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)
	defer limiter.Close()

	ctx := context.Background()

	// Act: 連續發送 3 個請求
	start := time.Now()
	for i := 0; i < 3; i++ {
		err := limiter.Wait(ctx, "burst.com")
		require.NoError(t, err)
	}
	burstElapsed := time.Since(start)

	// Assert: 前 3 個請求應該幾乎立即完成（使用 burst tokens）
	assert.Less(t, burstElapsed.Milliseconds(), int64(100),
		"First 3 requests should complete immediately with burst tokens (<100ms)")

	// 第 4 個請求應該等待約 1 秒
	start = time.Now()
	err := limiter.Wait(ctx, "burst.com")
	require.NoError(t, err)
	fourthElapsed := time.Since(start)

	assert.InDelta(t, 1000, fourthElapsed.Milliseconds(), 50,
		"Fourth request should wait ~1s (±50ms)")
}

// TestUS1_Integration_GetAllStats 驗證取得所有網域統計
func TestUS1_Integration_GetAllStats(t *testing.T) {
	// Arrange: 建立限流器，配置多個網域
	configs := map[string]ratelimit.LimitConfig{
		"javdb.com":   {RequestsPerSecond: 1.0, BurstCapacity: 1},
		"av-wiki.net": {RequestsPerSecond: 2.0, BurstCapacity: 1},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)
	defer limiter.Close()

	ctx := context.Background()

	// Act: 發送請求到各個網域
	require.NoError(t, limiter.Wait(ctx, "javdb.com"))
	require.NoError(t, limiter.Wait(ctx, "javdb.com"))
	require.NoError(t, limiter.Wait(ctx, "av-wiki.net"))

	// 取得所有統計
	allStats := limiter.GetAllStats()

	// Assert: 驗證統計資料
	require.Len(t, allStats, 2, "Should have stats for 2 domains")

	javdbStats, ok := allStats["javdb.com"]
	require.True(t, ok, "Should have JAVDB stats")
	assert.Equal(t, int64(2), javdbStats.TotalRequests, "JAVDB should have 2 requests")

	avwikiStats, ok := allStats["av-wiki.net"]
	require.True(t, ok, "Should have AV-WIKI stats")
	assert.Equal(t, int64(1), avwikiStats.TotalRequests, "AV-WIKI should have 1 request")
}
