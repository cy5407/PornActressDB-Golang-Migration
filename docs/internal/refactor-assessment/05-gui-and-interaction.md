# 區塊 5：GUI 與互動流程評估

## 本次檢閱範圍

已檢閱：

- `src/ui/main_gui.py`
- `src/ui/search_result_dialog.py`
- `src/ui/preferences_dialog.py`
- `src/ui/operation_history_dialog.py`
- `src/services/interactive_classifier.py`

## 這個區塊在做什麼

- Tkinter 主視窗
- 偏好設定
- 搜尋結果預覽
- 操作歷史視窗
- 多女優互動選擇 dialog
- GUI 執行緒安全更新

## 現況判斷

這一區塊是目前 Python 不容易快速拿掉的主要原因。

原因不是它太大，而是它依賴：

- Tkinter
- `root.after()`
- queue-based GUI message pump
- 對話框與 callback
- 本機桌面狀態管理

這些都不是單純把函式翻成另一種語言就能完成。

## 是否適合重構成 Golang

**判定：短期不適合，長期可做但屬於產品級重寫**

若改 Go GUI，通常不是「重構」，而是改成另一套桌面框架，例如：

- Wails
- Fyne

這會牽涉：

- 整個 UI 結構重做
- 事件模型重做
- 視窗與對話框流程重做

## 是否適合重構成 Rust

**判定：短期也不適合，但若未來要重寫 GUI，Rust 比 Go 更值得評估**

若有一天你決定完全重做桌面應用，Rust 的可能路線是：

- Tauri + Web UI
- Rust 核心 + 前端界面

這種情境下 Rust 的吸引力比 Go 高，因為桌面應用生態相對更成熟。

但要注意：這已經不是降低 Python 比例的「快速工程」，而是產品重建。

## 建議結論

### 短期

- 不要優先搬 GUI
- 讓 GUI 留在 Python
- 把背後的核心邏輯越搬越薄

### 長期

- 若未來要完全脫離 Python，可考慮整體改成 Rust/Tauri
- 若偏好全 Go，可評估 Wails，但會是另一個 UI 架構

## 建議遷移邊界

短期應保留 Python 的部分：

- 視窗與對話框
- 使用者互動
- 進度顯示
- 執行緒安全 GUI 更新

可逐步抽離的部分：

- dialog 背後的決策資料結構
- GUI 使用的任務狀態模型
- GUI 觸發的核心操作 API

## 建議優先度

**優先度：P3**

除非你已經決定重寫桌面應用，否則這不是降低 Python 比例的第一優先。

