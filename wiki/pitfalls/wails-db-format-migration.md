# Wails DB 資料格式不一致與正規化

> 歸檔日期：2026-04-08

---

## 問題描述

`data.json` 同時存在兩套 `search_status` 與 `search_method` 值，來自不同時期的不同來源：

### search_status 不一致

| 值 | 筆數 | 來源 | 問題 |
|----|------|------|------|
| `searched_found` | 1284 | 舊 Python 搜尋 | ✅ Python 標準值 |
| `imported` | 1345 | Python 匯入 | ✅ 正常 |
| `success` | 63 | Go Wails 新搜尋 | ❌ 與 Python 標準不符 |
| `searched_multiple` | 6 | 舊 AV-WIKI 爬蟲 | ❌ Go/Python 常數都未定義 |
| `searched_not_found` | 202 | Python 搜尋 | ✅ 正常 |
| `search_error` | 3 | Python 搜尋失敗 | ✅ 正常 |

**根本原因**：
- Go `pkg/database/types.go` 定義 `SearchStatusSuccess = "success"`
- Python `json_types.py` 定義 `SEARCHED_FOUND = "searched_found"`
- Go backend 寫入時使用了 Go 常數，造成兩種值並存

### search_method 非標準值

| 值 | 筆數 | 問題 |
|----|------|------|
| `JAVDB (安全增強版)` | 47 | 舊版方法名，非標準 |
| `''`（空） | 63 | Go 新搜尋未寫入 method |
| `shiroutowiki` | 6 | 已移除爬蟲的歷史殘留 |
| `chiba-f.net` | 1 | 已移除爬蟲（CLAUDE.md 記錄的合法歷史值） |

---

## 修正方式

### 程式碼修正（`app.go`）

```go
// 修正前
SearchStatus: database.SearchStatusSuccess,  // "success"

// 修正後
SearchStatus: "searched_found",  // 統一為標準值
```

快取命中判斷也同步簡化：
```go
// 修正前
if video.SearchStatus == database.SearchStatusSuccess || video.SearchStatus == "searched_found"

// 修正後
if video.SearchStatus == "searched_found"
```

commit: `33ed079`（2026-04-08）

### 資料修正（一次性 Python 腳本）

```python
# success → searched_found（63 筆）
# searched_multiple → searched_found（6 筆，有效女優資料保留）
# search_method 空白 → cascade（63 筆，wails-app 使用 WebSearcher cascade 流程）
# JAVDB (安全增強版) → JAVDB（47 筆，正規化）
```

修正後分佈：

| search_status | 筆數 |
|--------------|------|
| `imported` | 1345 |
| `searched_found` | 1353 |
| `searched_not_found` | 202 |
| `search_error` | 3 |

| search_method | 筆數 |
|--------------|------|
| `legacy-import` | 1346 |
| `AV-WIKI` | 1261 |
| `cascade` | 155 |
| `JAVDB` | 134 |
| `shiroutowiki` | 6（歷史保留） |
| `chiba-f.net` | 1（歷史保留） |

---

## 資料合併背景

同場進行的還有**將 `dist/data/json_db/data.json`（2903 筆原始資料）合併進 `wails-app/build/bin/data/json_db/data.json`**：

- 合併前：63 筆（只有 wails-app 新搜尋資料）
- 合併後：2903 筆（63 筆重疊保留較新版本，新增 2840 筆）

合併使用 `db.MergeFromFile(src, overwrite=false)` + `db.Compact()`。

---

## 預防措施

往後 Go backend 寫入 `search_status` 時統一使用字串 `"searched_found"`，不使用 `database.SearchStatusSuccess` 常數（其值為 `"success"`，與資料庫實際標準不同）。

若未來決定改用 Go 標準值 `"success"`，需同步：
1. 更新 `app.go` 寫入值
2. 批次遷移現有 2903 筆資料
3. 確認 Python 爬蟲端也輸出相容值（或 Python 不再使用）

---

## 涉及檔案

- `wails-app/backend/app.go`：`BatchSearch()` 寫入 DB 的 `SearchStatus` 欄位
- `wails-app/build/bin/data/json_db/data.json`：資料實體（.gitignore，不入 git）
- `data/json_db/data.json`：根目錄版本（.gitignore，不入 git）
