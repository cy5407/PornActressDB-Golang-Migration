# Gemini Context & Memory

## 專案概況：PornActressDB-Golang-Migration

這是一個「女優分類系統」的重構與遷移專案。原系統為 Python (Tkinter GUI)，目前正在逐步將核心效能敏感的部分遷移至 Go 語言。

### 語言與環境
- **主要語言**: Python 3.8+ (原有邏輯與 GUI)
- **遷移語言**: Go 1.21+ (高效能掃描與運算)
- **GUI**: Python Tkinter
- **作業系統**: Windows (主要), 支援跨平台路徑處理

## 核心任務：Go 遷移計畫

目前專案處於混合架構階段：

1.  **Phase 1 (已完成)**: 核心番號提取邏輯 (`pkg/extractor`) 已從 Python 移植到 Go，並通過單元測試。
2.  **Phase 2 (已完成)**: 高效能檔案掃描器 (`cmd/scanner`) 已實作，編譯為 `classifier.exe`。
3.  **Phase 3 (進行中/已完成)**: Python 與 Go 的整合 (`tools/integration/go_integration.py`)。

### 狀態檢查
- **Go 模組**: `go.mod`, `go.sum`
- **Go CLI 進入點**: `cmd/scanner/main.go` → `classifier.exe`
- **Wails GUI 進入點**: `wails-app/` → `actress-classifier.exe`

## 常用指令

### Go 開發
```powershell
# 執行單元測試
go test ./pkg/extractor -v

# 編譯掃描器
go build -o classifier.exe ./cmd/scanner

# 執行掃描器
.\classifier.exe -dir "目標資料夾路徑"
```

### 啟動主程式
```powershell
# 啟動 Wails GUI
.\actress-classifier.exe
```

## 專案結構索引

- **Go 程式碼**:
    - `cmd/scanner/`: CLI 掃描器主程式
    - `pkg/extractor/`: 番號提取核心邏輯
- **Python 核心**:
    - `src/models/`: 資料模型 (IncrementalJSONDB 等)
    - `src/services/`: 業務邏輯 (ClassifierCore, WebSearcher)
    - `src/scrapers/`: 爬蟲 (AVWiki, JAVDB)
    - `src/ui/`: Tkinter 介面
- **整合工具**:
    - `tools/integration/`: Python 呼叫 Go 的橋接程式

## 開發規範

1.  **語言**: 所有回應與註解使用 **繁體中文 (Traditional Chinese)**。
2.  **路徑**: 注意 Windows 路徑相容性 (使用 `filepath.Join` 或 `/` 處理)。
3.  **並發**: Go 掃描器預設使用並發處理，Python GUI 更新需注意執行緒安全 (使用 `root.after`)。
4.  **風格**: 
    - Python: PEP 8, 加上 Type Hints。
    - Go: Standard Go formatting (`gofmt`), Idiomatic Go.

## 參考文件
- `CLAUDE.md`: 原始專案詳細說明與 Python 架構。
- `GO_MVP_STATUS.md`: Go 遷移進度追蹤。
