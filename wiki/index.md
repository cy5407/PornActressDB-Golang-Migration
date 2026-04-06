# 女優分類系統 Wiki

> **維護方式**：由 AI Agent 負責撰寫與更新。你負責提問與探索；AI 負責整理、交叉引用、歸檔。
> 新增功能前先查 wiki，完成後更新 `log.md`。

---

## 架構 (architecture/)

| 頁面 | 摘要 |
|------|------|
| [架構總覽](architecture/overview.md) | Python + Go 混合架構、資料流、各層職責 |
| [Go CLI 設計](architecture/go-cli.md) | classifier.exe 命令結構、JSON 輸出規範 |
| [Go Bridge](architecture/go-bridge.md) | Python→Go 橋接層三層結構與 fallback 機制 |
| [資料庫系統](architecture/database.md) | IncrementalJSONDB / JSONDBManager / Journal 機制 |
| [搜尋引擎](architecture/search-engine.md) | AV-WIKI → JAVDB 級聯搜尋架構 |

---

## 開發模式 (patterns/)

| 頁面 | 摘要 |
|------|------|
| [新增 Go API 函式](patterns/add-go-api-function.md) | **必讀**：新增函式須同步更新的三個地方 |
| [新增 Go CLI 子命令](patterns/add-go-cli-command.md) | Go CLI 子命令標準寫法（含 -json flag） |
| [新增 GUI 按鈕](patterns/add-gui-button.md) | GUI 背景執行緒、GoBridge 取法、db_manager 路徑 |
| [PyInstaller 打包](patterns/pyinstaller.md) | spec 設定、sys._MEIPASS 路徑、dist 同步 |
| [零女優二次搜尋](patterns/zero-actress-retry.md) | 零女優自動清快取 + 第二輪 JAVDB 搜尋流程 |
| [命名規範](patterns/naming-conventions.md) | Python/Go/JSON/CLI API 動詞與跨語言對應規則 |
| [Python Fallback 移除](patterns/remove-python-fallback.md) | Phase 6 策略：寫入→RuntimeError、讀取→記憶體、整刪包裝類別 |

---

## 踩坑紀錄 (pitfalls/)

| 頁面 | 摘要 | 來源 Issue |
|------|------|------------|
| [go_api 匯出遺漏](pitfalls/go-api-export-missing.md) | 新增函式漏更新 `__init__.py` 導致 AttributeError | Issue 14 |
| [GUI Bridge 取法錯誤](pitfalls/gui-bridge-wrong-access.md) | `self.core.go_bridge` 不存在，應用 `get_bridge()` | Issue 13 |
| [Go CLI 未定義 -json](pitfalls/go-cli-json-flag-missing.md) | 新增子命令未宣告 -json flag 導致 ExitOnError | Issue 15 |
| [JAVDB False Positive](pitfalls/javdb-false-positive.md) | 搜尋無精確匹配時 fallback 第一筆造成誤匹配 | Issue 12 |
| [PyInstaller 路徑問題](pitfalls/pyinstaller-path.md) | studios.json 在打包環境下應從 sys._MEIPASS 讀取 | dist 測試 |
| [GitHub Actions 故障](pitfalls/github-actions-issues.md) | schedule/scope guard/Go API/Node.js Issue 1-15 全紀錄 | CI/CD |

---

## 快速查找

- **Python Fallback 移除** → [patterns/remove-python-fallback.md](patterns/remove-python-fallback.md)（Phase 6 完整策略）
- **CI/CD 故障排查** → [pitfalls/github-actions-issues.md](pitfalls/github-actions-issues.md)（Issue 1-19）
- **新增 Go API 功能** → [patterns/add-go-api-function.md](patterns/add-go-api-function.md)
- **新增 GUI 按鈕** → [patterns/add-gui-button.md](patterns/add-gui-button.md)
- **Rebuild EXE** → [patterns/pyinstaller.md](patterns/pyinstaller.md)
- **命名規範檢查** → [patterns/naming-conventions.md](patterns/naming-conventions.md)
- **搜尋架構理解** → [architecture/search-engine.md](architecture/search-engine.md)
- **完整茶包射手** → [docs/茶包射手/github-actions-workflow.md](../docs/茶包射手/github-actions-workflow.md)
