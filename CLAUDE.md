# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 語言偏好

**所有回應必須使用繁體中文。**

## 專案概述

這是一個智慧影片分類管理系統,專注於自動化女優識別、片商分類、多源搜尋與資料庫管理。系統當前為 Python 實作,正規劃遷移至 Go 語言(參見 `docs/go-重構指南.md`)。

**目前狀態**: Python v5.4.3 (生產就緒)
**重構計畫**: 三階段漸進式遷移至 Go (後端→CLI→GUI)

## 啟動與執行

### 主要啟動方式
```bash
# 推薦方式
python run.py

# 替代方式
run_test.bat          # Windows 批次檔
python src/main.py    # 直接執行
```

### 環境需求
- **Python**: 3.8+ (已測試 3.13.5)
- **作業系統**: Windows 10/11 (主要平台)
- **相依套件安裝**: `pip install -r requirements.txt`

### 初次設定
1. 系統會自動建立資料庫於 `C:\Users\{USERNAME}\Documents\ActressClassifier\`
2. 透過 GUI 的「偏好設定」調整參數
3. 設定檔案位於 `config.ini`

## 架構設計

### 核心模組結構
```
src/
├── models/              # 資料模型層
│   ├── config.py           # 設定管理 (INI 格式)
│   ├── database.py         # SQLite 資料庫操作 (CRUD + 自動遷移)
│   ├── extractor.py        # 番號提取邏輯 (正規表達式解析)
│   └── studio.py           # 片商識別引擎 (studios.json 對照)
│
├── services/            # 業務邏輯層
│   ├── classifier_core.py      # 統一分類核心 (單例模式)
│   ├── interactive_classifier.py # 互動式分類 (多女優共演處理)
│   ├── studio_classifier.py    # 片商分類邏輯 (信心度計算)
│   └── web_searcher.py         # 多源搜尋協調器
│
├── scrapers/            # 爬蟲引擎層
│   ├── unified_scraper.py      # 統一爬蟲介面
│   ├── async_scraper.py        # 非同步 HTTP 客戶端
│   ├── rate_limiter.py         # 頻率限制器 (Token Bucket)
│   ├── cache_manager.py        # 快取管理 (記憶體 + 檔案)
│   ├── encoding_utils.py       # 日文編碼處理 (Shift-JIS/EUC-JP)
│   └── sources/
│       ├── javdb_scraper.py    # JAVDB 資料源
│       ├── avwiki_scraper.py   # AV-WIKI 資料源
│       └── chibaf_scraper.py   # chiba-f.net 資料源
│
├── ui/                  # 使用者界面層
│   ├── main_gui.py         # 主視窗 (tkinter)
│   └── preferences_dialog.py # 偏好設定對話框
│
└── utils/               # 工具模組
    └── scanner.py          # 檔案掃描器 (遞迴搜尋影片)
```

### 關鍵設計模式

#### 1. 多源搜尋策略
- **主要來源**: AV-WIKI (最準確)
- **備用來源**: JAVDB, chiba-f.net
- **降級機制**: 主要來源失敗時自動切換備用
- **結果合併**: 智慧合併多源搜尋結果,避免重複

#### 2. 片商分類邏輯
- **信心度計算**: 基於影片數量比例 (threshold 預設 0.6)
- **分類策略**:
  - 高信心度 (≥60%): 歸類到主要片商資料夾
  - 低信心度: 歸類到「單體作品」資料夾
- **偏好學習**: 自動記住使用者的多女優分類偏好

#### 3. 互動式分類處理
- **單人作品**: 自動分類,無需介入
- **多人共演**: 彈出對話框選擇主要女優
- **偏好記憶**: 儲存組合偏好 (如「A+B → A」)
- **批次跳過**: 支援「跳過全部」選項

#### 4. 資料庫設計
- **主表**: videos (番號、檔案路徑、片商)
- **關聯表**: actresses (女優資訊)、video_actress_link (多對多關係)
- **自動升級**: 啟動時自動檢查並執行 schema 遷移
- **備份機制**: 重要操作前自動備份資料庫

### 編碼處理策略

日文網站爬蟲的特殊處理 (`encoding_utils.py`):
1. 自動檢測編碼 (UTF-8 → Shift-JIS → EUC-JP)
2. 嘗試多種解碼方式
3. 降級處理:使用 UTF-8 並替換無效字元
4. 警告過濾:抑制重複的編碼警告訊息

## 開發規範

### 測試命令
```bash
# 單元測試
pytest tests/ -v

# 覆蓋率測試
pytest --cov=src tests/

# 整合測試
python .ai-playground/validations/test_integrated_search.py
```

### 程式碼風格
- **格式化**: `black src/` (自動格式化)
- **檢查**: `flake8 src/` (語法檢查)
- **匯入排序**: `isort src/` (匯入語句排序)

### 日誌系統
- **主日誌**: `unified_classifier.log` (UTF-8 編碼)
- **等級**: INFO (一般操作) / ERROR (錯誤追蹤)
- **格式**: `時間 - 模組 - 等級 - 訊息`

## 常見開發任務

### 新增資料源
1. 在 `src/scrapers/sources/` 建立新的 scraper 類別
2. 繼承 `BaseScraper` 並實作 `search()` 方法
3. 在 `unified_scraper.py` 註冊新資料源
4. 在 `web_searcher.py` 新增對應的搜尋方法
5. 更新 `rate_limiter.py` 的 domain config

### 修改分類邏輯
- **核心檔案**: `src/services/classifier_core.py`
- **關鍵方法**:
  - `process_and_search()`: 搜尋流程
  - `move_files()`: 智慧移動檔案 (單人自動 + 多人互動)
  - `interactive_move_files()`: 純互動模式
  - `_parse_actresses_list()`: 解析女優列表 (處理 # 分隔)

### 資料庫操作
- **增刪改查**: `src/models/database.py` 的 `SQLiteDBManager` 類別
- **關鍵方法**:
  - `add_or_update_video()`: 新增/更新影片資料
  - `get_video_info()`: 查詢影片資訊
  - `get_all_videos()`: 取得全部影片
  - `upgrade_database()`: 自動升級 schema

## Go 重構計畫

**詳細文件**: `docs/go-重構指南.md`

### 三階段遷移策略
1. **階段一** (2-3 週): 後端核心邏輯
   - 爬蟲引擎 (goroutines 取代 asyncio)
   - JSON 資料庫 (取代 SQLite,避免 cgo)
   - 編碼處理 (`golang.org/x/text/encoding`)
   - 測試覆蓋率 ≥70%

2. **階段二** (1-2 週): CLI 工具
   - Cobra 框架
   - 搜尋、分類、統計命令
   - 跨平台建構 (Windows/Linux/macOS)

3. **階段三** (2-4 週): GUI 開發
   - **推薦方案**: Wails (Go + Vue/React) 或混合架構 (Python GUI + Go API)
   - **替代方案**: Fyne (純 Go,簡單但客製化有限)

### 關鍵技術決策
- **資料庫**: JSON 檔案 (符合憲法「不用額外安裝套件」)
- **並發**: goroutines + channels (取代 Python asyncio)
- **限流**: `golang.org/x/time/rate` (Token Bucket)
- **HTML 解析**: `goquery` (類似 BeautifulSoup)

## 特殊注意事項

### 編碼問題
- Windows 終端機預設為 Windows-1252,`run.py` 已處理 UTF-8 轉換
- 日文網站使用 Shift-JIS 或 EUC-JP,需特殊處理
- 所有日誌和資料庫使用 UTF-8 編碼

### 路徑處理
- 使用 `pathlib.Path` 處理跨平台路徑
- Windows 路徑使用反斜線,但 `pathlib` 會自動處理
- 避免硬編碼路徑,使用設定檔 `config.ini`

### 並發控制
- 爬蟲使用 `asyncio.Semaphore` 限制並發數
- 預設最大並發: 3-5 (可在 `config.ini` 調整)
- 每個網域有獨立的 RateLimiter (避免被封鎖)

### FC2/PPV 過濾
- 自動過濾 FC2/PPV 檔案 (通常無法搜尋到完整資訊)
- 過濾邏輯位於 `extractor.py` 的 `extract_code()` 方法

## 效能指標

**當前版本 (v5.4.3)**:
- 系統健康度: 98%
- 檔案處理速度: 1,462 MB/秒
- 記憶體使用: ~17 MB (穩定)
- 併發效率: 1,872 操作/秒
- 測試通過率: 97%+

## 疑難排解

### 常見問題
1. **模組導入錯誤**: 檢查是否在專案根目錄執行 `run.py`
2. **GUI 無法顯示**: 確認 tkinter 已安裝 (Python 內建)
3. **搜尋失敗**: 檢查網路連線和 `unified_classifier.log`
4. **編碼錯誤**: Windows 終端機請執行 `chcp 65001` 切換至 UTF-8

### 日誌位置
- **主日誌**: `unified_classifier.log` (專案根目錄)
- **測試日誌**: `tests/test_debug.log`
- **資料庫位置**: `C:\Users\{USERNAME}\Documents\ActressClassifier\`

## 相關文件

- **README.md**: 完整的功能說明和使用指南
- **啟動說明.md**: 詳細的啟動步驟和故障排除
- **docs/go-重構指南.md**: Go 遷移的完整實施計畫
- **docs/database_guide.md**: 資料庫配置和操作指南
