package contracts

import "time"

// MoveLog 定義 history CLI 中單一項目的 JSON DTO。
type MoveLog struct {
	Source      string `json:"source"`
	Destination string `json:"destination"`
	Status      string `json:"status"`
	Error       string `json:"error,omitempty"`
}

// OperationLog 定義 history CLI 的 JSON 輸出 DTO。
type OperationLog struct {
	ID           string    `json:"id"`
	Timestamp    time.Time `json:"timestamp"`
	Type         string    `json:"type"`
	Items        []MoveLog `json:"items"`
	TotalItems   int       `json:"total_items"`
	SuccessCount int       `json:"success_count"`
	FailedCount  int       `json:"failed_count"`
	SkippedCount int       `json:"skipped_count"`
	Status       string    `json:"status"`
}
