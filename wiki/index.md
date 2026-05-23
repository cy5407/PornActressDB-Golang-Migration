# 女優分類系統 Wiki

> **維護方式**：由 AI Agent 負責撰寫與更新。你負責提問與探索；AI 負責整理、交叉引用、歸檔。
> 新增功能前先查 wiki，完成後更新 `log.md` 並執行 `python wiki/gen_data.py`。

---

## 我是新來的 / 我遇到問題

- 🟢 **第一次來** → [getting-started.md](getting-started.md)：5 步驟讀懂這個 repo。
- 🔍 **遇到具體症狀** → [troubleshooting.md](troubleshooting.md)：以症狀為起點的反向查表（含驗證 fix 是否在你 build 的 grep 指令）。
- 📜 **想看最近做了什麼** → [log.md](log.md)：append-only 開發紀錄（最新在上）。

---

## 架構 (architecture/)

| 頁面 | 摘要 |
|------|------|
| [架構總覽](architecture/overview.md) | Wails + Go + Python 混合架構、雙 Go module、各層職責 |
| [Go CLI 設計](architecture/go-cli.md) | classifier.exe 命令結構、JSON stdout 規範、scan 番號提取契約 |
| [Go Bridge](architecture/go-bridge.md) | 現行 Python→Go 委派入口 `go_cli.py` 與舊橋接層移除狀態 |
| [資料庫系統](architecture/database.md) | SQLite v3 為 source of truth、`pkg/database/sqlite_schema.sql` canonical、Go/Rust 共用 schema |
| [SQLite 影子資料庫](architecture/sqlite-shadow-db.md) 📦 | 第一版 shadow SQLite（**歷史 / 退役**）；C2 後 runtime 直接走 SQLite，本頁保留為歷史紀錄 |
| [搜尋引擎](architecture/search-engine.md) | AV-WIKI → JAVDB 級聯搜尋、來源專用 API 與批次併發邊界 |
| [技術選型決策](architecture/tech-stack-decisions.md) | Wails + Go CLI + Python 搜尋 runtime 的現行分工 |
| [**Wails GUI 架構**](architecture/wails-gui.md) | Wails v2 + React 架構、完整 Bindings 對照、相關踩坑分組 |
| [**片商分類架構**](architecture/studio-classification.md) | W7/W8 番號前綴直查（studios.json）+ DB fallback + major_studios 雙層判定 |

> 每個架構頁底部都有「相關踩坑」區塊，雙向連結。

---

## 開發模式 (patterns/)

| 頁面 | 摘要 |
|------|------|
| [新增 Go API 函式](patterns/add-go-api-function.md) | **必讀**：Wails binding（app.go）或 go_cli.py 呼叫路徑選擇 |
| [新增 Go CLI 子命令](patterns/add-go-cli-command.md) | Go CLI 子命令標準寫法與 JSON stdout 契約 |
| [新增 GUI 按鈕](patterns/add-gui-button.md) | Wails/React 按鈕範本、EventsEmit 進度推送、binding 規範 |
| [零女優補搜](patterns/zero-actress-retry.md) | 來源限定 AV-WIKI / JAVDB 補搜與 `avwiki_*` / `javdb_*` 狀態欄位 |
| [批次爬蟲效能](patterns/batch-scraper-performance.md) | AV-WIKI async 批次、共享連線池、自適應併發與 Go/Python 分工 |
| [命名規範](patterns/naming-conventions.md) | Python/Go/JSON/CLI API 動詞與跨語言對應規則 |
| [Python Fallback 移除](patterns/remove-python-fallback.md) | Phase 6 策略：寫入→RuntimeError、讀取→記憶體、整刪包裝類別 |
| [Session Cleaner 工作流](patterns/session-cleaner-workflow.md) | 壓縮 Copilot CLI /share session 紀錄、保留策略、使用情境 |
| [PyInstaller 打包](patterns/pyinstaller.md) 📦 | spec 設定、sys._MEIPASS 路徑、dist 同步（**歷史存檔**，現行用 `setup.ps1`） |

---

## 踩坑紀錄 (pitfalls/)

> **狀態圖示**：✅ 已修復且本 build 應已含  ⚠️ 部分修復 / 規避方案  📦 歷史存檔（不再適用）  〰️ 仍可能踩到

### 現行踩坑（按子題分組）

#### 掃描 / 移動

| 頁面 | 摘要 | 來源 |
|------|------|------|
| [Wails 掃描重複番號](pitfalls/wails-scan-duplicate.md) ✅ | WalkDir 無去重導致同番號多次出現；`seen[]` map 已修 | E2E 實測 |
| [**同路徑移動永久刪除檔案**](pitfalls/wails-move-same-path-delete.md) ✅ | 輸入==輸出目錄時二次移動觸發偽衝突；三層修復 + 垃圾桶 | 2026-04-08 |
| [Wails 移動後路徑未更新](pitfalls/wails-move-stale-paths.md) 〰️ | 移動成功後 scanResults 仍持有舊路徑 | 2026-04-07 |

#### DB / 設定

| 頁面 | 摘要 | 來源 |
|------|------|------|
| [Wails dbOnce 無法重置](pitfalls/wails-dbonce-no-reset.md) ✅ | sync.Once → sync.Mutex + resetDB；UpdatePreferences 後自動重置 | 2026-04-07 |
| [Wails DB 路徑寫入錯誤目錄](pitfalls/wails-db-path-wrong-dir.md) ✅ | resolveConfigPath 三層 fallback；resolveDataDir 相對 config 解析 | 2026-04-07 |
| [Wails DB data.json 從未更新](pitfalls/wails-db-json-never-updated.md) ✅ | BatchSearch / ensureDB 三處補 Compact() 呼叫 | 2026-04-07 |
| [Wails DB 資料格式不一致](pitfalls/wails-db-format-migration.md) ✅ | Go 寫入統一為 `searched_found`；含 2903 筆資料合併紀錄 | 2026-04-08 |
| [Wails 快取狀態判定不一致](pitfalls/wails-cache-status-mismatch.md) 〰️ | 前後端對「已搜尋」判斷不一致 | 2026-04-07 |
| [Schema 共用：Go //go:embed vs Rust include_str!](pitfalls/schema-share-go-embed-vs-rust-include.md) ✅ | C3 schema 共用方向不對稱；canonical 必須留在 Go package 內 | 2026-05-23 |

#### 搜尋

| 頁面 | 摘要 | 來源 |
|------|------|------|
| [JAVDB False Positive](pitfalls/javdb-false-positive.md) ✅ | 無精確匹配 fallback 第一筆造成番號污染；二次驗證已加 | Issue 12 |
| [Wails 搜尋效能優化](pitfalls/wails-search-perf.md) ✅ | 75s → 10s：rate limiter 停用 + thread-local 並行初始化 | E2E 實測 |
| [**來源搜尋清空結果致未分類**](pitfalls/wails-source-search-clears-results.md) ✅ | `runSourceSearch` 清空 + 快取番號 filter；commit `20602f2` | 2026-04-19 |
| [**Python 欄位 method vs search_method 不一致**](pitfalls/python-search-method-field-mismatch.md) ✅ | Python 輸出 `method`、Go journal 期望 `search_method`；commit `b496dd5` | 2026-04-20 |
| [**女優分類污染候選與 AV-WIKI 純文字 fallback**](pitfalls/wails-actress-classification-polluted-candidates.md) ✅ | 多人共演 + 全文猜女優導致片名碎片變資料夾；分四批修復 | 2026-04-22 |

#### 片商分類

| 頁面 | 摘要 | 來源 |
|------|------|------|
| [**Wails 片商名稱正規化錯誤**](pitfalls/wails-studio-canonical-match.md) ⚠️ | A：`canonicalMajorStudio` 大小寫 ✅；B：`resolveMajorStudiosPath` 三層 fallback 未實作、靠 setup.ps1 補檔 | W8 |
| [Wails dist 缺少片商資料](pitfalls/wails-dist-missing-studio-data.md) ⚠️ | EXE 同目錄缺 `studios.json` / `major_studios.json`；裸 `wails build` 後請改跑 setup.ps1 | 2026-04-08 |

#### 番號提取 / 建置 / 工具

| 頁面 | 摘要 | 來源 |
|------|------|------|
| [Extractor `[CODE]` 格式被清空](pitfalls/go-extractor-bracket-format.md) 〰️ | `[SKMJ-310]`、PPV 位數、MGS 數字前綴等邊界 | 2026-04-08 / 2026-04-24 |
| [Wails 建置踩坑](pitfalls/wails-build-issues.md) 〰️ | npm 版本衝突、TS 命名空間、native dialog | E2E 實測 |
| [GitHub Actions 故障](pitfalls/github-actions-issues.md) 〰️ | schedule / scope guard / Go API / Node.js Issue 1-22 | CI/CD |
| [Chrome file:// CORS](pitfalls/viewer-file-cors.md) ✅ | viewer.html 改用內嵌 wiki-data.js | 2026-04-06 |

### 📦 歷史存檔（已不再適用於現行架構）

| 頁面 | 為何已過時 |
|------|-----------|
| [go_api 匯出遺漏](pitfalls/go-api-export-missing.md) 📦 | go_api/ 套件已於 W6 完全移除 |
| [GUI Bridge 取法錯誤](pitfalls/gui-bridge-wrong-access.md) 📦 | Tkinter GUI 與 go_bridge.py 已於 W6 完全移除 |
| [Go CLI 未定義 -json](pitfalls/go-cli-json-flag-missing.md) 📦 | 舊 go_runner 架構已移除；現行 go_cli.py 不自動加 -json |
| [PyInstaller 路徑問題](pitfalls/pyinstaller-path.md) 📦 | 改用 Wails portable bundle，不再用 sys._MEIPASS |
| [Wiki Viewer 選單脫鉤](pitfalls/wiki-viewer-nav-out-of-sync.md) ✅ | viewer.html 現由 wiki-data.js 自動產生側欄 |

---

## 快速查找

- **🆘 我遇到 XX，怎麼辦** → [troubleshooting.md](troubleshooting.md)
- **🆕 我是第一次來** → [getting-started.md](getting-started.md)
- **🛠️ 改 wiki 的流程** → [getting-started.md § 6](getting-started.md#6-想改-wiki)
- **Python Fallback 移除策略** → [patterns/remove-python-fallback.md](patterns/remove-python-fallback.md)
- **CI/CD 故障排查** → [pitfalls/github-actions-issues.md](pitfalls/github-actions-issues.md)（Issue 1-22）
- **新增 Go API / CLI / GUI** → [patterns/add-go-api-function.md](patterns/add-go-api-function.md) ｜ [patterns/add-go-cli-command.md](patterns/add-go-cli-command.md) ｜ [patterns/add-gui-button.md](patterns/add-gui-button.md)
- **Go CLI / 番號提取契約** → [architecture/go-cli.md](architecture/go-cli.md)
- **SQLite 影子資料庫** → [architecture/sqlite-shadow-db.md](architecture/sqlite-shadow-db.md)
- **Rebuild & 發行** → 開發跑 `wails build`；正式發行跑 `setup.ps1` 產出 portable bundle
- **命名規範檢查** → [patterns/naming-conventions.md](patterns/naming-conventions.md)
- **搜尋架構理解** → [architecture/search-engine.md](architecture/search-engine.md)
- **批次爬蟲效能** → [patterns/batch-scraper-performance.md](patterns/batch-scraper-performance.md)
- **完整茶包射手** → [docs/茶包射手/github-actions-workflow.md](../docs/茶包射手/github-actions-workflow.md) | [wails-e2e-scan.md](../docs/茶包射手/wails-e2e-scan.md)
