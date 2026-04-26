# 系統架構總覽

> 來源：`README.md`、`AGENTS.md`  
> 更新：2026-04-27（校正 setup.ps1 portable bundle 與 Python 搜尋 runtime 描述）

---

## 概述

**女優分類系統** — Windows 桌面影片整理工具。

- 從影片檔名提取番號
- 搜尋女優資訊（AV-WIKI → JAVDB 級聯）
- 依女優或片商自動分類到資料夾
- 批次移動 + 操作歷史 + 回滾

---

## 三層架構

```
┌─────────────────────────────────────────────────────┐
│       Wails 桌面應用（Go + React/TypeScript）         │
│  actress-classifier.exe                              │
│  wails-app/backend/app.go（Go Bindings）              │
│  wails-app/frontend/src/（React 18 + TypeScript）     │
└─────────────────────────────────────────────────────┘
              ↓ Go 直接 import（零橋接）
┌─────────────────────────────────────────────────────┐
│               Go CLI + pkg/ 套件                     │
│  classifier.exe（scan/move/history/db/identify/cache）│
│  pkg/extractor / mover / database / studio / cache  │
└─────────────────────────────────────────────────────┘
              ↓ subprocess（搜尋專用）
┌─────────────────────────────────────────────────────┐
│        Python 搜尋管線（爬蟲專用）                    │
│  src/scrapers/run_search.py / run_batch_search.py   │
│  src/services/web_searcher.py                       │
│  src/scrapers/ (AV-WIKI、JAVDB 爬蟲)                │
└─────────────────────────────────────────────────────┘
```

**分工**：
- **Go（Wails backend + pkg）**：GUI、掃描、移動、資料庫、操作歷史、片商識別
- **Python**：搜尋 / 爬蟲管線（AV-WIKI → JAVDB）；非爬蟲層不保留 Python fallback

> ⚠️ Python Tkinter GUI、`go_bridge.py`、`go_api/`、`go_runner.py` 已於 W6（2026-04-07）全數移除。

---

## 主要執行檔

| 執行檔 | 說明 |
|--------|------|
| `actress-classifier.exe` | Wails 桌面 GUI（主程式） |
| `classifier.exe` | Go CLI（掃描/移動/DB/快取/片商） |
| `run.py` | 優先啟動 Wails GUI，開發用入口 |

---

## 目錄結構

```
專案根目錄/
├── wails-app/                # Wails 桌面應用
│   ├── main.go               # Wails 進入點
│   ├── backend/
│   │   ├── app.go            # 所有 Go Bindings
│   │   ├── app_test.go       # backend 單元測試
│   │   └── services/
│   │       └── config.go     # config.ini 讀寫
│   └── frontend/
│       └── src/              # React 18 + TypeScript UI
│
├── cmd/scanner/              # classifier.exe 入口（多檔套件）
├── pkg/                      # Go 套件庫
│   ├── app/                  # 服務層（ScanService、MoveService）
│   ├── cache/                # 快取管理
│   ├── database/             # 增量 JSON DB
│   ├── extractor/            # 番號提取器
│   ├── mover/                # 檔案移動（含回滾歷史）
│   ├── pathutil/             # 路徑工具
│   ├── safefile/             # 安全檔案操作
│   └── studio/               # 片商識別器
│
├── src/                      # Python 搜尋管線
│   ├── scrapers/             # AV-WIKI、JAVDB 爬蟲
│   ├── services/             # web_searcher、go_cli、快取服務
│   ├── models/               # JSON DB 委派層
│   └── utils/                # scanner 等工具模組
│
├── data/json_db/             # 資料庫（執行時產生）
├── logs/                     # 操作歷史（Go 產生）
└── wiki/                     # 本知識庫
```

---

## 主要功能模組

### Go 端（Wails backend + pkg）

| 模組 | 職責 |
|------|------|
| `wails-app/backend/app.go` | 全部 Wails bindings：掃描、移動、DB、搜尋、片商、設定 |
| `wails-app/backend/services/config.go` | config.ini 讀寫（ConfigService） |
| `cmd/scanner/` | CLI 進入點，6 個子命令分派 |
| `pkg/app/` | 服務層（業務邏輯抽象） |
| `pkg/extractor/` | 番號提取（正則） |
| `pkg/mover/` | 檔案移動（含回滾歷史） |
| `pkg/database/` | 增量 JSON DB 操作 |
| `pkg/cache/` | 快取 get/set/delete |
| `pkg/studio/` | 片商識別 |
| `pkg/pathutil/` | 統一巢狀路徑判定 |

### Python 端（搜尋管線，爬蟲專用）

| 模組 | 職責 |
|------|------|
| `src/services/go_cli.py` | Python 呼叫 `classifier.exe` 的唯一正式入口 |
| `src/services/web_searcher.py` | 多源搜尋協調（AV-WIKI → JAVDB） |
| `src/scrapers/run_search.py` | Wails subprocess 呼叫入口（單筆搜尋） |
| `src/scrapers/run_batch_search.py` | 批次搜尋入口 |
| `src/models/json_database.py` | Go-only JSON DB 委派層 |
| `src/models/incremental_json_database.py` | 增量 DB / compact 委派層 |
| `src/scrapers/cache_manager.py` | 爬蟲快取層（委派 Go CLI） |
| `src/utils/scanner.py` | Go CLI 掃描薄適配層 |

---

## 快速開始

### 建置腳本

```powershell
# Windows（PowerShell）
.\setup.ps1
```

```bash
# Linux / macOS
chmod +x setup.sh && ./setup.sh
```

腳本行為：

- `setup.ps1`：建置 `classifier.exe`、建置並複製 `actress-classifier.exe`，再組裝 `dist\portable\` 與 `dist\PornActressDB-windows-portable.zip`。
- `setup.sh`：在 Linux / macOS 主要建置 Go CLI `classifier`；Wails GUI 仍以 Windows 為正式桌面發行目標。

portable bundle 的第一次啟動由 `Start-ActressClassifier.bat` 建立 `.venv` 並安裝 `requirements.txt`。開發環境若要直接跑搜尋腳本，仍可手動執行 `pip install -r requirements.txt`。

### 手動步驟

```powershell
# 建置 Go CLI（套件路徑，勿用 main.go）
go build -o classifier.exe .\cmd\scanner

# 建置 Wails 桌面應用
cd wails-app
wails build
# → wails-app\build\bin\actress-classifier.exe

# 啟動（開發用）
python run.py
```

---

## 效能對比

| 操作 | Python | Go | 提升 |
|------|--------|----|------|
| 掃描 1000 個檔案 | ~2.5s | ~0.15s | **16.7x** |
| 批次移動 100 個 | ~3.0s | ~0.3s | **10x** |
| 資料庫查詢 | ~5ms | 64ns | **78,000x** |
| 資料庫更新 | ~250ms | 182μs | **1,300x** |

---

## 相關頁面

- [go-bridge.md](go-bridge.md) — Python→Go 委派歷史與現況（go_cli.py）
- [go-cli.md](go-cli.md) — Go CLI 命令參考
- [database.md](database.md) — 增量 JSON DB 說明
- [search-engine.md](search-engine.md) — 搜尋引擎架構
- [wails-gui.md](wails-gui.md) — Wails GUI 架構
