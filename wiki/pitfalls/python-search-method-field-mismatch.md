---
category: Python-Go 介面
date: 2026-04-20
fixed_in: b496dd5
---
# Python 輸出 `"method"` 而 Go 期望 `"search_method"` 導致欄位遺失

## 症狀

搜尋完成後，`data.json` 中的 `search_method` 欄位為空字串（`""`），即使搜尋實際成功、來源為 AV-WIKI 或 JAVDB。

## 根因

`run_batch_search.py` 的 `_normalize()` 函式輸出的 JSON 欄位名為 `"method"`：

```python
# 修復前（錯誤）
return {
    ...
    "method": raw.get("search_method") or raw.get("method") or "",
    ...
}
```

但 Go `journal.go` 的 handler map 只處理 `"search_method"` key：

```go
// pkg/database/journal.go
"search_method": func(v interface{}) {
    video.SearchMethod = toString(v)
},
```

兩者 key 不一致，導致 Python 輸出的 `"method"` 被 Go 忽略，`SearchMethod` 永遠不被更新。

`run_search.py` 存在同樣問題。

## 正確做法

Python 搜尋結果 JSON 必須使用 `"search_method"` 作為欄位名（與 Go handler key 完全一致）：

```python
# 修復後（正確）
return {
    ...
    "search_method": raw.get("search_method") or raw.get("method") or "",
    ...
}
```

## 修復

- **commit**：`b496dd5` `fix(interface-audit-bug-1): Python 輸出改用 'search_method' 代替 'method'`
- **涉及檔案**：
  - `src/scrapers/run_batch_search.py`：`_normalize()` 與 `_build_error_result()` 改輸出 `search_method`
  - `src/scrapers/run_search.py`：result dict 改輸出 `search_method`（注意：`_error()` 函式的錯誤路徑目前仍輸出 `"method": ""`，為已知殘留問題）
  - 測試同步更新驗證新欄位名

## 預防

在新增或修改 Python 搜尋輸出欄位時，必須與 `pkg/database/journal.go` 的 handler map 核對欄位名一致。

參考：[INTERFACE_AUDIT.md](../../INTERFACE_AUDIT.md)、[wiki/architecture/database.md](../architecture/database.md)
