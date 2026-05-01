---
name: 從這裡開始
description: 第一次接觸這個 repo / 這個 wiki 的人應該怎麼閱讀
date: 2026-05-02
---

# 從這裡開始

> 給第一次來查修這個專案的人。讀完這頁應該能：知道這專案有哪些子系統、怎麼跑起來、卡住時去哪查。

---

## 1. 先理解三層架構（5 分鐘）

讀 [architecture/overview.md](architecture/overview.md)。重點抓三件事：

1. **Wails 桌面 GUI**（`wails-app/`，Go + React/TypeScript）— 一般使用者直接互動的層。
2. **Go CLI + pkg/**（`cmd/scanner/`、`pkg/`）— 掃描、移動、資料庫、片商識別都在這。
3. **Python 搜尋管線**（`src/scrapers/`、`src/services/`）— 只負責爬蟲；非爬蟲層**沒有** Python fallback。

> 注意有兩個 Go module：根目錄 `actress-classifier`（CLI 與 pkg）、`wails-app/wails-app`（GUI），後者用 `replace` 指令 import 前者。

---

## 2. 跑起來（10 分鐘）

```powershell
# 安裝 Python 相依
pip install -r requirements.txt

# 建 Go CLI
go build -o classifier.exe .\cmd\scanner

# 建 Wails GUI
Set-Location wails-app
wails build
```

> ⚠️ 不要直接複製 `wails-app\build\bin\actress-classifier.exe` 出去就以為能用。`studios.json` / `major_studios.json` 必須與 EXE 同目錄，現行 `resolveStudiosPath` 沒有「往上找專案根」的 fallback。**正式發行請改跑 `.\setup.ps1`** 產出 `dist\PornActressDB-windows-portable.zip`。

---

## 3. 改某個東西時去哪？

| 你想改 | 主要檔案 | 對應 pattern |
|--------|---------|--------------|
| Wails GUI 按鈕 / 頁面 | `wails-app/frontend/src/` | [add-gui-button](patterns/add-gui-button.md) |
| Wails 後端 API（Go binding） | `wails-app/backend/app.go` | [add-go-api-function](patterns/add-go-api-function.md) |
| CLI 子命令 | `cmd/scanner/*.go` | [add-go-cli-command](patterns/add-go-cli-command.md) |
| 番號提取規則 | `pkg/extractor/extractor.go` | — |
| DB schema / journal | `pkg/database/*.go` | — |
| 移動 / 回滾 | `pkg/mover/*.go` | — |
| 片商識別 | `pkg/studio/identifier.go` + `studios.json` / `major_studios.json` | — |
| AV-WIKI / JAVDB 爬蟲 | `src/services/web_searcher.py`、`src/scrapers/sources/*.py` | [batch-scraper-performance](patterns/batch-scraper-performance.md) |
| 搜尋 subprocess 入口 | `src/scrapers/run_search.py`、`run_batch_search.py` | — |
| Python ↔ Go CLI 委派 | `src/services/go_cli.py` | — |

---

## 4. 改完之後

```powershell
# 跑全部測試
go test .\pkg\... -v
go test .\cmd\scanner -v
Set-Location wails-app; go test .\backend -v
python -m pytest tests\ -q -p no:cacheprovider
```

如果改的是 GUI、要實機驗證，重跑 `setup.ps1` 並開啟 `dist\PornActressDB-windows-portable.zip` 測試（直接跑 build/bin 的 EXE 會踩 studios.json 路徑雷）。

---

## 5. 卡住怎麼辦？

依序：

1. **症狀查表** → [troubleshooting.md](troubleshooting.md)：以「我看到什麼錯誤」為起點。
2. **架構查詢** → [architecture/](architecture/)：理解這個子系統怎麼運作。
3. **踩坑全集** → [pitfalls/](pitfalls/)：歷史上踩過的坑（部分已修，每頁有狀態標示）。
4. **時間順序** → [log.md](log.md)：最近 3 個月做了什麼、修了什麼。
5. **viewer.html 全文搜尋**：直接 Ctrl+F，內容已透過 `wiki-data.js` 內嵌，無需 server。

---

## 6. 想改 wiki

修改 `wiki/**/*.md` 後**必須**：

1. 編輯 .md。
2. 在 `wiki/log.md` 追加當日紀錄（格式對照既有 entry，最新在上）。
3. 執行 `python wiki/gen_data.py` 重新產生 `wiki/wiki-data.js`（Windows console 若 `UnicodeEncodeError`，前面加 `$env:PYTHONIOENCODING='utf-8';`）。

否則 `viewer.html` 看到的仍是舊 wiki。

---

## 7. 不要做的事

- ❌ 在非爬蟲層恢復 / 新增 Python fallback（會違反 Go-only 邊界）。
- ❌ 直接手改 `data/json_db/data.json`（請走 `classifier.exe db ...` 或 `JSONDBManager`）。
- ❌ 跳過 `setup.ps1` 直接複製 EXE 發行（會缺資源檔）。
- ❌ 改完 wiki 不跑 `gen_data.py`（讀者看到的是快取的舊內容）。
- ❌ 把已修復的 pitfall 直接刪掉（保留作為歷史教訓，加 `status: resolved` 即可）。

---

## 8. 還想看哪些頁？

- [tech-stack-decisions](architecture/tech-stack-decisions.md)：為何選 Wails、為何把 Python 限縮在搜尋。
- [database](architecture/database.md)：增量 JSON DB 的 journal/index/compact 機制。
- [search-engine](architecture/search-engine.md)：AV-WIKI → JAVDB 級聯邏輯。
- [studio-classification](architecture/studio-classification.md)：片商分類的兩層判定。
- [naming-conventions](patterns/naming-conventions.md)：Python/Go/JSON 命名規則對應表。
- [remove-python-fallback](patterns/remove-python-fallback.md)：Phase 6 移除 Python fallback 的策略。
