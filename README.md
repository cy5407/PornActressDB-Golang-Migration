# 女優分類系統 (Chinese Ver.)

女優分類系統是一套專為 **Windows 桌面環境** 設計的影片整理工具。

它可以從影片檔名中提取番號，自動到多個網站搜尋女優資訊，再依女優名稱或片商將影片整理到對應資料夾，減少手動查詢與搬移檔案的時間。

本專案使用 **Python + Go 混合架構**：

- **Python**：負責 GUI 介面、搜尋流程、資料庫整合與主要邏輯
- **Go**：負責高速掃描、批次移動、資料庫工具與操作歷史

## 主要功能

- 掃描資料夾中的影片檔案並提取番號
- 透過 `AV-WIKI`、`chiba-f.net`、`JAVDB` 搜尋女優資訊
- 依女優自動分類影片
- 支援多人共演時的互動式分類
- 依片商整理女優資料夾
- 提供批次移動、操作歷史與回滾功能
- 使用 JSON 資料庫保存影片、女優與搜尋結果

## 適用環境

- Windows 10 / 11
- Python 3.11+
- Go 1.21+（若要自行建置 `classifier.exe`）

> 如果你只想使用 GUI，Python 環境是必要的；Go CLI 則屬於建議安裝，可提升掃描與搬移效率。

## 安裝方式

### 1. 下載專案

```powershell
git clone https://github.com/cy5407/PornActressDB-Golang-Migration
cd PornActressDB-Golang-Migration
```

### 2. 建立虛擬環境

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

### 3. 安裝相依套件

```powershell
pip install -r requirements.txt
```

### 4. 建立設定檔

```powershell
Copy-Item config.ini.example config.ini
```

建議先確認以下設定：

- `json_data_dir`：JSON 資料庫位置
- `default_input_dir`：預設掃描資料夾
- `go_integration.enabled`：是否啟用 Go CLI
- `go_integration.log_dir`：操作歷史目錄

### 5. 建置 Go CLI（選用，但建議）

```powershell
go build -o classifier.exe .\cmd\scanner
```

## 快速開始

### 啟動主程式

```powershell
python run.py
```

啟動後，主介面可用來：

- 掃描影片資料夾
- 搜尋女優資訊
- 執行智慧分類
- 執行互動式分類
- 進行片商分類
- 查看操作歷史與回滾結果

## 使用方式

### 一般使用流程

1. 啟動 `python run.py`
2. 選擇要處理的影片資料夾
3. 執行搜尋功能取得女優資訊
4. 檢查搜尋結果
5. 執行分類或移動
6. 如有需要，可從操作歷史中查看明細或回滾

### 搜尋來源

系統目前會依序使用以下來源搜尋：

1. `AV-WIKI`
2. `chiba-f.net`
3. `JAVDB`

### GUI 常見功能

- **日文網站搜尋**：從日文網站取得女優資訊
- **JAVDB 搜尋**：以 JAVDB 為主來源搜尋
- **智慧分類**：自動套用分類邏輯
- **互動式分類**：多人共演時讓使用者手動選擇
- **智慧搜尋並分類**：搜尋完成後直接進行整理
- **片商分類**：依片商規則整理資料夾
- **操作歷史**：查看批次移動與回滾紀錄

## Go CLI 用法

若已建置 `classifier.exe`，可直接在終端機使用。

### 掃描資料夾

```powershell
classifier.exe scan -dir "D:\Videos" -workers 10
```

### 單檔移動

```powershell
classifier.exe move -src "D:\Videos\A.mp4" -dst "D:\Sorted\A\A.mp4" -strategy skip
```

### 批次移動

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
classifier.exe db update STARS-707 video.json
classifier.exe db delete STARS-707
classifier.exe db compact
classifier.exe db merge -source dist\data\json_db\data.json
```

## JSON 資料庫

本專案使用 JSON 資料庫保存影片與搜尋結果，預設位置為：

```text
data\json_db\data.json
```

影片資料位於：

```text
videos[番號]
```

常見欄位包括：

- `code`
- `title`
- `studio`
- `actresses`
- `search_status`
- `search_method`
- `last_search_date`
- `original_filename`
- `file_path`

### 搜尋狀態

目前 `search_status` 使用以下值：

- `imported`
- `searched_found`
- `searched_not_found`
- `search_error`

### 搜尋來源標記

目前 `search_method` 使用以下值：

- `legacy-import`
- `AV-WIKI`
- `chiba-f.net`
- `JAVDB`
- `cascade`

## 資料維護工具

如果 `data.json` 來自舊版流程，想檢查或整理資料格式，可使用以下工具。

### 驗證資料格式

```powershell
python tools\verify\verify_json_db_schema.py data\json_db\data.json
```

### 預覽正規化結果

```powershell
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --dry-run
```

### 輸出正規化後的新檔案

```powershell
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --output normalized_data.json
```

### 直接寫回原始檔

```powershell
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --write
```

## 專案結構

```text
.
├── run.py
├── config.ini.example
├── requirements.txt
├── cmd\
│   └── scanner\              # Go CLI 入口
├── pkg\                      # Go 套件
├── src\
│   ├── models\               # 設定與資料模型
│   ├── services\             # 分類與搜尋核心
│   ├── scrapers\             # 搜尋來源
│   ├── ui\                   # GUI 介面
│   └── utils\                # 工具模組
├── data\
│   └── json_db\              # JSON 資料庫
├── tools\                    # 診斷與維護腳本
└── tests\                    # 測試
```

## 開發與測試

### Python

```powershell
python -m py_compile src\models\json_types.py src\services\classifier_core.py
python -m unittest src.services.go_bridge_test -v
python -m pytest tests\ -v
```

### Go

```powershell
go test .\pkg\... -v
go build -o classifier.exe .\cmd\scanner
```

## 注意事項

- 建議從專案根目錄執行 GUI 與工具腳本
- 若 Go CLI 不可用，部分流程會自動退回 Python 實作
- 不建議直接手動修改 `data\json_db\data.json`
- 若需要檢查或整理資料庫，請優先使用 `tools\verify` 與 `tools\diagnostics` 下的工具

## 授權

本專案採用 `MIT License`，詳細內容請參考 `LICENSE`。

---

# Actress Classification System

The Actress Classification System is a video organization tool designed specifically for the **Windows desktop environment**.

It can extract video codes from filenames, automatically search multiple websites for actress information, and then organize videos into corresponding folders by actress name or studio, reducing the time spent on manual lookups and file transfers.

This project uses a **Python + Go hybrid architecture**:

- **Python**: Responsible for the GUI, search workflow, database integration, and main logic
- **Go**: Responsible for high-speed scanning, batch moving, database tools, and operation history

## Main Features

- Scan video files in folders and extract video codes
- Search for actress information via `AV-WIKI`, `chiba-f.net`, and `JAVDB`
- Automatically classify videos by actress
- Supports interactive classification for multi-actress videos
- Organize actress folders by studio
- Provides batch move, operation history, and rollback functionality
- Uses a JSON database to save videos, actresses, and search results

## Supported Environment

- Windows 10 / 11
- Python 3.11+
- Go 1.21+ (if you want to build `classifier.exe` yourself)

> If you only want to use the GUI, a Python environment is required; the Go CLI is recommended and can improve scanning and file transfer efficiency.

## Installation

### 1. Download the Project

```powershell
git clone https://github.com/cy5407/PornActressDB-Golang-Migration
cd PornActressDB-Golang-Migration
```

### 2. Create a Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

### 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 4. Create Configuration File

```powershell
Copy-Item config.ini.example config.ini
```

It is recommended to confirm the following settings first:

- `json_data_dir`: JSON database location
- `default_input_dir`: Default scan folder
- `go_integration.enabled`: Whether to enable the Go CLI
- `go_integration.log_dir`: Operation history directory

### 5. Build the Go CLI (Optional, but Recommended)

```powershell
go build -o classifier.exe .\cmd\scanner
```

## Quick Start

### Launch the Main Program

```powershell
python run.py
```

After launching, the main interface can be used to:

- Scan video folders
- Search for actress information
- Perform smart classification
- Perform interactive classification
- Perform studio classification
- View operation history and rollback results

## How to Use

### General Workflow

1. Launch `python run.py`
2. Select the video folder to process
3. Run the search function to obtain actress information
4. Review search results
5. Perform classification or file moving
6. If needed, view details or rollback from the operation history

### Search Sources

The system currently searches the following sources in order:

1. `AV-WIKI`
2. `chiba-f.net`
3. `JAVDB`

### Common GUI Features

- **Japanese Website Search**: Retrieve actress information from Japanese websites
- **JAVDB Search**: Search using JAVDB as the primary source
- **Smart Classification**: Automatically apply classification logic
- **Interactive Classification**: Allows manual selection when multiple actresses are involved
- **Smart Search and Classify**: Directly organize after search is complete
- **Studio Classification**: Organize folders according to studio rules
- **Operation History**: View batch move and rollback records

## Go CLI Usage

If `classifier.exe` has been built, it can be used directly in the terminal.

### Scan a Folder

```powershell
classifier.exe scan -dir "D:\Videos" -workers 10
```

### Move a Single File

```powershell
classifier.exe move -src "D:\Videos\A.mp4" -dst "D:\Sorted\A\A.mp4" -strategy skip
```

### Batch Move

```powershell
classifier.exe move -batch moves.json
```

### View Operation History

```powershell
classifier.exe history list
classifier.exe history show abc123
classifier.exe history rollback abc123
classifier.exe history rollback --last
```

### Database Tools

```powershell
classifier.exe db stats
classifier.exe db list
classifier.exe db get STARS-707
classifier.exe db update STARS-707 video.json
classifier.exe db delete STARS-707
classifier.exe db compact
classifier.exe db merge -source dist\data\json_db\data.json
```

## JSON Database

This project uses a JSON database to save videos and search results. The default location is:

```text
data\json_db\data.json
```

Video data is located at:

```text
videos[video code]
```

Common fields include:

- `code`
- `title`
- `studio`
- `actresses`
- `search_status`
- `search_method`
- `last_search_date`
- `original_filename`
- `file_path`

### Search Status

The `search_status` field currently uses the following values:

- `imported`
- `searched_found`
- `searched_not_found`
- `search_error`

### Search Source Labels

The `search_method` field currently uses the following values:

- `legacy-import`
- `AV-WIKI`
- `chiba-f.net`
- `JAVDB`
- `cascade`

## Data Maintenance Tools

If `data.json` comes from an older workflow and you want to check or clean up the data format, you can use the following tools.

### Validate Data Format

```powershell
python tools\verify\verify_json_db_schema.py data\json_db\data.json
```

### Preview Normalization Results

```powershell
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --dry-run
```

### Output Normalized Data to a New File

```powershell
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --output normalized_data.json
```

### Write Directly Back to the Original File

```powershell
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --write
```

## Project Structure

```text
.
├── run.py
├── config.ini.example
├── requirements.txt
├── cmd\
│   └── scanner\              # Go CLI entry point
├── pkg\                      # Go packages
├── src\
│   ├── models\               # Configuration and data models
│   ├── services\             # Classification and search core
│   ├── scrapers\             # Search sources
│   ├── ui\                   # GUI interface
│   └── utils\                # Utility modules
├── data\
│   └── json_db\              # JSON database
├── tools\                    # Diagnostics and maintenance scripts
└── tests\                    # Tests
```

## Development and Testing

### Python

```powershell
python -m py_compile src\models\json_types.py src\services\classifier_core.py
python -m unittest src.services.go_bridge_test -v
python -m pytest tests\ -v
```

### Go

```powershell
go test .\pkg\... -v
go build -o classifier.exe .\cmd\scanner
```

## Notes

- It is recommended to run the GUI and tool scripts from the project root directory
- If the Go CLI is unavailable, some workflows will automatically fall back to the Python implementation
- It is not recommended to directly modify `data\json_db\data.json` manually
- If you need to check or organize the database, please prioritize using the tools under `tools\verify` and `tools\diagnostics`

## License

This project is licensed under the `MIT License`. For details, please refer to `LICENSE`.
