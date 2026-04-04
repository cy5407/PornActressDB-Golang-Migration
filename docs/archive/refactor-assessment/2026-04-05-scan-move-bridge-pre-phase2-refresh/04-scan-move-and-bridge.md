# 區塊 4：掃描、搬移與橋接層評估

## 本次檢閱範圍

已檢閱：

- `src/services/go_bridge.py`
- `src/utils/scanner.py`
- `src/utils/file_mover.py`
- `pkg/extractor/extractor.go`
- `pkg/mover/mover.go`
- `pkg/cache/cache.go`
- `pkg/studio/identifier.go`
- `cmd/scanner/main.go`

## 這個區塊在做什麼

- 掃描資料夾並提取番號
- 單檔/批次檔案移動
- 操作歷史與回滾
- Python 對 Go CLI 的 subprocess 橋接

## 現況判斷

這是整個專案中 **最明顯已經 Go 化** 的區塊。

代表檔案：

- `src/services/go_bridge.py` 約 838 行
- `src/utils/file_mover.py` 約 533 行
- `cmd/scanner/main.go` 約 643 行
- `pkg/mover/mover.go` 約 576 行
- `pkg/extractor/extractor.go` 已是核心番號提取實作

Python 在這一區塊很多時候只是：

- 啟用 / fallback 控制
- 結果格式轉換
- 錯誤訊息包裝

## 是否適合重構成 Golang

**判定：非常適合，而且應該優先完成**

理由：

1. 掃描、搬移、歷史回滾都屬於檔案 I/O 與並行工作，Go 非常合適。
2. 專案已有成熟 Go 版本。
3. Python 與 Go 目前存在一部分重複邏輯，可以進一步收斂。

## 是否適合重構成 Rust

**判定：不建議**

不是 Rust 做不到，而是這一區塊已經投入了大量 Go 基礎建設。  
若改成 Rust，幾乎是把現有優勢全部重做一遍。

## 建議結論

這一區塊應該直接定調為 **Go-only 核心區**。

## 建議遷移邊界

下一步可做的不是「再評估」，而是直接收斂：

- 把掃描與搬移的 Python fallback 盡量降到最薄
- 讓 Python 只保留 adapter
- 將更多批次流程直接交給 Go CLI 或 Go service
- 把目前 bridge 中與命令列參數對應的邏輯收斂成更穩定的 API

## 遷移風險

- `go_bridge.py` 目前仍承擔不少命令組裝、JSON 解析、timeout 控制
- 若 CLI 介面持續擴大，Python bridge 會繼續變肥
- 建議中長期從「subprocess + JSON stdout」走向更穩定的 RPC 或更完整的命令模型

## 建議優先度

**優先度：P0**

如果你要優先大幅減少 Python 比例，這裡是第一站。

