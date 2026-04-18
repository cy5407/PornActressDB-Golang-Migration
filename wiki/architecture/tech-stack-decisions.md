# 技術選型決策紀錄

> 記錄為什麼選擇特定語言/框架，以及未來潛在的升級路線。
> 更新：2026-04-07

---

## 爬蟲層：為什麼保留 Python

### 競爭者比較

| 語言 | 代表框架 | 優勢 | 劣勢 |
|------|---------|------|------|
| **Python**（現在） | BeautifulSoup / Playwright | 生態最成熟、日文編碼支援好、快速開發 | 速度慢 |
| Node.js | Puppeteer / Playwright / Cheerio | JS 執行最原生（SPA 網站）、async 天然 | 日文處理沒 Python 方便 |
| Go | Colly / Rod | 速度快、並發強 | HTML 解析不如 Python 方便、生態小 |
| Rust | reqwest + scraper | 最快、記憶體安全 | 開發慢、生態極小 |

### 結論

本專案爬取 AV-WIKI / JAVDB（**日文靜態 HTML 頁面**），Python 仍是最佳選擇：

- **日文編碼**（Shift_JIS / EUC-JP / UTF-8）處理：`chardet` + `BeautifulSoup` 最成熟
- **靜態 HTML**：不需要 JS 渲染，Playwright 殺雞用牛刀
- **快速迭代**：爬蟲常需要因網站改版調整，Python 開發速度快
- **Go Colly** 雖然快，但 CSS selector / XPath 解析遠不如 BeautifulSoup 方便

> 若未來需要爬取 SPA（React/Vue 動態頁面），可考慮 Node.js + Playwright。

---

## GUI 層：為什麼保留 Python Tkinter

### 競爭者比較

| 選項 | 語言 | 優勢 | 劣勢 |
|------|------|------|------|
| **Tkinter**（現在） | Python | 內建零安裝、與爬蟲共用 Python 環境 | 介面較舊、2000 年代風格 |
| PyQt6 / PySide6 | Python | 介面現代、仍是 Python | 需額外安裝、授權問題 |
| CustomTkinter | Python | Tkinter 改良版現代風格 | 仍是 Tkinter 基底 |
| Electron | Node.js + HTML/CSS | 介面漂亮、Web 技術 | 記憶體佔用高（200MB+） |
| **Wails** | **Go + HTML/CSS** | **與本專案 Go 架構整合最自然、輕量** | 前端仍需 HTML/JS |
| Tauri | Rust + HTML/CSS | 極輕量（~10MB）、快 | 需要 Rust 知識 |

### 結論（當前）

Tkinter 保留理由：
- 整個應用程式已用 Python，共用環境，不增加複雜度
- PyInstaller 打包成單一 .exe 已成熟（42MB）
- 介面功能滿足需求，不值得大規模重寫

---

## 未來升級路線（長期規劃）

### 最理想方向：Wails（Go-based GUI）

```
現在架構：
  Python Tkinter GUI
       ↓
  Python 業務邏輯 + 爬蟲
       ↓
  Go 橋接層 (go_api/)
       ↓
  Go CLI (classifier.exe)

目標架構：
  Wails GUI (HTML/CSS/JS 前端)
       ↓（直接呼叫 Go 函數，不需橋接）
  Go 後端（含現有 pkg/ 全部功能）
       ↓（子進程）
  Python 爬蟲服務（僅保留爬蟲部分）
```

**Wails 優勢**：
- GUI 直接呼叫 Go 函數，整個 Python 橋接層（`go_api/`, `go_bridge.py`）可以消失
- 打包成單一 `.exe`，比 PyInstaller 更乾淨
- 介面用現代 HTML/CSS，可以很漂亮
- Go 生態，與現有 `pkg/` 完全整合

**代價**：
- 需要重寫整個 GUI（~2,240 行 Python UI 代碼）
- 爬蟲仍需以 Python 子服務形式存在（HTTP API 或 subprocess）
- 工程量大，估計 3-6 個月全職開發

### 短期可做的 GUI 改善

若不想大規模重寫，可考慮：
- `CustomTkinter`：以最小改動讓現有 Tkinter 介面現代化
- `PyQt6`：遷移成本中等，介面品質大幅提升

---

## Python 無法被取代的部分（長期保留）

| 模組 | 行數 | 原因 |
|------|------|------|
| 爬蟲層 `scrapers/` | ~3,947 | 日文 HTML 解析、BeautifulSoup 生態 |
| GUI `ui/` | ~2,240 | Tkinter（除非 Wails 重寫） |
| 搜尋協調 `services/web_searcher.py` | ~1,119 | 爬蟲業務邏輯 |
| 測試 `tests/` | ~3,536 | pytest 測試套件 |

> 即使完成所有 Go 遷移，Python 仍會保留約 **10,000+ 行**（爬蟲 + GUI + 測試）。
> Go 負責效能敏感的後端（檔案操作、資料庫、識別），Python 負責網路與介面。

---

## 語言分工原則（確立於 Phase 10 後）

| 職責 | 語言 | 理由 |
|------|------|------|
| 檔案掃描 / 移動 | **Go** | 並發 I/O，速度 10-20x |
| 資料庫讀寫 | **Go** | 低延遲，速度 1,300x |
| 番號提取 / 片商識別 | **Go** | 正則引擎效能 |
| HTTP 爬蟲 / 解析 | **Python** | 生態成熟、日文支援 |
| GUI | **Python** | Tkinter 現有投資 |
| 搜尋流程協調 | **Python** | 業務邏輯，可讀性優先 |
| 測試 | **Python** | pytest 生態 |
