---
name: wiki-maintenance
description: Wiki 知識庫維護指引 - 新增功能後更新 wiki/，踩坑後歸檔 pitfalls/，定期 lint 確保交叉引用正確
argument-hint: "[ingest|query|lint|pitfall]"
---

# Wiki 維護 Skill

## Wiki 位置

```
wiki/
├── index.md          ← 所有頁面目錄（AI 每次更新後同步）
├── log.md            ← append-only 操作日誌
├── architecture/     ← 架構說明頁
├── patterns/         ← 開發模式（可預防問題的正確做法）
└── pitfalls/         ← 踩坑紀錄（已發生的問題）
```

---

## 四個操作

### 1. Ingest（新功能完成後）

觸發時機：完成一個功能、完成一次修復後。

步驟：
1. 若新功能引入了新的「正確做法」→ 在 `wiki/patterns/` 新增或更新頁面
2. 若發生了可預防的 Bug → 在 `wiki/pitfalls/` 新增頁面
3. 更新 `wiki/index.md` 的對應表格
4. 在 `wiki/log.md` 末尾追加一筆記錄
5. **同步 `wiki/viewer.html` 的 `WIKI` 物件**（見下方規則）
6. **重新產生 `wiki/wiki-data.js`**（讓 viewer.html 不需要 server）

```powershell
python wiki/gen_data.py
```

log 格式：
```
## [YYYY-MM-DD] <類型> | <摘要>

**涉及檔案**：...
**踩坑**：...（如有）
```

---

### 同步 viewer.html WIKI 物件（必須執行）

每次新增或刪除 `wiki/**/*.md` 後，必須同步更新 `wiki/viewer.html` 第 118 行起的 `const WIKI = { sections: [...] }` 物件。

**規則：**
- 標題（label）：從 md 檔的第一個 `# H1` 取得
- icon：依下表選取；無對應則 patterns 用 `📄`、pitfalls 用 `❌`
- 新增項目：插入到對應 section 的 `items` 陣列，**依字母排序**
- 刪除項目：從 `items` 陣列移除對應行

**Icon 參考表：**

| 目錄 | 預設 | 常見對應 |
|------|------|---------|
| root | — | `index`→🏠 `log`→📋 |
| architecture | 🗺️ | go-cli→⚙️ go-bridge→🌉 database→🗄️ search→🔍 |
| patterns | 📄 | add-*→➕ gui→🖱️ naming→📝 pkg→📦 retry→🔄 remove→🗑️ |
| pitfalls | ❌ | 全部 ❌ |

**格式（每行一個 item）：**
```js
{ label: "頁面標題", icon: "🔤", file: "patterns/new-page.md", path: "patterns/new-page" },
```

> viewer.html 直接用瀏覽器開啟（`file://`），不需要 server。  
> 保持 WIKI 物件同步即可確保側欄正確顯示。

---

### 2. Query（開始新任務前）

觸發時機：要新增功能、修改現有功能之前。

步驟：
1. 先讀 `wiki/index.md` 確認有哪些相關頁面
2. 閱讀 `patterns/` 中相關頁面（確認正確做法）
3. 閱讀 `pitfalls/` 中相關頁面（避免重踩）
4. 完成後執行 Ingest

---

### 3. Lint（定期健檢）

觸發時機：每隔 5-10 次 session，或有人要求時。

檢查項目：
- `index.md` 是否有頁面路徑失效
- `patterns/` 頁面引用的程式碼是否仍與現況吻合
- `pitfalls/` 的修正方法是否已反映在 `patterns/`
- `log.md` 最近幾筆是否有遺漏重大事件

---

### 4. Pitfall（緊急踩坑歸檔）

觸發時機：發現 Bug 且修復完成後。

步驟：
1. 在 `wiki/pitfalls/<描述性名稱>.md` 建立新頁面
2. 格式：**症狀**、**根因**、**正確做法**（連結到 patterns/）
3. 更新 `wiki/index.md` 踩坑紀錄表格（加入 Issue 編號）
4. 若此 Bug 有預防模式，在 `wiki/patterns/` 新增或更新對應頁面
5. 在 `wiki/log.md` 追加 `pitfall` 類型記錄

---

## 命名規範

- 頁面檔名：`kebab-case.md`，描述性，不加日期
- pitfall 頁面：以問題現象命名，如 `go-api-export-missing.md`
- pattern 頁面：以行動命名，如 `add-go-api-function.md`

---

## 不需要寫進 wiki 的東西

- 只在一個地方用到的實作細節 → 程式碼內的 docstring/註解即可
- 正在進行中、尚未確定的設計 → `docs/superpowers/plans/` 或 `docs/internal/`
- GitHub Actions 問題 → `docs/茶包射手/`（已有專屬文件）

---

## 與茶包射手的分工

| 文件 | 定位 |
|------|------|
| `wiki/pitfalls/` | **程式碼層**的 Bug：錯誤 API 用法、模式違反 |
| `docs/茶包射手/` | **CI/CD 和工具鏈**的問題：GitHub Actions、打包工具 |

兩者互補，不重複。pitfalls 頁面可連結到茶包射手對應 Issue。
