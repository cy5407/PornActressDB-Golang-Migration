# Build Test Guide

本文件記錄 **女優分類系統 v6.0.0** 的保守建置與驗證流程，重點是確認：

- Wails GUI 可正常建置
- 版本資訊與 `wails-app/wails.json` 一致
- `classifier.exe` 與必要資料檔沒有漏帶
- 打包後 Python 搜尋管線仍可被呼叫

## 1. 建置 Wails 桌面應用

在 `wails-app/` 目錄執行：

```bash
wails build
```

建置前請先確認：

- `wails-app/wails.json` 的 `productVersion` 正確
- `wails-app/wails.json` 的 `productName` 與輸出名稱正確
- 若在非 Windows 環境交叉檢查，需另外確認輸出目錄與目標平台是否符合預期

## 2. 版本與輸出物確認

至少確認以下項目：

- 應用版本資訊與 `wails-app/wails.json` 一致
- 主要 GUI 輸出檔名稱正確（例如 `actress-classifier.exe`）
- GUI 旁邊或發行包中有對應的必要檔案

目前專案在釋出或手動測試時，建議至少一併確認這些檔案：

- `classifier.exe`
- `major_studios.json`
- `studios.json`
- `config.ini`（或由 `config.ini.example` 複製後提供）

## 3. NSIS installer 驗證

若本次 release 會產生安裝程式，請確認：

- Installer 名稱與應用名稱一致
- 版本資訊正確
- 可正常安裝 / 啟動 / 解除安裝
- 安裝內容未遺漏必要檔案

### 建議驗證步驟

1. 執行 `wails build`
2. 確認產物與 installer 已生成
3. 在乾淨的 Windows 測試環境安裝
4. 從捷徑或安裝目錄啟動應用
5. 驗證搜尋 / 掃描 / 移動等核心流程
6. 解除安裝並確認捷徑與檔案清理正常

## 4. 確認 Python 搜尋管線仍可用

目前 Wails 後端仍會透過 subprocess 呼叫：

- `src/scrapers/run_search.py`

至少要確認：

- 打包後仍找得到 Python 解譯器
- 腳本路徑解析沒有壞掉
- `PythonSearch(code)` 的 stdout 仍為可解析 JSON
- stderr / timeout / JSON parse error 仍能被正確分類

## 5. 建議 smoke test checklist

建置後至少檢查：

- [ ] 應用可正常啟動
- [ ] 掃描功能正常
- [ ] 搜尋功能正常
- [ ] 移動 / 批次移動正常
- [ ] 操作歷史可列出
- [ ] rollback 正常
- [ ] Preferences 可讀取 / 更新 / 重設
- [ ] Python 搜尋管線仍可從 GUI 呼叫
- [ ] `classifier.exe` 可正常配合 GUI 使用
- [ ] `major_studios.json` / `studios.json` 未遺漏
- [ ] 錯誤訊息仍具可讀性

## 6. 保守 release gate

在正式發佈前，至少應滿足：

- `wails build` 成功
- 版本資訊正確
- installer（若有）可正常安裝 / 解除安裝
- Python / Go 相關測試已通過
- 打包後仍可呼叫 `run_search.py`
- smoke checklist 全綠
