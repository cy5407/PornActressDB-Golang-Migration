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

## 正確做法

1. **統一後端寫入時使用 `database.SearchStatusSuccess`**（值為 `"success"`）
2. **前端狀態判定改為看 `method` 或 `error` 欄位，而非 actresses 數量**
3. **無女優作品的 `search_status` 應設為 `"success_no_actress"` 或在 title 有值時也算成功**

暫行做法：前端把「有 title 或有 actresses」都算成功：
```typescript
function getStatus(r: SearchResult): 'success' | 'failed' {
  return !r.error && (r.title || (r.actresses?.length ?? 0) > 0) ? 'success' : 'failed';
}
```

## 參考

- `wails-app/backend/app.go` — `BatchSearch()` 快取判定邏輯（約 L440-L458）
- `wails-app/frontend/src/components/SearchResultDialog.tsx` — `getStatus()`（L121-L123）
- `pkg/database/jsondb.go` — `SearchStatusSuccess` 常數定義
