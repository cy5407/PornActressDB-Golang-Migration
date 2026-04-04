# Python -> Go/Rust 重構評估總覽

更新日期：2026-04-05

## 目的

本報告將整個專案拆成 6 個區塊，評估各區塊是否適合從 Python 重構為 Golang 或 Rust，並給出建議遷移順序。

其中第 4 區塊（掃描 / 搬移 / 橋接）已在 `refactor/go-migration-phase2` 上有明顯實作進展，相關舊版評估快照已另存於 `docs/archive/refactor-assessment/`，目前請以 04 系列現行文件為準。

這次檢閱的目標不是找語法問題，而是回答三件事：

1. 哪些 Python 程式碼最值得先搬走。
2. 這些程式碼比較適合搬到 Go 還是 Rust。
3. 若想盡量降低 Python 比例，應該怎麼分階段做。

## 本次盤點範圍

以 `*.py` / `*.go` 程式檔粗估：

| 區塊 | 檔案數 | 行數 |
|------|--------|------|
| `src/models` | 9 | 3210 |
| `src/services` | 12 | 6460 |
| `src/scrapers` | 12 | 4087 |
| `src/ui` | 5 | 2166 |
| `src/utils` | 8 | 1623 |
| `pkg` | 14 | 4151 |
| `cmd/scanner` | 2 | 748 |
| `tests` | 14 | 1946 |
| `tools` | 10 | 995 |

## 六個檢閱區塊

1. [01-data-layer.md](./01-data-layer.md)
2. [02-search-and-scrapers.md](./02-search-and-scrapers.md)
3. [03-classification-core.md](./03-classification-core.md)
4. [04-scan-move-and-bridge.md](./04-scan-move-and-bridge.md)
   深入版：[04-scan-move-and-bridge-deep-dive.md](./04-scan-move-and-bridge-deep-dive.md)
5. [05-gui-and-interaction.md](./05-gui-and-interaction.md)
6. [06-tests-and-tooling.md](./06-tests-and-tooling.md)

## 總結結論

### 整體判斷

- 這個專案若要「盡量減少 Python 比例」，**首選應該是 Go，不是 Rust**。
- 理由不是 Rust 不行，而是專案已經有成熟的 Go CLI、Go 套件、Go 測試與 Python 橋接層，繼續往 Go 擴張的成本最低、回收最快。
- Rust 只有在以下兩種情境才比較有吸引力：
  - 你準備做一次完整桌面 GUI 重寫，例如改成 Tauri。
  - 你想把核心邏輯做成長期可重用、高安全、高穩定的本機核心函式庫。

### Go / Rust 適配總覽

| 區塊 | Go 適配度 | Rust 適配度 | 建議 |
|------|-----------|-------------|------|
| 資料層 | 高 | 中 | 直接以 Go 為主，逐步吃掉 Python DB 包裝 |
| 搜尋/爬蟲 | 中高 | 中低 | 先搬網路基礎設施到 Go，解析器分段遷移 |
| 分類核心 | 中高 | 中低 | 將純業務規則搬到 Go，互動流程暫留 Python |
| 掃描/搬移/橋接 | 很高 | 很低 | phase2 已大幅落地，接下來以收斂邊界與 cancel 契約為主 |
| GUI/互動 | 低 | 中 | 短期不要硬搬；若重寫 GUI 才考慮 Rust |
| 測試/工具 | 中 | 低 | 跟著主模組遷移，不要獨立大搬家 |

## 建議遷移順序

### 第一階段：最划算

1. 掃描/搬移/橋接
2. 資料層
3. 分類核心中的純規則部分

### 第二階段：降低 Python 服務層比例

4. 搜尋協調器、快取、重試、rate limit
5. 爬蟲解析器逐站點遷移

### 第三階段：是否真的要脫離 Python GUI

6. GUI 與互動流程整體改寫

## 如果目標是快速把 Python 比例壓低

最務實的策略不是先碰 GUI，而是：

- 先把 Python 變成「薄殼」
- 把 DB、掃描、搬移、片商識別、分類決策、搜尋協調逐步搬到 Go
- 最後只留下 Tkinter GUI、偏好設定、少量流程控制

這條路線可以在不重做桌面應用的前提下，顯著壓低 Python 佔比。
