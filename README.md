# 女優分類系統

專為 **Windows 桌面**設計的影片整理工具。

從影片檔名提取番號，自動搜尋女優資訊，依女優或片商將影片整理到對應資料夾。

## 架構

```
actress-classifier.exe   ← 桌面 GUI（Go + React/TypeScript，Wails 框架）
classifier.exe           ← Go CLI（掃描、移動、資料庫工具）
Python 搜尋管線          ← 爬蟲後端（AV-WIKI、JAVDB），由 GUI 透過 subprocess 呼叫 `run_search.py` / `run_batch_search.py`
```

> Python 主要只保留搜尋 / 爬蟲用途；掃描、移動、資料庫、操作歷史與片商工具以 Go / Go CLI 為主。

## 主要功能

| 功能 | 說明 |
|------|------|
| 掃描 | 從資料夾批次提取番號，使用 Go 並發掃描 |
| 搜尋 | 依序查詢 AV-WIKI → JAVDB，結果寫入 JSON 資料庫 |
| 移動 | 依女優分類：`outputDir\女優名\番號.ext` |
| 🏢 片商分類 | 依片商分層：`outputDir\片商名\女優名\番號.ext` |
| 回滾 | 查看操作歷史，一鍵還原移動結果 |

## 快速開始

### 使用者（無需安裝開發工具）

1. 從 [Releases](https://github.com/cy5407/PornActressDB-Golang-Migration/releases) 下載：
   - `actress-classifier.exe`（主程式）
   - `classifier.exe`（Go CLI，掃描、移動、資料庫、快取 / 片商工具）
   - `major_studios.json`（大片商清單）
   - `studios.json`（片商識別規則）
2. 安裝 Python 3.11+，執行：
   ```powershell
   pip install -r requirements.txt
   ```
3. 將 `actress-classifier.exe`、`classifier.exe`、`major_studios.json`、`studios.json` 放在同一目錄，雙擊啟動

> Python 環境只用於搜尋爬蟲；GUI 本身不需要 Python 即可啟動，但搜尋功能需要。

### 開發者（自行建置）

```powershell
# 1. Clone 專案
git clone https://github.com/cy5407/PornActressDB-Golang-Migration
cd PornActressDB-Golang-Migration

# 2. 安裝 Python 爬蟲相依套件
pip install -r requirements.txt

# 3. 建置 Go CLI
go build -o classifier.exe .\cmd\scanner

# 4. 建置 Wails 桌面應用
cd wails-app
wails build
# → wails-app\build\bin\actress-classifier.exe
```

> 建置 `classifier.exe` 時請使用套件路徑，不要直接指定 `main.go`，否則會漏掉同套件的輔助檔案。
>
> 建置或釋出 Wails 應用時，請另外確認 `classifier.exe`、`major_studios.json`、`studios.json` 是否也放在預期位置，避免 GUI 啟動後部分功能可開啟但搜尋 / 片商分類失效。

## 操作流程

1. 啟動 `actress-classifier.exe`
2. 設定輸入資料夾（掃描來源）與輸出資料夾（移動目標）
3. 點「掃描」提取所有番號
4. 點「搜尋」查詢女優資訊（結果自動寫入資料庫）
5. 點「移動」或「🏢 片商分類」整理檔案
6. 如需還原，點「操作歷史」選擇回滾

## 片商分類邏輯

| 情況 | 目標路徑 |
|------|---------|
| 大片商女優（S1、MOODYZ 等） | `outputDir\片商名\女優名\番號.ext` |
| 非大片商女優 | `outputDir\單體企劃女優\女優名\番號.ext` |
| 無女優資料 | `outputDir\未分類\番號.ext` |

大片商清單定義於 `major_studios.json`（13 個）。

## Go CLI 參考

```powershell
# 掃描
classifier.exe scan -dir "D:\Videos" -workers 10

# 移動
classifier.exe move -src "A.mp4" -dst "dest\A.mp4" -strategy skip
classifier.exe move -batch moves.json

# 操作歷史
classifier.exe history list
classifier.exe history rollback abc123
classifier.exe history rollback --last

# 資料庫
classifier.exe db stats
classifier.exe db get STARS-707
classifier.exe db compact
classifier.exe db merge -source other\data.json
classifier.exe db merge -source other\data.json -overwrite
```

## JSON 資料庫

預設位置：`data\json_db\data.json`

主要欄位：`code`、`title`、`studio`、`actresses`、`search_status`、`search_method`、`file_path`

| `search_status` | 說明 |
|----------------|------|
| `imported` | 已匯入，尚未搜尋 |
| `searched_found` | 搜尋成功 |
| `searched_not_found` | 搜尋無結果 |
| `search_error` | 搜尋失敗 |

| `search_method` | 說明 |
|----------------|------|
| `AV-WIKI` | 主要來源 |
| `JAVDB` | 次要來源 |
| `cascade` | 多源級聯 |
| `legacy-import` | 舊版匯入 |

### 資料庫維護

```powershell
# 驗證格式
python tools\verify\verify_json_db_schema.py data\json_db\data.json

# 預覽正規化（不改檔）
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --dry-run

# 直接正規化（自動備份）
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --write
```

## 專案結構

```text
actress-classifier.exe    # Wails GUI（建置產物）
classifier.exe            # Go CLI（建置產物）
major_studios.json        # 大片商清單
studios.json              # 片商識別規則
config.ini                # 設定檔（從 config.ini.example 複製）
requirements.txt          # Python 爬蟲相依套件
│
wails-app\                # Wails 桌面應用原始碼
│   backend\app.go        # Go 後端 bindings
│   frontend\src\         # React + TypeScript UI
│
cmd\scanner\              # Go CLI 入口
pkg\                      # Go 套件
│   database\             # JSON 資料庫
│   extractor\            # 番號提取
│   mover\                # 檔案移動（含批次/回滾）
│   studio\               # 片商識別
│
src\                      # Python 搜尋管線
│   scrapers\             # AV-WIKI、JAVDB 爬蟲
│   services\             # 搜尋核心
│
data\json_db\             # JSON 資料庫（執行時產生）
tools\                    # 維護腳本
```

## 開發測試

```powershell
# Go 測試
go test .\pkg\... -v

# Python 測試
python -m pytest tests\ -v

# Wails 開發模式（熱重載）
cd wails-app && wails dev
```

## 授權

MIT License — 詳見 `LICENSE`

---

# Actress Classification System

A Windows desktop tool for organizing video files by actress and studio.

Extracts video codes from filenames, searches actress information from AV-WIKI and JAVDB, then moves files into organized folder structures.

## Architecture

- **`actress-classifier.exe`** — Desktop GUI (Go + React/TypeScript via Wails)
- **`classifier.exe`** — Go CLI for scanning, moving, and database operations
- **Python search pipeline** — Web scrapers called via subprocess by the GUI

## Quick Start

1. Download `actress-classifier.exe`, `classifier.exe`, `major_studios.json`, and `studios.json` from [Releases](https://github.com/cy5407/PornActressDB-Golang-Migration/releases)
2. Install Python 3.11+ and run `pip install -r requirements.txt` (required for search functionality)
3. Keep these files in the same directory, then launch `actress-classifier.exe`

## Workflow

1. Set input folder (scan source) and output folder (move target)
2. **Scan** — extract video codes from filenames
3. **Search** — fetch actress info from AV-WIKI → JAVDB, write to JSON database
4. **Move** → `outputDir\actress\code.ext`
   **Studio Classify** → `outputDir\studio\actress\code.ext`
5. Use **Operation History** to rollback if needed

## Studio Classification

| Case | Target path |
|------|-------------|
| Major studio actress | `outputDir\{studio}\{actress}\code.ext` |
| Independent/minor studio | `outputDir\單體企劃女優\{actress}\code.ext` |
| No actress data | `outputDir\未分類\code.ext` |

Major studios are defined in `major_studios.json`, while broader studio identification rules are provided by `studios.json`.

## Building from Source

```powershell
# Go CLI
go build -o classifier.exe .\cmd\scanner

# Wails desktop app
cd wails-app
wails build
```

## License

MIT License
