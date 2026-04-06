# 系統架構總覽

> 來源：`README.md`、`AGENTS.md`  
> 更新：2026-04-06

---

## 概述

**女優分類系統 v6.0.0** — Windows 桌面影片整理工具。

- 從影片檔名提取番號
- 搜尋女優資訊（AV-WIKI → JAVDB 級聯）
- 依女優或片商自動分類到資料夾
- 批次移動 + 操作歷史 + 回滾

**規模**：61 個程式檔，20,712 行（Python: 16,844 + Go: 3,868）

---

## 雙語言架構

```
┌─────────────────────────────────────────────────────┐
│                Python 層（GUI + 邏輯）                │
│  Tkinter GUI → ClassifierCore → WebSearcher → DB     │
│                       ↓                              │
│              GoBridge (Facade)                       │
│         go_api/*.py → GoCommandRunner                │
└─────────────────────────────────────────────────────┘
                        ↓ subprocess
┌─────────────────────────────────────────────────────┐
│               Go 層（效能敏感操作）                   │
│        classifier.exe（6 個子命令）                  │
│  scan | move | history | db | identify | cache       │
└─────────────────────────────────────────────────────┘
```

**分工**：
- **Python**：GUI、搜尋流程、分類邏輯、資料庫整合
- **Go**：高速掃描、批次移動、資料庫工具、操作歷史

---

## 效能對比

| 操作 | Python | Go | 提升 |
|------|--------|----|------|
| 掃描 1000 個檔案 | ~2.5s | ~0.15s | **16.7x** |
| 批次移動 100 個 | ~3.0s | ~0.3s | **10x** |
| 資料庫查詢 | ~5ms | 64ns | **78,000x** |
| 資料庫更新 | ~250ms | 182μs | **1,300x** |

---

## 目錄結構

```
專案根目錄/
├── src/                      # Python 核心
│   ├── models/               # 資料模型（DB、Extractor、Studio）
│   ├── services/             # 業務邏輯（GoBridge、WebSearcher、Core）
│   │   └── go_api/           # Go CLI 領域 API 封裝
│   ├── scrapers/             # 爬蟲（AV-WIKI、JAVDB）
│   ├── ui/                   # Tkinter GUI
│   └── utils/                # 工具模組
│
├── cmd/scanner/              # Go CLI 主程式（多檔套件）
├── pkg/                      # Go 套件庫
│   ├── app/                  # 服務層（ScanService、MoveService）
│   ├── cache/                # 快取管理
│   ├── database/             # 增量 JSON DB
│   ├── extractor/            # 番號提取器
│   ├── mover/                # 檔案移動器
│   └── studio/               # 片商識別器
│
├── data/json_db/             # 資料庫檔案
├── logs/                     # 操作歷史（Go 產生）
├── dist/                     # 發行版
│   ├── 女優分類系統_修復版.exe  # PyInstaller 打包
│   └── classifier.exe        # Go CLI（需手動同步）
└── wiki/                     # 本知識庫
```

---

## 主要功能模組

### Python 端

| 模組 | 職責 |
|------|------|
| `src/ui/main_gui.py` | Tkinter 主介面，所有按鈕與背景執行緒 |
| `src/services/classifier_core.py` | 分類核心：掃描 → 搜尋 → 分類 |
| `src/services/web_searcher.py` | 多源搜尋協調（AV-WIKI → JAVDB） |
| `src/services/go_bridge.py` | GoBridge Facade，Go CLI 統一入口 |
| `src/services/go_api/` | Go CLI 各子命令的 Python 封裝 |
| `src/models/incremental_json_database.py` | 增量 JSON DB（40x 加速） |
| `src/models/json_database.py` | 標準 JSON DB（委派給 Go） |

### Go 端

| 套件 | 職責 |
|------|------|
| `cmd/scanner/` | CLI 進入點，6 個子命令分派 |
| `pkg/app/` | 服務層（業務邏輯抽象） |
| `pkg/extractor/` | 番號提取（正則） |
| `pkg/mover/` | 檔案移動（含回滾歷史） |
| `pkg/database/` | 增量 JSON DB 操作 |
| `pkg/cache/` | 快取 get/set/delete |
| `pkg/studio/` | 片商識別 |

---

## 快速開始

```powershell
# 執行程式
python run.py

# 建置 Go CLI（套件路徑，勿用 main.go）
go build -o classifier.exe .\cmd\scanner

# 建立 Windows 發行版
python -m PyInstaller --clean --noconfirm "女優分類系統_修復版.spec"
Copy-Item .\classifier.exe .\dist\classifier.exe -Force
```

---

## 相關頁面

- [go-bridge.md](go-bridge.md) — GoBridge 委派架構詳解
- [go-cli.md](go-cli.md) — Go CLI 命令參考
- [database.md](database.md) — 增量 JSON DB 說明
- [search-engine.md](search-engine.md) — 搜尋引擎架構
