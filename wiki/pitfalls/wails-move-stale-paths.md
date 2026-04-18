---
category: Wails
date: 2026-04-08
---
# Wails 移動後 scanResults 路徑未更新

## 症狀

點擊「移動」成功後，`scanResults` 裡每個 entry 的 `path` 欄位仍然指向原始位置。若使用者不重新掃描就再次按移動，Go 後端會嘗試從已不存在的舊路徑移動，導致 `stat: no such file or directory` 錯誤。

## 根因

`App.tsx` 的 `handleMove()` 呼叫 `BatchMove()` 成功後，只發出 toast 通知，沒有更新 React state 中的 `scanResults`：

```typescript
// App.tsx（修復前）
const handleMove = async () => {
  const moves = scanResults.map(r => ({ source: r.path, dest: `${outputDir}\\${r.code}${pathExt(r.path)}` }));
  const result = await BatchMove(moves, strategy);
  // ← 沒有更新 scanResults
};
```

移動完成後，`scanResults` 依然持有舊路徑，下次移動操作會重複使用這些過期路徑。

## 正確做法

移動成功後，清空 `scanResults`（或用新路徑更新）：

```typescript
// 移動成功後清空，強迫用戶重新掃描
setScanResults([]);
```

或者更新每個 entry 的 path：

```typescript
setScanResults(prev =>
  prev.map(r => {
    const moved = result.items?.find(i => i.source === r.path);
    return moved?.success ? { ...r, path: moved.destination } : r;
  })
);
```

## 參考

- `wails-app/frontend/src/App.tsx` — `handleMove()`
- `wails-app/backend/app.go` — `BatchMove()` 回傳結構
