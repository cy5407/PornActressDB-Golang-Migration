package integration

import (
	"context"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"actress-classifier/internal/ratelimit"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"golang.org/x/sync/errgroup"
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

// ============================================================================
// US2 Integration Tests - 網域獨立限流管理
// ============================================================================

// TestUS2_Scenario1_MultiDomainParallelWithDifferentConfigs 驗證 US2 Scenario 1:
// 三個網域不同配置，並行發送請求，驗證總時間和獨立性
func TestUS2_Scenario1_MultiDomainParallelWithDifferentConfigs(t *testing.T) {
	// Arrange: 建立限流器，配置三個網域
	configs := map[string]ratelimit.LimitConfig{
		"javdb.com": {
			RequestsPerSecond: 1.0, // 1 req/s (慢)
			BurstCapacity:     1,
		},
		"av-wiki.net": {
			RequestsPerSecond: 2.0, // 2 req/s (中)
			BurstCapacity:     1,
		},
		"fast-site.com": {
			RequestsPerSecond: 5.0, // 5 req/s (快)
			BurstCapacity:     1,
		},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)
	defer limiter.Close()

	ctx := context.Background()

	// Act: 使用 errgroup 並行發送請求到各個網域
	g, gctx := errgroup.WithContext(ctx)

	var javdbElapsed, avwikiElapsed, fastElapsed time.Duration
	var javdbMu, avwikiMu, fastMu sync.Mutex

	// JAVDB: 3 個請求 = 0s + 1s + 1s = ~2s
	g.Go(func() error {
		start := time.Now()
		for i := 0; i < 3; i++ {
			if err := limiter.Wait(gctx, "javdb.com"); err != nil {
				return err
			}
		}
		javdbMu.Lock()
		javdbElapsed = time.Since(start)
		javdbMu.Unlock()
		return nil
	})

	// AV-WIKI: 3 個請求 = 0s + 0.5s + 0.5s = ~1s
	g.Go(func() error {
		start := time.Now()
		for i := 0; i < 3; i++ {
			if err := limiter.Wait(gctx, "av-wiki.net"); err != nil {
				return err
			}
		}
		avwikiMu.Lock()
		avwikiElapsed = time.Since(start)
		avwikiMu.Unlock()
		return nil
	})

	// fast-site.com: 6 個請求 = 0s + 0.2s + 0.2s + 0.2s + 0.2s + 0.2s = ~1s
	g.Go(func() error {
		start := time.Now()
		for i := 0; i < 6; i++ {
			if err := limiter.Wait(gctx, "fast-site.com"); err != nil {
				return err
			}
		}
		fastMu.Lock()
		fastElapsed = time.Since(start)
		fastMu.Unlock()
		return nil
	})

	// 等待所有並行任務完成
	err := g.Wait()
	require.NoError(t, err, "All parallel requests should succeed")

	// Assert: 驗證每個網域的執行時間
	javdbMu.Lock()
	assert.InDelta(t, 2000, javdbElapsed.Milliseconds(), 200,
		"JAVDB 3 requests should take ~2s (±200ms)")
	javdbMu.Unlock()

	avwikiMu.Lock()
	assert.InDelta(t, 1000, avwikiElapsed.Milliseconds(), 200,
		"AV-WIKI 3 requests should take ~1s (±200ms)")
	avwikiMu.Unlock()

	fastMu.Lock()
	assert.InDelta(t, 1000, fastElapsed.Milliseconds(), 200,
		"fast-site.com 6 requests should take ~1s (±200ms)")
	fastMu.Unlock()

	// 驗證統計資訊
	javdbStats, err := limiter.GetStats("javdb.com")
	require.NoError(t, err)
	assert.Equal(t, int64(3), javdbStats.TotalRequests, "JAVDB should have 3 requests")

	avwikiStats, err := limiter.GetStats("av-wiki.net")
	require.NoError(t, err)
	assert.Equal(t, int64(3), avwikiStats.TotalRequests, "AV-WIKI should have 3 requests")

	fastStats, err := limiter.GetStats("fast-site.com")
	require.NoError(t, err)
	assert.Equal(t, int64(6), fastStats.TotalRequests, "fast-site.com should have 6 requests")
}

// TestUS2_Scenario2_UnknownDomainUsesDefaultConfig 驗證 US2 Scenario 2:
// 未配置網域使用預設規則（1 req/s, burst 1）
func TestUS2_Scenario2_UnknownDomainUsesDefaultConfig(t *testing.T) {
	// Arrange: 建立限流器，只配置一個網域，設定預設配置為 1 req/s
	configs := map[string]ratelimit.LimitConfig{
		"javdb.com": {
			RequestsPerSecond: 2.0, // 已配置: 2 req/s
			BurstCapacity:     1,
		},
	}
	defaultConfig := ratelimit.LimitConfig{
		RequestsPerSecond: 1.0, // 預設: 1 req/s
		BurstCapacity:     1,
	}
	limiter := ratelimit.New(configs, defaultConfig)
	defer limiter.Close()

	ctx := context.Background()

	// Act: 請求未配置的網域
	start := time.Now()
	for i := 0; i < 3; i++ {
		err := limiter.Wait(ctx, "unknown-site.com")
		require.NoError(t, err, "Wait should not return error")
	}
	unknownElapsed := time.Since(start)

	// Assert: 驗證使用預設配置（1 req/s）
	// 3 個請求 = 0s + 1s + 1s = ~2s
	assert.InDelta(t, 2000, unknownElapsed.Milliseconds(), 100,
		"Unknown domain should use default config (1 req/s), 3 requests ~2s (±100ms)")

	// 驗證統計資訊
	stats, err := limiter.GetStats("unknown-site.com")
	require.NoError(t, err, "Should have stats for unknown domain")
	assert.Equal(t, int64(3), stats.TotalRequests, "Should record 3 requests for unknown domain")

	// 驗證已配置網域不受影響
	start = time.Now()
	for i := 0; i < 3; i++ {
		err := limiter.Wait(ctx, "javdb.com")
		require.NoError(t, err)
	}
	javdbElapsed := time.Since(start)

	// JAVDB 使用 2 req/s，3 個請求 = 0s + 0.5s + 0.5s = ~1s
	assert.InDelta(t, 1000, javdbElapsed.Milliseconds(), 100,
		"JAVDB should still use configured rate (2 req/s), 3 requests ~1s (±100ms)")
}

// TestUS2_EdgeCase_LoadFromConfigFile 驗證從配置檔案載入
func TestUS2_EdgeCase_LoadFromConfigFile(t *testing.T) {
	// Arrange: 建立臨時配置檔案
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.json")

	configContent := `{
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
				"burst_capacity": 1
			}
		}
	}`

	err := os.WriteFile(configPath, []byte(configContent), 0644)
	require.NoError(t, err, "Should create config file")

	// Act: 從配置檔案建立限流器
	limiter, err := ratelimit.NewFromConfig(configPath)
	require.NoError(t, err, "Should create limiter from config file")
	defer limiter.Close()

	ctx := context.Background()

	// 測試 JAVDB (1 req/s)
	start := time.Now()
	for i := 0; i < 2; i++ {
		err := limiter.Wait(ctx, "javdb.com")
		require.NoError(t, err)
	}
	javdbElapsed := time.Since(start)

	// Assert: 驗證載入的配置正確
	assert.InDelta(t, 1000, javdbElapsed.Milliseconds(), 100,
		"JAVDB from config should be 1 req/s, 2 requests ~1s (±100ms)")

	// 測試 AV-WIKI (2 req/s)
	start = time.Now()
	for i := 0; i < 2; i++ {
		err := limiter.Wait(ctx, "av-wiki.net")
		require.NoError(t, err)
	}
	avwikiElapsed := time.Since(start)

	assert.InDelta(t, 500, avwikiElapsed.Milliseconds(), 100,
		"AV-WIKI from config should be 2 req/s, 2 requests ~0.5s (±100ms)")

	// 驗證統計資訊
	allStats := limiter.GetAllStats()
	require.Len(t, allStats, 2, "Should have stats for 2 configured domains")
}

// TestUS2_EdgeCase_ConcurrentAccessToUnknownDomain 驗證並發存取未配置網域的執行緒安全性
func TestUS2_EdgeCase_ConcurrentAccessToUnknownDomain(t *testing.T) {
	// Arrange: 建立限流器，不預先配置任何網域
	limiter := ratelimit.New(map[string]ratelimit.LimitConfig{}, ratelimit.DefaultConfig)
	defer limiter.Close()

	ctx := context.Background()

	// Act: 並發存取未配置的網域
	g, gctx := errgroup.WithContext(ctx)

	for i := 0; i < 10; i++ {
		g.Go(func() error {
			return limiter.Wait(gctx, "concurrent-unknown.com")
		})
	}

	err := g.Wait()
	require.NoError(t, err, "All concurrent requests should succeed")

	// Assert: 驗證只建立了一個 limiter（不重複建立）
	stats, err := limiter.GetStats("concurrent-unknown.com")
	require.NoError(t, err)
	assert.Equal(t, int64(10), stats.TotalRequests, "Should record exactly 10 requests")

	// 驗證 GetAllStats 只返回一個網域的統計
	allStats := limiter.GetAllStats()
	require.Len(t, allStats, 1, "Should have stats for only 1 domain (no duplicate limiters)")
}

// ============================================================================
// US3 Integration Tests - 爬蟲任務可控中斷
// ============================================================================

// TestUS3_Scenario1_CancelQueuedRequests 驗證 US3 Scenario 1:
// 排隊 50 個請求，中途取消，驗證停止行為
func TestUS3_Scenario1_CancelQueuedRequests(t *testing.T) {
	// Arrange: 建立限流器，配置非常慢的速率
	configs := map[string]ratelimit.LimitConfig{
		"slow-site.com": {
			RequestsPerSecond: 2.0, // 2 req/s，50 個請求需要 ~25 秒
			BurstCapacity:     1,
		},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)
	defer limiter.Close()

	// 建立可取消的 context
	ctx, cancel := context.WithCancel(context.Background())

	// Act: 使用 errgroup 並發發送 50 個請求
	g, gctx := errgroup.WithContext(ctx)

	successCount := int64(0)
	canceledCount := int64(0)
	var mu sync.Mutex

	for i := 0; i < 50; i++ {
		g.Go(func() error {
			err := limiter.Wait(gctx, "slow-site.com")
			mu.Lock()
			defer mu.Unlock()
			if err == nil {
				successCount++
			} else if err == context.Canceled {
				canceledCount++
			}
			return nil // 不返回錯誤，讓所有 goroutine 完成
		})
	}

	// 等待一小段時間讓一些請求通過，然後取消
	time.Sleep(1 * time.Second)
	cancel()

	// 等待所有 goroutine 完成
	g.Wait()

	// Assert: 驗證行為
	mu.Lock()
	defer mu.Unlock()

	// 應該有一些請求成功（大約 2-4 個，因為等了 1 秒）
	assert.Greater(t, successCount, int64(0), "Some requests should succeed before cancellation")
	assert.Less(t, successCount, int64(10), "Not too many requests should succeed")

	// 應該有大量請求被取消
	assert.Greater(t, canceledCount, int64(30), "Most requests should be canceled")

	// 總數應該是 50
	assert.Equal(t, int64(50), successCount+canceledCount, "Total should be 50 requests")

	// 驗證統計只記錄成功的請求
	stats, err := limiter.GetStats("slow-site.com")
	require.NoError(t, err)
	assert.Equal(t, successCount, stats.TotalRequests, "Stats should only count successful requests")
}

// TestUS3_Scenario2_CloseAndRecreate 驗證 US3 Scenario 2:
// Close 後重新建立限流器，驗證狀態重置
func TestUS3_Scenario2_CloseAndRecreate(t *testing.T) {
	// Arrange: 建立第一個限流器
	configs := map[string]ratelimit.LimitConfig{
		"test-site.com": {
			RequestsPerSecond: 2.0,
			BurstCapacity:     1,
		},
	}
	limiter1 := ratelimit.New(configs, ratelimit.DefaultConfig)

	ctx := context.Background()

	// Act: 發送一些請求
	require.NoError(t, limiter1.Wait(ctx, "test-site.com"))
	require.NoError(t, limiter1.Wait(ctx, "test-site.com"))
	require.NoError(t, limiter1.Wait(ctx, "test-site.com"))

	// 檢查統計
	stats1, err := limiter1.GetStats("test-site.com")
	require.NoError(t, err)
	assert.Equal(t, int64(3), stats1.TotalRequests, "First limiter should have 3 requests")

	// Close 第一個限流器
	err = limiter1.Close()
	require.NoError(t, err, "Close should succeed")

	// 驗證 Close 後無法使用
	err = limiter1.Wait(ctx, "test-site.com")
	assert.Error(t, err, "Wait after Close should return error")

	// 建立第二個限流器（使用相同配置）
	limiter2 := ratelimit.New(configs, ratelimit.DefaultConfig)
	defer limiter2.Close()

	// 發送請求到第二個限流器
	require.NoError(t, limiter2.Wait(ctx, "test-site.com"))
	require.NoError(t, limiter2.Wait(ctx, "test-site.com"))

	// Assert: 驗證狀態已重置
	stats2, err := limiter2.GetStats("test-site.com")
	require.NoError(t, err)
	assert.Equal(t, int64(2), stats2.TotalRequests, "Second limiter should have fresh stats (2 requests)")
	assert.NotEqual(t, stats1.TotalRequests, stats2.TotalRequests, "Stats should be independent")
}

// TestUS3_EdgeCase_CloseIdempotent 驗證 Close 方法是冪等的
func TestUS3_EdgeCase_CloseIdempotent(t *testing.T) {
	// Arrange: 建立限流器
	limiter := ratelimit.New(map[string]ratelimit.LimitConfig{}, ratelimit.DefaultConfig)

	// Act: 多次呼叫 Close
	err1 := limiter.Close()
	err2 := limiter.Close()
	err3 := limiter.Close()

	// Assert: 所有呼叫都應該成功（冪等）
	assert.NoError(t, err1, "First Close should succeed")
	assert.NoError(t, err2, "Second Close should succeed (idempotent)")
	assert.NoError(t, err3, "Third Close should succeed (idempotent)")
}

// TestUS3_EdgeCase_ContextDeadlineVsCancellation 驗證 Context deadline 和取消的區別
func TestUS3_EdgeCase_ContextDeadlineVsCancellation(t *testing.T) {
	// Arrange: 建立限流器，配置慢速率
	configs := map[string]ratelimit.LimitConfig{
		"slow.com": {
			RequestsPerSecond: 0.5, // 2 秒 1 個請求
			BurstCapacity:     1,
		},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)
	defer limiter.Close()

	// Test 1: Context with timeout
	ctx1, cancel1 := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel1()

	// 第一個請求成功（使用 burst）
	err := limiter.Wait(ctx1, "slow.com")
	require.NoError(t, err, "First request should succeed")

	// 第二個請求應該因為 deadline 而失敗
	start := time.Now()
	err = limiter.Wait(ctx1, "slow.com")
	elapsed := time.Since(start)

	assert.Error(t, err, "Second request should fail due to timeout")
	// rate.Limiter.Wait() 會立即檢測到無法在 deadline 內完成
	assert.Less(t, elapsed.Milliseconds(), int64(200),
		"Should fail quickly when deadline cannot be met")

	// Test 2: Explicit cancellation
	ctx2, cancel2 := context.WithCancel(context.Background())

	// 在另一個 goroutine 中延遲取消
	go func() {
		time.Sleep(50 * time.Millisecond)
		cancel2()
	}()

	// 第三個請求（需要等待約 2 秒）
	start = time.Now()
	err = limiter.Wait(ctx2, "slow.com")
	elapsed = time.Since(start)

	assert.Error(t, err, "Request should fail due to cancellation")
	assert.Less(t, elapsed.Milliseconds(), int64(200),
		"Should fail quickly after cancellation")
}

// TestUS3_Integration_RealWorldScraperScenario 驗證真實爬蟲場景
func TestUS3_Integration_RealWorldScraperScenario(t *testing.T) {
	// Arrange: 模擬真實爬蟲場景
	// - JAVDB: 1 req/s（嚴格限流）
	// - AV-WIKI: 2 req/s（較寬鬆）
	configs := map[string]ratelimit.LimitConfig{
		"javdb.com":   {RequestsPerSecond: 1.0, BurstCapacity: 1},
		"av-wiki.net": {RequestsPerSecond: 2.0, BurstCapacity: 1},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)
	defer limiter.Close()

	// 建立可取消的 context（模擬用戶中斷）
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	// Act: 並行爬取兩個網站
	g, gctx := errgroup.WithContext(ctx)

	var javdbSuccess, javdbFailed int64
	var avwikiSuccess, avwikiFailed int64
	var mu sync.Mutex

	// 爬取 JAVDB（嘗試 20 個請求）
	for i := 0; i < 20; i++ {
		g.Go(func() error {
			err := limiter.Wait(gctx, "javdb.com")
			mu.Lock()
			defer mu.Unlock()
			if err == nil {
				javdbSuccess++
			} else {
				javdbFailed++
			}
			return nil
		})
	}

	// 爬取 AV-WIKI（嘗試 20 個請求）
	for i := 0; i < 20; i++ {
		g.Go(func() error {
			err := limiter.Wait(gctx, "av-wiki.net")
			mu.Lock()
			defer mu.Unlock()
			if err == nil {
				avwikiSuccess++
			} else {
				avwikiFailed++
			}
			return nil
		})
	}

	// 等待所有任務完成或超時
	g.Wait()

	// Assert: 驗證行為
	mu.Lock()
	defer mu.Unlock()

	// JAVDB 應該完成約 3-4 個請求（1 req/s * 3s）
	assert.InDelta(t, 3, javdbSuccess, 2, "JAVDB should complete ~3 requests in 3 seconds")
	assert.Greater(t, javdbFailed, int64(10), "Most JAVDB requests should be canceled")

	// AV-WIKI 應該完成約 6-8 個請求（2 req/s * 3s）
	assert.InDelta(t, 6, avwikiSuccess, 3, "AV-WIKI should complete ~6 requests in 3 seconds")
	assert.Greater(t, avwikiFailed, int64(10), "Some AV-WIKI requests should be canceled")

	// 驗證統計
	javdbStats, err := limiter.GetStats("javdb.com")
	require.NoError(t, err)
	assert.Equal(t, javdbSuccess, javdbStats.TotalRequests, "Stats should match successful requests")

	avwikiStats, err := limiter.GetStats("av-wiki.net")
	require.NoError(t, err)
	assert.Equal(t, avwikiSuccess, avwikiStats.TotalRequests, "Stats should match successful requests")

	t.Logf("JAVDB: %d success, %d failed", javdbSuccess, javdbFailed)
	t.Logf("AV-WIKI: %d success, %d failed", avwikiSuccess, avwikiFailed)
}

// ============================================================================
// US4 Integration Tests - 限流統計和監控
// ============================================================================

// TestUS4_Scenario1_StatisticsAccuracy 驗證 US4 Scenario 1:
// 執行 50 個請求，驗證統計準確性
func TestUS4_Scenario1_StatisticsAccuracy(t *testing.T) {
	// Arrange: 建立限流器，配置為 10 req/s（快速完成測試）
	configs := map[string]ratelimit.LimitConfig{
		"test-site.com": {
			RequestsPerSecond: 10.0,
			BurstCapacity:     5, // Burst 5 個
		},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)
	defer limiter.Close()

	ctx := context.Background()

	// Act: 執行 50 個請求
	const totalRequests = 50
	start := time.Now()

	for i := 0; i < totalRequests; i++ {
		err := limiter.Wait(ctx, "test-site.com")
		require.NoError(t, err, "Request %d should succeed", i+1)
	}

	totalElapsed := time.Since(start)

	// 取得統計
	stats, err := limiter.GetStats("test-site.com")
	require.NoError(t, err, "GetStats should succeed")

	// Assert: 驗證統計準確性（100% 準確）
	assert.Equal(t, int64(totalRequests), stats.TotalRequests,
		"TotalRequests should be exactly %d", totalRequests)

	// 計算預期的延遲請求數
	// Burst capacity = 5，所以前 5 個請求立即通過，後 45 個需要等待
	expectedDelayed := int64(totalRequests - 5)
	assert.Equal(t, expectedDelayed, stats.DelayedRequests,
		"DelayedRequests should be exactly %d (total - burst)", expectedDelayed)

	// 驗證 DelayRate 計算
	expectedDelayRate := float64(expectedDelayed) / float64(totalRequests)
	assert.InDelta(t, expectedDelayRate, stats.DelayRate, 0.001,
		"DelayRate should be %.4f", expectedDelayRate)

	// 驗證 TotalWaitTime > 0（有延遲）
	assert.Greater(t, stats.TotalWaitTime.Milliseconds(), int64(0),
		"TotalWaitTime should be greater than 0")

	// 驗證 AvgWaitTime 計算
	expectedAvgWaitTime := stats.TotalWaitTime / time.Duration(expectedDelayed)
	assert.Equal(t, expectedAvgWaitTime, stats.AvgWaitTime,
		"AvgWaitTime should match calculation")

	// 驗證總時間合理（50 個請求，10 req/s，預期約 5 秒）
	// 前 5 個立即通過（使用 burst），後 45 個以 10 req/s 的速度，需要 4.5 秒
	assert.InDelta(t, 4500, totalElapsed.Milliseconds(), 500,
		"Total time should be ~4.5s for 50 requests at 10 req/s with burst 5")

	// 驗證 LastRequestTime 更新
	assert.WithinDuration(t, time.Now(), stats.LastRequestTime, 1*time.Second,
		"LastRequestTime should be recent")

	t.Logf("Statistics Summary:")
	t.Logf("  Total Requests: %d", stats.TotalRequests)
	t.Logf("  Delayed Requests: %d", stats.DelayedRequests)
	t.Logf("  Delay Rate: %.2f%%", stats.DelayRate*100)
	t.Logf("  Total Wait Time: %v", stats.TotalWaitTime)
	t.Logf("  Avg Wait Time: %v", stats.AvgWaitTime)
	t.Logf("  Total Elapsed: %v", totalElapsed)
}

// TestUS4_Scenario2_MultiDomainStatisticsIndependence 驗證 US4 Scenario 2:
// 多網域統計獨立性
func TestUS4_Scenario2_MultiDomainStatisticsIndependence(t *testing.T) {
	// Arrange: 建立限流器，配置三個網域
	configs := map[string]ratelimit.LimitConfig{
		"site-a.com": {RequestsPerSecond: 5.0, BurstCapacity: 2},
		"site-b.com": {RequestsPerSecond: 10.0, BurstCapacity: 3},
		"site-c.com": {RequestsPerSecond: 2.0, BurstCapacity: 1},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)
	defer limiter.Close()

	ctx := context.Background()

	// Act: 並行發送不同數量的請求到各個網域
	g, gctx := errgroup.WithContext(ctx)

	// Site A: 10 個請求
	g.Go(func() error {
		for i := 0; i < 10; i++ {
			if err := limiter.Wait(gctx, "site-a.com"); err != nil {
				return err
			}
		}
		return nil
	})

	// Site B: 20 個請求
	g.Go(func() error {
		for i := 0; i < 20; i++ {
			if err := limiter.Wait(gctx, "site-b.com"); err != nil {
				return err
			}
		}
		return nil
	})

	// Site C: 5 個請求
	g.Go(func() error {
		for i := 0; i < 5; i++ {
			if err := limiter.Wait(gctx, "site-c.com"); err != nil {
				return err
			}
		}
		return nil
	})

	err := g.Wait()
	require.NoError(t, err, "All requests should succeed")

	// 取得所有統計
	allStats := limiter.GetAllStats()

	// Assert: 驗證統計獨立性
	require.Len(t, allStats, 3, "Should have stats for 3 domains")

	// Site A: 10 個請求，burst 2，延遲 8 個
	statsA := allStats["site-a.com"]
	require.NotNil(t, statsA, "Site A stats should exist")
	assert.Equal(t, int64(10), statsA.TotalRequests, "Site A should have 10 requests")
	assert.Equal(t, int64(8), statsA.DelayedRequests, "Site A should have 8 delayed requests")
	assert.InDelta(t, 0.80, statsA.DelayRate, 0.01, "Site A delay rate should be 80%")

	// Site B: 20 個請求，burst 3，延遲 17 個
	statsB := allStats["site-b.com"]
	require.NotNil(t, statsB, "Site B stats should exist")
	assert.Equal(t, int64(20), statsB.TotalRequests, "Site B should have 20 requests")
	assert.Equal(t, int64(17), statsB.DelayedRequests, "Site B should have 17 delayed requests")
	assert.InDelta(t, 0.85, statsB.DelayRate, 0.01, "Site B delay rate should be 85%")

	// Site C: 5 個請求，burst 1，延遲 4 個
	statsC := allStats["site-c.com"]
	require.NotNil(t, statsC, "Site C stats should exist")
	assert.Equal(t, int64(5), statsC.TotalRequests, "Site C should have 5 requests")
	assert.Equal(t, int64(4), statsC.DelayedRequests, "Site C should have 4 delayed requests")
	assert.InDelta(t, 0.80, statsC.DelayRate, 0.01, "Site C delay rate should be 80%")

	// 驗證統計彼此獨立（總數不相等）
	assert.NotEqual(t, statsA.TotalRequests, statsB.TotalRequests, "Stats should be independent")
	assert.NotEqual(t, statsB.TotalRequests, statsC.TotalRequests, "Stats should be independent")

	t.Logf("Site A: Total=%d, Delayed=%d, Rate=%.2f%%",
		statsA.TotalRequests, statsA.DelayedRequests, statsA.DelayRate*100)
	t.Logf("Site B: Total=%d, Delayed=%d, Rate=%.2f%%",
		statsB.TotalRequests, statsB.DelayedRequests, statsB.DelayRate*100)
	t.Logf("Site C: Total=%d, Delayed=%d, Rate=%.2f%%",
		statsC.TotalRequests, statsC.DelayedRequests, statsC.DelayRate*100)
}

// TestUS4_EdgeCase_ZeroDivisionProtection 驗證除以零保護
func TestUS4_EdgeCase_ZeroDivisionProtection(t *testing.T) {
	// Arrange: 建立限流器但不發送任何請求
	limiter := ratelimit.New(map[string]ratelimit.LimitConfig{
		"empty-site.com": {RequestsPerSecond: 1.0, BurstCapacity: 1},
	}, ratelimit.DefaultConfig)
	defer limiter.Close()

	// Act: 取得統計（沒有請求）
	stats, err := limiter.GetStats("empty-site.com")
	require.NoError(t, err, "GetStats should succeed even with no requests")

	// Assert: 驗證除以零保護
	assert.Equal(t, int64(0), stats.TotalRequests, "TotalRequests should be 0")
	assert.Equal(t, int64(0), stats.DelayedRequests, "DelayedRequests should be 0")
	assert.Equal(t, float64(0), stats.DelayRate, "DelayRate should be 0 (not NaN)")
	assert.Equal(t, time.Duration(0), stats.AvgWaitTime, "AvgWaitTime should be 0 (not division by zero)")
}

// TestUS4_EdgeCase_OnlyImmediateRequests 驗證只有立即請求的情況
func TestUS4_EdgeCase_OnlyImmediateRequests(t *testing.T) {
	// Arrange: 建立限流器，burst capacity 很大
	configs := map[string]ratelimit.LimitConfig{
		"high-burst.com": {
			RequestsPerSecond: 1.0,
			BurstCapacity:     100, // 足夠容納所有請求
		},
	}
	limiter := ratelimit.New(configs, ratelimit.DefaultConfig)
	defer limiter.Close()

	ctx := context.Background()

	// Act: 發送 50 個請求（都應該立即通過）
	for i := 0; i < 50; i++ {
		err := limiter.Wait(ctx, "high-burst.com")
		require.NoError(t, err)
	}

	stats, err := limiter.GetStats("high-burst.com")
	require.NoError(t, err)

	// Assert: 所有請求都應該是立即的（無延遲）
	assert.Equal(t, int64(50), stats.TotalRequests, "Should have 50 requests")
	assert.Equal(t, int64(0), stats.DelayedRequests, "No requests should be delayed")
	assert.Equal(t, float64(0), stats.DelayRate, "DelayRate should be 0%")
	assert.Equal(t, time.Duration(0), stats.TotalWaitTime, "TotalWaitTime should be 0")
	assert.Equal(t, time.Duration(0), stats.AvgWaitTime, "AvgWaitTime should be 0 (no delayed requests)")
}

// TestUS4_Integration_StatisticsSnapshot 驗證統計快照的不變性
func TestUS4_Integration_StatisticsSnapshot(t *testing.T) {
	// Arrange: 建立限流器
	limiter := ratelimit.New(map[string]ratelimit.LimitConfig{
		"test.com": {RequestsPerSecond: 5.0, BurstCapacity: 1},
	}, ratelimit.DefaultConfig)
	defer limiter.Close()

	ctx := context.Background()

	// Act: 發送 5 個請求
	for i := 0; i < 5; i++ {
		err := limiter.Wait(ctx, "test.com")
		require.NoError(t, err)
	}

	// 取得第一個快照
	snapshot1, err := limiter.GetStats("test.com")
	require.NoError(t, err)

	// 再發送 5 個請求
	for i := 0; i < 5; i++ {
		err := limiter.Wait(ctx, "test.com")
		require.NoError(t, err)
	}

	// 取得第二個快照
	snapshot2, err := limiter.GetStats("test.com")
	require.NoError(t, err)

	// Assert: 驗證快照不變性
	// 第一個快照應該保持不變
	assert.Equal(t, int64(5), snapshot1.TotalRequests, "Snapshot1 should remain unchanged")
	
	// 第二個快照應該反映新的請求
	assert.Equal(t, int64(10), snapshot2.TotalRequests, "Snapshot2 should show 10 requests")
	
	// 快照應該是獨立的
	assert.NotEqual(t, snapshot1.TotalRequests, snapshot2.TotalRequests,
		"Snapshots should be independent")

	t.Logf("Snapshot1: Total=%d, Delayed=%d", snapshot1.TotalRequests, snapshot1.DelayedRequests)
	t.Logf("Snapshot2: Total=%d, Delayed=%d", snapshot2.TotalRequests, snapshot2.DelayedRequests)
}
