package contracts

// MoveItem 定義 move CLI 接收/輸出的 DTO。
type MoveItem struct {
	Source      string `json:"source"`
	Destination string `json:"destination"`
	OnConflict  string `json:"on_conflict,omitempty"`
}

// MoveResult 定義單檔 move CLI 的 JSON 輸出 DTO。
type MoveResult struct {
	Source      string `json:"source"`
	Destination string `json:"destination"`
	Success     bool   `json:"success"`
	Error       string `json:"error,omitempty"`
	Skipped     bool   `json:"skipped,omitempty"`
	Renamed     string `json:"renamed,omitempty"`
}

// BatchResult 定義 batch move / rollback CLI 的 JSON 輸出 DTO。
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

// MergeResult 定義目錄 move CLI 的 JSON 輸出 DTO。
type MergeResult struct {
	SourceDir  string       `json:"source_dir"`
	DestDir    string       `json:"dest_dir"`
	FilesMoved int          `json:"files_moved"`
	FilesTotal int          `json:"files_total"`
	Errors     []MoveResult `json:"errors,omitempty"`
	Success    bool         `json:"success"`
	DeletedSrc bool         `json:"deleted_src"`
}
