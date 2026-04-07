# Wails E2E 驗收說明

這個目錄放的是 Wails 後端 / 前端整合驗收的執行說明與測試場景。

## 前置條件

- 需要可執行的 Go / Wails 開發環境
- 需要一個**測試用影片資料夾**，裡面放一些可辨識番號的檔案，例如：
  - `STARS-707.mp4`
  - `ABW-001.mkv`
  - `MIAA-123.avi`
- 建議準備一個獨立的暫存目錄做搬移與回滾測試，避免污染正式資料
- `src/scrapers/run_search.py` 必須存在，且 Python 執行環境可用

## 執行方式

先在 `wails-app/` 底下執行 backend integration test：

```bash
./e2e/run_e2e.sh
```

腳本會：

1. 檢查必要工具是否存在
2. 執行 Go backend 的 integration tests
3. 將測試結果摘要輸出到終端機

## 涵蓋場景

- 掃描目錄：`ScanDirectory(dir, workers, recursive)`
- 搜尋女優：`PythonSearch(code)` subprocess 呼叫
- 搬移檔案：`MoveFile` / `BatchMove`
- 回滾操作：`RollbackLast` / `RollbackOperation`
- 偏好設定讀寫：`GetPreferences` / `UpdatePreferences` / `ResetPreferences`
- 操作歷史讀取：`ListOperations` / `GetOperation`
- 錯誤情境：
  - Python timeout
  - Python stderr
  - JSON parse error

## 驗收重點

- backend 方法可被正常呼叫
- 掃描與搬移流程可重複執行
- 偏好設定能正確讀寫 config.ini
- 錯誤訊息要能區分 timeout / stderr / JSON parse error
- 測試結束後不要留下不可回復的檔案變動
