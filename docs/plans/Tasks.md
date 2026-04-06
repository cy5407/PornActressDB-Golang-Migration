# Wails Migration Tasks

## 模組：GUI主視窗

### 現有實作（Python）
- 檔案：`src/ui/main_gui.py`
- 方法：`UnifiedActressClassifierGUI.__init__`、`setup_ui`、`start_search`、`start_japanese_search`、`start_javdb_search`、`start_shiroutowiki_search`、`start_interactive_move`、`start_standard_move`、`start_smart_search_and_move`、`start_studio_classification`、`show_preferences`、`show_operation_history`
- 邏輯：建立主視窗、管理資料夾選擇與任務按鈕、啟動背景執行緒、顯示結果文字與狀態列、開啟偏好設定與操作歷史對話框。

### 遷移目標（Go/React）
- 方法：Wails binding 提供 `ScanDirectory`、`SearchAndClassify`、`MoveFiles`、`StartStudioClassification`、`OpenPreferences`、`OpenOperationHistory`
- 層層：Go binding / React 主視窗元件 / Wails Events
- 實作檔案：`wails-app/backend/app.go`、`wails-app/frontend/src/App.tsx`、`wails-app/frontend/src/components/MainLayout.tsx`、`wails-app/frontend/src/components/DirectoryPicker.tsx`、`wails-app/frontend/src/components/VideoList.tsx`
- 輸入輸出：輸入為資料夾路徑、搜尋模式、移動策略；回傳為結構化結果、進度事件與錯誤訊息 JSON。

### 驗收標準
- 可在 React 畫面選擇資料夾並觸發掃描/搜尋/移動。
- 任務進行時按鈕狀態與進度條會即時更新。
- 主視窗可正常開啟偏好設定與操作歷史視窗。

### 廃除條件
- `src/ui/main_gui.py`
- 與主視窗流程綁定的舊 Tkinter 啟動邏輯與背景執行緒控制。

## 模組：搜尋結果對話框

### 現有實作（Python）
- 檔案：`src/ui/search_result_dialog.py`
- 方法：`SearchResultDialog.__init__`、`_setup_ui`、`_populate_data`、`_apply_filter`、`_sort_by`、`_show_detail_dialog`、`_export_csv`、`_copy_failed`、`_copy_success`、`_copy_selected`、`show_search_results`
- 邏輯：顯示搜尋結果表格、支援篩選/排序/雙擊詳情、匯出 CSV 與複製番號到剪貼簿。

### 遷移目標（Go/React）
- 方法：Wails binding 提供 `GetSearchResults`、`ExportSearchResultsCSV`；React 提供 `SearchResultDialog`、`SearchResultTable`、`SearchResultDetailModal`
- 層層：Go binding / React Dialog / Wails Event
- 實作檔案：`wails-app/frontend/src/components/SearchResultDialog.tsx`、`wails-app/frontend/src/components/SearchResultTable.tsx`、`wails-app/backend/app.go`
- 輸入輸出：輸入為 `{code, actresses, source, status, studio, triedSources}`；輸出為表格資料、CSV 檔路徑與使用者操作結果。

### 驗收標準
- 可依狀態與關鍵字篩選結果。
- 可點欄位排序、雙擊查看單筆詳情。
- 可匯出 CSV 並複製成功/失敗番號。

### 廃除條件
- `src/ui/search_result_dialog.py`
- 舊有 `show_search_results` 入口與 Tkinter 依賴。

## 模組：操作歷史對話框

### 現有實作（Python）
- 檔案：`src/ui/operation_history_dialog.py`
- 方法：`OperationHistoryDialog.show`、`_connect_with_retry`、`_create_widgets`、`_load_history`、`_show_details`、`_rollback_selected`、`show_operation_history`
- 邏輯：透過 Go CLI 讀取歷史紀錄、顯示操作列表與詳情、執行回滾並重新載入資料。

### 遷移目標（Go/React）
- 方法：Wails binding 提供 `ListOperations`、`GetOperation`、`RollbackOperation`；React 提供 `OperationHistoryDialog`、`OperationHistoryTable`、`RollbackConfirmModal`
- 層層：Go binding / React Dialog / Wails Event
- 實作檔案：`wails-app/backend/app.go`、`wails-app/frontend/src/components/OperationHistoryDialog.tsx`
- 輸入輸出：輸入為查詢限制、操作 ID；輸出為操作日誌、詳情資料與回滾結果 JSON。

### 驗收標準
- 可載入最近 50 筆操作歷史。
- 可查看單筆操作詳情並觸發回滾。
- 回滾完成後列表會更新。

### 廃除條件
- `src/ui/operation_history_dialog.py`
- 舊有 `show_operation_history` 與重試連線邏輯。

## 模組：偏好設定對話框

### 現有實作（Python）
- 檔案：`src/ui/preferences_dialog.py`
- 方法：`PreferenceDialog.__init__`、`setup_dialog`、`_setup_actress_preferences_tab`、`_setup_classification_options_tab`、`_setup_studio_classification_tab`、`_setup_collaboration_tab`、`load_current_preferences`、`add_actress`、`remove_actress`、`remove_collaboration`、`clear_all_collaborations`、`reset_preferences`、`save_preferences`
- 邏輯：管理女優偏好、分類選項、片商分類參數與共演記錄，並寫回設定檔。

### 遷移目標（Go/React）
- 方法：Wails binding 提供 `GetPreferences`、`UpdatePreferences`、`ResetPreferences`、`ListCollaborations`；React 提供 `PreferencesDialog`、`PreferencesTabs`、`PreferencesForm`
- 層層：Go binding / React Dialog / Wails Event
- 實作檔案：`wails-app/frontend/src/components/PreferencesDialog.tsx`、`wails-app/frontend/src/components/PreferencesForm.tsx`、`wails-app/backend/app.go`
- 輸入輸出：輸入為偏好設定物件；輸出為儲存狀態、驗證錯誤與目前設定值。

### 驗收標準
- 可新增/刪除最愛女優與優先女優。
- 可調整片商分類門檻與資料夾名稱。
- 可儲存、重設與重新載入偏好設定。

### 廃除條件
- `src/ui/preferences_dialog.py`
- 舊 Tkinter 偏好設定表單與寫檔流程。

## 模組：Go橋接層

### 現有實作（Python）
- 檔案：`src/services/go_bridge.py`、`src/services/go_runner.py`
- 方法：`GoBridge.__init__`、`_find_exe`、`is_available`、`scan_directory`、`move_file`、`move_dir`、`batch_move`、`list_operations`、`rollback`、`db_get_video`、`db_update_video`、`db_delete_video`、`db_list_videos`、`db_get_stats`、`db_compact_journal`、`db_fix_studios`、`identify_studio`、`identify_studios_batch`、`list_studios`、`get_studio_prefixes`、`GoCommandRunner.run`、`run_json`、`parse_json`
- 邏輯：以 subprocess 呼叫 `classifier.exe`，處理 JSON 解析、錯誤分類、臨時檔清理與可用性檢查。

### 遷移目標（Go/React）
- 方法：完全移除 Python 橋接，改由 Wails 直接 binding 呼叫 Go 後端方法；需要時由 Go 內部直接操作 pkg/ 與 subprocess。
- 層層：Go binding / Go service / Wails Event
- 實作檔案：`wails-app/backend/app.go`、`wails-app/backend/services/*.go`、`wails-app/frontend/src/lib/api.ts`
- 輸入輸出：輸入為原本 bridge 的方法參數；輸出改為 Go struct 或 JSON 可序列化物件。

### 驗收標準
- 所有原本由 `go_bridge.py` 暴露的能力都可由 Wails backend 直接提供。
- 前端不再依賴 `classifier.exe` 的 Python bridge。
- Go CLI/Go service 的錯誤能被前端明確顯示。

### 廃除條件
- `src/services/go_bridge.py`
- `src/services/go_runner.py`
- `src/services/go_api/`

## 模組：爬蟲整合

### 現有實作（Python）
- 檔案：`src/services/go_api/scan.py`、`src/services/go_api/identify.py`、`src/services/go_api/db.py`、`src/services/go_api/move.py`、`src/services/go_api/cache.py`、`src/services/go_api/__init__.py`
- 方法：`scan_directory`、`extract_code`、`identify_studio`、`identify_studios_batch`、`list_studios`、`get_studio_prefixes`、`db_get_video`、`db_update_video`、`db_delete_video`、`db_list_videos`、`db_get_stats`、`db_compact_journal`、`db_fix_studios`、`move_file`、`move_dir`、`batch_move`、`list_operations`、`rollback`、`rollback_last`、`cache_get`、`cache_set`、`cache_delete`、`cache_get_stats`、`cache_prune`、`cache_clear`
- 邏輯：集中包裝 Go CLI 子命令，管理掃描、識別、資料庫、搬移與快取操作。

### 遷移目標（Go/React）
- 方法：Go 端直接實作掃描、識別、資料庫與搬移服務；Python 爬蟲改為獨立 subprocess 入口（例如 `run_search.py`）由 Go 呼叫。
- 層層：Go service / subprocess Python scraper / Wails binding
- 實作檔案：`wails-app/backend/services/scan.go`、`wails-app/backend/services/identify.go`、`wails-app/backend/services/db.go`、`wails-app/backend/services/move.go`、`src/scrapers/run_search.py`
- 輸入輸出：輸入為番號、資料夾、批次項目與快取參數；輸出為 Go struct、JSON 結果與錯誤資訊。

### 驗收標準
- 掃描、片商識別、資料庫與搬移功能可在 Go 後端完成。
- Python 爬蟲可透過 subprocess 取得 JSON 回傳。
- 批次流程與快取操作的結果格式穩定一致。

### 廃除條件
- `src/services/go_api/cache.py`
- `src/services/go_api/db.py`
- `src/services/go_api/identify.py`
- `src/services/go_api/move.py`
- `src/services/go_api/scan.py`
- `src/services/go_api/__init__.py`

## 模組：進度追蹤

### 現有實作（Python）
- 檔案：`src/ui/main_gui.py`
- 方法：`ProgressThrottler.should_update`、`ProgressThrottler.flush`、`SafeGUIUpdater._process_queue`、`SafeGUIUpdater.send_text`、`SafeGUIUpdater.send_error`、`SafeGUIUpdater.send_status`、`update_progress`、`safe_gui_update`、`_insert_text`、`_append_search_summary`、`_show_result_error`
- 邏輯：透過 Queue 與節流器控制 GUI 更新頻率，避免 Tkinter 卡頓並將背景任務進度寫入結果區與狀態列。

### 遷移目標（Go/React）
- 方法：Wails backend 使用 `runtime.EventsEmit` 發送 `progress`、`status`、`error`、`task:done` 事件；React 使用 event hook 更新 store 與進度條。
- 層層：Wails Event / React store / UI ProgressBar
- 實作檔案：`wails-app/backend/app.go`、`wails-app/frontend/src/stores/taskStore.ts`、`wails-app/frontend/src/components/ProgressBar.tsx`
- 輸入輸出：輸入為進度百分比、訊息與任務狀態；輸出為事件 payload 與前端可觀察狀態。

### 驗收標準
- 背景任務可即時推送進度與狀態更新到前端。
- 長時間任務不會凍結 UI。
- 重要訊息與錯誤能在前端被清楚呈現。

### 廃除條件
- `ProgressThrottler`、`SafeGUIUpdater` 與 `main_gui.py` 內的 Tkinter 進度輪詢/after 更新機制。

## 補充：已確認但 Tasks.md 先前漏寫的實作範圍

### 已存在的 Go 核心能力
- `pkg/app/scan_service.go`：`ScanFiles(req ScanRequest)`，實際支援 `Workers` 與 `Recursive` 參數，掃描時僅處理支援格式並回傳 `contracts.ScanResult`。
- `pkg/app/move_service.go`：除單檔與批次移動外，還有 `MoveDir`、`BatchMoveStdin`，且所有搬移都支援 `dryRun` 與 `logDir`。
- `pkg/app/history_service.go`：除 `ListOperations`、`Rollback` 外，還有 `ShowOperation`，對應前端詳情視窗會需要獨立查詢單筆操作。

### Tasks.md 需要補上的細節
- 主視窗的 React 元件清單應補上 `VideoCard`、`SearchPanel`、`StatusBar`，因為它們在計畫文件中已列入核心 UI 組成。
- `ScanDirectory` 的 binding 說明應補上 `workers` 與 `recursive`，否則無法對齊目前 Go 的 `ScanRequest`。
- `MoveFiles` 的設計應明確涵蓋 `MoveDir` 與 `BatchMoveStdin`，避免只寫到單一檔案搬移。
- `OperationHistoryDialog` 的 binding 應補上 `GetOperation` 對應 `ShowOperation`，否則詳情視窗的資料來源不完整。
- 若前端要完整顯示搬移歷史，`RollbackLast` 與 `RollbackOperation` 的差異也應在後續實作說明中分開標註。

### 驗收標準補充
- 掃描可依 `workers` 與 `recursive` 參數切換行為。
- 搬移模組可同時處理單檔、資料夾與 stdin 批次輸入。
- 歷史視窗可獨立查詢單筆操作詳情後再執行回滾。

### 進一步補充：從現有 Python 實作對齊 Wails 的行為細節
- **狀態管理 / 事件對應**：`main_gui.py` 目前是以 `queue.Queue` + `SafeGUIUpdater` 讓背景執行緒把 `TEXT / ERROR / STATUS / CLEAR / CALLBACK` 訊息送回主執行緒；`ProgressThrottler` 會把高頻率訊息節流，並保留 `pending_message` 於下次 flush。Wails 遷移時，React store 至少要拆成「結果文字區」、「狀態列」、「進度條」、「按鈕啟用狀態」四個可觀察狀態，且事件要能區分一般文字、錯誤、清除、狀態更新與需要在 UI 執行緒完成的 callback 類型。
- **錯誤處理 / fallback 行為**：現有流程遇到例外時多半會先 `logger.error(..., exc_info=True)`，再回傳 `{"status": "error", "message": str(e)}`；UI 端則透過 `_show_result_error` 顯示，或在 Go CLI 不可用時直接跳警告。新的 Wails 實作要保留「可恢復則降級、不可恢復才中止」的模式，例如：Go CLI 不可用時給明確 fallback 提示、搜尋失敗時仍需寫入可用的部分結果、背景任務被 stop 時要先輸出中止訊息再結束。
- **進度事件映射**：`web_searcher.batch_search` 目前會輸出 `處理批次 N/M`、`✅ 找到資料`、`⚠️ 搜尋頁面異常 - reason`、`❌ 未找到結果`、`💥 處理失敗 - e`；`process_and_search_cascade` 另外會輸出階段標題、AV-WIKI / 別名 fallback、來源統計與摘要。Wails 前端的 `progress` / `status` / `error` / `task:done` 事件要保留這些層次，並至少區分：批次開始、單筆成功、單筆暫時性異常、單筆失敗、階段切換、摘要完成。
- **Python subprocess 超時與錯誤細節**：`go_runner.py` 目前以 `subprocess.run(..., capture_output=True, text=True, encoding="utf-8", timeout=timeout)` 執行，超時會丟 `GoBridgeError("命令執行超時")`；`returncode != 0` 時會先看 stderr，若包含 `not found / no such / does not exist / 找不到` 則視為 not found，否則視為執行失敗；JSON 解析失敗則回傳含前 200 字輸出的 `GoBridgeJSONError`。若 Wails 仍保留 Python 爬蟲 subprocess，請把 timeout / stderr / JSON parse error 這三種失敗明確帶回前端，避免只顯示泛用「執行失敗」。
