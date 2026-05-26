---
name: actress-classifier
description: 女優分類系統開發指引 - 用於理解專案架構、程式碼規範、常用開發模式、術語對照表和 Python/Go 混合架構設計
---

# 女優分類系統開發 Skill

## 專案概述

這是一個 Python + Tkinter GUI 的影片女優分類系統 (v6.x)。
主要功能：從影片檔名提取番號，搜尋女優資訊，自動分類到對應資料夾。

## 語言規範

**所有回應、註解、UI 文字必須使用繁體中文 (zh-TW)**

### 術語對照表

| 英文 | 繁體中文 |
|------|----------|
| create | 建立 |
| object | 物件 |
| queue | 佇列 |
| stack | 堆疊 |
| information | 資訊 |
| invocation | 呼叫 |
| code | 程式碼 |
| running | 執行 |
| library | 函式庫 |
| package | 套件 |
| class | 類別 |
| function | 函式 |
| document | 文件 |

## 技術棧

- **Python**: 3.11+
- **GUI**: Tkinter / ttkbootstrap
- **非同步**: asyncio + aiohttp
- **JSON 處理**: orjson（高效能）
- **爬蟲**: BeautifulSoup4
- **資料庫**: 自製增量 JSON 資料庫（Journal 機制）

## 核心架構

```
src/
├── models/                              # 資料模型
│   ├── json_database.py                 # 基礎 JSON 資料庫
│   ├── incremental_json_database.py     # 增量儲存（Journal 機制）
│   └── extractor.py                     # 番號提取器
├── services/                            # 業務邏輯
│   ├── classifier_core.py               # 核心分類邏輯
│   └── web_searcher.py                  # 網路搜尋協調器
├── scrapers/                            # 爬蟲
│   └── sources/
│       ├── avwiki_scraper.py            # AV-WIKI（主要來源）
│       └── javdb_scraper.py             # JAVDB（補充 / 備援）
└── ui/                                  # 介面
    ├── main_gui.py                      # 主 GUI
    └── search_result_dialog.py          # 搜尋結果對話框
```

## 常用指令

```bash
# 啟動 Wails GUI
.\actress-classifier.exe

# 測試模組匯入
python -c "import sys; sys.path.insert(0, 'src'); from ui.main_gui import UnifiedActressClassifierGUI; print('OK')"

# 檢查語法
python -m py_compile src/ui/main_gui.py
```

## 程式碼規範

### 風格指南
- 遵循 PEP 8
- 使用 type hints
- 類別命名：PascalCase
- 函式/變數命名：snake_case
- 常數命名：UPPER_SNAKE_CASE

### 命名覆寫補充
- 通用命名原則以 `.Codex/skills/naming-conventions/SKILL.md` 為基準
- 本專案主業務識別碼以 `code` 為主名稱；`id` 僅在部分 JSON 結構中作為內部或舊版相容欄位
- GoBridge 的資料庫 wrapper 採 `db_` 前綴家族，例如 `db_get_video`、`db_get_stats`
- 批次命名依模組家族延續既有模式：搜尋服務常用 `batch_search` / `batch_cascade_search`，片商識別維持 `identify_studios_batch`
- Go CLI 已穩定使用 `-dir`、`-src`、`-dst`、`-batch` 等旗標，新文件與新介面描述需優先維持相容

### 日誌 Emoji 前綴
- 🚀 開始操作
- ✅ 成功完成
- ❌ 失敗錯誤
- ⚠️ 警告提示
- 📁 檔案操作
- 🔍 搜尋操作
- 💾 資料儲存
- 🧹 清理操作

## 重要開發模式

### 1. 資料庫操作（使用增量儲存）

```python
from models.incremental_json_database import IncrementalJSONDB

db = IncrementalJSONDB('data/json_db')
db.add_or_update_video(code, video_info)
# Journal 機制讓寫入快 40 倍
```

### 2. 非同步批次爬蟲

```python
# 批次併發搜尋（AV-WIKI 支援高併發）
results = await scraper.batch_search_concurrent(
    codes,
    max_concurrent=15,
    progress_callback=callback
)
```

### 3. GUI 背景執行緒

```python
import threading

# 長時間操作必須在背景執行緒
thread = threading.Thread(
    target=self._worker_function, 
    daemon=True
)
thread.start()

# GUI 更新需回到主執行緒
self.root.after(0, lambda: self.update_ui())
```

### 4. 級聯搜尋策略

搜尋順序：AV-WIKI → JAVDB

```python
result = self.web_searcher.batch_cascade_search(
    codes,
    stop_event,
    progress_callback,
    enable_javdb=True
)
```

## 注意事項

1. **編碼處理**：日文網站需處理 UTF-8, EUC-JP, Shift_JIS
2. **執行緒安全**：GUI 更新需使用 `root.after()` 回到主執行緒
3. **進度回報**：併發搜尋使用 threading.Lock 確保順序
4. **快取清理**：程式關閉時自動清理過期快取
5. **現況優先**：若 `AGENTS.md` 與本 Skill 對版本或流程描述不同，優先以 `AGENTS.md` 與目前程式碼為準

## 專案術語

- **番號** = 影片編號（如 STARS-707, SONE-123）
- **女優** = 演員
- **片商** = 製作公司（如 S1, MOODYZ, Idea Pocket）
- **Journal** = 增量日誌檔（用於快速寫入）
- **級聯搜尋** = 多來源依序搜尋直到成功
