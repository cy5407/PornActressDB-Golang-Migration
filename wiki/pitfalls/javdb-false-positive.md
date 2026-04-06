# Issue 12：JAVDB False Positive

**日期**：2026-04-06
**症狀**：搜尋 `WTB-045` 卻寫入 `AWTB-005` 的資料
**根因**：`search_javdb()` 無精確匹配時 fallback 取第一筆結果

## 修正

1. 移除 fallback：無精確匹配直接 `return None`
2. `_parse_detail_page()` 新增番號二次驗證（從頁面標題提取番號比對）

**檔案**：`src/services/safe_javdb_searcher.py`
