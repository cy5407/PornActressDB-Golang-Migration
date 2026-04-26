# 零女優補搜與來源限定重跑模式

> 更新：2026-04-27
> 舊 `classifier_core.py::process_and_search_javdb()` 二次搜尋流程已隨 Python GUI 清理移除。現行做法是透過 Wails 的來源限定搜尋 API 進行 AV-WIKI-only / JAVDB-only 補搜。

---

## 問題背景

有些番號會出現「整體資料已存在，但女優欄位仍為空」的狀態。常見原因包括：

- AV-WIKI 找到片名 / 片商但沒有結構化女優連結
- JAVDB 查無精確匹配
- 舊資料匯入或早期搜尋流程留下零女優資料
- 來源暫時錯誤或快取資料不完整

現行系統不再使用舊 Tkinter GUI 的「清快取後第二輪 JAVDB 搜尋」流程；補搜改由來源限定搜尋欄位追蹤。

---

## 現行流程

```text
Wails UI
  ↓
AV-WIKI-only / JAVDB-only 按鈕
  ↓
BatchSearchAVWiki(codes, workers) / BatchSearchJAVDB(codes, workers)
  ↓
run_batch_search.py + source_mode
  ↓
WebSearcher.search_avwiki_only() / search_javdb_only()
  ↓
更新 avwiki_* / javdb_* 欄位與必要的整體欄位
```

來源限定搜尋的定位：

- 針對特定來源補搜或重跑
- 不再依賴舊 `classifier_core.py`
- 不再用 `JAVDB (二次搜尋)` 當主要標記
- 透過 `avwiki_actress_status` / `javdb_actress_status` 追蹤來源結果

---

## 程式碼位置

| 功能 | 位置 |
|------|------|
| Wails 來源限定 binding | `wails-app/backend/app.go::BatchSearchAVWiki()` / `BatchSearchJAVDB()` |
| 批次搜尋主體 | `wails-app/backend/app.go::batchSearch()` |
| 前端來源按鈕流程 | `wails-app/frontend/src/App.tsx::handleSourceSearch()` |
| Python source mode dispatch | `src/scrapers/run_search.py::_search_with_mode()` |
| 批次 subprocess | `src/scrapers/run_batch_search.py` |
| JAVDB 快取輔助 | `src/services/safe_javdb_searcher.py::clear_cache_for_code()`（目前是輔助函式，不是 Wails 主流程入口） |

---

## 判定標準

現行補搜不只看整體 `search_status`，也看來源專屬欄位：

```text
avwiki_actress_status / javdb_actress_status
  found      → 該來源已有女優資料
  not_found  → 該來源查詢過但沒有女優資料
  error      → 該來源查詢失敗
```

前端來源補搜目前會先讀 DB：

- 若任一來源已是 found，會把快取資料補進 `searchResults`，避免後續分類漏資料。
- 若兩個來源都不是 found，才送去指定來源搜尋。

---

## 寫入規則

來源限定搜尋成功時，backend 會更新：

```json
{
  "search_status": "searched_found",
  "search_method": "AV-WIKI 或 JAVDB",
  "last_search_date": "UTC timestamp",
  "avwiki_actress_status 或 javdb_actress_status": "found"
}
```

未找到或錯誤時，至少會更新來源欄位：

```json
{
  "avwiki_actress_status 或 javdb_actress_status": "not_found 或 error",
  "avwiki_last_search_date 或 javdb_last_search_date": "UTC timestamp"
}
```

這讓後續補搜可以知道「哪個來源曾經查過」而不是只依賴整體 `search_status`。

---

## 維護注意事項

- 不要重新引入 `src/services/classifier_core.py` 或 Tkinter GUI 的二次搜尋流程。
- 若要加入「清除 JAVDB 快取後重跑」功能，應掛在 Wails source-specific search 流程上，並明確更新 `javdb_*` 欄位。
- `search_method = "JAVDB (二次搜尋)"` 屬於舊資料 / 舊流程標記，不應作為新流程 canonical 值。

---

## 相關頁面

- [搜尋引擎架構](../architecture/search-engine.md)
- [JAVDB False Positive](../pitfalls/javdb-false-positive.md)
- [來源搜尋清空結果致未分類](../pitfalls/wails-source-search-clears-results.md)
