# 女優分類系統

專為 **Windows 桌面**設計的影片整理工具。

> 正式桌面建置 / 發行目標為 Windows；Linux / macOS 目前主要用於 Go CLI、文件與測試驗證。

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
| 搜尋 | 預設主流程為級聯搜尋（主線仍是 AV-WIKI → JAVDB）；Wails 也提供 AV-WIKI-only / JAVDB-only 來源限定搜尋，方便針對性重跑或補查，結果寫入 JSON 資料庫 |
| 移動 | 依女優分類：`outputDir\女優名\番號.ext` |
| 🏢 片商分類 | 依片商分層：`outputDir\片商名\女優名\番號.ext` |
| 回滾 | 查看操作歷史，一鍵還原移動結果 |

## 快速開始

### 使用者（無需安裝開發工具）

1. 取得**完整 portable bundle**。
   - 若 repo 已提供 [Releases](https://github.com/cy5407/PornActressDB-Golang-Migration/releases)，請下載其中的 portable bundle。
   - 若目前尚未提供 Releases，請先依下方「開發者（自行建置）」執行 `.\setup.ps1`，使用輸出的 `dist\portable\`。
2. 確認 bundle 內至少包含以下內容，並保留原本目錄結構：
   - `actress-classifier.exe`
   - `classifier.exe`
   - `major_studios.json`
   - `studios.json`
   - `src\`（搜尋腳本與 Python 模組）
   - `requirements.txt`
3. 安裝 Python 3.11+，在 bundle 根目錄執行：
   ```powershell
   pip install -r requirements.txt
   ```
4. 在 bundle 根目錄雙擊執行 `actress-classifier.exe`

> Python 環境只用於搜尋爬蟲；GUI 本身不需要 Python 即可啟動，但搜尋功能需要。
>
> 重要：搜尋功能會直接呼叫 `src\scrapers\run_search.py` / `run_batch_search.py`，因此**不要只單獨複製 exe**。

#### 執行入口

- 正式釋出 / 一般使用：`actress-classifier.exe`
- CLI / 輔助工具：`classifier.exe`（Windows）或 `classifier`（Linux / macOS）
- 開發 / 輔助啟動入口：`python run.py`（會優先尋找並啟動已建好的 Wails 執行檔）

### 開發者（自行建置）

#### 建置腳本

```powershell
# Windows（PowerShell）
.\setup.ps1
```

```bash
# Linux / macOS
chmod +x setup.sh && ./setup.sh
```

腳本的實際行為如下：

- `setup.ps1`：執行 `go mod download`，建置 `classifier.exe`，再建置並複製 `actress-classifier.exe` 到專案根目錄，最後輸出 `dist\portable\` 完整 bundle（含 `src\`、資料檔與 `requirements.txt`）
- `setup.sh`：執行 `go mod download`，只建置 `classifier`（Linux / macOS）；Wails GUI 仍以 Windows 為正式桌面建置目標

> 這兩個腳本都不會建立 Python venv、不會安裝 `requirements.txt`、也不會替 `wails-app/frontend` 執行 `npm install`。

#### 手動步驟

```powershell
# 1. Clone 專案
git clone https://github.com/cy5407/PornActressDB-Golang-Migration
cd PornActressDB-Golang-Migration

# 2. 安裝 Python 爬蟲相依套件
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. 建置 Go CLI
go build -o classifier.exe .\cmd\scanner

# 4. 安裝 Frontend 相依
cd wails-app\frontend && npm install && cd ..\..

# 5. 建置 Wails 桌面應用
cd wails-app
wails build
# → wails-app\build\bin\actress-classifier.exe
```

> 若是首次建置或前端套件尚未安裝，請先手動執行 `wails-app\frontend` 內的 `npm install`；`setup.ps1` / `setup.sh` 不會代為安裝。

> 建置 `classifier.exe` 時請使用套件路徑，不要直接指定 `main.go`，否則會漏掉同套件的輔助檔案。
>
> 建置或釋出 Wails 應用時，請分發 `dist\portable\` 的完整內容；除了 `classifier.exe`、`major_studios.json`、`studios.json` 外，搜尋功能也需要同目錄的 `src\` 與 `requirements.txt`。

## 操作流程

1. 啟動 `actress-classifier.exe`
2. 設定輸入資料夾（掃描來源）與輸出資料夾（移動目標）
3. 點「掃描」提取所有番號
4. 點「搜尋」執行預設級聯搜尋主流程（主線為 AV-WIKI → JAVDB，結果自動寫入資料庫）
   - 另外，Wails 前後端也提供 AV-WIKI-only 與 JAVDB-only 的來源限定批次搜尋，可用於針對性重跑、補查，或比對單一來源結果。
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
classifier.exe db clean-actresses
classifier.exe db clean-actresses -write
```

## JSON 資料庫

預設位置：`data\json_db\data.json`

README 這裡只列常用欄位摘要；完整 schema 與欄位說明請見 `wiki/architecture/database.md`。

主要欄位摘要：`code`、`title`、`studio`、`actresses`、`search_status`、`last_search_date`、`search_method`、`avwiki_actress_status`、`avwiki_last_search_date`、`javdb_actress_status`、`javdb_last_search_date`、`file_path`、`error`、`error_kind`

其中 `avwiki_*` / `javdb_*` 欄位會分別記錄來源限定搜尋的狀態與最後搜尋時間，方便針對單一來源重跑後追蹤結果。

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

# 女優名單清洗（dry-run；只輸出變更，不寫入）
classifier.exe db clean-actresses

# 真正寫入清洗結果（會先自動建立 backup）
classifier.exe db clean-actresses -write

# 列出既有 backup
classifier.exe db backup-list

# 還原指定 backup（注意：這裡必須用 -backup-path）
classifier.exe db backup-restore -backup-path data\json_db\backup\backup_YYYY-MM-DD_HH-MM-SS.json
```

`clean-actresses` 是目前正式的 DB 清洗工具，會掃描所有影片的 `actresses` 欄位，移除已知污染字串、重複拼接名稱，以及像 `三田` 這種在 `三田真鈴` 同時存在時才應清掉的片段名稱。

行為重點：
- 預設是 dry-run，不會修改 DB
- 加 `-write` 才會真的寫入
- `-write` 時會先呼叫 `backup-create` 自動備份，再把變更 compact 回主 DB
- 輸出 JSON 會包含 `scanned_videos`、`changed_videos`、`removed_actresses` 與逐筆 `changes`
- 目前屬於高信心規則清洗，不是通用全文正規化器；若要擴規則，請同步更新 `pkg/database/actress_cleaner.go` 與對應測試

## 專案結構

```text
actress-classifier.exe    # Wails GUI（建置產物）
classifier.exe            # Go CLI（建置產物）
major_studios.json        # 大片商清單
studios.json              # 片商識別規則
config.ini                # 設定檔（從 config.ini.example 複製）
requirements.txt          # Python 爬蟲相依套件
setup.ps1                 # Windows 建置腳本（建置 classifier.exe 與 actress-classifier.exe）
setup.sh                  # Linux / macOS 建置腳本（建置 classifier）
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

> Windows is the formal desktop build/release target. Linux/macOS are currently used mainly for the Go CLI, documentation, and test verification.

Extracts video codes from filenames, runs the default cascade search flow (mainline AV-WIKI → JAVDB), and also supports AV-WIKI-only / JAVDB-only reruns for targeted checks before moving files into organized folder structures.

## Architecture

- **`actress-classifier.exe`** — Desktop GUI (Go + React/TypeScript via Wails)
- **`classifier.exe`** — Go CLI for scanning, moving, and database operations
- **Python search pipeline** — Web scrapers called via subprocess by the GUI

## Quick Start

1. Get a **complete portable bundle**.
   If the repo has published [Releases](https://github.com/cy5407/PornActressDB-Golang-Migration/releases), download the portable bundle there.
   If no release is published yet, build locally and use the generated `dist\portable\` output from `.\setup.ps1`.
2. Keep the bundle directory structure intact. Search requires:
   `actress-classifier.exe`, `classifier.exe`, `major_studios.json`, `studios.json`, `src\`, and `requirements.txt`.
3. Install Python 3.11+ in the bundle root and run `pip install -r requirements.txt` (required for search functionality).
4. Launch `actress-classifier.exe` from the bundle root.

> Search is implemented by directly invoking `src/scrapers/run_search.py` and `run_batch_search.py`, so copying only the EXE files is not enough.

Run entry points:

- Release / normal desktop entry: `actress-classifier.exe`
- CLI / helper entry: `classifier.exe` (Windows) or `classifier` (Linux/macOS)
- Dev / helper launcher: `python run.py` (prefers an already-built Wails executable)

## Workflow

1. Set input folder (scan source) and output folder (move target)
2. **Scan** — extract video codes from filenames
3. **Search** — the default/mainline flow is cascade search (AV-WIKI → JAVDB); Wails also exposes AV-WIKI-only and JAVDB-only batch search for targeted reruns or supplementary checks, with results written to the JSON database
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

### Build scripts

```powershell
# Windows (PowerShell)
.\setup.ps1
```

```bash
# Linux / macOS
chmod +x setup.sh && ./setup.sh
```

Actual script behavior:

- `setup.ps1`: runs `go mod download`, builds `classifier.exe`, builds and copies `actress-classifier.exe` to the repo root, then assembles a complete `dist\portable\` bundle for redistribution
- `setup.sh`: runs `go mod download` and builds only `classifier` on Linux/macOS; the Wails GUI remains a Windows-first desktop build target

These scripts do not create a Python venv, do not install `requirements.txt`, and do not run `npm install` in `wails-app/frontend`.

### Manual steps

```powershell
# Go CLI
go build -o classifier.exe .\cmd\scanner

# Frontend dependencies
cd wails-app\frontend && npm install && cd ..\..

# Wails desktop app
cd wails-app
wails build
```

Install frontend dependencies manually before the first Wails build. Python search dependencies also still require a separate `pip install -r requirements.txt`.
When redistributing the Wails app, ship the entire `dist\portable\` directory instead of only the EXE files.

## License

MIT License
