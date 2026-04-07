# E2E 測試場景

## Fixture 說明

測試 fixture 在 `wails-app/e2e/fixtures/` 下：
- `videos/`：100 個假影片檔（0-byte），覆蓋 10 個廠牌
- `test_db/data.json`：對應 DB 資料，search_status 全為 "failed"，可用來模擬「尚未搜尋、待分類」狀態
- 重新產生：`python3 gen_fixtures.py`

測試流程建議：
1. 執行掃描 → 確認 100 筆都被 ScanDirectory 偵測到
2. 執行搜尋（可 mock 或真實）→ 確認 search_status 更新
3. 執行搬移 → 確認檔案依女優/片商分類到正確目錄
4. 執行回滾 → 確認檔案回到原目錄

以下場景用來驗收 Wails 遷移後的 Go backend 與前端事件串接是否完整。

## 1. 掃描目錄

### 1.1 基本掃描
- 準備一個包含測試影片的資料夾
- 呼叫 `ScanDirectory(dir, workers=1, recursive=false)`
- 驗證只掃描目錄第一層

### 1.2 多工掃描
- 呼叫 `ScanDirectory(dir, workers=4, recursive=true)`
- 驗證可回傳多筆結果
- 驗證檔名中的番號可被正確抽出

### 1.3 递迴掃描
- 在子目錄中放入影片檔
- 呼叫 `ScanDirectory(dir, workers=2, recursive=true)`
- 驗證子目錄內容也會被掃描

### 1.4 非递迴掃描
- 在子目錄中放入影片檔
- 呼叫 `ScanDirectory(dir, workers=2, recursive=false)`
- 驗證子目錄內容不會被掃描

## 2. 搜尋女優（PythonSearch subprocess）

### 2.1 正常回傳
- 呼叫 `PythonSearch("STARS-707")`
- 驗證 stdout JSON 可解析
- 驗證 `code`、`title`、`studio`、`method` 等欄位存在

### 2.2 多筆批次搜尋
- 呼叫 `BatchSearch([]string{"STARS-707", "ABW-001"}, workers=2)`
- 驗證每筆都會回傳結果
- 驗證會送出 progress / result / done 事件

## 3. 搬移檔案

### 3.1 MoveFile
- 建立單一來源檔案與目的地
- 呼叫 `MoveFile(src, dst, "skip")`
- 驗證搬移成功且目的地存在

### 3.2 BatchMove
- 準備多個 `MoveItem`
- 呼叫 `BatchMove(items, "skip")`
- 驗證成功 / 失敗 / 跳過統計正確

### 3.3 MoveDir
- 準備整個來源資料夾
- 呼叫 `MoveDir(srcDir, dstDir, "rename")`
- 驗證資料夾搬移結果與衝突策略

## 4. 回滾操作

### 4.1 RollbackLast
- 先做一次搬移
- 呼叫 `RollbackLast()`
- 驗證最近一次操作被還原

### 4.2 RollbackOperation
- 先取得 `ListOperations()`
- 取出指定 `operationID`
- 呼叫 `RollbackOperation(operationID)`
- 驗證對應操作可被還原

## 5. 偏好設定讀寫

### 5.1 GetPreferences
- 呼叫 `GetPreferences()`
- 驗證可回傳預設值或現有設定

### 5.2 UpdatePreferences
- 修改 `batch_size`、`mode`、`log_dir` 等欄位
- 呼叫 `UpdatePreferences(prefs)`
- 再次讀取確認有寫回

### 5.3 ResetPreferences
- 先修改偏好設定
- 呼叫 `ResetPreferences()`
- 驗證回到預設值

## 6. 操作歷史讀取

### 6.1 ListOperations
- 執行一次或多次搬移後呼叫 `ListOperations()`
- 驗證可取得最近操作列表

### 6.2 GetOperation
- 使用某筆 `operationID`
- 呼叫 `GetOperation(operationID)`
- 驗證可取得單筆詳情

## 7. 錯誤情境

### 7.1 Python timeout
- 模擬 Python 腳本執行超時
- 驗證回傳的 `ErrorKind` 為 `timeout`

### 7.2 stderr 錯誤
- 模擬 Python 腳本寫入 stderr 並退出失敗
- 驗證回傳的 `ErrorKind` 為 `stderr`

### 7.3 JSON parse error
- 模擬 stdout 不是合法 JSON
- 驗證回傳的 `ErrorKind` 為 `json_parse`

## 8. 驗收標準

- 所有核心 binding 都要能被直接呼叫
- 事件型 progress 要能正常發送
- 回滾、偏好設定、歷史查詢不可互相破壞資料
- 錯誤分類不能混成單一 generic failure
