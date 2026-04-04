# 掃描 / 搬移 / 橋接層：完整重構執行計劃

更新日期：2026-04-05  
基底分支：`refactor/go-migration-phase2`

依據文件：[04-scan-move-and-bridge-deep-dive.md](./04-scan-move-and-bridge-deep-dive.md)

---

## 目標

將掃描 / 搬移 / 橋接層收斂成：

> **Go = 唯一核心實作，Python = thin adapter / compatibility facade / degraded fallback**

這份文件不再記錄 phase1 的舊估算，而是直接對齊目前 `refactor/go-migration-phase2` 的真實狀態。

---

## 現況快照

| 檔案 | 目前行數 | 目前角色 |
|---|---:|---|
| `src/services/go_bridge.py` | 116 | facade / compatibility layer |
| `src/services/go_runner.py` | 54 | CLI runtime / JSON runner |
| `src/services/go_api/move.py` | 310 | 搬移 / 歷史 API |
| `src/services/go_api/scan.py` | 37 | 掃描 API |
| `src/utils/file_mover.py` | 72 | thin adapter |
| `src/utils/scanner.py` | 42 | thin adapter |
| `cmd/scanner/main.go` | 242 | CLI 入口 |
| `pkg/app/move_service.go` | 112 | move service |
| `pkg/app/scan_service.go` | 72 | scan service |
| `pkg/app/history_service.go` | 75 | history service |

---

## 已完成

### P0：CLI 輸出契約與 bridge 拆層

- [x] `cmd/scanner/main.go` 已轉為薄 CLI 入口。
- [x] `pkg/contracts/scan.go`、`move.go`、`history.go` 已建立並使用。
- [x] `pkg/app/scan_service.go`、`move_service.go`、`history_service.go` 已建立並接上 CLI。
- [x] `src/services/go_runner.py` 已建立，集中 subprocess / timeout / JSON 執行責任。
- [x] `src/services/go_api/scan.py`、`move.py`、`db.py`、`identify.py` 已建立。
- [x] `src/services/go_bridge.py` 已縮成 facade，scan / move / history / db / identify 已主要委派到 `go_api/*`。

### P0：目錄搬移與批次輸入 Go 化

- [x] `move -kind dir` 已正式暴露 `MoveDir`。
- [x] `FileMover.move_dir()` 已改走 Go 主路徑。
- [x] `_move_with_go()` 的 Python 前置建目錄責任已移除，改由 Go mover 單一負責。
- [x] `move -batch-stdin` 已存在，可直接從 stdin 讀取批次 JSON。

### P0：scanner Go-only 化

- [x] `scan_with_codes()` 已明確改為 Go-only capability。
- [x] `scanner.py` 已縮成薄 adapter；Python fallback 不再承擔完整主流程責任。

### P1：Go service / mover 拆分

- [x] `pkg/mover` 已由單檔拆成 `file_move.go`、`dir_move.go`、`batch.go`、`history.go`、`rollback.go`、`types.go`。
- [x] `main.go` 的主要業務責任已下沉到 `pkg/app/*`。

---

## 未完成

### P1：context cancel 與長任務契約

- [ ] `pkg/mover` 的 `BatchMove` 尚未完整落實 `ctx.Done()` 取消語意。
- [ ] directory move 與其他長任務尚未明確定義 cancellation / partial result 契約。
- [ ] scan service 尚未補齊可由 GUI 直接依賴的 timeout / cancel 模型。

### P1：Python 邊界再收斂

- [ ] `src/services/go_api/move.py` 仍偏大，move / history / rollback 可再拆分。
- [ ] `GoBridge` 仍是 compatibility layer，尚未完全退場。
- [ ] fallback 雖已退位，但文件與註解上還沒全面統一成 degraded / emergency mode。

### P2：文件與測試補強

- [ ] 補齊針對 cancel / partial result 的 Go 測試。
- [ ] 補齊 Python 端 thin adapter 的整合測試敘述與文件同步。
- [ ] 盤點 CI 對 scan / move / history contract 的覆蓋缺口。

---

## 下一步

1. 先在 `pkg/mover/batch.go` 補 `ctx.Done()` 檢查與 cancellation summary。
2. 再把 scan service 的 timeout / cancel 契約補進 `pkg/app/scan_service.go` 與 CLI。
3. 最後拆薄 `src/services/go_api/move.py`，把 move / history / rollback 分開，讓 bridge 進一步退化成 compatibility facade。

---

## 建議執行順序

### 第 1 步：補 cancel 契約

目標：

- GUI 能安全取消長時間批次搬移
- Go 回傳部分完成結果，而不是只有失敗 / 成功二元狀態

優先修改：

- `pkg/mover/batch.go`
- `pkg/app/move_service.go`
- `pkg/contracts/move.go`

### 第 2 步：補 scan timeout / cancel

目標：

- 掃描大目錄時能以 Go service 為中心治理 timeout / cancel

優先修改：

- `pkg/app/scan_service.go`
- `cmd/scanner/main.go`
- `pkg/contracts/scan.go`

### 第 3 步：繼續拆薄 Python move API

目標：

- `go_api/move.py` 不再同時承擔 move / history / rollback 三種責任

優先修改：

- `src/services/go_api/move.py`
- 視需要新增 `src/services/go_api/history.py`

---

## 完成指標

- [ ] `BatchMove` 支援 context cancel，且有明確 partial result schema
- [ ] scan service 支援 timeout / cancel，且 CLI / Python adapter 契約一致
- [ ] `go_api/move.py` 再拆分，bridge / api 邊界清楚
- [ ] Python fallback 在文件與程式中統一標示為 degraded / emergency mode
- [ ] 04 系列文件與 repo 現況持續同步，不再混用舊版 phase1 數字
