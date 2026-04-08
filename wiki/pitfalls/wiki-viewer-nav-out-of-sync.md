---
category: 工具
date: 2026-04-08
---
# Wiki Viewer 導覽選單與 wiki-data.js 脫鉤

## 問題描述

新增 `wiki/pitfalls/*.md` 後，`viewer.html` 的左側導覽選單沒有出現新頁面。

```
# 症狀：viewer.html 顯示「找不到頁面」或選單根本沒有新條目
# 但 wiki-data.js 已包含對應內容（搜尋可以找到）
```

## 根本原因

`wiki/` 目錄有**兩套獨立系統**，各需單獨維護：

| 系統 | 產生方式 | 包含什麼 |
|------|---------|---------|
| `wiki-data.js` | `python wiki/gen_data.py` 自動產生 | 所有 `.md` 的**內容** |
| `viewer.html` nav | **手動**維護 JS 陣列（~行 118）| 左側選單**導覽項目** |

`gen_data.py` 掃描所有 `.md` 並寫入 `wiki-data.js`，但 **不會修改 `viewer.html`** 的 nav 陣列。  
兩者脫鉤：wiki-data.js 有內容，但選單沒有入口。

## 實際踩坑

2026-04-07 新增三個 Wails 踩坑頁面後，執行了 `gen_data.py`（26 個頁面），  
但忘記同步 `viewer.html`，導致左側選單缺少三個條目：
- `wails-scan-duplicate.md`
- `wails-build-issues.md`
- `wails-search-perf.md`

## 正確做法

每次新增 `.md` 後，**必須執行兩個步驟**（缺一不可）：

### Step A：重新產生 wiki-data.js（自動）
```powershell
python wiki/gen_data.py
```

### Step B：同步更新 viewer.html nav 陣列（手動）

在 `viewer.html` 找到對應 section 的 `items` 陣列，插入新項目：

```js
// pitfalls section 範例
{ label: "Wails 掃描重複番號", icon: "❌", file: "pitfalls/wails-scan-duplicate.md", path: "pitfalls/wails-scan-duplicate" },
{ label: "Wails 搜尋效能優化 75s→10s", icon: "⚡", file: "pitfalls/wails-search-perf.md", path: "pitfalls/wails-search-perf" },
```

**Icon 選擇**：
- 踩坑（錯誤/Bug）→ `❌`
- 效能優化 → `⚡`
- 架構說明 → `🏛️` / `🗺️`
- 開發模式 → `📄`

## 驗證方法

用瀏覽器開啟 `wiki/viewer.html`，確認左側選單有新頁面，點擊後能正確顯示內容。

## 相關文件

- [wiki-maintenance Skill](../../.agents/skills/wiki-maintenance/SKILL.md)
- [Chrome file:// CORS 封鎖](./viewer-file-cors.md)
