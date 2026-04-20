# 資料庫架構

> 來源：`src/models/incremental_json_database.py`、`MIGRATION_STATUS.md`  
> 更新：2026-04-21（drift audit：新增 W8 error_kind 欄位文件）

---

## 概述

本專案使用自製的 **增量 JSON 資料庫**，無需安裝資料庫軟體。

| 特性 | 說明 |
|------|------|
| 格式 | JSON（人類可讀） |
| 備份 | 複製單一 `data.json` 即可 |
| 並行 | 重試（retry）機制，filelock 已於 p13 移除 |
| 效能 | Journal 機制提升寫入速度 40x |
| Go 加速 | 查詢/更新委派給 Go CLI（78,000x 讀取加速） |

---

## 檔案結構

```
data/json_db/
├── data.json       # 主資料（完整狀態）
├── data.journal    # 增量變更日誌（JSON Lines）
└── data.index      # Dirty keys 索引（快速查找）
```

---

## Journal 機制

```
寫入時：
  append data.journal  ← 快（append-only）
  update data.index

讀取時：
  if key in dirty_index → 從 journal 讀最新值
  else → 從 data.json 讀

合併時（compact）：
  journal → data.json 全量合併
  清空 journal + index
```

### 操作類型

| 類型 | 說明 |
|------|------|
| `ADD` | 新增記錄 |
| `UPDATE` | 更新記錄 |
| `DELETE` | 刪除記錄 |

### 自動合併閾值

| 條件 | 閾值 |
|------|------|
| Journal 記錄數 | 超過 **1000 條** |
| Journal 年齡 | 超過 **1 小時** |

---

## 使用 API

### Python 端（IncrementalJSONDB）

```python
from models.incremental_json_database import IncrementalJSONDB

db = IncrementalJSONDB('data/json_db')

# 快速寫入（透過 journal）
db.update_video('STARS-707', {'title': '新標題', 'actresses': ['女優名']})

# 讀取（自動從 journal 或主檔案）
video = db.get_video('STARS-707')

# 手動合併
db.compact()

# 自動判斷是否需要合併
db.compact_if_needed()
```

### Python 端（JSONDBManager）

```python
from models.json_database import JSONDBManager

db = JSONDBManager('data/json_db')

# 以下方法在 Go 可用時委派給 Go CLI
db.get_video_info('STARS-707')         # → Go: db get STARS-707
db.add_or_update_video('STARS-707', data)  # → Go: db update STARS-707
db.delete_video('STARS-707')           # → Go: db delete STARS-707
db.get_all_videos()                    # → Go: db list --full
```

### Go 端（直接使用）

```bash
classifier.exe db get STARS-707
classifier.exe db update STARS-707 video.json
classifier.exe db list --full
classifier.exe db stats
classifier.exe db merge -source dist\data\json_db\data.json
classifier.exe db fix-studios -studios studios.json
```

---

## 影片資料 Schema（主要欄位）

```json
{
  "code": "STARS-707",
  "original_filename": "STARS-707.mp4",
  "file_path": "D:\\Videos\\STARS-707.mp4",
  "actresses": ["女優名"],
  "studio": "S1",
  "title": "影片標題",
  "search_status": "searched_found",
  "search_method": "AV-WIKI",
  "last_search_date": "2026-01-01T00:00:00",
  "error": "Optional error message if search failed",
  "error_kind": "timeout"
}
```

### search_status 枚舉

| 值 | 說明 |
|----|------|
| `imported` | 已導入，尚未搜尋 |
| `searched_found` | 搜尋成功 |
| `searched_not_found` | 搜尋過，確實找不到 |
| `search_error` | 搜尋失敗（網路等問題） |

### search_method 枚舉

| 值 | 說明 |
|----|------|
| `AV-WIKI` | 從 AV-WIKI 找到 |
| `JAVDB` | 從 JAVDB 找到 |
| `JAVDB (二次搜尋)` | 零女優二次搜尋成功 |
| `cascade` | 級聯搜尋 |
| `legacy-import` | 舊版匯入 |

### error_kind 枚舉（搜尋失敗原因分類，W8 新增）

| 值 | 說明 |
|----|------|
| `` (空) | 無錯誤 |
| `timeout` | 搜尋超時（Python subprocess 執行逾時） |
| `stderr` | Python 標準錯誤輸出（爬蟲異常） |
| `json_parse` | JSON 解析失敗（爬蟲輸出格式錯誤） |

> **注意**：`error` 欄位存放具體錯誤訊息，`error_kind` 用於分類。兩者僅在 `search_status == "search_error"` 時填入。

---

## 使用建議

✅ **適合 IncrementalJSONDB**：
- 頻繁的小規模更新（新增/修改單一影片）

❌ **不適合 IncrementalJSONDB**（改用 JSONDBManager）：
- 大規模批次更新（數百筆以上）

---

## schema 維護工具

```bash
# 驗證 schema
python tools\verify\verify_json_db_schema.py data\json_db\data.json

# 預覽正規化（不改檔）
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --dry-run

# 套用正規化（自動備份）
python tools\diagnostics\normalize_json_db_schema.py data\json_db\data.json --write
```

---

## 相關頁面

- [wiki/architecture/go-bridge.md](go-bridge.md)
- [wiki/architecture/go-cli.md](go-cli.md)
