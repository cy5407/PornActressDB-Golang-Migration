# 掃描 / 搬移 / 橋接層深入重構方案

更新日期：2026-04-05

## 目的

這份文件是 [04-scan-move-and-bridge.md](./04-scan-move-and-bridge.md) 的深入版，重點不再是「是否值得 Go 化」，而是整理 phase2 之後：

1. 哪些拆層已經落地。
2. 哪些 Python 邏輯已經降為 thin adapter。
3. 哪些缺口還阻止這一區塊完全收斂成 Go-only 核心。

## 本次深入檢閱範圍

已細讀：

- `src/services/go_bridge.py`
- `src/services/go_runner.py`
- `src/services/go_api/scan.py`
- `src/services/go_api/move.py`
- `src/services/go_api/db.py`
- `src/services/go_api/identify.py`
- `src/utils/scanner.py`
- `src/utils/file_mover.py`
- `src/services/go_bridge_test.py`
- `tests/test_scanner_integration.py`
- `cmd/scanner/main.go`
- `pkg/app/*.go`
- `pkg/contracts/*.go`
- `pkg/mover/*.go`
- `pkg/extractor/extractor.go`

## 一句話結論

這一區已經不再是「Python 包一層邏輯，Go 再做一次核心」的雙層模式。  
**目前更接近的真實狀態是：Go 已經是核心，Python 還剩少量 adapter、fallback 與 GUI 對接責任。**

---

## 一、目前已落地的架構調整

### 1. `go_bridge.py` 已從大檔降成 facade

目前 `src/services/go_bridge.py` 只剩：

- 建立 / 持有 `GoCommandRunner`
- re-export 結果型別與 helper
- 將 scan / move / history / db / identify 委派到 `go_api/*`

這表示先前「bridge 混雜 runtime、JSON 容錯、領域 API、DTO」的情況已經明顯改善。

### 2. CLI runtime 已獨立成 `go_runner.py`

`src/services/go_runner.py` 現在集中處理：

- `classifier.exe` 探索
- subprocess 執行
- timeout
- JSON decode / error handling

這個拆層讓 bridge 不再自己管理 subprocess 細節。

### 3. scan / move API 已拆成 domain modules

目前已存在：

- `src/services/go_api/scan.py`
- `src/services/go_api/move.py`
- `src/services/go_api/db.py`
- `src/services/go_api/identify.py`

這代表 Python 端已開始採用「薄 API 模組 + 共用 runner」模型，而不是所有邏輯都塞回 `GoBridge`。

### 4. Go CLI 已接到 `pkg/app` + `pkg/contracts`

目前 `cmd/scanner/main.go` 已是薄入口，主要工作是：

- 解析 flags
- 呼叫 `pkg/app`
- 透過 `pkg/contracts` 輸出契約

scan / move / history 的服務層已分別存在於：

- `pkg/app/scan_service.go`
- `pkg/app/move_service.go`
- `pkg/app/history_service.go`

### 5. `pkg/mover` 已拆檔，不再是單一巨型 `mover.go`

目前 mover 核心已拆為：

- `pkg/mover/file_move.go`
- `pkg/mover/dir_move.go`
- `pkg/mover/batch.go`
- `pkg/mover/history.go`
- `pkg/mover/rollback.go`
- `pkg/mover/types.go`

這代表先前 deep dive 中「Go 核心需要先從單一大檔拆開」的建議已經完成大半。

---

## 二、已完成 / 未完成 / 下一步

## 已完成

- `move -kind dir` 已暴露 `MoveDir`，`FileMover.move_dir()` 已切到 Go 主路徑。
- `move -batch-stdin` 已存在，CLI 可直接從 stdin 吃批次 JSON。
- `scan_with_codes()` 已改成 Go-only，不再回傳 fallback 空 `code`。
- `cmd/scanner/main.go` 已降成薄 CLI 入口，主要流程已搬進 `pkg/app`。
- `pkg/contracts` 已成為 scan / move / history 的契約來源。
- `go_bridge.py` 已從巨型橋接檔拆成 facade + runner + domain APIs。
- `file_mover.py` 與 `scanner.py` 都已接近 thin adapter。

## 未完成

- `go_api/move.py` 還偏大，move / history / rollback 仍可再拆。
- `pkg/mover` 的 `BatchMove` 雖接受 `context.Context`，但取消語意仍不完整。
- scan service 目前也尚未形成明確的 cancel / timeout contract。
- Python fallback 雖已退位，但仍未在所有文件中標記為 degraded mode。
- 目前的 `GoBridge` facade 仍兼任 compatibility layer，尚未完全退場。

## 下一步

1. 先補 `pkg/mover` 的 `ctx.Done()` 檢查、部分完成結果與 cancellation summary。
2. 再把 scan service 的 timeout / cancel 契約補齊，讓 GUI 可直接依賴 Go service。
3. 繼續拆 `go_api/move.py`，讓 bridge / api 邊界更穩定。

---

## 三、逐檔案狀態更新

### A. `src/services/go_bridge.py`

#### 現況

已經不是核心實作檔，而是 compatibility facade。

#### 保留理由

- 舊呼叫點仍可維持穩定介面
- 可漸進式導向 `go_api/*`

#### 剩餘問題

- 還在扮演過渡期入口
- 若 `go_api/*` 繼續成長，應避免再把責任回灌進 bridge

### B. `src/utils/scanner.py`

#### 現況

- `scan_directory()` 仍保留 Go 優先、Python fallback
- `scan_with_codes()` 已明確改為 Go-only

#### 判斷

這已經是合理終態附近，剩下是把 fallback 的地位寫清楚。

### C. `src/utils/file_mover.py`

#### 現況

- `move_file()` / `move_dir()` / `batch_move()` 主路徑都應優先委派 Go
- 檔案已縮到 72 行，顯示 Python 不再保留完整搬移邏輯

#### 判斷

這個檔案已不再是重構熱點，後續只要避免重新膨脹。

### D. `cmd/scanner/main.go`

#### 現況

已完成第一波瘦身，主要 CLI 流程已委派給 `pkg/app`。

#### 剩餘問題

- 未來若要加入進度、timeout、更多模式，仍應優先擴充 service 層，不要再把流程拉回 `main.go`

### E. `pkg/mover/*.go`

#### 現況

檔案拆分已完成，核心能力完整，剩下是長任務治理。

#### 下一個真正有價值的補強

- `BatchMove` / directory operations 的 context cancel
- 部分完成結果契約
- 與 GUI 取消操作對齊的錯誤與狀態模型

---

## 四、最終目標架構

```text
Tkinter GUI / Python Service
        |
        v
 thin adapter / compatibility facade
        |
        v
 Go command runner + go_api/*
        |
        v
 pkg/app services
        |
        v
 pkg/contracts + pkg/mover + pkg/extractor + other Go packages
```

### Python 最終只保留

- GUI 事件處理
- compatibility facade
- fallback / degraded mode
- timeout 與例外轉譯

### Go 最終負責

- 掃描
- 番號提取
- 單檔 / 目錄 / 批次搬移
- 歷史與 rollback
- machine-readable contracts
- 長任務 cancel / partial result 語意

---

## 五、實作結論

這一區塊目前最值得做的，不再是大量「把 Python 換成 Go」，而是補最後那幾個真正會影響 GUI 與長任務體驗的缺口：

1. context cancel
2. timeout / partial result 契約
3. move API 繼續拆薄
4. 文件與 fallback 定位同步

完成這些後，scan / move / bridge 這條線就會真正從「已大幅 Go 化」走到「結構上已收斂完成」。
