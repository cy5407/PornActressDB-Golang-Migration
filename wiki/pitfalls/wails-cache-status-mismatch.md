---
category: Wails
date: 2026-04-08
---
# Wails 快取狀態判定：Go 後端與前端標準不一致

## 症狀

後端已把一筆資料存入 DB（`search_status = "success"`），下次搜尋也確認為快取命中，但前端顯示該筆為 ❌ 失敗（女優欄位空白）。

## 根因

快取命中的判定標準在後端與前端不同：

### Go 後端（app.go）
```go
// 只看 search_status，不管 actresses 有沒有資料
if video.SearchStatus == database.SearchStatusSuccess || 
   video.SearchStatus == "searched_found" {
    // 視為快取命中
}
```

### React 前端（SearchResultDialog.tsx）
```typescript
// 同時要求：沒有 error 且 actresses.length > 0
function getStatus(r: SearchResult): 'success' | 'failed' {
  return !r.error && r.actresses?.length > 0 ? 'success' : 'failed';
}
```

如果影片沒有女優資訊（例如無女優的作品），後端仍將其標記為 `success` 並快取，前端卻顯示為失敗，造成混淆。

此外，`database.SearchStatusSuccess = "success"` 與 Python 版 `"searched_found"` 的雙值問題，雖然後端已同時處理，但新增資料時若未正確設定，可能只存入其中一種值。

## 實際修正做法（2026-04-08）

**後端統一寫入 `"searched_found"`**（與資料庫現有 2840+ 筆標準一致）：

```go
// wails-app/backend/app.go — BatchSearch() 寫入 DB
SearchStatus: "searched_found",  // 不使用 database.SearchStatusSuccess（值為 "success"）
```

快取命中判斷也同步簡化為單一條件：
```go
// 修正後（移除多餘的 SearchStatusSuccess 判斷）
if err == nil && video.SearchStatus == "searched_found" {
```

**前端狀態判定** 則在 T1（2026-04-07）已修正，把「有 title 或有 actresses」都算成功：
```typescript
function getStatus(r: SearchResult): 'success' | 'failed' {
  return !r.error && (r.title || (r.actresses?.length ?? 0) > 0) ? 'success' : 'failed';
}
```

> **注意**：`database.SearchStatusSuccess = "success"` 這個 Go 常數與資料庫實際使用的 `"searched_found"` 不同。
> 詳見 [wails-db-format-migration.md](wails-db-format-migration.md)。

commit: `33ed079`（2026-04-08）

## 參考

- `wails-app/backend/app.go` — `BatchSearch()` 快取判定與寫入邏輯
- `wails-app/frontend/src/components/SearchResultDialog.tsx` — `getStatus()`
- `pkg/database/types.go` — `SearchStatusSuccess` 常數定義
- [wails-db-format-migration.md](wails-db-format-migration.md) — 完整格式正規化紀錄
