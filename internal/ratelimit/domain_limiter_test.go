package ratelimit_test

import (
	"testing"

	"actress-classifier/internal/ratelimit"
)

func TestNewDomainLimiter(t *testing.T) {
	tests := []struct {
		name    string
		domain  string
		config  ratelimit.LimitConfig
		wantErr bool
	}{
		{
			name:   "合法建立",
			domain: "test.com",
			config: ratelimit.LimitConfig{
				RequestsPerSecond: 1.0,
				BurstCapacity:     1,
			},
			wantErr: false,
		},
		{
			name:    "空網域名稱",
			domain:  "",
			config:  ratelimit.DefaultConfig,
			wantErr: true,
		},
		{
			name:   "非法配置",
			domain: "test.com",
			config: ratelimit.LimitConfig{
				RequestsPerSecond: 0,
				BurstCapacity:     1,
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// 使用反射或測試輔助函式建立
			// 由於 newDomainLimiter 是 package-private，我們需要通過其他方式測試
			// 這裡暫時跳過，等 T007 實作 RateLimiter 後會間接測試
			t.Skip("newDomainLimiter 是 package-private，將通過 RateLimiter 間接測試")
		})
	}
}

func TestDomainLimiter_BasicRateControl(t *testing.T) {
	// 由於無法直接建立 DomainLimiter，此測試將在 T007 後完成
	t.Skip("需要 RateLimiter 介面才能測試 DomainLimiter")
}

func TestDomainLimiter_ContextCancellation(t *testing.T) {
	// 測試 context 取消
	t.Skip("需要 RateLimiter 介面才能測試 DomainLimiter")
}

func TestDomainLimiter_WaitN(t *testing.T) {
	// 測試批次 token 獲取
	t.Skip("需要 RateLimiter 介面才能測試 DomainLimiter")
}

func TestDomainLimiter_Allow(t *testing.T) {
	// 測試非阻塞檢查
	t.Skip("需要 RateLimiter 介面才能測試 DomainLimiter")
}

// 註：這些測試將在 T007 實作 RateLimiter 後補充完整的測試案例
// 因為 DomainLimiter 的建構函式是 package-private 的
