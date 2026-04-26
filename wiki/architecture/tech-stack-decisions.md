# 技術選型決策紀錄

> 記錄目前語言 / 框架分工，以及哪些 Python 模組值得繼續 Go 化。
> 更新：2026-04-27（Wails 已成為正式 GUI，修正舊 Tkinter 描述）

---

## 現行結論

本專案目前不是「Python 全面替換成 Go」，而是採用明確邊界的混合架構：

| 職責 | 現行技術 | 判斷 |
|------|----------|------|
| 桌面 GUI | Wails v2 + Go backend + React/TypeScript | 正式主 GUI |
| 掃描 / 移動 / 回滾 | Go CLI / `pkg/app` / `pkg/mover` | 繼續維持 Go-only |
| JSON DB / compact / backup | Go DB + Python 委派殼 | 繼續維持 Go-only 寫入 |
| 番號提取 / 片商識別 | Go `pkg/extractor` / `pkg/studio` | 繼續維持 Go-only |
| 搜尋 / 爬蟲解析 | Python `WebSearcher` + AV-WIKI / JAVDB scrapers | 暫時保留 Python |
| 測試 | pytest + Go test | 依模組語言分流 |

核心原則：

- 本機資料與檔案操作：優先 Go 化，讓 Wails 與 CLI 共用同一份能力。
- 爬蟲與 HTML 解析：保留 Python，因為網站格式變動快，BeautifulSoup / aiohttp / 編碼處理仍較省維護成本。
- Python 不再作為非爬蟲層 fallback；非爬蟲能力若 Go CLI 不可用，應明確失敗。

---

## 爬蟲層：為什麼保留 Python

### 競爭者比較

| 語言 | 代表框架 | 優勢 | 劣勢 |
|------|----------|------|------|
| Python | BeautifulSoup / aiohttp / requests | 日文編碼、HTML 解析、快速調整規則最成熟 | 打包與執行環境需額外處理 |
| Node.js | Cheerio / Playwright / Puppeteer | 動態網站與 JS 執行能力強 | 對本專案靜態日文頁面不是必要 |
| Go | goquery / Colly / Rod | 單一 binary、併發強 | HTML 解析與站點規則迭代成本較高 |
| Rust | reqwest + scraper | 效能與型別安全強 | 開發速度與生態不符合目前需求 |

### 結論

AV-WIKI / JAVDB 目前仍以靜態 HTML 解析、日文編碼處理、反爬語意與錯誤分類為主要成本。這些工作不太需要 Go 的 CPU 效能，反而需要快速修正解析規則。

因此目前最合理的設計是：

```text
Wails backend / Go CLI
    ↓ subprocess（固定 JSON / JSON Lines 契約）
Python 搜尋入口 run_search.py / run_batch_search.py
    ↓
WebSearcher + scrapers
```

未來若要 Go 化搜尋層，應優先搬「調度、契約、結果正規化」這類穩定部分；HTML 解析本身不需要急著重寫。

---

## GUI 層：為什麼已改用 Wails

舊的 Python Tkinter GUI 已於 W6 清理移除；現行正式桌面 GUI 是 `wails-app/`：

| 選項 | 狀態 | 評估 |
|------|------|------|
| Tkinter | 已移除 | 歷史 GUI，已不再是主入口 |
| PyQt / CustomTkinter | 不採用 | 仍會把 GUI 綁回 Python runtime |
| Electron | 不採用 | 對 Windows 桌面工具而言 runtime 偏重 |
| Wails | 已採用 | Go backend 可直接 import `pkg/`，前端用 React/TypeScript |
| Tauri | 未採用 | Rust 生態與既有 Go 遷移方向不合 |

Wails 的實際收益：

- GUI backend 直接呼叫 Go 函式，不需要舊 `go_bridge.py` / `go_api/`。
- 掃描、移動、DB、片商分類能和 CLI 共用 Go 套件。
- 發行目標可以收斂為 Windows portable bundle：`actress-classifier.exe` + `classifier.exe` + Python 搜尋 runtime。
- 前端互動比 Tkinter 更容易維護與擴充。

---

## Go 化優先順序

適合繼續 Go 化：

| 類型 | 例子 | 原因 |
|------|------|------|
| 本機 I/O | 掃描、移動、回滾、衝突處理 | 效能、錯誤處理與 Windows 路徑語意較穩 |
| 資料庫維護 | compact、backup、merge、clean-actresses | 需要單一真實寫入路徑 |
| 規則型解析 | 番號提取、片商前綴、路徑分類 | 規格穩定，適合測試固定 |
| Wails backend 調度 | 批次子程序、DB 快取、事件推送 | GUI 與 Go 套件整合自然 |

不急著 Go 化：

| 類型 | 例子 | 原因 |
|------|------|------|
| HTML 爬蟲解析 | AV-WIKI / JAVDB parser | 網站改版頻繁，Python 調整成本低 |
| 搜尋例外語意 | 反爬、timeout、來源錯誤原因 | 仍在快速演進 |
| pytest 測試 | Python 搜尋與委派層測試 | 與保留的 Python 搜尋 runtime 同步即可 |

---

## 現行語言分工原則

| 職責 | 語言 | 原則 |
|------|------|------|
| Wails GUI backend | Go | 直接使用 `pkg/`，避免再新增 Python GUI 邏輯 |
| Frontend UI | React/TypeScript | 僅透過 Wails bindings 呼叫 backend |
| Go CLI | Go | 提供掃描、移動、DB、片商、快取等非爬蟲能力 |
| Python 搜尋入口 | Python | 僅作為搜尋 / 爬蟲 runtime |
| Python 委派層 | Python | `go_cli.py` 只負責呼叫 `classifier(.exe)` |
| 非爬蟲 fallback | 不保留 | Go 不可用時明確報錯 |

---

## 相關頁面

- [overview.md](overview.md) — 系統架構總覽
- [wails-gui.md](wails-gui.md) — Wails GUI 架構
- [go-bridge.md](go-bridge.md) — Python→Go 委派層
- [search-engine.md](search-engine.md) — 搜尋引擎架構
