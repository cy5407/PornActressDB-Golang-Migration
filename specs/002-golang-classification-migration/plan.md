# Implementation Plan: 分類功能 Golang 遷移

**Branch**: `002-golang-classification-migration` | **Date**: 2025-10-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-golang-classification-migration/spec.md`

## Summary

本功能旨在將現有 Python 實作的三大核心分類功能（檔案掃描與番號提取、女優資料夾分類、片商資料夾分類）遷移至 Golang，以實現 5-10 倍的效能提升。採用混合 CLI + gRPC 通訊方案，80% 批次操作使用 CLI 介面，20% 互動操作使用 gRPC 協定，確保與現有 Python GUI 無縫整合。目標是在保持功能完整性的同時，將 10,000 檔案掃描時間從 5-10 分鐘縮短至 30 秒內。

## Technical Context

**Language/Version**: Go 1.22+ (latest stable)  
**Primary Dependencies**: 
- `encoding/json` (標準庫 - JSON 資料庫讀寫)
- `path/filepath` (標準庫 - 檔案掃描)
- `regexp` (標準庫 - 番號提取)
- `google.golang.org/grpc` (gRPC 通訊)
- `google.golang.org/protobuf` (Protocol Buffers)
- `github.com/spf13/cobra` (CLI 框架)
- `go.uber.org/zap` (結構化日誌)

**Storage**: JSON 檔案資料庫 (`data.json`) - 無外部資料庫依賴  
**Testing**: Go 標準測試框架 (`testing` 套件) + `github.com/stretchr/testify`  
**Target Platform**: 跨平台 (Windows/Linux/macOS) - 靜態連結可執行檔  
**Project Type**: Hybrid (Go CLI/gRPC server + Python GUI 前端)  
**Performance Goals**: 
- 10,000 檔案掃描 ≤30 秒
- 1,000 檔案分類 ≤1 分鐘
- 100 女優資料夾片商分類 ≤30 秒
- gRPC 通訊延遲 <10ms

**Constraints**: 
- 記憶體使用 ≤500MB (處理 50,000 檔案)
- 番號提取準確率 ≥95%
- 檔案移動成功率 ≥99%
- 並行處理最大 worker 數: 8
- 可執行檔大小 ≤50MB

**Scale/Scope**: 
- 支援 50,000+ 影片檔案
- 支援 10 種以上番號格式
- 3 個核心分類功能
- 2 種通訊模式 (CLI + gRPC)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### ✅ Communication Standards
- [x] AI 回應使用繁體中文
- [x] 程式碼註解使用繁體中文
- [x] Git commit 訊息使用英文 (Conventional Commits)
- [x] 文件使用繁體中文

### ✅ Progressive Migration Strategy
- [x] 採用分階段遷移策略（符合 Phase 1-3 架構）
- [x] 每階段達成 ≥70% 測試覆蓋率
- [x] 階段間整合測試

### ✅ Code Quality Standards
- [x] Go 1.22+ 版本
- [x] 遵循 Effective Go 和 Clean Code 原則
- [x] 函數認知複雜度 ≤15 (gocognit)
- [x] 使用 golangci-lint 檢查
- [x] 錯誤處理使用 fmt.Errorf 包裝上下文
- [x] 結構化日誌 (zap)
- [x] 測試覆蓋率: ≥70% 單元測試, ≥50% 整合測試

### ✅ Concurrency and Performance
- [x] 使用 goroutines 和 channels 並行處理
- [x] 資料夾層級並行 (最大 8 workers)
- [x] 使用 errgroup 協調 goroutine
- [x] Context-based 取消機制
- [x] 效能目標明確定義

### ✅ Data Storage
- [x] 使用 JSON 檔案資料庫 (無 cgo 依賴)
- [x] 原子寫入 (temp file + rename)
- [x] 適用於 <100,000 筆記錄

### ⚠️ GUI Development Strategy
- [x] 選擇 Hybrid Architecture (Python GUI + Go API)
- [x] 理由: 最低遷移風險，漸進式方法，保留現有 GUI 投資
- [x] Python 自動管理 Go gRPC 伺服器生命週期

### ✅ Dependency Management
- [x] 核心依賴符合最小化原則
- [x] 所有依賴支援 Go 1.22+
- [x] 無 cgo 依賴 (CLI/gRPC server 部分)

**結論**: ✅ 所有 Constitution 檢查通過，可進入 Phase 0

## Project Structure

### Documentation (this feature)

```
specs/002-golang-classification-migration/
├── spec.md                      # 功能規格 (已完成)
├── implementation-cost-analysis.md  # 成本分析 (已完成)
├── deployment-guide.md          # 部署指南 (已完成)
├── plan.md                      # 本檔案 (實施計劃)
├── research.md                  # Phase 0 輸出 (待生成)
├── data-model.md                # Phase 1 輸出 (待生成)
├── quickstart.md                # Phase 1 輸出 (待生成)
├── contracts/                   # Phase 1 輸出 (待生成)
│   ├── classifier.proto         # gRPC Protocol Buffers 定義
│   └── cli-interface.md         # CLI 介面規格
└── tasks.md                     # Phase 2 輸出 (待生成 - 由 /speckit.tasks 產生)
```

### Source Code (repository root)

```
# Golang 模組
golang/
├── cmd/
│   ├── classifier/              # CLI 主程式
│   │   └── main.go
│   └── classifier-server/       # gRPC 伺服器
│       └── main.go
├── internal/
│   ├── scanner/                 # 檔案掃描與番號提取
│   │   ├── scanner.go
│   │   ├── code_extractor.go
│   │   └── scanner_test.go
│   ├── classifier/              # 女優分類邏輯
│   │   ├── actress_classifier.go
│   │   ├── studio_classifier.go
│   │   └── classifier_test.go
│   ├── database/                # JSON 資料庫存取
│   │   ├── json_db.go
│   │   ├── actress_repository.go
│   │   └── studio_repository.go
│   ├── fileops/                 # 檔案操作 (移動、衝突處理)
│   │   ├── mover.go
│   │   ├── conflict_resolver.go
│   │   └── fileops_test.go
│   ├── models/                  # 資料模型
│   │   ├── video.go
│   │   ├── actress.go
│   │   └── studio.go
│   └── grpc/                    # gRPC 實作
│       ├── server.go
│       ├── handlers.go
│       └── progress_stream.go
├── pkg/
│   └── proto/                   # 生成的 Protocol Buffers 程式碼
│       ├── classifier.pb.go
│       └── classifier_grpc.pb.go
├── go.mod
├── go.sum
└── Makefile

# Python 整合層
src/
├── golang_integration/          # Python-Go 整合
│   ├── __init__.py
│   ├── cli_wrapper.py           # CLI 呼叫包裝
│   ├── grpc_client.py           # gRPC 客戶端
│   └── server_manager.py        # gRPC 伺服器生命週期管理
└── ...existing Python code...

# 測試
tests/
├── integration/
│   ├── test_cli_integration.py  # Python-Go CLI 整合測試
│   ├── test_grpc_integration.py # Python-Go gRPC 整合測試
│   └── ratelimit_test.go        # (現有)
└── ...existing tests...
```

**Structure Decision**: 採用 Hybrid Architecture，Golang 程式碼放在 `golang/` 目錄，Python 整合層放在 `src/golang_integration/`。Golang 使用標準專案結構（cmd/ 放主程式，internal/ 放私有程式碼，pkg/ 放可匯出程式碼）。Python 端透過 subprocess 呼叫 CLI 或 gRPC 客戶端與 Golang 通訊。

## Complexity Tracking

*本功能無 Constitution 違規，此區段為空。*

---

## Phase 0: Research & Discovery

### 研究任務

#### 1. gRPC 串流進度回報最佳實踐
**研究目標**: 確定如何使用 gRPC Server Streaming 實現每 100 檔案或每 1 秒更新一次的批次進度回報  
**關鍵問題**:
- Server Streaming 的效能特性和延遲
- 如何在 Go 端實作定時批次發送
- Python grpcio 客戶端如何接收串流
- 錯誤處理和重連機制

#### 2. Goroutine 並行檔案操作最佳實踐
**研究目標**: 確定資料夾層級並行的實作細節  
**關鍵問題**:
- Worker Pool 模式實作（使用 buffered channel 限制並行度）
- 如何避免對同一目標資料夾的並行寫入衝突
- 使用 sync.Mutex 或 channel 協調資料夾存取
- 錯誤聚合和部分失敗處理

#### 3. JSON 資料庫原子操作
**研究目標**: 確定多程序環境下的 JSON 檔案安全讀寫  
**關鍵問題**:
- 檔案鎖定機制 (Go 的 syscall.Flock 或第三方套件)
- Temp file + rename 的跨平台實作
- Python 和 Go 程序同時存取時的競爭條件
- 讀寫效能優化（記憶體映射、批次操作）

#### 4. 跨平台路徑處理
**研究目標**: 確保 Windows/Linux/macOS 路徑相容性  
**關鍵問題**:
- filepath.Join vs path.Join 的使用場景
- 特殊字元（日文、中文、Emoji）處理
- UNC 路徑支援 (Windows 網路路徑)
- 符號連結 (symlink) 處理策略

#### 5. Python subprocess 與 Golang 互動
**研究目標**: 確定 CLI 模式下的標準輸入/輸出處理  
**關鍵問題**:
- Python subprocess.run() vs subprocess.Popen() 選擇
- JSON 輸出的緩衝和解析
- 大量輸出時的記憶體管理
- 進程終止和清理機制

**輸出**: `research.md` 文件，包含所有決策、理由和替代方案

---

## Phase 1: Design & Contracts

**前置條件**: research.md 完成

### 1.1 資料模型設計 (`data-model.md`)

從功能規格的 Key Entities 提取並細化：

#### 影片檔案 (VideoFile)
```go
type VideoFile struct {
    Path         string    // 檔案完整路徑
    Name         string    // 檔案名稱
    Size         int64     // 檔案大小 (bytes)
    Code         string    // 提取的番號
    ActressNames []string  // 關聯女優名稱列表
    StudioName   string    // 關聯片商名稱
    CreatedAt    time.Time // 建立時間
    ModifiedAt   time.Time // 修改時間
}
```

#### 番號 (VideoCode)
```go
type VideoCode struct {
    Code       string   // 完整番號 (e.g., "SONE-123")
    Prefix     string   // 片商前綴 (e.g., "SONE")
    Number     string   // 數字部分 (e.g., "123")
    Actresses  []string // 關聯女優名稱
    Studio     string   // 關聯片商名稱
}
```

#### 女優 (Actress)
```go
type Actress struct {
    Name           string            // 女優主要名稱
    Aliases        []string          // 別名列表
    VideoCount     int               // 影片數量
    StudioDistribution map[string]int // 片商分佈 (片商名 -> 影片數量)
    FolderPath     string            // 女優資料夾路徑
}
```

#### 片商 (Studio)
```go
type Studio struct {
    Name         string   // 片商名稱
    CodePrefixes []string // 番號前綴列表 (e.g., ["SONE", "STARS"])
    VideoCount   int      // 影片數量
    ActressCount int      // 女優數量
}
```

#### 掃描結果 (ScanResult)
```go
type ScanResult struct {
    TotalFiles      int          // 總檔案數
    SuccessCount    int          // 成功提取數
    FailedFiles     []string     // 失敗檔案列表
    Duration        time.Duration // 耗時
    Timestamp       time.Time    // 時間戳
}
```

#### 分類操作 (ClassificationOperation)
```go
type ClassificationOperation struct {
    SourcePath    string    // 來源路徑
    TargetPath    string    // 目標路徑
    OperationType string    // 操作類型 ("auto" / "interactive")
    Status        string    // 結果狀態 ("success" / "failed" / "skipped")
    ErrorMessage  string    // 錯誤訊息 (if failed)
    Timestamp     time.Time // 時間戳
}
```

#### 片商統計 (StudioStatistics)
```go
type StudioStatistics struct {
    ActressName        string            // 女優名稱
    StudioDistribution map[string]int    // 片商分佈 (片商名 -> 數量)
    PrimaryStudio      string            // 主要片商
    Confidence         float64           // 信心度百分比 (0.0-1.0)
    RecommendedClass   string            // 推薦分類 (片商名 or "SOLO_ACTRESS")
}
```

### 1.2 API Contracts

#### CLI 介面規格 (`contracts/cli-interface.md`)

**命令 1: 掃描檔案**
```bash
classifier scan --folder <path> --recursive --format json
```

輸出 (JSON):
```json
{
  "total_files": 10000,
  "success_count": 9500,
  "failed_files": ["path/to/failed1.mp4", ...],
  "duration_ms": 25000,
  "timestamp": "2025-10-18T10:30:00Z"
}
```

**命令 2: 女優分類 (自動模式)**
```bash
classifier classify-actress --folder <path> --mode auto --conflict skip
```

輸出 (JSON):
```json
{
  "total_videos": 1000,
  "moved": 950,
  "skipped": 30,
  "failed": 20,
  "duration_ms": 45000,
  "timestamp": "2025-10-18T10:35:00Z"
}
```

**命令 3: 片商分類**
```bash
classifier classify-studio --folder <path> --threshold 0.7 --workers 4
```

輸出 (JSON):
```json
{
  "total_actresses": 100,
  "classified": 85,
  "solo_actress": 15,
  "duration_ms": 20000,
  "statistics": [
    {
      "actress_name": "女優A",
      "primary_studio": "S1",
      "confidence": 0.85,
      "video_count": 120
    },
    ...
  ]
}
```

#### gRPC 介面規格 (`contracts/classifier.proto`)

```protobuf
syntax = "proto3";

package classifier;

option go_package = "github.com/cy5407/porn-actress-classifier/pkg/proto";

// 分類服務
service ClassifierService {
  // 掃描檔案 (串流進度)
  rpc ScanFiles(ScanRequest) returns (stream ScanProgress);
  
  // 女優分類 (互動模式，雙向串流)
  rpc ClassifyActress(stream ClassifyActressRequest) returns (stream ClassifyActressResponse);
  
  // 片商分類 (串流進度)
  rpc ClassifyStudio(ClassifyStudioRequest) returns (stream ClassifyStudioProgress);
}

// 掃描請求
message ScanRequest {
  string folder_path = 1;
  bool recursive = 2;
}

// 掃描進度
message ScanProgress {
  string current_file = 1;      // 當前處理檔案
  int32 processed_count = 2;    // 已處理數量
  int32 total_count = 3;        // 總數量
  float percentage = 4;         // 完成百分比
  int64 estimated_remaining_ms = 5; // 預估剩餘時間 (毫秒)
}

// 女優分類請求 (互動模式)
message ClassifyActressRequest {
  oneof request_type {
    StartClassificationRequest start = 1;
    UserChoiceRequest choice = 2;
  }
}

message StartClassificationRequest {
  string folder_path = 1;
  string conflict_strategy = 2; // "ask", "skip", "overwrite", "rename"
}

message UserChoiceRequest {
  string video_path = 1;
  string chosen_actress = 2;
}

// 女優分類回應
message ClassifyActressResponse {
  oneof response_type {
    ProgressUpdate progress = 1;
    ActressChoicePrompt prompt = 2;
    OperationComplete complete = 3;
  }
}

message ProgressUpdate {
  string current_file = 1;
  int32 processed = 2;
  int32 total = 3;
  float percentage = 4;
}

message ActressChoicePrompt {
  string video_path = 1;
  repeated string actress_options = 2;
}

message OperationComplete {
  int32 moved = 1;
  int32 skipped = 2;
  int32 failed = 3;
}

// 片商分類請求
message ClassifyStudioRequest {
  string folder_path = 1;
  float threshold = 2;
  int32 workers = 3;
}

// 片商分類進度
message ClassifyStudioProgress {
  string current_actress = 1;
  int32 processed = 2;
  int32 total = 3;
  float percentage = 4;
  repeated StudioStatistic statistics = 5;
}

message StudioStatistic {
  string actress_name = 1;
  string primary_studio = 2;
  float confidence = 3;
  int32 video_count = 4;
}
```

### 1.3 快速開始指南 (`quickstart.md`)

提供開發者和測試者的快速上手指南：
- 環境設置 (Go 1.22+ 安裝)
- 依賴安裝 (`go mod download`)
- 編譯指令 (`make build`)
- 基本使用範例
- 測試執行 (`make test`)

### 1.4 更新 Agent 上下文

執行 `.specify/scripts/powershell/update-agent-context.ps1 -AgentType copilot`，更新 `.github/copilot-instructions.md`，加入本功能的技術堆疊和關鍵路徑。

**輸出**: 
- `data-model.md`
- `contracts/cli-interface.md`
- `contracts/classifier.proto`
- `quickstart.md`
- 更新的 agent 上下文檔案

---

## Phase 2: Task Decomposition

**注意**: 此階段由 `/speckit.tasks` 命令執行，不在 `/speckit.plan` 範圍內。

將在 Phase 2 生成 `tasks.md`，包含：
- 詳細的任務分解（對應規格中的 Phase 1-5）
- 每個任務的驗收標準
- 任務依賴關係
- 預估工時
- 優先級排序

---

## Success Metrics

### 效能指標 (必須達成)
- ✅ 10,000 檔案掃描 ≤30 秒
- ✅ 1,000 檔案女優分類 ≤1 分鐘
- ✅ 100 女優資料夾片商分類 ≤30 秒
- ✅ 50,000 檔案處理記憶體 ≤500MB
- ✅ gRPC 通訊延遲 <10ms

### 品質指標 (必須達成)
- ✅ 番號提取準確率 ≥95%
- ✅ 檔案移動成功率 ≥99%
- ✅ 單元測試覆蓋率 ≥70%
- ✅ 整合測試覆蓋率 ≥50%
- ✅ 所有 golangci-lint 檢查通過

### 交付物
- ✅ 2 個可執行檔: `classifier.exe`, `classifier-server.exe`
- ✅ Python 整合套件: `golang_integration/`
- ✅ Protocol Buffers 定義和生成的程式碼
- ✅ 完整的測試套件
- ✅ 使用者文件和 API 文件

---

## Next Steps

1. **立即執行**: 開始 Phase 0 研究，填寫 `research.md`
2. **Phase 0 完成後**: 執行 Phase 1，生成資料模型和契約
3. **Phase 1 完成後**: 執行 `/speckit.tasks` 生成詳細任務分解
4. **準備開發**: 設置 Golang 開發環境，建立專案結構

**預估總時程**: 10-14 週
- Phase 0 (研究): 1 週
- Phase 1 (CLI 掃描+分類): 2-3 週
- Phase 2 (片商分類): 2-3 週
- Phase 3 (gRPC 整合): 3-4 週
- Phase 4 (測試+優化): 2-3 週
