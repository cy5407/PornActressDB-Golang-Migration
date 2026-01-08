# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 語言偏好

**所有回應必須使用繁體中文 (zh-TW)**

術語對照：create=建立, object=物件, code=程式碼, library=函式庫, package=套件, class=類別, function=函式

## 專案概述

**女優分類系統 (Actress Classifier)** - 智慧影片管理與分類工具

這是一個功能完整的桌面應用程式，用於自動識別女優、片商分類、多源搜尋與資料庫管理。

- **主要語言**: Python 3.8+ (核心邏輯、GUI、爬蟲)
- **效能加速**: Go 1.24.5 (檔案掃描、批次移動)
- **GUI 框架**: tkinter
- **版本**: v5.4.3 (MVP-5 整合完成)
- **主進入點**: `run.py`

## 快速開始

### 啟動應用程式
```bash
python run.py
```

### 安裝相依套件

**Python 相依套件**:
```bash
pip install -r requirements.txt
```

**建置 Go CLI** (可選，用於效能加速):
```bash
# 從專案根目錄執行
go build -o classifier.exe cmd/scanner/main.go

# 或使用標準 Go 工具鏈
cd cmd/scanner
go build -o ../../classifier.exe
```

**驗證 Go CLI**:
```bash
# 檢查是否可用
classifier.exe help

# 測試掃描功能
classifier.exe scan -dir "測試目錄" -workers 10
```

### 執行測試

**Python 測試**:
```bash
# 資料庫狀態檢查
python check_database.py

# FC2/PPV 過濾測試
python test_fc2_filter.py

# 搜尋功能測試
python test_enhanced_search.py
```

**Go 測試**:
```bash
# 執行所有 Go 單元測試
go test ./pkg/...

# 測試特定套件
go test ./pkg/extractor -v
go test ./pkg/mover -v
```

## 專案架構

### 整體架構 (混合語言設計)

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
│   ├── extractor/           # 番號提取器
│   └── mover/               # 檔案移動器 (含操作歷史)
│
├── data/json_db/            # JSON 資料庫
├── logs/                    # 操作日誌 (Go mover 產生)
└── classifier.exe           # 編譯後的 Go CLI (Windows)
```

### Python 核心模組結構

```
src/
├── models/                    # 資料模型層
│   ├── config.py             # ConfigManager - 設定管理
│   ├── incremental_json_database.py  # IncrementalJSONDB - 增量資料庫 (40x 加速)
│   ├── json_database.py      # JSONDBManager - 標準資料庫
│   ├── extractor.py          # UnifiedCodeExtractor - 檔案名稱解析
│   ├── studio.py             # StudioIdentifier - 片商識別
│   └── json_types.py         # 型別定義
│
├── services/                  # 業務邏輯層
│   ├── classifier_core.py    # UnifiedClassifierCore - 分類核心
│   ├── web_searcher.py       # WebSearcher - 多源搜尋引擎
│   ├── interactive_classifier.py  # InteractiveClassifier - 互動分類
│   ├── studio_classifier.py  # StudioClassificationCore - 片商分類
│   ├── safe_searcher.py      # SafeSearcher - 安全 HTTP 請求
│   ├── safe_javdb_searcher.py # SafeJAVDBSearcher - JAVDB 專用
│   └── go_bridge.py          # GoBridge - Go CLI 橋接層 ⚡
│
├── scrapers/                  # 爬蟲層
│   ├── sources/
│   │   ├── avwiki_scraper.py    # AVWikiScraper - AV-WIKI 爬蟲
│   │   ├── chibaf_scraper.py    # ChibafScraper - chiba-f.net 爬蟲
│   │   └── javdb_scraper.py     # JAVDBScraper - JAVDB 爬蟲
│   ├── cache_manager.py       # CacheManager - 快取管理
│   └── unified_scraper.py     # 統一爬蟲介面
│
├── ui/                        # 使用者界面層
│   ├── main_gui.py           # UnifiedActressClassifierGUI - 主介面
│   ├── preferences_dialog.py # PreferencesDialog - 偏好設定
│   └── search_result_dialog.py # 搜尋結果對話框
│
└── utils/                     # 工具模組
    ├── scanner.py            # UnifiedFileScanner - 檔案掃描
    └── progress_tracker.py   # 進度追蹤
```

### Go 模組結構

```
cmd/scanner/main.go           # CLI 主程式
├── scan 命令                # 掃描目錄提取番號
├── move 命令                # 移動檔案 (單檔/批次)
└── history 命令             # 操作歷史管理

pkg/
├── extractor/               # 番號提取套件
│   ├── extractor.go        # CodeExtractor 實作
│   └── extractor_test.go   # 單元測試
│
└── mover/                   # 檔案移動套件
    ├── mover.go            # Mover 實作 (含歷史記錄)
    └── mover_test.go       # 單元測試
```

### 工具腳本目錄

```
tools/
├── analysis/         # 資料分析腳本 (analyze_actresses.py, analyze_names.py)
├── diagnostics/      # 診斷與修復腳本 (check_database.py, debug_avwiki.py)
├── manual_tests/     # 手動測試腳本 (test_smart_search.py)
├── studio_updates/   # 片商資料維護 (update_s1_studio.py)
└── verify/           # 驗證腳本 (verify_fixes.py)
```

**執行規則**: 工具腳本預設依賴 `data/json_db/data.json` 和 `config.ini`，建議從專案根目錄執行。

## 核心架構設計

### Go 橋接層 (Python ⟷ Go 整合)

**設計原理**: Python 負責業務邏輯與 GUI，Go 負責效能敏感操作

#### GoBridge 類別 (src/services/go_bridge.py)

**核心功能**:
```python
from services.go_bridge import GoBridge

bridge = GoBridge()

# 1. 掃描目錄 (Go 並發掃描，速度提升 10-20x)
results = bridge.scan_directory(
    directory="D:\\Videos",
    workers=10,           # 並發數
    recursive=True        # 遞迴掃描
)
# 返回: list[ScanResult(path, code)]

# 2. 移動檔案 (單檔)
result = bridge.move_file(
    source="A.mp4",
    destination="dest/A.mp4",
    strategy="skip"       # skip, overwrite, rename
)

# 3. 批次移動 (Go 並發處理)
items = [
    {"source": "A.mp4", "destination": "dest/A.mp4"},
    {"source": "B.mp4", "destination": "dest/B.mp4"},
]
result = bridge.batch_move(items, strategy="skip")

# 4. 操作歷史
logs = bridge.list_operations()              # 列出所有操作
log = bridge.get_operation("abc123")        # 取得詳細記錄
result = bridge.rollback("abc123")          # 回滾指定操作
result = bridge.rollback_last()             # 回滾最近一次
```

**fallback 機制**:
```python
# GoBridge 自動偵測 classifier.exe 是否可用
if bridge.is_available:
    # 使用 Go 加速
    results = bridge.scan_directory(dir)
else:
    # 降級到 Python 實作
    results = python_scanner.scan(dir)
```

**自動偵測路徑**:
1. 專案根目錄 `classifier.exe`
2. 當前工作目錄
3. PATH 環境變數

#### Go CLI 命令列介面

**classifier.exe 命令**:
```bash
# 掃描目錄
classifier.exe scan -dir "D:\Videos" -workers 10 -recursive=true

# 移動檔案 (單檔)
classifier.exe move -src "A.mp4" -dst "dest/A.mp4" -strategy skip

# 批次移動
classifier.exe move -batch moves.json -strategy skip

# 操作歷史
classifier.exe history list                 # 列出所有操作
classifier.exe history show <操作ID>        # 顯示詳細記錄
classifier.exe history rollback <操作ID>    # 回滾操作
classifier.exe history rollback --last      # 回滾最近一次
```

**輸出格式**: JSON (方便 Python 解析)

#### 效能對比

| 操作 | Python | Go | 提升倍數 |
|------|--------|----|---------|
| 掃描 1000 個檔案 | ~2.5s | ~0.15s | **16.7x** |
| 批次移動 100 個檔案 | ~3.0s | ~0.3s | **10x** |
| 番號提取 (正則) | ~100 μs | ~5 μs | **20x** |

#### 操作歷史系統

**日誌結構** (`logs/*.json`):
```json
{
  "id": "abc123",
  "timestamp": "2025-12-22T10:30:00Z",
  "type": "batch_move",
  "status": "completed",
  "items": [
    {
      "source": "A.mp4",
      "destination": "dest/A.mp4",
      "success": true
    }
  ]
}
```

**使用場景**:
- 分類錯誤需要回滾
- 批次操作前預覽
- 審計與除錯

### 資料庫系統

**IncrementalJSONDB (增量資料庫)**
- **效能優化**: 寫入速度提升 40 倍
- **機制**: Journal 檔案記錄增量變更 (JSON Lines)
- **檔案結構**:
  - `data.json` - 主資料檔案
  - `data.journal` - 增量變更日誌
  - `data.index` - Dirty keys 索引
- **使用時機**:
  - ✅ 頻繁的小規模更新 (新增/修改單一影片)
  - ❌ 大規模批次更新 (建議用 JSONDBManager)
- **自動合併閾值**:
  - Journal 超過 1000 條記錄
  - Journal 年齡超過 1 小時

**關鍵 API**:
```python
db = IncrementalJSONDB('data/json_db')
db.update_video('STARS-707', {'title': '新標題'})  # 快速更新
db.compact_if_needed()  # 自動判斷是否合併
db.compact()  # 強制合併
```

### 搜尋引擎架構

**級聯搜尋順序** (失敗時自動降級):
1. **AV-WIKI** (主要來源)
2. **chiba-f.net** (備用來源)
3. **JAVDB** (最終來源)

**WebSearcher 核心特性**:
- SafeSearcher: 速率限制、重試機制、快取
- 日文網站專用配置: 更短延遲 (0.5-1.5s)
- JAVDB 專用搜尋器: SafeJAVDBSearcher
- 自動編碼檢測: chardet + BeautifulSoup

**配置 (config.ini)**:
```ini
[search]
batch_size = 10
thread_count = 5
batch_delay = 2.0
request_timeout = 20
avwiki_concurrent_enabled = true
avwiki_max_concurrent = 15
```

### 分類系統

**UnifiedClassifierCore**:
- 整合女優分類與片商分類功能
- 使用 `IncrementalJSONDB` 作為資料層
- 支援互動模式與自動模式

**StudioClassificationCore**:
- 信心度計算: 基於影片數量比例
- 分類策略: 高信心度 (>80%) 直接分類
- 路徑管理: 安全的檔案移動

## 重要開發規範

### Go ⟷ Python 整合規範

**Go CLI 設計原則**:
- ✅ **無狀態**: 每次呼叫獨立執行，不依賴先前狀態
- ✅ **JSON 輸出**: stdout 輸出結構化 JSON，stderr 輸出錯誤訊息
- ✅ **零相依**: Go 模組不依賴 Python 環境，可獨立執行
- ✅ **向後相容**: 保留舊有命令列介面 (如 `-dir` 參數)

**Python 橋接規範**:
```python
# ✅ 正確做法: 使用 GoBridge 封裝
from services.go_bridge import get_bridge
bridge = get_bridge()
if bridge.is_available:
    results = bridge.scan_directory(dir)

# ❌ 錯誤做法: 直接呼叫 subprocess
subprocess.run(["classifier.exe", "scan", "-dir", dir])  # 缺乏錯誤處理
```

**fallback 策略**:
```python
# 永遠準備 Python fallback
try:
    if go_bridge.is_available:
        result = go_bridge.scan_directory(dir)  # 優先使用 Go
    else:
        result = python_scanner.scan(dir)       # 降級到 Python
except GoBridgeError as e:
    logger.warning(f"Go 加速失敗，切換 Python: {e}")
    result = python_scanner.scan(dir)
```

**測試策略**:
1. **Go 單元測試**: `go test ./pkg/...`
2. **Python 整合測試**: 測試 GoBridge API
3. **端對端測試**: 測試 GUI → GoBridge → Go CLI 完整流程

### 執行緒安全

**GUI 更新必須回主執行緒**:
```python
# ✅ 正確做法
root.after(0, lambda: progress_callback("訊息"))

# ❌ 錯誤做法
progress_callback("訊息")  # 直接在背景執行緒呼叫
```

**長時間操作使用背景執行緒**:
```python
def long_task():
    thread = threading.Thread(target=do_work)
    thread.start()
```

### 日誌規範

**統一使用 emoji 前綴**:
- 🚀 開始/啟動
- ✅ 成功
- ❌ 失敗/錯誤
- ⚠️ 警告
- 📊 統計/資料
- 🔍 搜尋
- 💾 資料庫操作

```python
logger.info("🚀 開始搜尋女優資訊...")
logger.info("✅ 搜尋完成，找到 5 筆結果")
logger.error("❌ 搜尋失敗: 網路連線逾時")
```

### 編碼處理

**Windows 相容性** (run.py 中已設定):
```python
if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
```

**日文網站爬蟲**:
- 使用 `chardet` 自動檢測編碼
- 明確拒絕 Brotli 壓縮 (`Accept-Encoding: identity`)
- 支援 Shift_JIS、EUC-JP、UTF-8

## 資料庫設定

### 配置檔案 (config.ini)

```ini
[database]
json_data_dir = data/json_db

[paths]
default_input_dir = C:/Users/cy540/Downloads

[classification]
mode = interactive
auto_apply_preferences = true
```

### JSON 資料庫優勢
- ✓ 無需額外安裝資料庫軟體
- ✓ 易於備份和遷移 (單一 JSON 檔案)
- ✓ 支援並行讀寫 (filelock 機制)
- ✓ 人類可讀的資料格式
- ✓ 輕量級部署，適合個人使用

## 常見開發任務

### 修改 Go CLI 功能

**新增命令**:
1. 在 `cmd/scanner/main.go` 中新增命令處理函式
2. 更新 `printUsage()` 說明文字
3. 在 `pkg/` 中實作核心邏輯
4. 撰寫單元測試 `*_test.go`
5. 更新 `go_bridge.py` 的 Python 介面

**修改番號提取邏輯**:
1. 編輯 `pkg/extractor/extractor.go`
2. 執行測試: `go test ./pkg/extractor -v`
3. 重新建置: `go build -o classifier.exe cmd/scanner/main.go`
4. 驗證 Python 整合: `python -c "from services.go_bridge import GoBridge; print(GoBridge().is_available)"`

**範例: 新增番號模式**:
```go
// pkg/extractor/extractor.go
patterns := []string{
    `[A-Z]+-\d+`,           // 現有模式
    `FC2-PPV-\d+`,          // 現有模式
    `YOUR-NEW-PATTERN`,     // 新增模式
}
```

### 新增爬蟲來源

1. 在 `src/scrapers/sources/` 建立新爬蟲
2. 繼承 `BaseScraper` 類別
3. 實作 `search()` 方法
4. 在 `WebSearcher` 中整合級聯邏輯

### 修改資料庫結構

1. 更新 `src/models/json_types.py` 中的型別定義
2. 修改 `IncrementalJSONDB` 或 `JSONDBManager` 的對應方法
3. 執行遷移腳本 (如需要)
4. 更新單元測試

### 新增 GUI 功能

1. 在 `src/ui/main_gui.py` 中新增按鈕/方法
2. 確保長時間操作使用背景執行緒
3. 使用 `root.after()` 更新 GUI 元件
4. 新增對應的 `services` 層方法

### 整合新的 Go 功能到 GUI

**範例: 整合 Go 掃描到 GUI**:
```python
# src/ui/main_gui.py

from services.go_bridge import get_bridge

def scan_with_go(self):
    """使用 Go 加速掃描"""
    bridge = get_bridge()

    if not bridge.is_available:
        messagebox.showwarning("警告", "Go CLI 不可用，使用 Python 掃描")
        return self.scan_with_python()

    try:
        results = bridge.scan_directory(
            directory=self.input_dir,
            workers=10
        )
        self.display_results(results)
    except Exception as e:
        logger.error(f"Go 掃描失敗: {e}")
        # Fallback 到 Python
        self.scan_with_python()
```

## 開發工具最佳實踐

### 程式碼搜尋策略

**使用 `grep` 工具** (預設，95% 情況)：
```python
# 一般搜尋
grep pattern: "def search", glob: "*.py"

# 顯示上下文
grep pattern: "class.*Config", output_mode: "content", -C: 3

# 統計匹配數
grep pattern: "import requests", output_mode: "count"
```

**使用 `rg` 指令** (特殊需求，5% 情況)：
```bash
# JSON 輸出（用於程式化處理）
rg "TODO|FIXME" --json | python parse.py

# 詳細統計（搜尋速度、檔案數等）
rg "pattern" --stats

# 特殊正則引擎
rg "(?P<name>pattern)" --pcre2
```

**選擇原則**：
- ✅ 預設用 `grep` 工具（簡潔、結構化輸出）
- 🔧 需要 JSON/stats 時才用 `rg` 指令

## 關鍵檔案位置

- **資料庫**: `data/json_db/data.json`
- **快取**: `cache/` (搜尋結果快取)
- **日誌**: `unified_classifier.log`
- **設定**: `config.ini`

## 已知限制

- GUI 框架: tkinter (單執行緒模型)
- 資料庫: JSON 檔案型 (不適合超大規模資料)
- 平台: 主要測試於 Windows 10/11

## 參考文件

- [專案計畫書](專案管理/專案計畫/專案計畫書_v1.0.md)
- [需求規格書](專案管理/需求規格/需求規格書_v1.0.md)
- [功能改善計畫](docs/IMPROVEMENT_PLAN.md)
- [Copilot 指引](.github/copilot-instructions.md)
