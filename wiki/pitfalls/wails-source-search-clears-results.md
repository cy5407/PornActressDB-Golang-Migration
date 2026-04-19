---
category: Wails
date: 2026-04-19
---
# 來源搜尋（AV-WIKI / JAVDB）導致部分番號落入 未分類

## 症狀

連續執行任意搜尋組合（cascade → AV-WIKI → JAVDB，或只用 AV-WIKI + JAVDB）後點分類移動，部分番號全部被移到 `未分類` 資料夾，即便 data.json 裡已有正確的女優資料。

## 根本原因（兩個獨立 Bug）

### Bug 1：`runSourceSearch` 清空前輪結果

```typescript
// App.tsx — 修復前（錯誤）
async function runSourceSearch(...) {
  setStatus('searching');
  clearSearchResults();  // ← 每次 source search 都清空前輪結果
  resetProgress();
}
```

分類邏輯從記憶體內的 `searchResults` store 建立對應表。`clearSearchResults()` 每輪都呼叫，導致只有最後一輪結果留存：

```
cascade → store:[A,B]
AV-WIKI → clearResults → store:[] → store:[C,D]
JAVDB   → clearResults → store:[] → store:[E,F]
分類    → 只有 E,F 正確，A,B,C,D → 未分類
```

### Bug 2：已快取番號被 filter 掉後從未進 `searchResults`

`handleSourceSearch` 在執行前先過濾出「任一來源已找到女優」的番號並跳過：

```typescript
// 跳過已有快取的番號
const codes = videoStates
  .filter(({ video }) =>
    !isFoundSearchStatus(video?.['avwiki_actress_status']) &&
    !isFoundSearchStatus(video?.['javdb_actress_status'])
  )
  .map(({ code }) => code);

// 被跳過的番號 → 從未呼叫 addSearchResult → 不在 store 裡
await runSourceSearch(source, codes, searchFn);
```

結果：即使只使用 AV-WIKI 或 JAVDB 搜尋，第一次搜到的番號在第二次開啟程式時就會被 filter 掉，永遠進不了 `searchResults`，分類時落入 `未分類`。

```
第一次開程式：AV-WIKI 找到 A（avwiki_actress_status=found）→ 分類正確
第二次開程式：AV-WIKI 啟動 → filter 掉 A（已有 avwiki status）→ A 不在 store
            → 分類時 A → 未分類
```

## 修正

### Bug 1：移除 `runSourceSearch` 內的 `clearSearchResults()`

```typescript
// App.tsx — 修復後
async function runSourceSearch(...) {
  setStatus('searching');
  // clearSearchResults() ← 移除
  resetProgress();
}
```

`handleSearch`（cascade）保留清空：

```typescript
async function handleSearch() {
  clearSearchResults();  // ← 保留：重新搜尋時應從乾淨狀態開始
  ...
}
```

### Bug 2：被跳過的快取番號補進 `searchResults`

```typescript
// handleSourceSearch — 修復後
const alreadyCached = videoStates.filter(({ video }) =>
  isFoundSearchStatus(video?.['avwiki_actress_status']) ||
  isFoundSearchStatus(video?.['javdb_actress_status'])
);

// 已快取項目補進 searchResults，讓後續分類不遺漏
const existingCodes = new Set(searchResults.map((sr) => sr.code));
for (const { code, video } of alreadyCached) {
  if (video && !existingCodes.has(code)) {
    addSearchResult({
      code,
      title: video.title ?? '',
      studio: video.studio ?? '',
      release_date: video.release_date ?? '',
      url: video.url ?? '',
      actresses: video.actresses ?? [],
      method: video.search_method ?? '',
      error: '',
    });
    existingCodes.add(code);
  }
}
```

使用 `existingCodes` Set 去重，避免多次呼叫 source search 時重複加入同一筆。

## 修復後的資料流

```
任意搜尋組合完成後 searchResults 狀態：

cascade → store:[A,B]
AV-WIKI → 快取 A,B 補入 store（去重） + 新搜 C,D → store:[A,B,C,D]
JAVDB   → 快取 A,B,C,D 補入 store（去重）+ 新搜 E,F → store:[A,B,C,D,E,F]
分類    → 全部正確分類
```

## 涉及檔案

- `wails-app/frontend/src/App.tsx`
  - `runSourceSearch()`：移除 `clearSearchResults()`
  - `handleSourceSearch()`：補入已快取番號到 `searchResults`
- `wails-app/frontend/src/stores/taskStore.ts` — `searchResults` store、`addSearchResult`
