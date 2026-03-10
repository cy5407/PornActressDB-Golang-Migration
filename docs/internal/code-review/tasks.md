# GoBridge 修正任務清單

建立時間: 2026-03-10 13:52:20 +08:00

來源文件:
1. docs/internal/code-review/SYSTEM_CODE_REVIEW_GoBridge-Gemini.md

## 修正目標

這份任務清單用來把 GoBridge review 結論轉成可執行修復工作，範圍聚焦在：
1. 恢復 GoBridge 的例外傳播與 Python fallback 鏈路
2. 降低資料庫單筆操作造成的 subprocess N+1 開銷
3. 統一橋接層命名與暫存檔清理行為

## 修正範圍

主要檔案：
1. src/services/go_bridge.py
2. src/models/go_accelerated_db.py
3. src/models/go_accelerated_studio.py
4. test_go_db_bridge.py

關聯驗證檔案：
1. src/services/go_bridge_test.py
2. tests/ 內與 GoBridge / Go fallback 相關測試

## P0

### P0-1 恢復 Fallback 鏈路

說明：
1. 移除 `db_*` 與 `identify_*` 模組級 helper 中寬泛的 `except Exception`
2. 底層 Go 橋接失敗時，應讓 `GoBridgeError` 往外傳，不能在 helper 內被吃掉後轉成 `None`、`False`、`[]` 或預設 dict

影響函式：
1. `db_get_video`
2. `db_update_video`
3. `db_delete_video`
4. `db_list_videos`
5. `db_get_stats`
6. `db_compact_journal`
7. `identify_studio`
8. `identify_studios_batch`
9. `list_studios`
10. `get_studio_prefixes`

驗證方式：
1. 模擬 `classifier.exe` 不可用
2. 驗證 `GoAcceleratedDB` 與 `GoAcceleratedStudioIdentifier` 能正確 fallback 到 Python
3. 驗證呼叫端不再把橋接失敗誤判成「查無資料」

### P0-2 清點例外契約

說明：
1. 明確區分「橋接失敗」與「業務上找不到資料」
2. 文件、測試、呼叫端都要依同一契約判斷

驗證方式：
1. 補測試覆蓋 Go CLI 不存在、命令失敗、JSON 解析失敗情境
2. 確認 fallback 只在橋接失敗時啟動

## P1

### P1-1 規劃批次資料庫 API

說明：
1. 為 `db get` / `db update` 增加批次能力，避免逐筆建立 subprocess
2. 介面方向以 `db_get_videos_batch`、`db_update_videos_batch` 類型能力為主

輸出項目：
1. CLI 介面草案
2. Python wrapper 草案
3. 高層切換點盤點

驗證方式：
1. 至少提出單行程處理多筆資料的介面設計
2. 明確標示哪裡應優先改接批次 API

### P1-2 盤點高層切換點

說明：
1. 找出 `src/models/go_accelerated_db.py` 與上層服務中仍可能逐筆呼叫 `db_*` 的路徑
2. 評估哪些流程能直接切到 batch API

驗證方式：
1. 列出受影響函式與預估收益

## P2

### P2-1 統一橋接層命名

說明：
1. 模組級 helper 內部命令列變數命名由混用的 `cmd` / `args` 收斂為單一風格
2. 優先跟 `GoBridge` 類別方法對齊

驗證方式：
1. 搜尋 `src/services/go_bridge.py`，確認同一家族不再混用命令陣列變數名稱

### P2-2 補暫存檔刪除警告日誌

說明：
1. `batch_move`、`db_update_video`、`identify_studios_batch` 的清理區塊不得再用 `except Exception: pass`
2. 刪除失敗時至少記錄 `logger.warning`

驗證方式：
1. 模擬暫存檔刪除失敗
2. 確認日誌中能看到警告資訊

### P2-3 測試與文件對齊

說明：
1. 更新 bridge 測試，反映「橋接失敗以例外傳播」的新契約
2. 若 README 或其他文件有示例，補充 fallback 行為說明

驗證方式：
1. `python test_go_db_bridge.py`
2. `python -m pytest tests/ -v`
3. `python -m pytest src/services/go_bridge_test.py -v`

## 命名與介面對齊注意事項

1. `db_*` 為穩定橋接家族前綴，維持不變
2. `identify_studio` / `identify_studios_batch` 為既有單筆 / 批次配對，維持同一家族
3. 新增 batch API 時，不要再混入第三種批次命名樣式

## 不在本次修正範圍

1. Go CLI 主程式的大規模重寫
2. `pkg/` 下非 review 直接涉及的功能擴充
3. 與 GoBridge review 無關的新功能開發
