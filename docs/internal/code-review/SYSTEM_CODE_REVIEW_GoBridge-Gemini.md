# 系統級 Code Review 報告：GoBridge 模組

> 審查範圍：`src/services/go_bridge.py`
> 審查依據：`SYSTEM_CODE_REVIEW_CORE.md` 範本（未納入本 repo）

## 審查摘要
1. **[嚴重隱患] 錯誤處理吞沒例外，破壞 Fallback 機制**：`db_*` 與 `identify_*` 系列的輔助函式過度捕捉例外，把 `GoBridgeError` 靜默掉回傳 `None/False/[]`，不僅與核心 API 風格不一，還會導致調用層無法判斷 Go 崩潰或不存在，造成無法降級（Fallback）回 Python。
2. **[效能隱患] 資料庫單筆操作產生巨大進程開銷**：Go 橋接層為每次單筆 (`db_get_video`, `db_update_video`) 創建單獨的 `subprocess`。在迴圈或高頻率情況下，頻繁建立進程將抹殺任何效能紅利，比純 Python 檔案 I/O 還慢。
3. **[API 介面不一致] 傳遞參數與例外設計風格分歧**：類別內方法與模組級便捷函式（Global functions）在異常處理、回傳值風格及內部變數命名（如 `args` vs `cmd`）不連貫。

---

## 問題清單

### 1. 異常處理吞沒例外，破壞 Fallback 機制
- **嚴重度**：高
- **面向**：實作方法一致性
- **證據**：`src/services/go_bridge.py` 中 `db_get_video`、`db_update_video`、`identify_studio` 等模組級函式尾端使用 `try... except Exception as e: return None / False`（例如第 590, 638 行）。
- **影響**：當 Go 執行檔不存在或超時觸發 `GoBridgeError` 時，底層例外會被該 `except` 攔截。呼叫端會誤判為「查無這筆資料」或「更新單純失敗」，而不是觸發應有的「降級回 Python 實作」機制，直接癱瘓部分業務邏輯。
- **建議修復**：移除所有 `db_*` 與 `identify_*` 中一體適用的 `except Exception` 攔截。將 `GoBridgeError` 向外拋出，讓上層的資料庫/片商識別管理層 (`GoAcceleratedDB` / `ClassifierCore`) 能憑此例外確實觸發 Fallback 機制。
- **優先序**：P0

### 2. 單一資料庫操作伴隨巨大的 Subprocess 效能開銷
- **嚴重度**：高
- **面向**：效能
- **證據**：`db_get_video` 等函式皆直接透過 `bridge._run_command(cmd)` 呼叫 `classifier.exe`（見第 585 行、618 行）。
- **影響**：Python 中呼叫 `subprocess.run` 建立新行程（尤以 Windows 平台更甚）代價極高。連續針對 500 部影片進行單筆 Update 或 Get 將產生 500 個獨立的 Go 行程，其耗時絕對遠超過純 Python 對 JSON 進行記憶體讀寫。
- **建議修復**：這屬於架構層級的效能盲點，最小可行修復：應設計配套的批次查詢/更新介面（如 `db_get_videos_batch(codes: list[str])`），並確保高層調用儘可能批次塞入臨時檔案，由單個 Go 行程一次處理完畢。
- **優先序**：P1

### 3. 例外通報與命名風格嚴重不一致
- **嚴重度**：中
- **面向**：命名/參數/函式一致性
- **證據**：`GoBridge` 類內的核心方法（如 `scan_directory`、`move_file`）在失敗時拋出 `GoBridgeError`；然 `db_*` 等函式選擇回傳 `Optional[]` 或布林值。同時，命令陣列在類別方法叫 `args`，在輔助函式時卻叫 `cmd`。
- **影響**：對開發者將造成混亂：同樣使用此模組，判斷錯誤的方式卻分裂成了「例外捕捉」與「空值檢查」兩套標準。
- **建議修復**：統一將介面名稱改成 `args`，並一律採取拋出例外的方式作為底層連線失敗、找不到執行檔的錯誤回報機制。
- **優先序**：P2

### 4. 暫存檔管理：強制刪除失敗遭靜默，恐留檔案殘渣
- **嚴重度**：低
- **面向**：資安 / 實作方法一致性
- **證據**：第 480 行 (`batch_move`)、630 行 (`db_update_video`) 移除暫存檔的 `finally` 區塊，直接寫入 `except Exception: pass`。
- **影響**：在 Windows 環境下，若 Go 行程當機而卡住該 `temp_file.json` 對應的 file lock，刪除檔的過程拋錯便會被忽略。日積月累會在 `temp` 目錄留下大量的暫存檔，且可能殘留有系統敏感性的檔案路徑資訊。
- **建議修復**：將 `pass` 更改為 `logger.warning(f"⚠️ 無法刪除暫存檔，可能被佔用: {temp_file}，錯誤原因: {e}")`，以留驗證軌跡。
- **優先序**：P2

---

## 總結

### Top 5 風險
1. **[P0]** 異常處理吞沒例外，破壞 GoBridge 架構規定的 Fallback 降級機制。
2. **[P1]** `db_update/get` 等單點操作濫生子進程，大批次資料時將嚴重拖垮系統效能。
3. **[P2]** 介面的回傳風格不一致（拋出例外 vs. 回傳預設空值）。
4. **[P2]** 暫存檔清除機制過於隨意，未將鎖定與異常情形打入日誌。

### 可在 1 天內完成的修復項目
- 移除 `db_*` 與 `identify_*` 中寬泛捕獲的 `except Exception: return None/False`，恢復向外拋出 `GoBridgeError`。
- 修正規範函式內部命名（`cmd` → `args`）。
- 在暫存檔清除的 `except` 捕獲區塊加上 `logger.warning` 的日誌回報。

### 需要排程的技術債
- 針對 `db_get` 與 `db_update` 設計 `batch` 機制，由 Python 段聚集所有需要查改的目標存入單一暫存 JSON 丟給 Go，根絕 N+1 次的 Subprocess 喚起效能瓶頸。
