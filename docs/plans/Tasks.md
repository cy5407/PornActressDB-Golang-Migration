# Wails Migration Tasks

> 此文件為規格書 + 執行追蹤二合一。每完成一項請勾選對應的 checkbox。

---

## W8 同名女優資料夾合併語意修正（待實作）

> 2026-04-08 新澄清：同名女優資料夾應比照 Windows 直接合併，不應整個資料夾 rename 成 `ABC_1`。  
> 完整計畫見：`docs/superpowers/plans/2026-04-08-w8-folder-merge-semantics.md`

- [x] 同名女優資料夾不再整個 rename，改為直接合併
- [x] `rename` 僅套用在資料夾內部的同名檔案
- [x] Wails backend 新增 `PlanDirMergeMoves()` binding，提供 file-level merge move items
- [x] 片商分類的同名資料夾改走 file-level conflict flow
- [x] `summary` / `lastBatchResult` / `scanResults` 在 merge 模式下維持正確

---

## W8 片商分類後續修復

- [x] D1：`MoveDir` 在部分 moved + skipped 時不再刪除來源資料夾
- [x] D8：`MoveDir` 改為保留空子目錄，一起搬移整個女優資料夾結構
- [x] D9：`BatchMoveDirs` 僅在資料夾完整搬走時才算 success；部分完成不再提前自列表移除
- [x] D10：`handleStudioMove` 以正規化路徑比較 `inputDir`，避免誤搬整個輸入根目錄
- [x] D11：directory `rename` 改為整個資料夾改名，衝突對話框文案同步
- [x] D12：片商分類兩階段目錄移動結果已合併到最終 summary / `lastBatchResult`

---

## 前置準備

- [x] 確認 Go 環境可用
- [x] 安裝 Wails v2 CLI：`go install github.com/wailsapp/wails/v2/cmd/wails@latest`
- [x] 執行 `wails doctor` 確認環境健康
- [x] 安裝 Node.js 18+
- [x] 確認 `node --version` / `npm --version`
- [x] 確認 WebView2 Runtime 可用（Windows 11 內建；Windows 10 需手動安裝）
- [x] 確認 CGO 可用

---

## W1. 環境建置 & PoC

- [x] 建立 `wails-app/` 子目錄
- [x] 初始化 Wails React + TypeScript 專案（`wails init`）
- [x] 建立 `wails-app/backend/app.go`
- [x] 暴露第一個 binding：`ScanDirectory(dir string)`
- [x] React 前端呼叫 `ScanDirectory`
- [x] 顯示回傳結果
- [x] 驗證 `wails dev`
- [x] 驗證 `wails build`
- [x] 確認可產生 `.exe`

**W1 驗收**
- [x] `wails dev` 可啟動
- [x] 前端按鈕能呼叫 Go binding
- [x] 畫面能顯示掃描結果

---

## W2. Go Backend Bindings

- [x] 建立 Wails backend app 骨架
- [x] 實作 `ScanDirectory`（含 `workers`、`recursive` 參數）
- [x] 實作 `MoveFile` / `MoveDir` / `BatchMove` / `BatchMoveStdin`
- [x] 實作 `RollbackLast` / `RollbackOperation`
- [x] 實作 `DbGetVideo` / `DbUpdateVideo` / `DbListVideos`
- [x] 實作 `IdentifyStudio` / `ListStudios`
- [x] 實作 `ListOperations` / `GetOperation`
- [x] 實作 `GetPreferences` / `UpdatePreferences` / `ResetPreferences`
- [x] 定義對應 Go struct 型別
- [x] 建立 Python subprocess wrapper `PythonSearch(code string)`
- [x] 新增 `src/scrapers/run_search.py`
- [x] 產生 TypeScript bindings（`wails generate module`）
- [x] 建立 `wails-app/backend/app_test.go`

**W2 驗收**
- [x] Go bindings 可被前端呼叫
- [x] Python 搜尋能透過 subprocess 正常回傳 JSON
- [x] backend 單元測試通過

---

## W3. 核心 UI 元件

- [x] 設定 Tailwind CSS
- [x] 整合 shadcn/ui
- [x] 建立 `<MainLayout>`（側邊欄 + 主內容區）
- [x] 建立 `<DirectoryPicker>`
- [x] 建立 `<VideoList>` + `<VideoCard>`
- [x] 建立 `<SearchPanel>`
- [x] 建立 `<ProgressBar>`
- [x] 建立 `<StatusBar>`
- [x] 建立共用 Modal 基底（`<DialogShell>` 或採用 shadcn/ui Dialog）
- [x] 建立 `src/stores/taskStore.ts`（Zustand）
- [x] 串接 Wails events
- [x] 用 React state 顯示進度

**W3 驗收**
- [x] 能瀏覽主畫面
- [x] 能選目錄
- [x] 能顯示掃描清單
- [x] 能顯示進度事件
- [x] 共用 Modal 可在所有對話框複用

---

## W4. 進階對話框

- [x] 建立 `<SearchResultDialog>` + `<SearchResultTable>` + `<SearchResultDetailModal>`
- [x] 建立 `<OperationHistoryDialog>` + `<OperationHistoryTable>` + `<RollbackConfirmModal>`
- [x] 建立 `<PreferencesDialog>`（四個 Tab：女優搜尋、分類選項、片商分類、系統設定）
- [x] 建立 `backend/services/config.go`（集中處理 config.ini 讀寫）
- [x] 讓設定可透過 `GetPreferences` / `UpdatePreferences` 讀寫 `config.ini`
- [x] 讓操作歷史可顯示單筆詳情與回滾

**W4 驗收**
- [x] 三個對話框整合至 App.tsx，可透過 toolbar 按鈕開啟
- [x] 設定可儲存/重設/重新載入（透過 ConfigService）
- [x] 回滾流程可執行並更新列表（RollbackConfirmModal + RollbackOperation binding）

---

## W5. 爬蟲整合

- [x] 建立 `src/scrapers/run_search.py`（輸出 JSON stdout）
- [x] 實作 Go subprocess wrapper（含 timeout 與錯誤分類）
- [x] timeout / stderr / JSON parse error 三種失敗分別帶回前端
- [x] 加入 spinner / 搜尋中狀態
- [x] 實作批次搜尋 subprocess pool
- [x] 實作 Python 路徑偵測

**W5 驗收**
- [x] 搜尋能成功呼叫 Python 爬蟲
- [x] JSON stdout 可被正確解析
- [x] 三種失敗情境有明確錯誤訊息
- [x] 批次搜尋進度可在 UI 顯示

---

## W6. 打包與清理

- [x] 設定 `wails build`（圖示、版本資訊）
- [x] 設定 NSIS installer
- [x] 確認 Python 爬蟲可隨安裝流程使用
- [x] 移除 `src/ui/`
- [x] 移除 `src/services/go_bridge.py`
- [x] 移除 `src/services/go_runner.py`
- [x] 移除 `src/services/go_api/`
- [x] 更新 `run.py`
- [x] 更新 `README.md`
- [x] 更新 `MIGRATION_STATUS.md`
- [x] 做完整 E2E 測試

**W6 驗收**
- [x] 單一 Wails `.exe` 可執行
- [x] 舊 Python GUI 移除完成
- [x] 所有核心功能可正常跑完

---

## 模組：GUI主視窗

### 現有實作（Python）
- 檔案：`src/ui/main_gui.py`
- 方法：`UnifiedActressClassifierGUI.__init__`、`setup_ui`、`start_search`、`start_japanese_search`、`start_javdb_search`、`start_shiroutowiki_search`、`start_interactive_move`、`start_standard_move`、`start_smart_search_and_move`、`start_studio_classification`、`show_preferences`、`show_operation_history`
- 邏輯：建立主視窗、管理資料夾選擇與任務按鈕、啟動背景執行緒、顯示結果文字與狀態列、開啟偏好設定與操作歷史對話框。

### 遷移目標（Go/React）
- 方法：Wails binding 提供 `ScanDirectory`、`SearchAndClassify`、`MoveFiles`、`StartStudioClassification`、`OpenPreferences`、`OpenOperationHistory`
- 層層：Go binding / React 主視窗元件 / Wails Events
- 實作檔案：`wails-app/backend/app.go`、`wails-app/frontend/src/App.tsx`、`wails-app/frontend/src/components/MainLayout.tsx`、`wails-app/frontend/src/components/DirectoryPicker.tsx`、`wails-app/frontend/src/components/VideoList.tsx`、`wails-app/frontend/src/components/VideoCard.tsx`、`wails-app/frontend/src/components/SearchPanel.tsx`、`wails-app/frontend/src/components/StatusBar.tsx`、`wails-app/frontend/src/components/ProgressBar.tsx`
- 補充：主視窗元件需明確納入 `VideoCard`、`SearchPanel`、`StatusBar`，與清單/搜尋/狀態區的拆分一致，避免後續實作時只做出單一大頁面。
- 輸入輸出：輸入為資料夾路徑、搜尋模式、移動策略；回傳為結構化結果、進度事件與錯誤訊息 JSON。
- 補充：`ScanDirectory` 需明確支援 `workers` 與 `recursive`，對齊 `pkg/app/scan_service.go` 的 `ScanFiles(req ScanRequest)`。
- 補充：`ScanDirectory` 的回傳與進度事件要維持批次摘要、成功、暫時性異常與失敗的可測試輸出，避免前端只剩單一 loading 狀態。
- 補充：前端狀態至少拆為結果清單、進度條、狀態列與按鈕啟用狀態，並以事件區分一般文字、錯誤、清除與 callback 類型。
- 補充：搜尋執行需保留批次狀態展示與搜尋迴圈結果摘要，至少能顯示批次開始、處理中、成功、暫時性異常、失敗與完成訊息，避免只剩單一 spinner。

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
- 補充：詳情視窗所需單筆資料應由 `GetOperation` / `ShowOperation` 類型的獨立查詢支援，不要只依賴列表資料。

### 驗收標準
- 可依狀態與關鍵字篩選結果。
- 可點欄位排序、雙擊查看單筆詳情。
- 可多選結果列後批次複製、匯出或查看選取摘要。
- 可匯出 CSV 並複製成功/失敗番號。

### 廃除條件
- `src/ui/search_result_dialog.py`
- 舊有 `show_search_results` 入口與 Tkinter 依賴。
- 舊的單選/複選結果操作流程與剪貼簿輔助邏輯。

## 模組：操作歷史對話框

### 現有實作（Python）
- 檔案：`src/ui/operation_history_dialog.py`
- 方法：`OperationHistoryDialog.show`、`_connect_with_retry`、`_create_widgets`、`_load_history`、`_show_details`、`_rollback_selected`、`show_operation_history`
- 邏輯：透過 Go CLI 讀取歷史紀錄、顯示操作列表與詳情、執行回滾並重新載入資料。

### 遷移目標（Go/React）
- 方法：Wails binding 提供 `ListOperations`、`GetOperation`、`RollbackOperation`；React 提供 `OperationHistoryDialog`、`OperationHistoryTable`、`RollbackConfirmModal`
- 補充：`GetOperation` 需明確對應 `pkg/app/history_service.go` 的 `ShowOperation`，讓詳情視窗不必依賴列表資料。
- 層層：Go binding / React Dialog / Wails Event
- 實作檔案：`wails-app/backend/app.go`、`wails-app/frontend/src/components/OperationHistoryDialog.tsx`
- 輸入輸出：輸入為查詢限制、操作 ID；輸出為操作日誌、詳情資料與回滾結果 JSON。
- 補充：歷史列表需支援獨立查詢單筆操作詳情，對齊 `pkg/app/history_service.go` 的 `ShowOperation`。
- 補充：`RollbackLast` 與 `RollbackOperation` 的語意要分開，前者是最近一次，後者是指定操作。

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
- 補充：偏好頁面應保留女優偏好、分類選項、片商分類與共演記錄四個區塊，避免只做單一表單。

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
- 方法：完全移除 Python 橋接，改由 Wails direct binding 呼叫 Go 後端方法；需要時由 Go 內部直接操作 pkg/ 與 subprocess。
- 層層：Go binding / Go service / Wails Event
- 實作檔案：`wails-app/backend/app.go`、`wails-app/backend/services/*.go`、`wails-app/frontend/src/lib/api.ts`
- 補充：`MoveFiles` 的設計需同時涵蓋 `MoveFile`、`MoveDir`、`BatchMove` 與 `BatchMoveStdin`，不要只寫單一檔案搬移。
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
- 補充：掃描能力需保留 `workers` 與 `recursive` 參數，並限制只處理支援格式。
- 補充：爬蟲 subprocess 若保留，timeout / stderr / JSON parse error 需分開回傳前端，避免只顯示泛用失敗。

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
- 補充：事件層要區分批次開始、單筆成功、暫時性異常、單筆失敗、階段切換與摘要完成。

### 驗收標準
- 背景任務可即時推送進度與狀態更新到前端。
- 長時間任務不會凍結 UI。
- 重要訊息與錯誤能在前端被清楚呈現。
- 批次搜尋時可看到目前批次 / 總批次、成功數、失敗數與暫時性異常數的即時變化。

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

### 進一步補充：Wails 專案骨架與型別/事件契約
- **專案路徑**：`wails-app/` 目前在 repo 中尚未建立；Tasks.md 應先把這個目錄視為新專案根目錄，底下至少要有 `wails-app/backend/app.go`、`wails-app/backend/services/`、`wails-app/frontend/src/`、`wails-app/frontend/src/components/`、`wails-app/frontend/src/lib/`、`wails-app/frontend/src/stores/`，避免後續實作時文件路徑漂移。
- **TypeScript 型別**：前端不能只靠 `any`。至少要補 `frontend/src/lib/types.ts` 或等價型別檔，定義 `ScanResult`、`MoveResult`、`MergeResult`、`BatchResult`、`OperationLog`、`MoveItem`、`VideoData`/`Preferences`、以及 Wails 事件 payload（例如 `ProgressEvent`、`StatusEvent`、`TaskDoneEvent`、`ErrorEvent`）。
- **Wails 事件名稱**：建議在文件中明確固定事件契約，避免前後端各寫各的。至少要列出 `scan:progress`、`task:progress` 或共用 `progress`、`status`、`error`、`task:done`、`task:clear`、`task:callback` 這幾類事件，並說清楚 payload 格式（例如 `{message, current, total, level, taskId}`）。

### 進一步補充：對話框共用元件、config.ini 與小視窗互動
- **共用 Modal 規劃**：除各對話框專屬元件外，需另列一個共用 Modal 基底（例如 `Modal.tsx` / `DialogShell.tsx`）或統一採用 shadcn/ui Dialog 包裝，讓 `SearchResultDetailModal`、`RollbackConfirmModal`、偏好設定與其他彈窗共用標題列、關閉動作、遮罩、ESC 關閉與寬度策略，避免各對話框各做各的。
- **config.ini 讀寫落點**：偏好設定模組不只要提到「讀/寫 config.ini」，還要明確寫出 Go 後端的讀寫責任，例如由 `backend/services/config.go`（或等價檔案）集中處理載入、驗證、預設值合併、儲存與錯誤回報，前端只透過 `GetPreferences` / `UpdatePreferences` 操作，不直接碰檔案系統。
- **多視窗 / 小視窗互動**：需補上主視窗在小尺寸或多視窗情境下的互動檢討，例如側欄折疊、彈窗在窄寬度下改成全寬或底部抽屜、進度條與狀態列在縮窄時仍可讀、History / Preferences 互斥開啟策略，以及視窗狀態切換時避免焦點遺失或背景任務資訊被遮蔽。
- **binding / service 分工**：`backend/app.go` 應只負責 binding 入口與事件轉發，實作邏輯放到 `backend/services/*.go`，避免把掃描、搬移、歷史、偏好與 subprocess 全塞進單一檔案；前端 `App.tsx` 也只應組裝版面，主要狀態與事件處理由 store / hooks / components 分層承接。
- **缺漏檢查清單**：若後續建立 `wails-app/`，先確認生成的預設檔案是否包含 bindings、types、events、store、測試與打包設定；否則容易只完成畫面而漏掉 Go binding 與事件資料格式，導致 UI 看得到但無法可靠串接。


## W7. E2E 驗收 & 打包確認

- [ ] 執行 `e2e/run_e2e.sh` 通過
- [ ] 所有 E2E 場景手動驗證通過（參見 e2e/test_scenarios.md）
- [ ] `wails build` 可產生 `.exe`
- [ ] NSIS installer 可正常安裝與解安裝
- [ ] Python 爬蟲在打包後可被 Go subprocess 正確呼叫
- [ ] 打包 smoke test checklist 全部通過
- [ ] 更新 MIGRATION_STATUS.md 標記專案完成

**W7 驗收**
- [ ] 單一 `.exe` 可在乾淨 Windows 環境執行
- [ ] 所有核心功能 E2E 驗證完成
- [ ] 文件更新完畢
