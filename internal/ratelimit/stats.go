package ratelimit

import (
	"sync"
	"sync/atomic"
	"time"
)

// LimitStats 統計資訊結構
// 使用 atomic 操作處理計數器，使用 mutex 保護時間戳
type LimitStats struct {
	// 原子計數器（無需 mutex）
	totalRequests   atomic.Int64 // 總請求數
	delayedRequests atomic.Int64 // 被延遲的請求數

	// 需要 mutex 保護的欄位
	mu              sync.Mutex
	totalWaitTime   time.Duration // 總等待時間
	lastRequestTime time.Time     // 最後請求時間
}

// StatsSnapshot 統計資訊快照（只讀）
type StatsSnapshot struct {
	TotalRequests   int64         `json:"total_requests"`    // 總請求數
	DelayedRequests int64         `json:"delayed_requests"`  // 被延遲的請求數
	TotalWaitTime   time.Duration `json:"total_wait_time"`   // 總等待時間（納秒）
	LastRequestTime time.Time     `json:"last_request_time"` // 最後請求時間

	// 衍生指標
	DelayRate   float64       `json:"delay_rate"`    // 延遲率 = DelayedRequests / TotalRequests
	AvgWaitTime time.Duration `json:"avg_wait_time"` // 平均等待時間 = TotalWaitTime / DelayedRequests
}

// NewLimitStats 建立新的統計資訊
func NewLimitStats() *LimitStats {
	return &LimitStats{}
}

// IncrementTotal 原子遞增總請求數
func (s *LimitStats) IncrementTotal() {
	s.totalRequests.Add(1)
}

// RecordDelay 記錄延遲時間（需要 mutex）
func (s *LimitStats) RecordDelay(duration time.Duration) {
	s.delayedRequests.Add(1)

	s.mu.Lock()
	s.totalWaitTime += duration
	s.mu.Unlock()
}

// UpdateLastRequestTime 更新最後請求時間
func (s *LimitStats) UpdateLastRequestTime(t time.Time) {
	s.mu.Lock()
	s.lastRequestTime = t
	s.mu.Unlock()
}

// Snapshot 返回統計資訊快照
func (s *LimitStats) Snapshot() *StatsSnapshot {
	// 讀取原子計數器（無需鎖）
	totalRequests := s.totalRequests.Load()
	delayedRequests := s.delayedRequests.Load()

	// 讀取需要保護的欄位
	s.mu.Lock()
	totalWaitTime := s.totalWaitTime
	lastRequestTime := s.lastRequestTime
	s.mu.Unlock()

	// 計算衍生指標
	var delayRate float64
	if totalRequests > 0 {
		delayRate = float64(delayedRequests) / float64(totalRequests)
	}

	var avgWaitTime time.Duration
	if delayedRequests > 0 {
		avgWaitTime = totalWaitTime / time.Duration(delayedRequests)
	}

	return &StatsSnapshot{
		TotalRequests:   totalRequests,
		DelayedRequests: delayedRequests,
		TotalWaitTime:   totalWaitTime,
		LastRequestTime: lastRequestTime,
		DelayRate:       delayRate,
		AvgWaitTime:     avgWaitTime,
	}
}

// Reset 重置統計資訊（用於測試）
func (s *LimitStats) Reset() {
	s.totalRequests.Store(0)
	s.delayedRequests.Store(0)

	s.mu.Lock()
	s.totalWaitTime = 0
	s.lastRequestTime = time.Time{}
	s.mu.Unlock()
}
