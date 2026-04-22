# README / Wiki 文件更新 Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 讓 `README.md` 與核心 wiki 頁面回到以目前 live code 為準的狀態，修正文檔漂移、補齊搜尋模式與資料欄位說明，並同步更新 wiki 派生資料。

**Architecture:** 先以 live code / build scripts / Wails backend / Python 搜尋入口作為唯一 source of truth，再更新 `README.md` 與 wiki 的高價值頁面。這次屬文件修正，不改 production code；採用「docs 版 TDD」：先列出目前可被程式碼證偽的失真點，再逐項修正文檔，最後用產生器與 diff/測試命令驗證。

**Tech Stack:** Markdown、Python wiki generator、git、Wails backend (`app.go`)、Python 搜尋入口 (`run_search.py` / `run_batch_search.py`)、Go DB schema (`pkg/database/types.go`)

---

## 執行前建議：test-driven-development 的套用方式

這次是文件更新，不是功能實作，所以不適合硬套傳統單元測試 red-green；但仍應遵守 `test-driven-development` 的精神：

1. 先找出「目前文件說法會被實作打臉」的具體證據。
2. 把這些證據當成 fail case 清單。
3. 文件修正後，再跑驗證命令確認不再自相矛盾。

本次 fail case 清單：
- `README.md` 宣稱 `setup.ps1` / `setup.sh` 會建立 Python venv、安裝 pip 套件與 `npm install`，但實際腳本沒有這些步驟。
- `README.md` 只描述 AV-WIKI → JAVDB 級聯搜尋，未說明前端/後端已有 AV-WIKI-only 與 JAVDB-only API。
- `wiki/architecture/search-engine.md` 把搜尋行為寫成單一路徑，未反映 `run_search.py` / `run_batch_search.py` 的 `source_mode`。
- `wiki/architecture/database.md` frontmatter/來源標頭重複，JSON schema 範例格式錯誤且欄位說明落後於 `pkg/database/types.go`。

---

### Task 1: 建立 drift 證據清單

**Objective:** 把 README / wiki 與 live code 的落差整理成明確可執行的修改範圍。

**Files:**
- Inspect: `README.md`
- Inspect: `setup.ps1`
- Inspect: `setup.sh`
- Inspect: `wails-app/backend/app.go`
- Inspect: `src/scrapers/run_search.py`
- Inspect: `src/scrapers/run_batch_search.py`
- Inspect: `pkg/database/types.go`
- Inspect: `wiki/architecture/search-engine.md`
- Inspect: `wiki/architecture/database.md`
- Inspect: `wiki/index.md`

**Step 1: 收集實作證據**

確認以下事實並記錄：
- `setup.ps1`：建置 `classifier.exe` 與 `actress-classifier.exe`，但不建立 venv、不 `pip install`、不 `npm install`
- `setup.sh`：只建置 Linux `classifier`，並明寫 Wails GUI 僅支援 Windows 建置
- `app.go`：存在 `BatchSearch`、`BatchSearchAVWiki`、`BatchSearchJAVDB`
- `run_search.py` / `run_batch_search.py`：支援 `cascade` / `avwiki` / `javdb` 模式
- `pkg/database/types.go`：`VideoData` 含 `avwiki_*`、`javdb_*`、`search_method`、`error`、`error_kind`

**Step 2: Run evidence checks**

Run:
```bash
cd '/home/yuta/桌面/PornActressDB-Golang-Migration' && \
python3 - <<'PY'
from pathlib import Path
files = [
    'README.md',
    'setup.ps1',
    'setup.sh',
    'wails-app/backend/app.go',
    'src/scrapers/run_search.py',
    'src/scrapers/run_batch_search.py',
    'pkg/database/types.go',
    'wiki/architecture/search-engine.md',
    'wiki/architecture/database.md',
]
for f in files:
    p = Path(f)
    print(f'=== {f} ===')
    print('exists=', p.exists())
PY
```
Expected: all target files exist.

**Step 3: Commit**

No commit in this task.

---

### Task 2: 更新 README 的安裝 / 建置 / 執行描述

**Objective:** 讓 `README.md` 的快速開始與建置流程符合 `setup.ps1` / `setup.sh` 的真實行為。

**Files:**
- Modify: `README.md`

**Step 1: 修改以下段落**

把 README 中這些失真敘述改正：
- 不再寫 setup 腳本會建立 venv、安裝 pip 套件、跑 `npm install`
- 清楚區分：
  - Windows `setup.ps1`：建置 `classifier.exe` + `actress-classifier.exe`
  - Linux/macOS `setup.sh`：只建置 `classifier`
  - Python 搜尋功能需另外 `pip install -r requirements.txt`
- 在開發者段落補一行：Wails 前端相依安裝需要手動進 `wails-app/frontend` 執行 `npm install`
- 若 README 提到 GUI，需說明 Windows 為正式桌面建置目標；Linux 主要可做 CLI / 文件 / 測試驗證

**Step 2: 補充實際執行入口**

在 README 補上更精準的入口說明：
- 發行版：`actress-classifier.exe`
- 開發/輔助：`classifier(.exe)` 與 `run.py`

**Step 3: Run verification**

Run:
```bash
cd '/home/yuta/桌面/PornActressDB-Golang-Migration' && git diff -- README.md
```
Expected: diff 只顯示 README 的安裝/建置/執行描述修正，沒有 unrelated 內容。

**Step 4: Commit**

暫不 commit，等所有文件一起驗證後再處理。

---

### Task 3: 更新 README 的搜尋流程與資料庫欄位說明

**Objective:** 讓 README 反映目前搜尋 API 與資料欄位，不再把功能寫得比實作更舊。

**Files:**
- Modify: `README.md`

**Step 1: 修正搜尋描述**

把「搜尋 = 單純 AV-WIKI → JAVDB」調整為更精準描述：
- 預設批次搜尋主路徑仍是 cascade
- Wails 前端/後端另有 AV-WIKI-only 與 JAVDB-only 來源搜尋
- 來源搜尋屬補查/指定來源重跑，不應描述成唯一主流程

**Step 2: 修正 JSON 資料庫欄位摘要**

在 README 的 JSON 資料庫區塊至少補到：
- `avwiki_actress_status`
- `avwiki_last_search_date`
- `javdb_actress_status`
- `javdb_last_search_date`
- `error`
- `error_kind`

並明寫：更完整 schema 請看 wiki database 頁。

**Step 3: Run verification**

Run:
```bash
cd '/home/yuta/桌面/PornActressDB-Golang-Migration' && git diff -- README.md | sed -n '1,240p'
```
Expected: README 搜尋與 schema 區塊已對齊 live code，沒有把 source-specific search 寫成不存在。

**Step 4: Commit**

暫不 commit。

---

### Task 4: 更新 wiki/architecture/search-engine.md

**Objective:** 修正搜尋架構頁，準確描述主流程與 source-specific 路徑的差異。

**Files:**
- Modify: `wiki/architecture/search-engine.md`

**Step 1: 更新頁首 metadata**

- 更新來源欄位，加入：
  - `wails-app/backend/app.go`
  - `src/scrapers/run_search.py`
  - `src/scrapers/run_batch_search.py`
  - `src/services/web_searcher.py`
- 更新日期為本次修改日期

**Step 2: 改寫搜尋策略段落**

文件需明確區分：
- 預設 `BatchSearch` / `search_info` = cascade 主流程
- `BatchSearchAVWiki` / `BatchSearchJAVDB` = source-specific 補查 API
- `run_search.py` 與 `run_batch_search.py` 支援 `source_mode`（`cascade` / `avwiki` / `javdb`）
- source-specific 執行時，會更新 `avwiki_*` / `javdb_*` 狀態欄位

**Step 3: 補充前端行為**

加入一小節說明 Wails UI 已有來源搜尋按鈕，這是「指定來源重跑 / 補查」能力，而非另一路獨立爬蟲架構。

**Step 4: Run verification**

Run:
```bash
cd '/home/yuta/桌面/PornActressDB-Golang-Migration' && git diff -- wiki/architecture/search-engine.md
```
Expected: 搜尋頁不再只描述單一路徑，且沒有憑空新增不存在的搜尋來源。

**Step 5: Commit**

暫不 commit。

---

### Task 5: 清理並更新 wiki/architecture/database.md

**Objective:** 修正 database wiki 頁的 header 漂移、JSON 範例格式錯誤、欄位描述落後等問題。

**Files:**
- Modify: `wiki/architecture/database.md`

**Step 1: 清理頁首與來源**

- 移除重複的來源/更新標頭
- 不再把已刪除的根目錄 `MIGRATION_STATUS.md` 當成主要來源
- 主要來源改為：
  - `pkg/database/types.go`
  - `src/models/incremental_json_database.py`
  - `src/models/json_database.py`
  - `wails-app/backend/app.go`（若欄位狀態邏輯有引用）

**Step 2: 修正 JSON 範例**

範例 JSON 必須是合法 JSON：
- 移除重複 `error` / `error_kind` 行
- 補齊缺少的逗號與整體結構
- 加入 `avwiki_actress_status`、`avwiki_last_search_date`、`javdb_actress_status`、`javdb_last_search_date`
- `search_method`、`error`、`error_kind` 說明要與現況一致

**Step 3: 調整枚舉與欄位說明**

至少寫清楚：
- app / Python 搜尋流程目前使用的 `search_status` 值：`imported` / `searched_found` / `searched_not_found` / `search_error`
- `error_kind` 常見值目前至少有：`not_found`、`error`，另外 Go/Wiki 歷史文件曾提 `timeout`、`stderr`、`json_parse`，若保留需註明屬可分類擴充值，不要寫成目前唯一固定全集
- `search_error_reason` 是 Python 管線暫時欄位，非 Go DB 持久化欄位

**Step 4: Run verification**

Run:
```bash
cd '/home/yuta/桌面/PornActressDB-Golang-Migration' && python3 - <<'PY'
from pathlib import Path
text = Path('wiki/architecture/database.md').read_text(encoding='utf-8')
print('source headers =', text.count('> 來源：'))
print('update headers =', text.count('> 更新：'))
PY
```
Expected: 頁首 metadata 不重複；來源/更新標頭各維持合理次數。

**Step 5: Commit**

暫不 commit。

---

### Task 6: 更新 wiki/log.md 記錄本次 drift 修正

**Objective:** 依 wiki 維護規則追加一筆文件漂移修正紀錄。

**Files:**
- Modify: `wiki/log.md`

**Step 1: 在最上方新增一筆 docs log**

格式參考現有條目，內容至少涵蓋：
- README 安裝/建置敘述校正
- 搜尋架構頁補齊 source-specific search
- database 頁修正欄位與 JSON sample

**Step 2: Run verification**

Run:
```bash
cd '/home/yuta/桌面/PornActressDB-Golang-Migration' && git diff -- wiki/log.md
```
Expected: 只新增一筆最新 log，沒有重複標頭或破壞既有排序。

**Step 3: Commit**

暫不 commit。

---

### Task 7: 重新產生 wiki-data.js 並驗證

**Objective:** 讓 wiki 派生資料與 markdown 同步。

**Files:**
- Modify: `wiki/wiki-data.js`
- Input: `wiki/gen_data.py`

**Step 1: 產生派生資料**

Run:
```bash
cd '/home/yuta/桌面/PornActressDB-Golang-Migration' && python3 wiki/gen_data.py
```
Expected: 成功輸出 `wiki/wiki-data.js`，頁面數正常。

**Step 2: 驗證派生檔包含更新頁面**

Run:
```bash
cd '/home/yuta/桌面/PornActressDB-Golang-Migration' && rg -n "source-specific|BatchSearchAVWiki|error_kind|setup.ps1|setup.sh" README.md wiki/architecture/search-engine.md wiki/architecture/database.md wiki/wiki-data.js
```
Expected: 關鍵字至少出現在對應 markdown 與 `wiki/wiki-data.js` 中。

**Step 3: Commit**

暫不 commit。

---

### Task 8: 最終驗證與選擇性提交

**Objective:** 確認文件修改乾淨、無格式問題，且不誤納入 unrelated dirty files。

**Files:**
- Verify: `README.md`
- Verify: `wiki/architecture/search-engine.md`
- Verify: `wiki/architecture/database.md`
- Verify: `wiki/log.md`
- Verify: `wiki/wiki-data.js`

**Step 1: Run validation commands**

Run:
```bash
cd '/home/yuta/桌面/PornActressDB-Golang-Migration' && \
git diff --check -- README.md wiki/architecture/search-engine.md wiki/architecture/database.md wiki/log.md wiki/wiki-data.js && \
git status --short
```
Expected:
- `git diff --check` 無 trailing whitespace / malformed hunk 問題
- `git status --short` 只顯示本次相關修改，另保留既有 unrelated untracked：
  - `docs/plans/2026-04-21-healthchecker-fix-and-tests.md`
  - `uv.lock`

**Step 2: 若使用者要 commit，僅 stage 本次文件**

```bash
git add README.md wiki/architecture/search-engine.md wiki/architecture/database.md wiki/log.md wiki/wiki-data.js docs/plans/2026-04-21-readme-wiki-update-plan.md
```

**Step 3: Commit message（只有在使用者要求 commit 時）**

```bash
git commit -m "docs: align README and wiki with current implementation"
```

---

## 完成定義

本計畫完成時，必須同時滿足：
- `README.md` 不再誤稱 setup script 會做 venv/pip/npm 安裝
- `README.md` 與 wiki 都明確區分 cascade 主流程與 source-specific search
- `wiki/architecture/database.md` 不再引用已刪除根目錄 `MIGRATION_STATUS.md` 作為主要事實來源
- `wiki/architecture/database.md` JSON sample 合法且欄位說明反映 `VideoData`
- `wiki/wiki-data.js` 已重新產生
- 未誤 stage `uv.lock` 或其他 unrelated dirty files
