# 跨層介面契約審查清單 — 完整版（2026-04-20）

## 概述

本文檔列出所有跨層介面點、資料格式、函式簽名，用於指導 TDD 契約測試的編寫。基於代碼掃描 + 人工確認。

---

## 第一層：Python → Go JSON 介面

### 1.1 Python 輸出的 JSON 格式

#### 來源 1: `run_batch_search.py` 的 `_normalize()` 函式

位置：`src/scrapers/run_batch_search.py:82-96`

```python
return {
    "code": raw.get("code") or code,
    "title": raw.get("title") or "",
    "studio": raw.get("studio") or "",
    "release_date": raw.get("release_date") or raw.get("releaseDate") or "",
    "url": raw.get("url") or "",
    "actresses": actresses,
    "method": raw.get("search_method") or raw.get("method") or "",  # ← 輸出欄位名稱
    "error": "",
    "error_kind": raw.get("error_kind") or "",
}
```

#### 來源 2: `run_batch_search.py` 的 `_build_error_result()` 函式

位置：`src/scrapers/run_batch_search.py:99-110`

```python
return {
    "code": code,
    "title": "",
    "studio": "",
    "release_date": "",
    "url": "",
    "actresses": [],
    "method": "",  # ← 輸出欄位名稱
    "error": message,
    "error_kind": error_kind,
}
```

#### 來源 3: `web_searcher.py` 的 `_build_search_error_result()` 函式

位置：`src/services/web_searcher.py:286-293`

```python
return {
    "source": source,
    "actresses": [],
    "search_status": "search_error",
    "search_error_reason": reason,
    "last_search_date": datetime.now(UTC).isoformat(),
}
```

**注意**：此函式返回不同的結構（無 code、title、studio 等）。

---

### 1.2 Go JSON Handler Map

位置：`pkg/database/journal.go:170-279`（applyVideoJournalUpdate 的 handler map）

| Python 欄位 | Go Handler Key | Go 目標欄位 | 狀態 |
|-----------|---|---|---|
| `code` | `"code"` | `video.Code` | ✅ |
| `title` | `"title"` | `video.Title` | ✅ |
| `studio` | `"studio"` | `video.Studio` | ✅ |
| `studio_code` | `"studio_code"` | `video.StudioCode` | ✅ |
| `release_date` | `"release_date"` | `video.ReleaseDate` | ✅ |
| `url` | `"url"` | `video.URL` | ✅ |
| `actresses` | `"actresses"` | `video.Actresses` | ✅ |
| **`method`** | **`"search_method"`** | **`video.SearchMethod`** | ❌ **欄位名不一致** |
| `error` | （無） | — | ❌ **Go 無對應 handler** |
| `error_kind` | （無） | — | ❌ **Go 無對應 handler** |
| （新增）`search_status` | `"search_status"` | `video.SearchStatus` | ✅ |
| （新增）`last_search_date` | `"last_search_date"` | `video.LastSearchDate` | ✅ |

### 1.3 已知 Bug 清單

#### Bug 1: Python 輸出 `"method"` vs Go 期望 `"search_method"`

- **位置**：
  - Python: `src/scrapers/run_batch_search.py:93` 輸出 `"method"`
  - Go: `pkg/database/journal.go:274` 只有 `"search_method"` handler
  
- **影響**：
  - Python 傳給 Go 的 `"method"` 欄位被 journal handler 無視
  - DB 裡 `search_method` 永遠空白
  - 分類時無法取得搜尋來源資訊

- **修復方案**：
  - 選項 A：Python 改輸出 `"search_method"` 而非 `"method"`
  - 選項 B：Go 加入 `"method"` handler 並對應到 `SearchMethod`
  - **建議**：選項 A（統一用 `search_method`）

#### Bug 2: Python 輸出 `"error"` 和 `"error_kind"` vs Go 無對應 handler

- **位置**：
  - Python: `src/scrapers/run_batch_search.py:108-109` 輸出 error 資訊
  - Go: `pkg/database/journal.go` 沒有對應的 handler
  
- **影響**：
  - 搜尋錯誤資訊無法進入 DB
  - 前端無法顯示搜尋失敗原因

- **修復方案**：
  - Go 在 journal handler map 新增 `"error"` 和 `"error_kind"` handler
  - 對應到 `VideoData` 新欄位或現有欄位

---

## 第二層：Go CLI JSON 輸出 → Python 消費

### 2.1 Go BatchSearch 輸出格式

位置：`wails-app/backend/app.go:521-533`（SearchResult 型別）

```go
type SearchResult struct {
    Code      string   `json:"code"`
    Title     string   `json:"title"`
    Studio    string   `json:"studio"`
    Release   string   `json:"release_date"`
    URL       string   `json:"url"`
    Actresses []string `json:"actresses"`
    Method    string   `json:"method"`
    Error     string   `json:"error,omitempty"`
    ErrorKind string   `json:"error_kind,omitempty"`
    Current   int      `json:"current,omitempty"`
    Total     int      `json:"total,omitempty"`
}
```

### 2.2 Go 至 DB 的 persist 邏輯

位置：`wails-app/backend/app.go:671-705`（persistBatchSearchResult）

**寫入欄位對應**：
```
res.Code           → updates["code"]
res.Title          → updates["title"]
res.Studio         → updates["studio"]
res.Release        → updates["release_date"]
res.URL            → updates["url"]
res.Actresses      → updates["actresses"]
res.Method         → updates["search_method"]  ← ✅ 正確轉換
res.Error          → (被忽略，僅在 error != "" 時跳過 persist)
res.ErrorKind      → (未在 persist 邏輯中使用)
```

---

## 第三層：函式簽名改動掃描

### 3.1 所有帶 `stop_event` 參數的函式

| 函式 | 檔案 | 簽名中的 stop_event |
|------|------|---|
| `_search_with_mode()` | `src/scrapers/run_search.py:99` | `stop_event: threading.Event` |
| `search_info()` | `src/services/web_searcher.py:173` | `stop_event: threading.Event` |
| `_search_av_wiki()` | `src/services/web_searcher.py:587` | `stop_event: threading.Event` |
| `_search_javdb()` | `src/services/web_searcher.py:663` | `stop_event: threading.Event` |
| `batch_search_avwiki_concurrent()` | `src/services/web_searcher.py:700` | `stop_event: threading.Event` |
| `batch_search_javdb_concurrent()` | `src/services/web_searcher.py:834` | `stop_event: threading.Event` |
| `batch_cascade_search()` | `src/services/web_searcher.py:1086` | `stop_event: threading.Event` |
| `_run_avwiki_batch_search()` | `src/services/web_searcher.py:639` | `stop_event: threading.Event` |

### 3.2 呼叫端檢查

| 呼叫端 | 被呼叫函式 | 傳入 stop_event? | 位置 |
|--------|---------|---|---|
| `run_batch_search.py:search_one()` | `_search_with_mode()` | ✅ 是 | line 117 |
| `run_search.py:main()` | `_search_with_mode()` | ✅ 是 | line 197 |
| `web_searcher.py:batch_cascade_search()` | `batch_search_avwiki_concurrent()` | ✅ 是 | line 856 |

**結論**：✅ 所有呼叫端都正確傳入 `stop_event`

---

## 第四層：前端 ↔ Wails Backend Binding

### 4.1 Wails 綁定的公開方法

位置：`wails-app/backend/app.go` 所有 `func (a *App) Xxx()` 的公開方法

**搜尋相關方法**：
| 方法 | 簽名 | 返回 |
|------|------|------|
| `BatchSearch` | `(codes []string, workers int)` | `[]SearchResult` |
| `BatchSearchAVWiki` | `(codes []string, workers int)` | `[]SearchResult` |
| `BatchSearchJAVDB` | `(codes []string, workers int)` | `[]SearchResult` |
| `PythonSearch` | `(code string)` | `(*SearchResult, error)` |

### 4.2 前端呼叫方式

位置：`wails-app/frontend/src/App.tsx`

**imports**：
```typescript
import { BatchSearch, BatchSearchAVWiki, BatchSearchJAVDB } from '../wailsjs/go/backend/App';
```

**呼叫點**：
- line 379: `const results = await BatchSearch(codes, 0);`
- line 466: `await handleSourceSearch('AV-WIKI', BatchSearchAVWiki);`
- line 470: `await handleSourceSearch('JAVDB', BatchSearchJAVDB);`

### 4.3 SearchResult 在前端的使用

位置：`wails-app/frontend/src/App.tsx:130, 444, 988`

**使用欄位**：
```typescript
searchFn: (codes: string[], workers: number) => Promise<backend.SearchResult[]>

// 使用欄位列表
addSearchResult({
    code: sr.code,
    title: sr.title,
    studio: sr.studio,
    release_date: sr.release_date,
    url: sr.url,
    actresses: sr.actresses,
    method: sr.method,  // ← 使用 "method"，Go 側會輸出 "method"
    error: sr.error,
})
```

**結論**：✅ 前端使用 `method`，Go 側 SearchResult 也定義 `Method` 欄位 → 一致

---

## 第五層：前端搜尋流程邏輯

### 5.1 最近修復的 Bug（已合併到 main）

位置：`wails-app/frontend/src/App.tsx`（commit 20602f2）

**Bug 修復**：
1. ✅ 移除 `runSourceSearch()` 內的 `clearSearchResults()` 呼叫（line 133）
2. ✅ `handleSearch()` 保留 `clearSearchResults()` 呼叫（line 369）
3. ✅ `handleSourceSearch()` 移除了快取項目補入邏輯（舊 line 441-458 已刪除）

**修復後的資料流**：
```
cascade          → store: [A,B,C,D]
AV-WIKI source   → store: [A,B,C,D,E,F]（保留前輪結果，加入新搜）
JAVDB source     → store: [A,B,C,D,E,F,G,H]（保留所有結果，加入新搜）
分類              → 全部正確分類（無項目落入未分類）
```

---

## 第六層：已知待修復項目總結

| 優先度 | 項目 | 檔案 | 問題 | 修復方案 |
|--------|------|------|------|---------|
| 🔴 高 | Python 輸出 `"method"` vs Go 期望 `"search_method"` | `run_batch_search.py:93` | JSON 欄位名不一致 | 改 Python 輸出 `"search_method"` |
| 🔴 高 | Go 無對應 handler for `error` 和 `error_kind` | `pkg/database/journal.go` | 搜尋錯誤無法進 DB | Go 新增 handler 或忽略 |
| 🟢 低 | 前端搜尋流程邏輯 | `wails-app/frontend/src/App.tsx` | 已於 20602f2 修復 | ✅ 完成 |
| 🟢 低 | 函式簽名 `stop_event` | `src/services/web_searcher.py` | 所有呼叫端已同步 | ✅ 一致 |

---

## 第七層：TDD 契約測試規劃

基於上述審查，應編寫以下測試：

### 必須測試的介面點

1. **Python → Go JSON 欄位一致性測試**
   - 驗證 `run_batch_search.py._normalize()` 輸出欄位
   - 驗證 `run_batch_search.py._build_error_result()` 輸出欄位
   - 驗證 Go journal handler 能否正確消費

2. **函式簽名驗證測試**
   - 掃描所有帶 `stop_event` 的函式簽名
   - 驗證所有呼叫端都傳入該參數

3. **Go ↔ Frontend SearchResult 一致性測試**
   - 驗證 Go `SearchResult` struct tags 與前端使用一致
   - 驗證 wailsjs binding 正確映射

4. **端到端整合煙測試**
   - `test-file/` 掃描 → batch search → 分類完整流程
   - 驗證搜尋結果正確進入 DB

---

## 文檔版本

- **版本**：1.0
- **建檔日期**：2026-04-20
- **最後更新**：2026-04-20
- **審查人**：Agent（自動掃描 + 人工確認）

