# 掃描 / 搬移 / 橋接層：完整重構執行計劃

建立日期：2026-04-04
依據文件：[04-scan-move-and-bridge-deep-dive.md](./04-scan-move-and-bridge-deep-dive.md)

---

## 目標

將目前「Python 包邏輯 + Go 再做核心」的雙層模式，收斂成：

> **Go = 唯一核心實作，Python = 極薄 adapter + GUI 對接**

---

## 現況數字

| 檔案 | 行數 | 問題嚴重度 |
|---|---|---|
| `src/services/go_bridge.py` | **934 行** | 🔴 最肥，5 種責任混雜 |
| `src/utils/file_mover.py` | **549 行** | 🔴 Python / Go 雙份實作並存 |
| `cmd/scanner/main.go` | **760 行** | 🟡 CLI 夾雜業務邏輯 |
| `pkg/mover/mover.go` | **666 行** | 🟡 核心正確但需拆模組 |
| `src/utils/scanner.py` | **185 行** | 🟢 相對薄，但有雙模式 API 問題 |

---

## 最優先的 5 個行動（按效益排序）

| 優先順序 | 行動 | 預估可刪 Python 行數 |
|---|---|---|
| 1 | CLI 新增 `move -kind dir`，`file_mover.move_dir()` 改走 Go | ~75 行 |
| 2 | 刪掉 `_move_with_go()` 裡的重複建目錄 | ~5 行（消除重複責任） |
| 3 | 規範 Go CLI stdout 純 JSON，刪 `_parse_json_from_output()` | ~30 行 |
| 4 | 拆解 `go_bridge.py` 成 runner + domain api | 934 行 → 5 個薄檔 |
| 5 | `pkg/mover/mover.go` 補齊 context cancel | Go 端補強，非刪 Python |

---

## 階段 1：清責任邊界（不動功能，先拆層）

**原則：零功能改動，只搬位置。**

### 目前進度（2026-04-04）

- [x] `GoBridge.batch_move()`、`get_operation()`、`rollback()` 已改為直接解析純 JSON stdout，不再容忍混合輸出。
- [x] `go_bridge` 單元測試已更新為純 JSON 契約，並新增混合 stdout 視為契約違反的測試。
- [x] `list_operations()` 已移除舊版表格輸出 fallback，改為只接受 `history list -json` 的純 JSON 輸出。
- [x] `cache prune` / `cache clear` 的狀態提示已移到 `stderr`，保留 `stdout` 給 JSON 結果。
- [x] `cmd/scanner/main.go` 內兩個既有 `printError` 編譯錯誤已修正，`go test ./cmd/scanner/...` 可通過。
- [x] `db update` / `db delete` / `db compact` 已新增 `-json` 成功輸出模式，Python bridge 也已切換為使用此契約。
- [x] `go_bridge` 資料庫 helper 測試已覆蓋 `-json` 呼叫與成功回應解析。
- [x] `identify -list` / `identify -prefixes` 已新增 `-json` 輸出模式，Python bridge 不再依賴字串切割解析。
- [x] `cache` 無子命令時的說明文字已改走 `stderr`，避免與未來 machine-readable stdout 混用。
- [x] 已新增 [`src/services/go_runner.py`](./../../src/services/go_runner.py) 作為 CLI 執行與 JSON 解析共用層，`GoBridge` 已開始用組合方式接它。
- [x] `GoBridge.scan_directory()`、`move_file()`、`get_operation()` 等路徑已改用 runner 的 `run_json()` / `parse_json()`，bridge 本體責任開始變薄。
- [x] 已新增 [`src/services/go_api/db.py`](./../../src/services/go_api/db.py) 與 [`src/services/go_api/identify.py`](./../../src/services/go_api/identify.py)，`db_*` / `identify_*` 家族已從 `go_bridge.py` 搬出。
- [x] `go_accelerated_db.py` / `go_accelerated_studio.py` 已開始直接依賴新的 `go_api` 模組，而不是全部繞經 `go_bridge.py`。
- [ ] CLI 其餘命令的人類訊息與 JSON 輸出路徑尚未全面盤點。

### 下一步

下一個最小步驟是繼續拆 `scan/move/history` 這條線，優先考慮建立 `go_api/move.py` 或等價模組，把 `batch_move` / `rollback` / `list_operations` 的組裝與轉換搬出 `GoBridge`，讓 class 本體更接近 runtime facade。

### 1-A：拆解 `go_bridge.py`（934 行 → 多個薄檔）

目前 `go_bridge.py` 同時承擔 5 種責任，拆分目標：

```
src/services/
  go_runtime.py       ← 找 classifier.exe、檢查可用性、快取結果
  go_runner.py        ← subprocess 執行、timeout、JSON decode
  go_api/
    scan.py           ← scan_directory() 領域 API
    move.py           ← move_file() / batch_move() / rollback() 領域 API
    db.py             ← db_* 家族
    identify.py       ← identify_* 家族
```

對應關係：

| 現有位置 | 移到 |
|---|---|
| `_find_exe()` | `go_runtime.py` |
| `_run_subprocess()` | `go_runner.py` |
| `_parse_json_from_output()` | `go_runner.py`（最終刪除，見 1-B） |
| `ScanResult` / `MoveResult` 等 dataclass | 逐步改成 `dict`（見 1-C） |
| `scan_directory()` | `go_api/scan.py` |
| `move_file()` / `batch_move()` / `rollback()` | `go_api/move.py` |
| `db_*` 家族 | `go_api/db.py` |
| `identify_*` 家族 | `go_api/identify.py` |

### 1-B：規範 Go CLI 輸出格式

**規則：**
- `stdout`：永遠只輸出一個完整 JSON 物件
- `stderr`：人類可讀訊息、進度、log

**影響：** Python 端的混合輸出容錯邏輯（`_parse_json_from_output()`）可完全刪除。

**需修改的 Go 檔案：** `cmd/scanner/main.go` — 確認所有命令的輸出路徑都只走 `outputJSON()`，任何非結構化訊息改到 `stderr`。

### 1-C：建立 Go 端 contracts（輸出 schema 真相來源）

新增目錄 `pkg/contracts/`：

```
pkg/contracts/
  scan.go      ← ScanResult struct
  move.go      ← MoveResult, BatchResult struct
  history.go   ← OperationLog struct
```

Python 端的四個 dataclass（`ScanResult`、`MoveResult`、`BatchMoveResult`、`OperationLog`）改為直接使用 `dict`，逐步廢棄。

---

## 階段 2：目錄搬移與批次輸入徹底 Go 化

**目標：刪掉 `file_mover.py` 最肥的幾段 Python。**

### 2-A：CLI 暴露 `MoveDir`（高優先度）

Go 的 `pkg/mover/mover.go:212` `MoveDir()` 已完整實作，但 CLI 未暴露。

新增 CLI 命令：

```bash
# 方案 A：擴充現有 move 命令
classifier.exe move -kind dir -src <dir> -dst <dir> -strategy skip

# 方案 B：獨立命令（更清楚）
classifier.exe move-dir -src <dir> -dst <dir> -strategy skip
```

**建議選方案 A**，維持命令一致性。

修改 `cmd/scanner/main.go` 的 `moveCmd()`，偵測 `-kind dir` 後呼叫 `mover.MoveDir()`。

### 2-B：`FileMover.move_dir()` 改走 Go 主路徑

`file_mover.py:241-315` 的 `move_dir()` 現有完整 Python 邏輯（逐檔迭代、衝突處理、建目錄），全部是 Go 已有能力。

**重構後：**

```python
def move_dir(self, src: str, dst: str, strategy: str = "skip") -> dict:
    """搬移整個目錄，委派 Go 核心處理"""
    if self.go_bridge.is_available:
        return self._go_move_api.move_dir(src, dst, strategy)
    # fallback：保留最小 Python 應急版本
    return self._move_dir_python_fallback(src, dst, strategy)
```

### 2-C：支援 `batch-stdin`（中期）

目前 `batch_move()` 需要先把 JSON 寫成暫存檔，再傳給 CLI。

建議 Go CLI 支援：

```bash
classifier.exe move -batch-stdin
```

Python 端改成直接 pipe stdin，不再需要落地暫存檔。

**修改 `cmd/scanner/main.go` 的 `moveCmd()`**：偵測 `-batch-stdin` flag，從 `os.Stdin` 讀取 JSON。

### 2-D：刪掉 `_move_with_go()` 的重複建目錄

`file_mover.py:187-221` 的 `_move_with_go()` 在呼叫 Go 前先執行：

```python
if create_dirs:
    destination.parent.mkdir(parents=True, exist_ok=True)
```

Go `MoveFile()` 已自己建目錄，這段直接刪除。

若 `create_dirs=False` 是真實需求，應變成 Go API 的顯式選項，而非 Python 本地行為。

---

## 階段 3：掃描變成真正的 Go service

### 3-A：抽出 Go service 層

目前 `cmd/scanner/main.go` 的 `scanCmd()`（第 100-230 行）既解析 flag 又跑掃描流程。

新增：

```
pkg/app/
  scan_service.go      ← 純掃描服務，接受 ScanRequest，回傳 []contracts.ScanResult
  move_service.go      ← 純搬移服務
  history_service.go   ← 純歷史查詢服務
```

`main.go` 只做：**旗標解析 → 呼叫 service → 呼叫 `outputJSON()`**

### 3-B：`scan_with_codes()` 明確 Go-only

`scanner.py:143-164` 的 `scan_with_codes()` 在 fallback 模式下回傳 `code: ""`，導致同一個 API 兩種語義。

**作法：**

```python
def scan_with_codes(self, path: str, recursive: bool = True) -> list[dict]:
    """Go-only capability：掃描並提取番號。Go 不可用時拋出明確錯誤。"""
    if not self.go_bridge.is_available:
        raise RuntimeError("scan_with_codes 需要 Go CLI，目前不可用")
    return self._go_scan_api.scan_with_codes(path, recursive)
```

### 3-C：補齊 `BatchMove` context cancel 語意

`pkg/mover/mover.go:283` 的 `BatchMove(ctx, ...)` 雖接受 `ctx`，但幾乎沒有用到。

補齊：

```go
for _, item := range items {
    select {
    case <-ctx.Done():
        return partialResult(results, "cancelled")
    default:
    }
    // 處理 item...
}
```

這讓 GUI 的「取消批次操作」改由 Go 控制，不再需要 Python 在外層強制殺 subprocess。

---

## 階段 4：Python 只剩 GUI adapter（終態）

### `src/utils/scanner.py` 終態（目標 < 60 行）

```python
class UnifiedFileScanner:
    def scan_directory(self, path: str, recursive: bool = True) -> list[Path]:
        return self._go_scan_api.scan(path, recursive)

    def scan_with_codes(self, path: str, recursive: bool = True) -> list[dict]:
        # Go-only，不可用時明確拋錯
        return self._go_scan_api.scan_with_codes(path, recursive)

    @classmethod
    def from_config(cls, config) -> "UnifiedFileScanner":
        ...
```

### `src/utils/file_mover.py` 終態（目標 < 80 行）

```python
class FileMover:
    def move_file(self, src, dst, strategy="skip") -> dict:
        return self._go_move_api.move_file(src, dst, strategy)

    def move_dir(self, src, dst, strategy="skip") -> dict:
        return self._go_move_api.move_dir(src, dst, strategy)

    def batch_move(self, items, strategy="skip") -> dict:
        return self._go_move_api.batch_move(items, strategy)

    def rollback(self, operation_id=None) -> dict:
        return self._go_move_api.rollback(operation_id)

    def list_operations(self, limit=10) -> list[dict]:
        return self._go_move_api.list_operations(limit)
```

### `src/services/go_bridge.py` 終態

不再是 934 行大檔，分裂成多個小型 adapter（見階段 1-A）。

---

## Go 目錄最終結構

```
pkg/
  contracts/          ← 新增：輸出入 schema（Go 是真相來源）
    scan.go
    move.go
    history.go

  app/                ← 新增：命令用服務層（main.go 業務邏輯移到這）
    scan_service.go
    move_service.go
    history_service.go

  moveops/            ← 新增：從 mover.go 拆出
    file_move.go
    dir_move.go
    batch.go
    rollback.go
    history_store.go

  runtime/            ← 新增：CLI 共用工具
    jsonio.go         （outputJSON 移到這）
    exitcodes.go

  mover/              ← 現有，重構後只留 Mover struct 與組合邏輯
  extractor/          ← 現有，已是好樣板，不動
  database/           ← 現有，不動
  cache/              ← 現有，不動
  studio/             ← 現有，不動
```

---

## 哪些 Python 邏輯不應繼續擴充

| Python 邏輯 | 處置方式 |
|---|---|
| Python 掃描能力（`_scan_with_python()`） | 降格為 emergency fallback，停止擴充 |
| Python 搬移能力（`_move_with_python()`、`_batch_move_with_python()`） | 降格為 emergency fallback，停止擴充 |
| Python 端輸出語義修補（`_parse_json_from_output()`） | 直接刪除（前提：Go CLI stdout 規範完成） |
| Python 端 DTO dataclass | 逐步改成 `dict`，最終移除 |

---

## 哪些 Python 應繼續留著（不搬到 Go）

| Python 邏輯 | 理由 |
|---|---|
| `classifier.exe` 路徑探索 | 和 Python 環境綁定，搬到 Go 多此一舉 |
| subprocess 啟動與 timeout 設定 | 同上 |
| GUI 需要的例外訊息轉換 | 和 tkinter 事件循環綁定 |

---

## 重構完成指標

- [ ] `go_bridge.py` 行數 < 100 行（或已拆分，單一檔案不超過 150 行）
- [ ] `file_mover.py` 行數 < 80 行
- [ ] `scanner.py` 行數 < 60 行
- [ ] `cmd/scanner/main.go` 行數 < 400 行
- [ ] `pkg/mover/mover.go` 已拆成 `pkg/moveops/` 各子檔案
- [ ] Go CLI 所有命令 stdout 均為純 JSON
- [ ] `MoveDir` 已透過 CLI 暴露
- [ ] `BatchMove` 支援 context cancel 取消語意
- [ ] Go `pkg/contracts/` 目錄存在且被 CLI 使用
- [ ] Python 端無任何掃描或搬移的核心實作（只保留 fallback 標記）
