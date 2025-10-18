# Data Model: 分類功能 Golang 遷移

**Feature**: 002-golang-classification-migration  
**Date**: 2025-10-18  
**Purpose**: 定義核心資料結構，為 Golang 實作提供型別規範

---

## 核心實體 (Core Entities)

### 1. VideoFile - 影片檔案

**用途**: 代表實體影片檔案，包含掃描過程中提取的所有資訊

```go
package models

import "time"

// VideoFile 代表一個影片檔案
type VideoFile struct {
    // 檔案系統屬性
    Path       string    `json:"path"`        // 檔案完整路徑 (絕對路徑)
    Name       string    `json:"name"`        // 檔案名稱 (含副檔名)
    Size       int64     `json:"size"`        // 檔案大小 (bytes)
    CreatedAt  time.Time `json:"created_at"`  // 建立時間
    ModifiedAt time.Time `json:"modified_at"` // 最後修改時間
    
    // 業務屬性
    Code         string   `json:"code"`          // 提取的番號 (e.g., "SONE-123")
    ActressNames []string `json:"actress_names"` // 關聯女優名稱列表
    StudioName   string   `json:"studio_name"`   // 關聯片商名稱
    
    // 處理狀態
    Scanned      bool      `json:"scanned"`       // 是否已掃描
    Classified   bool      `json:"classified"`    // 是否已分類
    Error        string    `json:"error"`         // 錯誤訊息 (如果有)
}

// IsValid 檢查影片檔案是否有效
func (v *VideoFile) IsValid() bool {
    return v.Path != "" && v.Size > 0
}

// HasCode 檢查是否成功提取番號
func (v *VideoFile) HasCode() bool {
    return v.Code != ""
}

// IsSingleActress 檢查是否為單女優影片
func (v *VideoFile) IsSingleActress() bool {
    return len(v.ActressNames) == 1
}

// IsMultiActress 檢查是否為多女優共演影片
func (v *VideoFile) IsMultiActress() bool {
    return len(v.ActressNames) > 1
}
```

**驗證規則**:
- `Path` 必須為非空絕對路徑
- `Size` 必須 > 0
- `Code` 如果非空，必須符合番號格式 (正則驗證)
- `ActressNames` 可以為空 (未分類) 或包含 1+ 女優

---

### 2. VideoCode - 番號

**用途**: 代表番號識別碼，用於連結影片、女優和片商

```go
package models

// VideoCode 代表一個番號
type VideoCode struct {
    Code      string   `json:"code"`       // 完整番號 (e.g., "SONE-123")
    Prefix    string   `json:"prefix"`     // 片商前綴 (e.g., "SONE")
    Number    string   `json:"number"`     // 數字部分 (e.g., "123")
    Actresses []string `json:"actresses"`  // 關聯女優名稱列表
    Studio    string   `json:"studio"`     // 關聯片商名稱
}

// Normalize 標準化番號格式 (大寫、統一格式)
func (c *VideoCode) Normalize() string {
    return strings.ToUpper(c.Prefix) + "-" + c.Number
}

// IsFC2 檢查是否為 FC2 番號
func (c *VideoCode) IsFC2() bool {
    return strings.HasPrefix(c.Prefix, "FC2")
}

// IsPPV 檢查是否為 PPV (按次付費) 番號
func (c *VideoCode) IsPPV() bool {
    return strings.Contains(c.Code, "PPV")
}
```

**驗證規則**:
- `Code` 必須非空
- `Prefix` 必須為 2-6 個大寫英文字母
- `Number` 必須為 3-8 個數字
- `Studio` 可以為空 (未識別片商)

---

### 3. Actress - 女優

**用途**: 代表女優實體，追蹤其影片數量和片商分佈

```go
package models

// Actress 代表一個女優
type Actress struct {
    Name               string         `json:"name"`                 // 女優主要名稱
    Aliases            []string       `json:"aliases"`              // 別名列表
    VideoCount         int            `json:"video_count"`          // 影片數量
    StudioDistribution map[string]int `json:"studio_distribution"`  // 片商分佈 (片商名 -> 數量)
    FolderPath         string         `json:"folder_path"`          // 女優資料夾路徑
    
    // 中繼資料
    CreatedAt time.Time `json:"created_at"` // 建立時間
    UpdatedAt time.Time `json:"updated_at"` // 最後更新時間
}

// PrimaryStudio 計算主要片商 (影片數量最多的片商)
func (a *Actress) PrimaryStudio() (string, float64) {
    if len(a.StudioDistribution) == 0 {
        return "", 0.0
    }
    
    maxStudio := ""
    maxCount := 0
    
    for studio, count := range a.StudioDistribution {
        if count > maxCount {
            maxStudio = studio
            maxCount = count
        }
    }
    
    confidence := float64(maxCount) / float64(a.VideoCount)
    return maxStudio, confidence
}

// AddVideo 新增影片到女優記錄
func (a *Actress) AddVideo(studio string) {
    a.VideoCount++
    if a.StudioDistribution == nil {
        a.StudioDistribution = make(map[string]int)
    }
    a.StudioDistribution[studio]++
    a.UpdatedAt = time.Now()
}
```

**驗證規則**:
- `Name` 必須非空
- `VideoCount` 必須 ≥0
- `StudioDistribution` 的所有計數總和必須等於 `VideoCount`
- `FolderPath` 如果非空，必須為有效路徑

---

### 4. Studio - 片商

**用途**: 代表片商實體，維護番號前綴映射

```go
package models

// Studio 代表一個片商
type Studio struct {
    Name         string   `json:"name"`          // 片商名稱
    CodePrefixes []string `json:"code_prefixes"` // 番號前綴列表 (e.g., ["SONE", "STARS"])
    VideoCount   int      `json:"video_count"`   // 影片數量
    ActressCount int      `json:"actress_count"` // 女優數量
    
    // 中繼資料
    CreatedAt time.Time `json:"created_at"` // 建立時間
    UpdatedAt time.Time `json:"updated_at"` // 最後更新時間
}

// HasPrefix 檢查番號前綴是否屬於此片商
func (s *Studio) HasPrefix(prefix string) bool {
    prefix = strings.ToUpper(prefix)
    for _, p := range s.CodePrefixes {
        if strings.ToUpper(p) == prefix {
            return true
        }
    }
    return false
}

// AddPrefix 新增番號前綴
func (s *Studio) AddPrefix(prefix string) {
    if !s.HasPrefix(prefix) {
        s.CodePrefixes = append(s.CodePrefixes, strings.ToUpper(prefix))
    }
}
```

**驗證規則**:
- `Name` 必須非空
- `CodePrefixes` 至少包含 1 個前綴
- `VideoCount` 和 `ActressCount` 必須 ≥0

---

### 5. ScanResult - 掃描結果

**用途**: 記錄掃描操作的統計資訊

```go
package models

import "time"

// ScanResult 代表一次掃描操作的結果
type ScanResult struct {
    TotalFiles   int           `json:"total_files"`    // 總檔案數
    SuccessCount int           `json:"success_count"`  // 成功提取番號數
    FailedFiles  []string      `json:"failed_files"`   // 失敗檔案列表
    Duration     time.Duration `json:"duration_ms"`    // 耗時 (毫秒)
    Timestamp    time.Time     `json:"timestamp"`      // 時間戳
    
    // 詳細統計
    VideoFiles []*VideoFile `json:"video_files"` // 所有掃描的檔案
}

// SuccessRate 計算成功率
func (r *ScanResult) SuccessRate() float64 {
    if r.TotalFiles == 0 {
        return 0.0
    }
    return float64(r.SuccessCount) / float64(r.TotalFiles) * 100
}

// FailureCount 計算失敗數
func (r *ScanResult) FailureCount() int {
    return r.TotalFiles - r.SuccessCount
}

// AverageSpeed 計算平均處理速度 (檔案/秒)
func (r *ScanResult) AverageSpeed() float64 {
    if r.Duration == 0 {
        return 0.0
    }
    return float64(r.TotalFiles) / r.Duration.Seconds()
}
```

**驗證規則**:
- `TotalFiles` ≥ `SuccessCount`
- `len(FailedFiles)` = `TotalFiles` - `SuccessCount`
- `Duration` > 0

---

### 6. ClassificationOperation - 分類操作

**用途**: 記錄單一檔案移動操作的詳細資訊

```go
package models

import "time"

// OperationType 操作類型
type OperationType string

const (
    OperationTypeAuto        OperationType = "auto"        // 自動分類
    OperationTypeInteractive OperationType = "interactive" // 互動式分類
)

// OperationStatus 操作狀態
type OperationStatus string

const (
    StatusSuccess OperationStatus = "success" // 成功
    StatusFailed  OperationStatus = "failed"  // 失敗
    StatusSkipped OperationStatus = "skipped" // 跳過
)

// ClassificationOperation 代表一次分類操作
type ClassificationOperation struct {
    SourcePath    string          `json:"source_path"`    // 來源路徑
    TargetPath    string          `json:"target_path"`    // 目標路徑
    OperationType OperationType   `json:"operation_type"` // 操作類型
    Status        OperationStatus `json:"status"`         // 結果狀態
    ErrorMessage  string          `json:"error_message"`  // 錯誤訊息 (if failed)
    Timestamp     time.Time       `json:"timestamp"`      // 時間戳
    
    // 額外資訊
    ActressName string `json:"actress_name"` // 目標女優名稱
    FileSize    int64  `json:"file_size"`    // 檔案大小
}

// IsSuccess 檢查操作是否成功
func (o *ClassificationOperation) IsSuccess() bool {
    return o.Status == StatusSuccess
}

// IsFailed 檢查操作是否失敗
func (o *ClassificationOperation) IsFailed() bool {
    return o.Status == StatusFailed
}
```

**驗證規則**:
- `SourcePath` 和 `TargetPath` 必須非空
- `Status` 必須為 success/failed/skipped 之一
- 如果 `Status` = failed，`ErrorMessage` 必須非空

---

### 7. StudioStatistics - 片商統計

**用途**: 分析女優資料夾的片商分佈，用於片商分類功能

```go
package models

// StudioStatistics 代表女優的片商分佈統計
type StudioStatistics struct {
    ActressName        string         `json:"actress_name"`         // 女優名稱
    StudioDistribution map[string]int `json:"studio_distribution"`  // 片商分佈 (片商名 -> 數量)
    PrimaryStudio      string         `json:"primary_studio"`       // 主要片商
    Confidence         float64        `json:"confidence"`           // 信心度 (0.0-1.0)
    RecommendedClass   string         `json:"recommended_class"`    // 推薦分類
    TotalVideos        int            `json:"total_videos"`         // 總影片數
}

// CalculateConfidence 計算信心度
func (s *StudioStatistics) CalculateConfidence() {
    if s.TotalVideos == 0 {
        s.Confidence = 0.0
        return
    }
    
    maxCount := 0
    for _, count := range s.StudioDistribution {
        if count > maxCount {
            maxCount = count
        }
    }
    
    s.Confidence = float64(maxCount) / float64(s.TotalVideos)
}

// DetermineClassification 根據閾值決定分類
func (s *StudioStatistics) DetermineClassification(threshold float64) string {
    if s.Confidence >= threshold {
        return s.PrimaryStudio
    }
    return "SOLO_ACTRESS"
}

// ExceedsThreshold 檢查是否超過閾值
func (s *StudioStatistics) ExceedsThreshold(threshold float64) bool {
    return s.Confidence >= threshold
}
```

**驗證規則**:
- `ActressName` 必須非空
- `Confidence` 必須在 0.0-1.0 範圍內
- `TotalVideos` 必須等於 `StudioDistribution` 的所有計數總和
- `RecommendedClass` 必須為片商名或 "SOLO_ACTRESS"

---

## 輔助結構 (Helper Structures)

### ConflictResolution - 衝突解決策略

```go
package models

// ConflictStrategy 衝突解決策略
type ConflictStrategy string

const (
    ConflictAsk       ConflictStrategy = "ask"       // 詢問使用者
    ConflictSkip      ConflictStrategy = "skip"      // 跳過
    ConflictOverwrite ConflictStrategy = "overwrite" // 覆蓋
    ConflictRename    ConflictStrategy = "rename"    // 重新命名
)

// ConflictResolution 衝突解決配置
type ConflictResolution struct {
    Strategy      ConflictStrategy `json:"strategy"`        // 策略
    RememberChoice bool            `json:"remember_choice"` // 記住選擇
}
```

### ProgressUpdate - 進度更新

```go
package models

// ProgressUpdate 代表一次進度更新
type ProgressUpdate struct {
    CurrentFile         string  `json:"current_file"`          // 當前處理檔案
    ProcessedCount      int     `json:"processed_count"`       // 已處理數量
    TotalCount          int     `json:"total_count"`           // 總數量
    Percentage          float64 `json:"percentage"`            // 完成百分比
    EstimatedRemainingMs int64  `json:"estimated_remaining_ms"` // 預估剩餘時間 (毫秒)
}

// IsComplete 檢查是否完成
func (p *ProgressUpdate) IsComplete() bool {
    return p.ProcessedCount >= p.TotalCount
}

// CalculatePercentage 計算百分比
func (p *ProgressUpdate) CalculatePercentage() {
    if p.TotalCount == 0 {
        p.Percentage = 0.0
        return
    }
    p.Percentage = float64(p.ProcessedCount) / float64(p.TotalCount) * 100
}
```

---

## 資料庫結構 (Database Structure)

### JSON 檔案資料庫格式

```json
{
  "version": "1.0.0",
  "last_updated": "2025-10-18T10:30:00Z",
  "actresses": [
    {
      "name": "女優A",
      "aliases": ["別名1", "別名2"],
      "video_count": 150,
      "studio_distribution": {
        "S1": 120,
        "MOODYZ": 30
      },
      "folder_path": "/path/to/actresses/女優A",
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2025-10-18T10:00:00Z"
    }
  ],
  "studios": [
    {
      "name": "S1",
      "code_prefixes": ["SONE", "STARS", "SSNI"],
      "video_count": 5000,
      "actress_count": 200,
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2025-10-18T10:00:00Z"
    }
  ],
  "video_codes": [
    {
      "code": "SONE-123",
      "prefix": "SONE",
      "number": "123",
      "actresses": ["女優A"],
      "studio": "S1"
    }
  ]
}
```

---

## 型別關係圖 (Type Relationships)

```
VideoFile
  ├── Code (string) ────► VideoCode
  ├── ActressNames ([]string) ────► Actress
  └── StudioName (string) ────► Studio

VideoCode
  ├── Actresses ([]string) ────► Actress
  └── Studio (string) ────► Studio

Actress
  ├── StudioDistribution (map[string]int) ────► Studio
  └── FolderPath (string)

Studio
  └── CodePrefixes ([]string)

ScanResult
  └── VideoFiles ([]*VideoFile)

ClassificationOperation
  ├── SourcePath (string) ────► VideoFile
  ├── TargetPath (string)
  └── ActressName (string) ────► Actress

StudioStatistics
  ├── ActressName (string) ────► Actress
  ├── PrimaryStudio (string) ────► Studio
  └── StudioDistribution (map[string]int) ────► Studio
```

---

## 驗證與約束總結

### 必須驗證的欄位

1. **VideoFile**: Path (非空), Size (>0)
2. **VideoCode**: Code (非空), Prefix (2-6 字母), Number (3-8 數字)
3. **Actress**: Name (非空), VideoCount (≥0)
4. **Studio**: Name (非空), CodePrefixes (≥1)
5. **ScanResult**: TotalFiles ≥ SuccessCount
6. **ClassificationOperation**: SourcePath/TargetPath (非空), Status (有效值)
7. **StudioStatistics**: ActressName (非空), Confidence (0.0-1.0)

### 不變性約束 (Invariants)

1. `Actress.VideoCount` = `sum(Actress.StudioDistribution)`
2. `ScanResult.FailedFiles.length` = `TotalFiles - SuccessCount`
3. `StudioStatistics.TotalVideos` = `sum(StudioDistribution)`
4. `VideoFile.Classified` = true 僅當 `ActressNames` 非空

---

**版本**: 1.0  
**更新日期**: 2025-10-18  
**狀態**: ✅ 已審核，可用於實作
