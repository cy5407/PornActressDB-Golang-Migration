# 區塊 4：掃描、搬移與橋接層評估

更新日期：2026-04-05

## 本次檢閱範圍

已檢閱：

- `src/services/go_bridge.py`
- `src/services/go_runner.py`
- `src/services/go_api/scan.py`
- `src/services/go_api/move.py`
- `src/utils/scanner.py`
- `src/utils/file_mover.py`
- `cmd/scanner/main.go`
- `pkg/app/scan_service.go`
- `pkg/app/move_service.go`
- `pkg/app/history_service.go`
- `pkg/contracts/scan.go`
- `pkg/contracts/move.go`
- `pkg/contracts/history.go`
- `pkg/mover/*.go`
- `pkg/extractor/extractor.go`

舊版 phase1 評估快照已保存到：

- `docs/archive/refactor-assessment/2026-04-05-scan-move-bridge-pre-phase2-refresh/`

## 這個區塊在做什麼

- 掃描資料夾並提取番號
- 單檔 / 目錄 / 批次搬移
- 操作歷史與回滾
- Python 對 Go CLI 的 adapter 與 runtime bridge

## 現況判斷

這一區塊仍然是整個專案中 **最接近 Go-only 核心** 的部分，而且 phase2 已經把「Python 大檔包住 Go」的型態明顯收斂。

代表檔案現況：

- `src/services/go_bridge.py`：116 行，已縮成 facade
- `src/services/go_runner.py`：54 行，負責 subprocess / JSON runner
- `src/services/go_api/move.py`：310 行，集中搬移 / 歷史 API
- `src/services/go_api/scan.py`：37 行，集中掃描 API
- `src/utils/file_mover.py`：72 行，已是 thin adapter
- `src/utils/scanner.py`：42 行，已是 thin adapter
- `cmd/scanner/main.go`：242 行，已轉成薄 CLI 入口
- `pkg/app/*.go`：72 / 112 / 75 行，承接 scan / move / history service
- `pkg/contracts/*.go`：輸出契約已獨立
- `pkg/mover/*.go`：已從單一 `mover.go` 拆成多檔

## 是否適合重構成 Golang

**判定：非常適合，且已進入收尾式重構階段。**

理由：

1. 核心流程已經主要在 Go，Python 現在多數只剩 adapter、fallback 與 GUI 對接。
2. CLI contract、service 層、mover 模組拆分都已經落地，不再只是規劃。
3. 剩餘工作大多是邊界收斂，而不是重新設計整個功能。

## 是否適合重構成 Rust

**判定：仍不建議。**

目前這一區已經有完整的 Go contracts、service、CLI 與 Python bridge。  
若改成 Rust，會是重建既有成熟能力，而不是補齊缺口。

## 已完成

- `GoBridge` 已拆出 runner 與 domain API，bridge 本體不再承擔所有責任。
- `scan` / `move` / `history` CLI 已接到 `pkg/app` service 層。
- `pkg/contracts` 已成為 scan / move / history 輸出契約來源。
- `move -kind dir` 已正式暴露 `MoveDir`。
- `move -batch-stdin` 已存在，Python 不再只能靠暫存 JSON 檔。
- `FileMover.move_dir()` 已改成 Go 主路徑，Python 只留 fallback。
- `scan_with_codes()` 已明確收斂為 Go-only 能力。
- `pkg/mover` 已拆成 `file_move.go`、`dir_move.go`、`batch.go`、`history.go`、`rollback.go`、`types.go`。

## 未完成

- `go_api/move.py` 仍偏大，搬移 / 歷史 / rollback 還可再分模組。
- 掃描與批次搬移的 context cancel 語意尚未完整落到 Go 核心。
- Python fallback 還存在，但文件上應明確標示為 degraded / emergency mode。
- CLI 的 stdout/stderr 契約雖已大幅收斂，仍需持續避免新命令回到混合輸出。

## 下一步

1. 補齊 `pkg/mover` 與 scan service 的 `ctx.Done()` 取消語意與 partial result 契約。
2. 繼續拆薄 `src/services/go_api/move.py`，把 move / history / rollback 分成更清楚的小模組。
3. 把 Python fallback 的定位正式寫成 emergency mode，避免再把新功能加回 Python 主路徑。

## 建議結論

這一區塊已不再是「要不要 Go 化」的問題，而是「如何把剩餘邊界完全收乾淨」。  
因此它仍是 **P0 優先區塊**，但工作性質已從大規模搬移轉成：

- contract 固化
- adapter 繼續變薄
- cancel / error model 補齊
- fallback 降格與文件同步
