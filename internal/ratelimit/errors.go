package ratelimit

import "errors"

// 錯誤定義
var (
	// ErrInvalidConfig 配置無效
	ErrInvalidConfig = errors.New("配置無效")

	// ErrInvalidDomain 網域名稱無效
	ErrInvalidDomain = errors.New("網域名稱無效")

	// ErrLimiterClosed 限流器已關閉
	ErrLimiterClosed = errors.New("限流器已關閉")

	// ErrDomainNotFound 網域不存在
	ErrDomainNotFound = errors.New("網域不存在")
)
