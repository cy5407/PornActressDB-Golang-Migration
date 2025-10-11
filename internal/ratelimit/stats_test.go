package ratelimit_test

import (
	"sync"
	"testing"
	"time"

	"actress-classifier/internal/ratelimit"

	"github.com/stretchr/testify/assert"
)

func TestLimitStats_BasicOperations(t *testing.T) {
	stats := ratelimit.NewLimitStats()

	// 初始狀態應該為零
	snapshot := stats.Snapshot()
	assert.Equal(t, int64(0), snapshot.TotalRequests)
	assert.Equal(t, int64(0), snapshot.DelayedRequests)
	assert.Equal(t, time.Duration(0), snapshot.TotalWaitTime)
	assert.Equal(t, 0.0, snapshot.DelayRate)
	assert.Equal(t, time.Duration(0), snapshot.AvgWaitTime)

	// 測試 IncrementTotal
	stats.IncrementTotal()
	snapshot = stats.Snapshot()
	assert.Equal(t, int64(1), snapshot.TotalRequests)

	// 測試 RecordDelay
	stats.RecordDelay(100 * time.Millisecond)
	snapshot = stats.Snapshot()
	assert.Equal(t, int64(1), snapshot.DelayedRequests)
	assert.Equal(t, 100*time.Millisecond, snapshot.TotalWaitTime)

	// 測試 UpdateLastRequestTime
	now := time.Now()
	stats.UpdateLastRequestTime(now)
	snapshot = stats.Snapshot()
	assert.Equal(t, now, snapshot.LastRequestTime)
}

func TestLimitStats_DerivedMetrics(t *testing.T) {
	stats := ratelimit.NewLimitStats()

	// 測試延遲率計算
	stats.IncrementTotal()
	stats.IncrementTotal()
	stats.IncrementTotal()
	stats.IncrementTotal() // 總共 4 個請求

	stats.RecordDelay(100 * time.Millisecond)
	stats.RecordDelay(200 * time.Millisecond) // 2 個延遲

	snapshot := stats.Snapshot()
	assert.Equal(t, int64(4), snapshot.TotalRequests)
	assert.Equal(t, int64(2), snapshot.DelayedRequests)
	assert.Equal(t, 0.5, snapshot.DelayRate)                    // 2/4 = 0.5
	assert.Equal(t, 150*time.Millisecond, snapshot.AvgWaitTime) // (100+200)/2 = 150ms
}

func TestLimitStats_EdgeCases(t *testing.T) {
	stats := ratelimit.NewLimitStats()

	// 測試除以零的情況
	snapshot := stats.Snapshot()
	assert.Equal(t, 0.0, snapshot.DelayRate) // 0/0 應該是 0
	assert.Equal(t, time.Duration(0), snapshot.AvgWaitTime)

	// 只有總請求，沒有延遲
	stats.IncrementTotal()
	stats.IncrementTotal()
	snapshot = stats.Snapshot()
	assert.Equal(t, 0.0, snapshot.DelayRate) // 0/2 = 0
	assert.Equal(t, time.Duration(0), snapshot.AvgWaitTime)

	// 有延遲但沒有總請求（理論上不應該發生，但要測試）
	stats.Reset()
	stats.RecordDelay(100 * time.Millisecond)
	snapshot = stats.Snapshot()
	assert.Equal(t, int64(0), snapshot.TotalRequests)
	assert.Equal(t, int64(1), snapshot.DelayedRequests)
	// DelayRate 應該是 0（因為 totalRequests 為 0）
	// 但這種情況在實際使用中不應該出現
}

func TestLimitStats_Concurrency(t *testing.T) {
	stats := ratelimit.NewLimitStats()
	const goroutines = 100
	const iterations = 100

	var wg sync.WaitGroup

	// 並發遞增總請求數
	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < iterations; j++ {
				stats.IncrementTotal()
			}
		}()
	}

	// 並發記錄延遲
	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < iterations; j++ {
				stats.RecordDelay(10 * time.Millisecond)
			}
		}()
	}

	// 並發更新最後請求時間
	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < iterations; j++ {
				stats.UpdateLastRequestTime(time.Now())
			}
		}()
	}

	// 並發讀取快照
	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < iterations; j++ {
				_ = stats.Snapshot()
			}
		}()
	}

	wg.Wait()

	// 驗證結果
	snapshot := stats.Snapshot()
	assert.Equal(t, int64(goroutines*iterations), snapshot.TotalRequests)
	assert.Equal(t, int64(goroutines*iterations), snapshot.DelayedRequests)

	// 總等待時間應該是 10ms * goroutines * iterations
	expectedWaitTime := time.Duration(goroutines*iterations) * 10 * time.Millisecond
	assert.Equal(t, expectedWaitTime, snapshot.TotalWaitTime)
}

func TestLimitStats_Reset(t *testing.T) {
	stats := ratelimit.NewLimitStats()

	// 設定一些數據
	stats.IncrementTotal()
	stats.IncrementTotal()
	stats.RecordDelay(100 * time.Millisecond)
	stats.UpdateLastRequestTime(time.Now())

	// 重置
	stats.Reset()

	// 驗證所有欄位都被重置
	snapshot := stats.Snapshot()
	assert.Equal(t, int64(0), snapshot.TotalRequests)
	assert.Equal(t, int64(0), snapshot.DelayedRequests)
	assert.Equal(t, time.Duration(0), snapshot.TotalWaitTime)
	assert.True(t, snapshot.LastRequestTime.IsZero())
	assert.Equal(t, 0.0, snapshot.DelayRate)
	assert.Equal(t, time.Duration(0), snapshot.AvgWaitTime)
}

func TestLimitStats_SnapshotIsolation(t *testing.T) {
	stats := ratelimit.NewLimitStats()

	stats.IncrementTotal()
	stats.RecordDelay(100 * time.Millisecond)

	// 取得快照
	snapshot1 := stats.Snapshot()

	// 修改統計
	stats.IncrementTotal()
	stats.RecordDelay(200 * time.Millisecond)

	// 取得新快照
	snapshot2 := stats.Snapshot()

	// 驗證第一個快照沒有被修改
	assert.Equal(t, int64(1), snapshot1.TotalRequests)
	assert.Equal(t, int64(1), snapshot1.DelayedRequests)
	assert.Equal(t, 100*time.Millisecond, snapshot1.TotalWaitTime)

	// 驗證第二個快照有新數據
	assert.Equal(t, int64(2), snapshot2.TotalRequests)
	assert.Equal(t, int64(2), snapshot2.DelayedRequests)
	assert.Equal(t, 300*time.Millisecond, snapshot2.TotalWaitTime)
}

func TestLimitStats_MultipleDelays(t *testing.T) {
	stats := ratelimit.NewLimitStats()

	// 記錄多個不同的延遲時間
	delays := []time.Duration{
		50 * time.Millisecond,
		100 * time.Millisecond,
		150 * time.Millisecond,
		200 * time.Millisecond,
	}

	for _, delay := range delays {
		stats.IncrementTotal()
		stats.RecordDelay(delay)
	}

	snapshot := stats.Snapshot()

	// 總請求數
	assert.Equal(t, int64(4), snapshot.TotalRequests)
	assert.Equal(t, int64(4), snapshot.DelayedRequests)

	// 總等待時間 = 50 + 100 + 150 + 200 = 500ms
	assert.Equal(t, 500*time.Millisecond, snapshot.TotalWaitTime)

	// 平均等待時間 = 500 / 4 = 125ms
	assert.Equal(t, 125*time.Millisecond, snapshot.AvgWaitTime)

	// 延遲率 = 4/4 = 1.0 (100%)
	assert.Equal(t, 1.0, snapshot.DelayRate)
}
