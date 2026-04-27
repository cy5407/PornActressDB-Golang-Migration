# 資料庫架構

> 來源：`pkg/database/types.go`、`src/models/json_types.py`、`src/models/incremental_json_database.py`、`src/models/json_database.py`、`src/scrapers/run_search.py`、`src/scrapers/run_batch_search.py`、`src/services/web_searcher.py`、`wails-app/backend/app.go`
> 更新：2026-04-22（依現行 Go / Python schema 與搜尋流程校正文檔）

---

## 概述

本專案使用自製的 JSON 資料庫，資料目錄位於 `data/json_db/`。

目前實作分成兩層：

- `JSONDBManager`：JSON DB 的主要管理介面
- `IncrementalJSONDB`：增量資料庫包裝層，但目前讀取、寫入與 compact 均委派給 Go CLI / Go DB 實作

因此，雖然資料庫仍保留 `data.json`、`data.journal`、`data.index` 三個檔案，實際狀態管理已由 Go 端維護，Python 端不再自行重播 journal。

---

## 檔案結構

```text
data/json_db/
├── data.json       # 主資料（完整狀態）
├── data.journal    # 增量變更日誌（JSON Lines）
├── data.index      # Dirty keys / journal 統計索引
└── backup/         # 備份目錄
```

---

## Journal / Compact 機制

目前 Go / Python 共同使用下列檔名與 compact 閾值：

| 項目 | 值 |
|------|----|
| `data.json` | 主資料檔 |
| `data.journal` | 增量日誌 |
| `data.index` | dirty index |
| Journal 記錄數閾值 | `1000` |
| Journal 年齡閾值 | `3600` 秒（1 小時） |

`IncrementalJSONDB` 目前的行為重點：

- 初始化時從 `data.index` 讀取 journal 統計
- 更新 / 新增 / 刪除影片時，委派 Go CLI 寫入
- `compact()` 時委派 Go CLI 執行 `db compact`
- compact 後會重載主資料並重設 dirty tracking

也就是說，這份文件應以目前的 Go / Python 共同 schema 與委派行為為準，而不是舊版純 Python journal 邏輯描述。

---

## 使用 API

### Python 端（IncrementalJSONDB）

```python
from models.incremental_json_database import IncrementalJSONDB

db = IncrementalJSONDB('data/json_db')

video = db.get_video_info('STARS-707')
db.update_video('STARS-707', {'title': '新標題'})
db.add_or_update_video('STARS-707', {'studio': 'S1'})
db.compact_if_needed()
db.compact()
```

### Python 端（JSONDBManager）

```python
from models.json_database import JSONDBManager

db = JSONDBManager('data/json_db')
db.get_video_info('STARS-707')
db.add_or_update_video('STARS-707', data)
db.delete_video('STARS-707')
db.get_all_videos()
```

### Go 端（直接使用）

```bash
classifier.exe db get STARS-707
classifier.exe db update STARS-707 video.json
classifier.exe db list --full
classifier.exe db stats
classifier.exe db compact
classifier.exe db clean-actresses
classifier.exe db clean-actresses -write
```

### DB 清洗工具：`clean-actresses`

目前 repo 內「最後做的 DB 清洗工具」是 Go 端的 `classifier.exe db clean-actresses`，不是 Python 一次性腳本。

它的資料流如下：

```text
load DB
  ↓
掃描全部 videos[].actresses
  ↓
依 `pkg/database/actress_cleaner.go` 規則產生清洗報告
  ↓
預設：dry-run，只輸出 JSON report
  ↓
若加 `-write`：先 BackupCreate() → UpdateVideo() → CompactJournal()
```

這個工具目前只處理高信心規則：
- 已知污染字串黑名單
- 已知合法女優名保留
- 片段名 `三田` 僅在 `三田真鈴` 同時存在時移除
- 重複拼接名稱（例如 `蒼乃美月蒼乃美月`）僅在基底名已存在時移除
- 去重複項目並保留順序

`-write` 的結果 JSON 會多出 `backup_path`，可搭配 `classifier.exe db backup-list` 與 `classifier.exe db backup-restore -backup-path <path>` 回復。

---

## 根層 Schema

主資料庫根層為：

```json
{
  "schema_version": "1.0.0",
  "metadata": {
    "description": "Python 女優分類系統 JSON 資料庫",
    "encoding": "UTF-8"
  },
  "data_hash": "",
  "created_at": "2026-04-22T00:00:00Z",
  "updated_at": "2026-04-22T00:00:00Z",
  "videos": {},
  "actresses": {},
  "links": [],
  "statistics": {
    "actress_statistics": [],
    "studio_statistics": [],
    "enhanced_actress_studio_statistics": [],
    "computed_at": "2026-04-22T00:00:00Z"
  }
}
```

根層欄位名稱以目前程式碼為準：`videos`、`actresses`、`links`、`statistics`。
舊欄位 `video_actress_links` 已不再接受。

---

## 影片資料 Schema（主要欄位）

目前影片資料欄位的正式持久化 schema 以 `pkg/database/types.go` 的 `VideoData` 為準；Python 端的 `src/models/json_types.py` 與相關 helper 反映的是目前常用資料形狀與預設值，但兩邊仍可能存在少量欄位落差（例如新近加入的錯誤欄位）。因此文件在欄位定義上應優先以 Go DB schema 為準，再補充 Python 端實際使用情況。

```json
{
  "code": "STARS-707",
  "title": "影片標題",
  "studio": "S1",
  "release_date": "2026-01-01",
  "url": "https://example.com/title/STARS-707",
  "actresses": ["女優名"],
  "search_status": "searched_found",
  "search_method": "AV-WIKI",
  "last_search_date": "2026-04-22T00:00:00Z",
  "avwiki_actress_status": "found",
  "avwiki_last_search_date": "2026-04-22T00:00:00Z",
  "javdb_actress_status": "not_found",
  "javdb_last_search_date": "2026-04-22T00:05:00Z",
  "created_at": "2026-04-21T23:50:00Z",
  "updated_at": "2026-04-22T00:05:00Z",
  "original_filename": "STARS-707.mp4",
  "file_path": "D:\\Videos\\STARS-707.mp4",
  "metadata": {
    "source": "",
    "confidence": 0.0
  },
  "error": "",
  "error_kind": ""
}
```

### 欄位說明

| 欄位 | 說明 |
|------|------|
| `code` | 影片番號；Go 端另保留舊相容欄位 `id`，但主要識別值仍是 `code` |
| `title` | 片名 |
| `studio` | 片商 |
| `release_date` | 發行日期 |
| `url` | 搜尋結果頁 / 詳情頁 URL |
| `actresses` | 女優名稱清單 |
| `search_status` | 整體搜尋狀態 |
| `search_method` | 本次資料的搜尋來源 / 方法字串 |
| `last_search_date` | 整體搜尋狀態最後更新時間 |
| `avwiki_actress_status` | AV-WIKI 單一來源的女優搜尋狀態 |
| `avwiki_last_search_date` | AV-WIKI 單一來源最後搜尋時間 |
| `javdb_actress_status` | JAVDB 單一來源的女優搜尋狀態 |
| `javdb_last_search_date` | JAVDB 單一來源最後搜尋時間 |
| `created_at` / `updated_at` | 建立 / 更新時間 |
| `original_filename` | 原始檔名 |
| `file_path` | 原始完整路徑 |
| `metadata` | 額外資訊，目前包含 `source`、`confidence` |
| `error` | 持久化的錯誤訊息 |
| `error_kind` | 持久化的錯誤分類字串 |

---

## `search_status` 目前使用值

目前 app / Python 流程實際使用的整體搜尋狀態如下：

| 值 | 說明 |
|----|------|
| `imported` | 僅導入，尚未完成搜尋 |
| `searched_found` | 已搜尋且找到資料 |
| `searched_not_found` | 已搜尋但找不到資料 |
| `search_error` | 搜尋流程失敗或來源異常 |

補充：

- `src/models/json_types.py` 將上述四個值定義為目前 Python schema 常數。
- Wails backend 在寫回 DB 時也使用 `searched_found`、`searched_not_found`、`search_error`。
- `pkg/database/types.go` 內仍可見舊常數 `success / partial / failed`，但這不是目前影片資料 `search_status` 的主流程值，文件不應以那些舊值作為現況說明。

---

## 單一來源欄位：`avwiki_*` / `javdb_*`

`run_search.py` 與 Wails backend 的 split-source / batch 流程，會分別更新單一來源欄位：

| 欄位 | 來源 |
|------|------|
| `avwiki_actress_status` / `avwiki_last_search_date` | AV-WIKI-only 搜尋 |
| `javdb_actress_status` / `javdb_last_search_date` | JAVDB-only 搜尋 |

目前這些單一來源狀態的實際值來自搜尋流程判斷，至少包含：

| 值 | 說明 |
|----|------|
| `found` | 該來源有找到女優資料 |
| `not_found` | 該來源有查詢，但沒有找到女優資料 |
| `error` | 該來源查詢時發生錯誤 |

其中：

- `run_search.py` 會依 `raw.search_status == "search_error"` 決定單一來源狀態為 `error`
- 若回傳有 `actresses`，則單一來源狀態為 `found`
- 否則為 `not_found`

這些欄位是「來源別搜尋紀錄」，和整體 `search_status` 不完全相同。
例如某次只跑 JAVDB-only 搜尋時，可能只更新 `javdb_*` 欄位，而不一定立即代表整體搜尋流程完成。

---

## `search_method`

`search_method` 是持久化在影片資料中的字串欄位，用來記錄目前資料是透過哪種方法或來源得到。

目前程式內可確認的常見值包括：

| 值 | 說明 |
|----|------|
| `legacy-import` | 舊資料匯入預設值 |
| `AV-WIKI` | 由 AV-WIKI 搜尋取得 |
| `JAVDB` | 由 JAVDB 搜尋取得 |
| `cascade` | 級聯搜尋流程 |

實務上此欄位是字串欄位，Go DB 會直接持久化寫入值；因此舊資料、測試資料或特殊流程也可能出現其他字串。文件應以前述值視為目前 canonical / 常見值，而不是宣稱唯一固定枚舉。

---

## `error` / `error_kind`

### 持久化欄位

Go 端 `VideoData` 目前正式包含：

- `error`
- `error_kind`

這兩個欄位屬於持久化 schema，可寫入 JSON DB。

### 目前流程中的實際語意

| 欄位 | 說明 |
|------|------|
| `error` | 搜尋失敗時的具體錯誤訊息 |
| `error_kind` | 搜尋失敗時的分類字串；目前是可擴充字串，不應視為硬編碼唯一全集 |

目前從程式碼可直接確認：

- `run_batch_search.py` 失敗結果至少會輸出
  - `error_kind = "not_found"`
  - `error_kind = "error"`
- `wails-app/backend/app.go` 的單次 Python 搜尋包裝，還會把程序層失敗分類為
  - `timeout`
  - `stderr`
  - `json_parse`

因此，`error_kind` 較準確的描述是：

- 目前至少已有 `not_found`、`error`
- 也可能出現 `timeout`、`stderr`、`json_parse` 等較底層整合分類
- 未來仍可擴充，文件不應把它寫成封閉且唯一的固定枚舉

### 與 `search_status` 的關係

- `search_status = "search_error"` 時，`error` / `error_kind` 最有意義
- 成功結果通常應為空字串
- `not_found` 與 `search_error` 是不同概念：找不到資料屬於搜尋結果，流程出錯才是 `search_error`

---

## `search_error_reason` 的定位

`search_error_reason` 目前可在 Python 搜尋流程中看到，例如：

- `src/services/web_searcher.py`
- `src/scrapers/run_search.py`
- `src/scrapers/run_batch_search.py`

但它是 Python 搜尋管線的暫時性中介欄位，用來描述來源異常原因；目前不是 `pkg/database/types.go` 定義的正式 Go DB 持久化欄位。

換句話說：

- Python 搜尋流程可能會產生 `search_error_reason`
- 寫入 Go DB 時，應以 `error` / `error_kind` 作為持久化錯誤欄位
- 不應把 `search_error_reason` 視為目前 DB schema 的正式欄位

---

## 維護注意事項

- 文件請以 `pkg/database/types.go` 與 `src/models/json_types.py` 的現行 schema 為主
- `src/models/json_database.py` / `src/models/incremental_json_database.py` 反映目前委派與正規化行為
- 搜尋狀態與錯誤欄位語意，請以 `run_search.py`、`run_batch_search.py`、`web_searcher.py`、`wails-app/backend/app.go` 的現行流程為主
- 不要再把已刪除的根層 `MIGRATION_STATUS.md` 當作這份頁面的主要事實來源

---

## 相關頁面

- [wiki/architecture/go-bridge.md](go-bridge.md)
- [wiki/architecture/go-cli.md](go-cli.md)
- [wiki/architecture/sqlite-shadow-db.md](sqlite-shadow-db.md)
