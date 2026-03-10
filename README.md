# 女優分類系統 - 智慧影片管理工具

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Go](https://img.shields.io/badge/Go-1.24.5+-00ADD8.svg)](https://go.dev/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-success.svg)]()

一個功能完整的智慧影片分類管理系統，支援自動女優識別、片商分類、多源搜尋與資料庫管理。**採用 Python + Go 混合架構**，效能關鍵路徑使用 Go 加速。

## ✨ 主要功能

### 🤖 AI 開發增強
- **11 個 Agent Skills**: 專案特定的 AI 開發指引（VS Code Copilot Chat 整合）
- **智能程式碼審查**: 高信噪比審查（僅報告關鍵問題）
- **Go 橋接開發**: Python ↔ Go 整合完整工作流程
- **智能程式碼搜尋**: fd + rg 工具，10-100x 搜尋加速

### 🔍 智慧搜尋系統
- **多源級聯搜尋**: 支援 AV-WIKI、chiba-f.net、JAVDB 三層級聯搜尋
- **批次併發處理**: AV-WIKI 支援 15 並發批次搜尋（11.7x 效能提升）
- **自動回退**: 主要搜尋失敗時自動切換備用源
- **智慧過濾**: 自動過濾 FC2/PPV 檔案，避免無效搜尋

### 🗂️ 分類管理
- **女優分類**: 根據檔案名稱自動識別女優並分類
- **片商分類**: 基於信心度的智慧片商分類系統
- **互動模式**: 支援手動確認和自動分類模式
- **操作回滾**: 支援一鍵回滾錯誤的分類操作

### 💾 資料庫系統
- **增量寫入**: Journal 機制實現 40x 寫入加速
- **Go 加速**: 資料庫操作使用 Go 實現，查詢速度達 64ns
- **並行安全**: 支援多執行緒讀寫，檔案鎖定保護
- **自動合併**: 智慧判斷 Journal 合併時機

### ⚡ Go 加速模組
- **檔案掃描**: Go 並發掃描，16.7x 效能提升
- **批次移動**: Go 批次處理，10x 效能提升
- **番號提取**: Go 正則處理，20x 效能提升
- **片商識別**: Go 前綴匹配，10x 效能提升

### 🎨 使用者界面
- **現代化 GUI**: 基於 tkinter 的直觀界面
- **操作歷史**: 完整的操作記錄與回滾功能
- **即時進度**: 詳細的處理進度與狀態顯示
- **偏好設定**: 可客製化的使用者偏好

## 📊 效能提升統計

| 模組 | Python 基準 | Go 實測 | 提升倍數 |
|------|------------|---------|---------|
| 檔案掃描 | ~2.5s (1000檔) | ~0.15s | **16.7x** |
| 批次移動 | ~3.0s (100檔) | ~0.3s | **10x** |
| 番號提取 | ~100μs | ~5μs | **20x** |
| 片商識別 | ~1ms | ~0.1ms | **10x** |
| 資料庫查詢 | ~5ms | 64ns | **78,000x** |
| 資料庫更新 | ~250ms | 182μs | **1,300x** |

## 🚀 快速開始

### 系統需求
- Python 3.8 或更高版本
- Go 1.24.5 或更高版本（選用，用於效能加速）
- Windows 10/11 (主要測試平台)
- 網路連接 (用於線上搜尋功能)

### 安裝步驟

1. **複製專案**
   ```bash
   git clone https://github.com/YOUR_USERNAME/actress-classifier.git
   cd actress-classifier
   ```

2. **建立虛擬環境**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   ```

3. **安裝 Python 相依套件**
   ```bash
   pip install -r requirements.txt
   ```

4. **建置 Go CLI（選用，用於效能加速）**
   ```bash
   go build -o classifier.exe ./cmd/scanner
   ```

5. **啟動程式**
   ```bash
   python run.py
   ```

### 驗證安裝

```bash
# 檢查 Go CLI 是否可用
classifier.exe help

# 執行 Go 測試
go test ./pkg/... -v

# 檢查資料庫狀態
classifier.exe db stats
```

## 🛠️ 技術架構

### 混合語言設計

```
專案根目錄/
├── src/                      # Python 核心邏輯
│   ├── models/              # 資料層
│   ├── services/            # 業務邏輯層 (含 go_bridge.py)
│   ├── scrapers/            # 爬蟲層
│   ├── ui/                  # GUI 層
│   └── utils/               # 工具層
│
├── cmd/                      # Go CLI 主程式
│   └── scanner/
│       └── main.go          # classifier.exe 進入點
│
├── pkg/                      # Go 套件
│   ├── cache/               # 快取管理套件
│   ├── database/            # 增量資料庫 (Journal 機制)
│   ├── extractor/           # 番號提取器
│   ├── mover/               # 檔案移動器 (含操作歷史)
│   └── studio/              # 片商識別器
│
├── .claude/skills/          # Agent Skills (11 個)
├── data/json_db/            # JSON 資料庫
├── logs/                    # 操作日誌
└── classifier.exe           # 編譯後的 Go CLI
```

### Go CLI 命令

```bash
# 掃描目錄
classifier.exe scan -dir "D:\Videos" -workers 10

# 移動檔案
classifier.exe move -src "A.mp4" -dst "dest/A.mp4" -strategy skip

# 批次移動
classifier.exe move -batch moves.json

# 操作歷史
classifier.exe history list
classifier.exe history rollback <操作ID>
classifier.exe history rollback --last

# 資料庫操作
classifier.exe db get STARS-707
classifier.exe db update STARS-707 video.json
classifier.exe db list
classifier.exe db stats
classifier.exe db compact

# 片商識別
classifier.exe identify SONE-123
classifier.exe identify -batch codes.txt
classifier.exe identify -list

# 快取管理
classifier.exe cache stats
classifier.exe cache clear
classifier.exe cache get <key>
classifier.exe cache set <key> <value>
```

### Python 橋接層

```python
from services.go_bridge import GoBridge, db_get_video, db_get_stats

# 初始化
bridge = GoBridge()

# 掃描目錄 (Go 加速)
results = bridge.scan_directory("D:\\Videos", workers=10)

# 資料庫操作
video = db_get_video("STARS-707")
stats = db_get_stats()
```

### 核心技術
- **Python 3.8+**: GUI、爬蟲、業務邏輯
- **Go 1.24.5+**: 效能關鍵路徑（掃描、移動、資料庫）
- **tkinter**: GUI 框架
- **JSON**: 輕量級資料儲存 (增量 Journal 機制)
- **httpx/aiohttp**: 非同步 HTTP 客戶端
- **BeautifulSoup**: HTML 解析

## 🔧 設定說明

### config.ini

```ini
[database]
json_data_dir = data/json_db

[paths]
default_input_dir = .

[search]
batch_size = 10
thread_count = 5
avwiki_concurrent_enabled = true
avwiki_max_concurrent = 15

[classification]
mode = interactive
auto_apply_preferences = true

[go_integration]
enabled = true
exe_path = classifier.exe
default_workers = 10
default_strategy = skip
```

## 🧪 測試

### Go 測試
```bash
# 執行所有 Go 測試
go test ./pkg/... -v

# 執行基準測試
go test -bench=. ./pkg/database/...

# 測試特定套件
go test ./pkg/extractor -v
go test ./pkg/mover -v
go test ./pkg/studio -v
go test ./pkg/database -v
```

### Python 測試
```bash
# 資料庫狀態檢查
python check_database.py

# FC2/PPV 過濾測試
python test_fc2_filter.py

# 搜尋功能測試
python test_enhanced_search.py
```

### JSON 資料庫 Schema 維護

當 `data/json_db/data.json` 的 `videos` 欄位出現歷史遺留格式不一致時，可使用以下工具腳本：

```bash
# 先檢查目前 schema 問題（非 0 exit code 代表驗證失敗）
python tools\verify\verify_json_db_schema.py data\json_db\data.json

# 預覽正規化變更，不寫入檔案
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --dry-run

# 輸出正規化結果到新檔案
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --output normalized_data.json

# 直接覆寫原始 data.json（會自動建立 backup）
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --write
```

目前正規化腳本會處理：

- 統一 `search_status` 為 `imported`、`searched_found`、`searched_not_found`、`search_error`
- 統一 `search_method` 為 `legacy-import`、`AV-WIKI`、`chiba-f.net`、`JAVDB`、`cascade`
- 移除 `id == code` 的重複欄位
- 移除測試欄位 `test_field`
- 補齊缺少的 `original_filename` / `file_path`

## 📚 文件

### 核心文檔
- [CLAUDE.md](CLAUDE.md) - AI 開發指引與專案架構（最重要）
- [README.md](README.md) - 專案說明與快速開始（本檔案）
- [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md) - 快速上手指南

### Agent Skills
- [VSCODE_AGENT_SKILLS_GUIDE.md](docs/internal/ai/VSCODE_AGENT_SKILLS_GUIDE.md) - VS Code Agent Skills 完整指南
- [CODE_REVIEW_SKILL_GUIDE.md](docs/internal/ai/CODE_REVIEW_SKILL_GUIDE.md) - Code Review Skill 使用指南
- [SKILLS_ANALYSIS_REPORT.md](docs/internal/ai/SKILLS_ANALYSIS_REPORT.md) - Skills 分析報告

### 開發指引
- 11 個 Agent Skills 位於 `.claude/skills/` 目錄
- 在 VS Code Copilot Chat 中自動載入
- 查看 [VSCODE_SKILLS_QUICK_REFERENCE.md](docs/internal/ai/VSCODE_SKILLS_QUICK_REFERENCE.md) 快速參考
- 查看 [docs/README.md](docs/README.md) 了解目前保留的文件分類與清理規則

## 📈 版本歷史

### v6.0.0 (2026-02-18) - 當前版本
- ⚡ **Go 加速整合**: 完成 Python + Go 混合架構
- 🗄️ **增量資料庫**: Go 實現的 Journal 機制，1300x 更新加速
- 🔄 **操作回滾**: 完整的操作歷史與一鍵回滾功能
- 📊 **效能提升**: 整體效能提升 10-78,000 倍
- 🤖 **Agent Skills**: 新增 11 個專業 Agent Skills（VS Code Copilot 整合）
- 💾 **快取系統**: Go 快取管理套件，支援 LRU、TTL、持久化
- 📝 **專案規模**: 61 程式檔，20,712 行程式碼（Python: 16,844 + Go: 3,868）

### v5.4.3 (2025-12-21)
- 🚀 Go 橋接層完成 (MVP-1 到 MVP-5)
- 🔍 AV-WIKI 批次併發搜尋
- 🛡️ 片商識別器 Go 實現

### v5.2 (2025-06-18)
- 🚀 完整系統模組化重構
- 🔍 多源搜尋引擎整合
- 🛡️ FC2/PPV 智慧過濾

## 🐛 問題回報

如遇到問題，請提供以下資訊：
1. 錯誤訊息的完整內容
2. 作業系統版本
3. Python / Go 版本
4. 重現步驟

## 🤝 貢獻指南

1. Fork 此專案
2. 建立功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交變更 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 開啟 Pull Request

## 📄 授權

此專案採用 MIT 授權條款 - 詳見 [LICENSE](LICENSE) 檔案

## 🙏 致謝

- 感謝所有使用者的回饋與建議
- 感謝開源社群提供的工具與函式庫
- 特別感謝 AI 輔助開發工具的支援

---

**注意**: 此工具僅供個人使用，請遵守相關法律法規與版權規定。
