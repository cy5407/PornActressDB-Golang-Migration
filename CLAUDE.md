# CLAUDE.md

本檔提供此 repo 目前有效的開發指引。

## 語言偏好

**所有回應一律使用繁體中文 (zh-TW)。**

- 預設不使用簡體中文。
- 除非使用者明確指定其他語言，否則說明、註解與文件皆以繁體中文撰寫。

## 專案現況

**女優分類系統 (Actress Classifier)** 是一個以 **Wails (Go + React/TypeScript)** 為桌面 GUI、以 **Go CLI** 處理掃描 / 移動 / 資料庫、以 **Python** 負責搜尋與爬蟲的 Windows 桌面工具。

- **主 GUI**：`actress-classifier.exe`
- **Go CLI**：`classifier.exe`
- **Python 搜尋管線**：`src/scrapers/`、`src/services/web_searcher.py`
- **主進入點**：`run.py`（優先啟動已建好的 Wails 執行檔）

## 快速開始

### 安裝 Python 相依

```powershell
pip install -r requirements.txt
```

### 建置 Go CLI

```powershell
go build -o classifier.exe .\cmd\scanner
```

> 不要直接編譯 `cmd\scanner\main.go`，否則會漏掉同套件其他 `.go` 檔案。

### 建置 Wails 桌面應用

```powershell
Set-Location wails-app
wails build
```

### 啟動

```powershell
python run.py
```

## 目前目錄結構

```text
src\
├── models\                  # JSON 資料模型、番號提取、片商識別
├── scrapers\                # AV-WIKI、JAVDB 與快取管理
├── services\                # go_cli、搜尋器、快取服務
└── utils\                   # scanner、file_mover 等薄適配層

cmd\scanner\                 # classifier.exe 入口
pkg\                         # Go 核心套件（database/extractor/mover/studio/cache/pathutil）
wails-app\
├── backend\                 # Wails Go bindings
└── frontend\                # React + TypeScript UI
```

## 重要模組

- `src/services/go_cli.py`：Python 呼叫 `classifier.exe` 的唯一正式入口
- `src/models/json_database.py`：Go-only JSON DB 委派層
- `src/models/incremental_json_database.py`：增量 DB / compact 委派層
- `src/scrapers/cache_manager.py`：爬蟲快取層（仍由 Python 呼叫 Go CLI）
- `src/utils/scanner.py`：Go CLI 掃描薄適配層
- `src/utils/file_mover.py`：Go CLI 移動 / rollback 薄適配層
- `wails-app/backend/app.go`：Wails 後端 API

## 測試命令

### Python

```powershell
python -m pytest tests\ -q -p no:cacheprovider
python -m pytest tests\integration\ -v --tb=short -p no:cacheprovider
python -m pytest tests\test_incremental_db.py tests\test_json_database.py -q -p no:cacheprovider
```

### Go

```powershell
go test .\pkg\... -v
go test .\cmd\scanner -v
```

### Wails backend

```powershell
Set-Location wails-app
go test .\backend -v
```

## 開發規範

### Go-only 邊界

- **非爬蟲層採 Go-only**：不要再新增或恢復 Python fallback。
- DB、掃描、搬移、操作歷史等能力，都應透過 `src/services/go_cli.py` 委派給 `classifier.exe`。
- 若 Go CLI 不可用，非爬蟲層應明確回報錯誤，不要靜默假成功。

### 爬蟲層例外

- `src/scrapers/` 與搜尋器仍可保留 Python-first 實作。
- 搜尋順序固定為：**AV-WIKI → JAVDB**。
- 修正爬蟲時優先考慮穩定性、限流、快取與錯誤語意。

### GUI 規範

- 舊版 Python GUI 已移除。
- GUI 相關修改請改動：
  - `wails-app/frontend/src/`（畫面與互動）
  - `wails-app/backend/`（bindings 與後端流程）

### 資料庫規範

- JSON DB 位置：`data\json_db\`
- 不要直接手改 `data\json_db\data.json`；優先透過 `JSONDBManager` / `IncrementalJSONDB` 或既有工具腳本操作。
- schema 驗證 / 正規化工具：

```powershell
python tools\verify\verify_json_db_schema.py data\json_db\data.json
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --dry-run
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --write
```

## 常見工作

### 修改 Go CLI

1. 修改 `pkg\...` 或 `cmd\scanner\...`
2. 執行對應 `go test`
3. 重新建置 `classifier.exe`
4. 讓 Python / Wails 呼叫端維持同一份 CLI 契約

### 修改掃描或搬移適配層

- 統一走 `src/services/go_cli.py`
- `go_exe_path` / `exe_path` 必須傳遞到 `go_cli.is_available(...)/run(...)/move_file(...)`
- 不要在 `scanner.py` / `file_mover.py` 自己各寫一套 classifier 路徑解析

### 修改 GUI

1. 調整 `wails-app/frontend/src/components/` 或 `App.tsx`
2. 若需要新 backend 能力，更新 `wails-app/backend/app.go`
3. 視需要補 `wails-app/backend/app_test.go`

## 備註

- `README.md` 是對外使用說明；若架構或測試命令改變，請同步更新。
- `MIGRATION_STATUS.md` 現在記錄的是**目前狀態摘要**，不是舊 phase 的逐項流水帳。
