// Package mover 提供檔案移動和合併功能
package mover

import "time"

// ConflictStrategy 定義衝突處理策略
type ConflictStrategy string

const (
	Skip      ConflictStrategy = "skip"      // 跳過
	Overwrite ConflictStrategy = "overwrite" // 覆蓋
	Rename    ConflictStrategy = "rename"    // 重命名
	Merge     ConflictStrategy = "merge"     // 合併到子目錄
)

// MoveItem 表示單一移動項目
type MoveItem struct {
	Source      string           `json:"source"`
	Destination string           `json:"destination"`
	OnConflict  ConflictStrategy `json:"on_conflict,omitempty"`
}

// MoveResult 表示移動結果
type MoveResult struct {
	Source      string `json:"source"`
	Destination string `json:"destination"`
	Success     bool   `json:"success"`
	Error       string `json:"error,omitempty"`
	Skipped     bool   `json:"skipped,omitempty"`
	Renamed     string `json:"renamed,omitempty"`
}

// MergeResult 表示資料夾合併結果
type MergeResult struct {
	SourceDir  string       `json:"source_dir"`
	DestDir    string       `json:"dest_dir"`
	FilesMoved int          `json:"files_moved"`
	FilesTotal int          `json:"files_total"`
	Errors     []MoveResult `json:"errors,omitempty"`
	Success    bool         `json:"success"`
	DeletedSrc bool         `json:"deleted_src"`
}

// BatchResult 表示批次移動結果
type BatchResult struct {
	OperationID  string       `json:"operation_id,omitempty"`
	TotalItems   int          `json:"total_items"`
	SuccessCount int          `json:"success_count"`
	FailedCount  int          `json:"failed_count"`
	SkippedCount int          `json:"skipped_count"`
	Results      []MoveResult `json:"results"`
	Status       string       `json:"status,omitempty"`
	Summary      string       `json:"summary,omitempty"`
	Duration     string       `json:"duration"`
}

// MoveLog 記錄單一移動操作
type MoveLog struct {
	Source      string `json:"source"`
	Destination string `json:"destination"`
	Status      string `json:"status"` // pending, success, failed, rolled_back
	Error       string `json:"error,omitempty"`
}

// OperationLog 記錄批次操作
type OperationLog struct {
	ID           string    `json:"id"`
	Timestamp    time.Time `json:"timestamp"`
	Type         string    `json:"type"` // batch_move, rollback, merge
	Items        []MoveLog `json:"items"`
	TotalItems   int       `json:"total_items"`
	SuccessCount int       `json:"success_count"`
	FailedCount  int       `json:"failed_count"`
	SkippedCount int       `json:"skipped_count"`
	Status       string    `json:"status"` // started, completed, partial, failed
}

// Mover 檔案移動器
type Mover struct {
	LogDir          string           // 操作日誌目錄
	DefaultStrategy ConflictStrategy // 預設衝突策略
	DryRun          bool             // 模擬執行模式
}

// NewMover 建立新的移動器
func NewMover(logDir string) *Mover {
	return &Mover{
		LogDir:          logDir,
		DefaultStrategy: Skip,
		DryRun:          false,
	}
}
