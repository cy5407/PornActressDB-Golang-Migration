# 女優分類系統

Windows 桌面工具，用來掃描影片檔案、提取番號、搜尋女優資訊，並依女優或片商進行分類整理。

專案採用 **Python + Go 混合架構**：

- Python 負責 GUI、搜尋流程、資料庫整合與業務邏輯
- Go 負責檔案掃描、批次移動、資料庫工具與操作歷史

如果你只是想使用程式，從 `python run.py` 開始即可。

如果你要開發、除錯或維護資料，這份 README 會告訴你主要入口、常用指令與資料維護工具。

## 主要功能

- 掃描指定資料夾中的影片檔案並提取番號
- 透過 AV-WIKI、chiba-f.net、JAVDB 進行多來源搜尋
- 將影片依女優自動分類，或在多人共演時進行互動式選擇
- 依片商進行女優資料夾分類
- 使用 Go CLI 提供較快的掃描、移動與操作歷史
- 使用 JSON 資料庫保存影片、女優與搜尋結果
- 支援操作歷史檢視與回滾

## 適用環境

- 作業系統：Windows 10 / 11
- Python：`3.11+`
- Go：建議 `1.24.5+`（若要自行建置 `classifier.exe`）

> 專案目前以 Windows 為主要使用與測試平台。

## 專案入口

### GUI 主程式

```powershell
python run.py
```

### Go CLI

```powershell
classifier.exe help
```

若尚未建置：

```powershell
go build -o classifier.exe .\cmd\scanner
```

## 快速開始

### 1. 複製專案

```powershell
git clone https://github.com/cy5407/PornActressDB-Golang-Migration
cd PornActressDB-Golang-Migration
```

### 2. 建立虛擬環境

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

### 3. 安裝 Python 相依套件

```powershell
pip install -r requirements.txt
```

### 4. 準備設定檔

```powershell
Copy-Item config.ini.example config.ini
```

請至少確認：

- `default_input_dir`
- `json_data_dir`
- `go_integration.enabled`

### 5. 建置 Go CLI（選用但建議）

```powershell
go build -o classifier.exe .\cmd\scanner
```

### 6. 啟動程式

```powershell
python run.py
```

## 常用操作

### 使用 GUI

啟動後可在主介面中使用：

- 日文網站搜尋
- JAVDB 搜尋
- 智慧分類
- 互動式分類
- 智慧搜尋並分類
- 片商分類
- 操作歷史

### 使用 Go CLI 掃描

```powershell
classifier.exe scan -dir "D:\Videos" -workers 10
```

### 使用 Go CLI 移動

```powershell
classifier.exe move -src "D:\Videos\A.mp4" -dst "D:\Sorted\A\A.mp4" -strategy skip
```

### 使用 Go CLI 批次移動

```powershell
classifier.exe move -batch moves.json
```

### 查看操作歷史

```powershell
classifier.exe history list
classifier.exe history show abc123
classifier.exe history rollback abc123
classifier.exe history rollback --last
```

### 資料庫工具

```powershell
classifier.exe db stats
classifier.exe db list
classifier.exe db get STARS-707
classifier.exe db compact
```

## JSON 資料庫說明

資料庫位於：

```text
data\json_db\data.json
```

根層是標準資料庫結構，影片資料位於：

```text
videos[番號]
```

常見影片欄位包含：

- `code`
- `title`
- `studio`
- `actresses`
- `search_status`
- `search_method`
- `last_search_date`
- `original_filename`
- `file_path`
- `metadata`

### 搜尋狀態規範

目前影片資料的 `search_status` 使用以下值：

- `imported`
- `searched_found`
- `searched_not_found`
- `search_error`

### 搜尋來源規範

目前影片資料的 `search_method` 使用以下值：

- `legacy-import`
- `AV-WIKI`
- `chiba-f.net`
- `JAVDB`
- `cascade`

## JSON 資料庫 schema 維護工具

如果 `data.json` 裡的歷史資料格式不一致，可使用這兩個腳本：

### 驗證 schema

```powershell
python tools\verify\verify_json_db_schema.py data\json_db\data.json
```

### 預覽正規化變更

```powershell
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --dry-run
```

### 輸出正規化結果到新檔案

```powershell
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --output normalized_data.json
```

### 直接寫回原始資料（自動備份）

```powershell
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --write
```

正規化腳本目前會處理：

- 統一 `search_status`
- 統一 `search_method`
- 移除 `id == code` 的重複欄位
- 移除測試欄位 `test_field`
- 補齊缺少的 `original_filename` / `file_path`

## 專案結構

```text
.
├── run.py
├── config.ini.example
├── requirements.txt
├── pyproject.toml
├── cmd\
│   └── scanner\              # Go CLI 入口
├── pkg\
│   ├── cache\                # Go 快取工具
│   ├── database\             # Go 資料庫工具
│   ├── extractor\            # Go 番號提取
│   ├── mover\                # Go 檔案移動與歷史
│   └── studio\               # Go 片商識別
├── src\
│   ├── models\               # JSON DB、設定、型別
│   ├── services\             # 分類核心、GoBridge、搜尋流程
│   ├── scrapers\             # 各網站搜尋來源
│   ├── ui\                   # Tkinter GUI
│   └── utils\                # 掃描器、進度、檔案工具
├── data\
│   └── json_db\              # JSON 資料庫
├── tools\                    # 維護、修復、驗證腳本
├── tests\                    # Python 測試
└── classifier.exe            # 建置後的 Go CLI
```

## 開發與測試

### Python 語法檢查

```powershell
python -m py_compile src\models\json_types.py src\services\classifier_core.py
```

### Python 測試

```powershell
python -m unittest src.services.go_bridge_test -v
python -m pytest tests\ -v
```

> `pytest` 相關套件列在 `requirements.txt`，若尚未安裝請先執行 `pip install -r requirements.txt`。

### Go 測試

```powershell
go test .\pkg\... -v
go test .\pkg\mover -v
go test .\pkg\extractor -v
```

### Go 建置

```powershell
go build -o classifier.exe .\cmd\scanner
```

## 設定檔

範例設定檔位於：

```text
config.ini.example
```

主要段落：

- `[database]`：JSON 資料庫位置
- `[paths]`：預設輸入資料夾
- `[search]`：批次搜尋與逾時設定
- `[cache]`：快取保留策略
- `[go_integration]`：Go CLI 啟用與日誌設定

## 相關文件

- `CLAUDE.md`：開發指引與專案架構
- `QUICK_START_GUIDE.md`：特定功能的快速操作說明
- `CODING_STANDARDS.md`：程式碼規範
- `docs\`：補充文件

## 注意事項

- GUI 與工具腳本預設從專案根目錄執行
- 請不要直接手動編輯 `data\json_db\data.json`，除非你很清楚 schema 與後果
- 若需要整理 `data.json`，優先使用 `tools\diagnostics\normalize_json_db_schema.py`
- 若需要確認資料是否乾淨，優先使用 `tools\verify\verify_json_db_schema.py`

## 授權

本專案採用 `MIT License`。

詳細內容請見 `LICENSE`。
