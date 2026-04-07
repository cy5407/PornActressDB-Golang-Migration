# Wails 遷移 Python 程式碼審計報告

**建立日期**: 2026-04-07  
**分支**: `wails-implementation`  
**目的**: 完整分析 `src/` 目錄下所有 Python 模組的現況、必要性與可刪除性

---

## 一、總覽

### 架構現況（Wails 遷移後）

```
Wails 前端 (React/TypeScript)
    ↓ Wails bindings
Go 後端 (wails-app/backend/app.go)
    ├── 掃描 / 移動 / DB / 片商識別 → 直接呼叫 pkg/ Go 套件
    └── 搜尋影片元資料 → subprocess 呼叫 src/scrapers/run_search.py
                                              ↓
                                     WebSearcher (Python 爬蟲)
                                     AV-WIKI / JAVDB / ShiroutoWiki
```

**結論**：Python 層的唯一生產用途是**爬蟲搜尋**，由 `run_search.py` 作為 subprocess 入口。

---

## 二、問題一：哪些 Python 檔案仍被 Wails 直接依賴？

### 2.1 Wails 的直接呼叫點

**`wails-app/backend/app.go`** 的 `PythonSearch()` 函式：
```go
// app.go:317-326
cmd := exec.CommandContext(ctx, pythonExe, scriptPath, code)
// scriptPath = src/scrapers/run_search.py
```

→ 唯一的 Python 入口是 `src/scrapers/run_search.py`。

### 2.2 run_search.py 的依賴鏈

```
src/scrapers/run_search.py
├── models.config.ConfigManager
└── services.web_searcher.WebSearcher
        ├── scrapers.sources.avwiki_scraper.AVWikiScraper
        │       ├── scrapers.encoding_utils (create_safe_soup, validate_japanese_content)
        │       ├── utils.retry_utils (AdaptiveConcurrencyController, ExponentialBackoff)
        │       └── utils.actress_name_filter.ActressNameFilter
        ├── scrapers.sources.shiroutowiki_scraper.ShiroutoWikiScraper
        ├── services.safe_javdb_searcher.SafeJAVDBSearcher
        │       ├── scrapers.sources.javdb_scraper.JAVDBScraper
        │       │       ├── scrapers.encoding_utils
        │       │       └── utils.actress_name_filter
        │       └── utils.json_utils
        ├── services.safe_searcher.SafeSearcher
        │       └── utils.json_utils
        ├── services.unified_cache.get_cache_manager
        ├── models.studio.StudioIdentifier
        │       └── utils.json_utils
        └── utils.progress_tracker.SearchProgressInfo (lazy import, batch_search 用)
```

**必須隨 Wails 保留的 Python 檔案清單**（共 18 個）：

| 檔案 | 說明 |
|------|------|
| `src/scrapers/run_search.py` | Wails subprocess 入口 |
| `src/services/web_searcher.py` | 核心搜尋引擎 |
| `src/services/safe_searcher.py` | HTTP 安全請求層 |
| `src/services/safe_javdb_searcher.py` | JAVDB 專用搜尋器 |
| `src/services/unified_cache.py` | web_searcher 快取整合 |
| `src/scrapers/sources/avwiki_scraper.py` | AV-WIKI 爬蟲 |
| `src/scrapers/sources/javdb_scraper.py` | JAVDB 爬蟲 |
| `src/scrapers/sources/shiroutowiki_scraper.py` | ShiroutoWiki 爬蟲 |
| `src/scrapers/sources/__init__.py` | 套件初始化 |
| `src/scrapers/base_scraper.py` | 爬蟲基礎類別 |
| `src/scrapers/rate_limiter.py` | 速率限制器 |
| `src/scrapers/cache_manager.py` | 磁碟 + 記憶體快取（依賴 go_cli） |
| `src/scrapers/encoding_utils.py` | 日文編碼偵測工具 |
| `src/models/config.py` | 設定管理器 |
| `src/models/studio.py` | 片商識別（薄層包裝 go_cli） |
| `src/utils/json_utils.py` | JSON 讀寫工具（多處使用） |
| `src/utils/actress_name_filter.py` | 女優名稱過濾（爬蟲使用） |
| `src/utils/retry_utils.py` | 重試與並發控制（avwiki_scraper 使用） |
| `src/utils/progress_tracker.py` | 搜尋進度型別（web_searcher batch_search 使用） |

---

## 三、問題二：go_cli.py 的使用狀況與可刪除性

### 3.1 使用清單

`src/services/go_cli.py` 被以下 7 個模組 import：

| 使用方 | 使用的函式 |
|--------|-----------|
| `src/models/extractor.py` | `extract_code` |
| `src/models/studio.py` | `identify_studio` |
| `src/models/json_database.py` | `db_get_video`, `db_update_video`, `db_delete_video`, `db_get_all_videos`, `db_compact_journal`, actress CRUD, backup 系列 |
| `src/models/incremental_json_database.py` | `db_get_video`, `db_update_video`, `db_delete_video`, `db_get_all_videos`, `db_compact_journal` |
| `src/scrapers/cache_manager.py` | `cache_get`, `cache_set`, `cache_delete`, `cache_get_stats`, `cache_prune`, `cache_clear` |
| `src/utils/file_mover.py` | `is_available`, `move_file`, `move_dir`, `batch_move`, `rollback`, `list_operations` |
| `src/utils/scanner.py` | `is_available`, `run`（呼叫 scan 指令） |

### 3.2 結論

**❌ go_cli.py 不可刪除**。它是整個專案 Python ↔ Go 橋接的唯一入口，取代了舊有的 `go_bridge.py` / `go_runner.py` / `go_api/`。刪除後 7 個模組立即失效。

---

## 四、問題三：src/ui/ 是否已完全移除？

**✅ 已完全移除。** `src/ui/` 目錄不存在。

Tkinter GUI 已被 Wails (React + Go) 取代，截至目前的程式碼中無任何 tkinter 相關 import。

---

## 五、問題四：go_bridge.py / go_runner.py / go_api/ 是否已完全移除？

**✅ 三者均已不存在。**

- `src/services/go_bridge.py` — 不存在  
- `src/services/go_runner.py` — 不存在  
- `src/services/go_api/` — 不存在  

均已被 `src/services/go_cli.py` 完整取代（485 行）。

---

## 六、問題五：目前各 Python 模組的角色

### 6.1 爬蟲層（核心，Wails subprocess 依賴）

| 模組 | 角色 |
|------|------|
| `src/scrapers/run_search.py` | Wails 唯一 Python 入口，subprocess CLI |
| `src/services/web_searcher.py` | 主搜尋引擎，串接 AV-WIKI / ShiroutoWiki / JAVDB |
| `src/services/safe_searcher.py` | 帶速率限制與重試的 HTTP 客戶端包裝 |
| `src/services/safe_javdb_searcher.py` | JAVDB 專用搜尋器 |
| `src/scrapers/sources/avwiki_scraper.py` | AV-WIKI 爬蟲 |
| `src/scrapers/sources/javdb_scraper.py` | JAVDB 爬蟲 |
| `src/scrapers/sources/shiroutowiki_scraper.py` | ShiroutoWiki 爬蟲 |
| `src/scrapers/base_scraper.py` | 爬蟲共用基礎類別（重試 / 健康檢查） |
| `src/scrapers/rate_limiter.py` | 域名級別速率限制 |
| `src/scrapers/cache_manager.py` | 搜尋結果快取（磁碟 + 記憶體，委派 go_cli） |

### 6.2 Go 橋接層

| 模組 | 角色 |
|------|------|
| `src/services/go_cli.py` | Python ↔ Go 唯一橋接，透過 subprocess 呼叫 classifier.exe |

### 6.3 Go 委派包裝器（薄層）

| 模組 | 角色 |
|------|------|
| `src/models/extractor.py` | 包裝 `go_cli.extract_code`（31 行） |
| `src/models/studio.py` | 包裝 `go_cli.identify_studio` + 本地規則載入（170 行） |
| `src/utils/file_mover.py` | 包裝 `go_cli` 移動操作（107 行） |
| `src/utils/scanner.py` | 包裝 `go_cli` 掃描操作（88 行） |

### 6.4 資料模型層（主要委派 Go）

| 模組 | 角色 |
|------|------|
| `src/models/config.py` | 設定管理，被 run_search 和多處使用（330 行） |
| `src/models/json_types.py` | 型別定義（299 行） |
| `src/models/json_database.py` | 資料庫操作大型類別，主要委派 Go（993 行） |
| `src/models/incremental_json_database.py` | 增量 journal 資料庫，主要委派 Go（388 行） |

### 6.5 工具層

| 模組 | 角色 |
|------|------|
| `src/utils/json_utils.py` | JSON 讀寫工具，被 config/studio/cache_manager/safe_searcher 使用 |
| `src/utils/actress_name_filter.py` | 女優名稱過濾，被 avwiki/javdb/safe_javdb 使用 |
| `src/utils/retry_utils.py` | 自適應並發控制，被 avwiki_scraper 使用 |
| `src/utils/progress_tracker.py` | 搜尋進度資訊型別，被 web_searcher batch_search 使用 |

### 6.6 快取整合層

| 模組 | 角色 |
|------|------|
| `src/services/unified_cache.py` | 整合多快取來源，被 web_searcher 使用 |
| `src/scrapers/encoding_utils.py` | 日文編碼偵測，被 avwiki/javdb/base_scraper/async_scraper 使用 |

### 6.7 歷史殘留（僅測試 / 工具依賴）

| 模組 | 角色 | 說明 |
|------|------|------|
| `src/services/classifier_core.py` | 分類核心（1498 行） | 僅被 `tests/` 和 `tools/integration/benchmark.py` 使用，Wails 路徑不依賴 |
| `src/services/interactive_classifier.py` | 互動分類器（255 行） | 僅被 classifier_core import |
| `src/services/studio_classifier.py` | 片商分類核心（853 行） | 僅被 classifier_core import |

### 6.8 疑似死碼（無生產依賴）

| 模組 | 說明 |
|------|------|
| `src/services/encoding_enhancer.py` | 沒有任何外部 import，只有 module-level 單例 |
| `src/services/japanese_site_enhancer.py` | 沒有任何外部 import，只有 `if __name__ == "__main__":` 示範 |
| `src/scrapers/enhanced/encoding_handler.py` | 僅被 `tests/test_code_review_regressions.py` 使用 |
| `src/scrapers/unified_scraper.py` | 無任何外部 import（scrapers/__init__.py 未 export，tests 中未直接使用） |
| `src/scrapers/async_scraper.py` | 僅被 `tests/test_code_review_regressions.py` 使用 |
| `src/utils/path_setup.py` | 僅在自身模組中引用自己（自循環），無外部使用 |

---

## 七、問題六：多餘的 Python 程式碼

### 7.1 可安全刪除的檔案

以下檔案在生產路徑（Wails subprocess → run_search.py）中**無任何直接或間接依賴**：

| 檔案 | 行數 | 刪除理由 |
|------|------|---------|
| `src/services/encoding_enhancer.py` | 169 | 無任何外部 import，完全孤立 |
| `src/services/japanese_site_enhancer.py` | 248 | 無任何外部 import，完全孤立 |
| `src/scrapers/enhanced/encoding_handler.py` | - | 僅測試依賴，不在生產路徑 |
| `src/scrapers/enhanced/` (整個目錄) | - | 唯一的 encoding_handler.py 已判定可刪 |
| `src/scrapers/unified_scraper.py` | 527 | 無外部 import，不在生產路徑 |
| `src/scrapers/async_scraper.py` | 461 | 僅測試依賴，不在生產路徑 |
| `src/utils/path_setup.py` | 77 | 自循環引用，無外部使用 |

> **注意**：若刪除 `async_scraper.py`，需同步更新 `src/scrapers/__init__.py`（目前有 `from .async_scraper import AsyncWebScraper` 的 export）。

### 7.2 歷史殘留（可刪除，但需同步清理測試）

以下檔案僅被 `tests/` 和 `tools/` 使用，不在 Wails 生產路徑：

| 檔案 | 行數 | 說明 |
|------|------|------|
| `src/services/classifier_core.py` | 1498 | 舊版 Python 分類核心，Wails 已不使用 |
| `src/services/interactive_classifier.py` | 255 | classifier_core 的子元件 |
| `src/services/studio_classifier.py` | 853 | classifier_core 的子元件 |

若刪除這三個檔案，需同步刪除或更新：
- `tests/test_code_review_regressions.py`（用到 classifier_core_module）
- `tools/integration/benchmark.py`（用到 UnifiedClassifierCore）

---

## 八、問題七：必要保留的 Python 程式碼

以下為**爬蟲路徑的核心鏈**，必須保留，不得刪除：

### 核心爬蟲鏈（必須保留）

```
src/scrapers/run_search.py           ← Wails subprocess 入口
src/services/web_searcher.py         ← 搜尋引擎核心
src/services/safe_searcher.py        ← HTTP 安全請求
src/services/safe_javdb_searcher.py  ← JAVDB 專用
src/services/unified_cache.py        ← 快取整合
src/scrapers/sources/avwiki_scraper.py
src/scrapers/sources/javdb_scraper.py
src/scrapers/sources/shiroutowiki_scraper.py
src/scrapers/sources/__init__.py
src/scrapers/base_scraper.py
src/scrapers/rate_limiter.py
src/scrapers/cache_manager.py
src/scrapers/encoding_utils.py
```

### 支援層（必須保留）

```
src/services/go_cli.py               ← Go 橋接唯一入口
src/models/config.py                 ← 設定
src/models/studio.py                 ← 片商識別
src/models/json_types.py             ← 型別定義
src/models/json_database.py          ← 資料庫（Wails DB 操作委派 Go）
src/models/incremental_json_database.py
src/utils/json_utils.py
src/utils/actress_name_filter.py
src/utils/retry_utils.py
src/utils/progress_tracker.py
```

### Go 委派包裝器（建議保留，但長期可合併進 go_cli.py）

```
src/models/extractor.py              ← 31 行薄層
src/utils/file_mover.py              ← 107 行薄層
src/utils/scanner.py                 ← 88 行薄層
```

---

## 九、可刪除檔案清單

### 立即可刪除（無任何生產依賴）

```
src/services/encoding_enhancer.py
src/services/japanese_site_enhancer.py
src/scrapers/enhanced/encoding_handler.py
src/scrapers/enhanced/__init__.py       (若目錄變空)
src/scrapers/unified_scraper.py
src/utils/path_setup.py
```

### 條件可刪除（需同步清理 tests/ 相關）

```
src/scrapers/async_scraper.py           (同步更新 src/scrapers/__init__.py)
src/services/classifier_core.py         (同步刪除 tests/test_code_review_regressions.py 相關測試)
src/services/interactive_classifier.py  (classifier_core 的子元件)
src/services/studio_classifier.py       (classifier_core 的子元件)
```

---

## 十、應保留的檔案清單

| 分類 | 保留檔案 |
|------|---------|
| **Wails 入口** | `src/scrapers/run_search.py` |
| **搜尋引擎** | `src/services/web_searcher.py`, `safe_searcher.py`, `safe_javdb_searcher.py`, `unified_cache.py` |
| **爬蟲** | `src/scrapers/sources/avwiki_scraper.py`, `javdb_scraper.py`, `shiroutowiki_scraper.py`, `sources/__init__.py`, `base_scraper.py`, `rate_limiter.py`, `cache_manager.py`, `encoding_utils.py`, `__init__.py` |
| **Go 橋接** | `src/services/go_cli.py` |
| **資料模型** | `src/models/config.py`, `json_database.py`, `incremental_json_database.py`, `json_types.py`, `studio.py`, `extractor.py`, `__init__.py` |
| **工具** | `src/utils/json_utils.py`, `actress_name_filter.py`, `retry_utils.py`, `progress_tracker.py`, `file_mover.py`, `scanner.py`, `__init__.py` |
| **套件初始化** | `src/__init__.py`, `src/services/__init__.py` |

---

## 十一、遷移狀態摘要

| 項目 | 狀態 |
|------|------|
| `src/ui/` (Tkinter GUI) | ✅ 已完全移除 |
| `go_bridge.py` | ✅ 已完全移除，由 `go_cli.py` 取代 |
| `go_runner.py` | ✅ 已完全移除 |
| `go_api/` | ✅ 已完全移除 |
| Python 爬蟲層 | ✅ 保留，Wails subprocess 依賴 |
| `go_cli.py` | ✅ 唯一橋接入口，結構清晰 |
| 死碼清理 | ⚠️ 尚有 ~1,500 行可刪除（classifier_core 三件組） |
| 孤立模組 | ⚠️ 6 個檔案無生產依賴，可安全刪除 |

---

*報告產生於 2026-04-07，基於 `wails-implementation` 分支最新狀態。*
