# Chrome file:// CORS 封鎖 wiki fetch

## 問題描述

直接雙擊 `wiki/viewer.html` 開啟時，所有 `fetch()` 呼叫失敗：

```
❌ 無法載入 architecture/go-bridge.md：Failed to fetch
```

## 根本原因

Chrome 在 `file://` 協議下封鎖所有 `XMLHttpRequest` / `fetch` 呼叫（包含相對路徑），屬於 CORS 安全限制。Firefox 允許，但不能依賴非主流瀏覽器。

## 解決方案

**嵌入式 JS 資料（wiki-data.js）**

1. 執行 `python wiki/gen_data.py` 產生 `wiki/wiki-data.js`  
2. `viewer.html` 透過 `<script src="wiki-data.js">` 載入  
3. `loadPage()` 優先讀 `window.WIKI_DATA[item.file]`，再 fallback 到 `fetch`

這樣 `file://` 和 `http://` 兩種模式都能正常運作。

## 維護流程

每次新增或修改 `.md` 檔後，必須重新產生：

```powershell
python wiki/gen_data.py
```

`wiki-maintenance` Skill Step 6 已包含此步驟。

## 不推薦的替代方案

| 方案 | 問題 |
|------|------|
| 強制用 serve.py | 需要啟動 server，使用不便 |
| Firefox | 依賴特定瀏覽器，無法保證 |
| `--allow-file-access-from-files` Chrome 旗標 | 需要特殊啟動，有安全風險 |
| `<script src="*.md">` | 非標準，不可行 |
