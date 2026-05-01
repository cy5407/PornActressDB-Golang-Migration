---
category: 工具
date: 2026-04-08
status: resolved
---
# Wiki Viewer 導覽選單與 wiki-data.js 脫鉤

> 狀態：歷史踩坑。現行 `viewer.html` 已改為從 `window.WIKI_DATA` 自動產生側欄，不再需要手動維護 nav 陣列。

## 問題描述

早期新增 `wiki/pitfalls/*.md` 後，`viewer.html` 的左側導覽選單沒有出現新頁面。

```text
# 症狀：viewer.html 顯示「找不到頁面」或選單根本沒有新條目
# 但 wiki-data.js 已包含對應內容（搜尋可以找到）
```

## 當時根本原因

早期 `wiki/` 有兩套獨立系統：

| 系統 | 產生方式 | 包含什麼 |
|------|----------|----------|
| `wiki-data.js` | `python wiki/gen_data.py` 自動產生 | 所有 `.md` 的內容 |
| `viewer.html` nav | 手動維護 JS 陣列 | 左側選單導覽項目 |

`gen_data.py` 掃描所有 `.md` 並寫入 `wiki-data.js`，但當時不會修改 `viewer.html` 的 nav 陣列。

## 現行修正

`viewer.html` 現在會自動從 `window.WIKI_DATA` 建立側欄：

```js
const SECTION_META = [
  { key: 'root', match: f => !f.includes('/') },
  { key: 'architecture', match: f => f.startsWith('architecture/') },
  { key: 'patterns', match: f => f.startsWith('patterns/') },
  { key: 'pitfalls', match: f => f.startsWith('pitfalls/'), grouped: true },
];
```

因此目前新增或修改 wiki 頁面的必要步驟是：

```powershell
$env:PYTHONIOENCODING='utf-8'
python wiki\gen_data.py
```

只要 `wiki-data.js` 重新產生，`viewer.html` 側欄就會自動包含新頁面。

## 驗證方法

1. 執行 `python wiki\gen_data.py`。
2. 用瀏覽器開啟 `wiki/viewer.html`。
3. 確認左側選單出現新頁面，點擊後能正確顯示內容。

Windows PowerShell 若遇到 `UnicodeEncodeError`，請先設定：

```powershell
$env:PYTHONIOENCODING='utf-8'
```

## 相關文件

- [wiki-maintenance Skill](../../.agents/skills/wiki-maintenance/SKILL.md)
- [Chrome file:// CORS 封鎖](./viewer-file-cors.md)
