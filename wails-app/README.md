# Wails App

這個子目錄是 **女優分類系統** 的 Wails 桌面應用原始碼。

- 前端：React + TypeScript
- 桌面框架：Wails
- 後端：Go bindings
- 搜尋：透過 subprocess 呼叫專案根目錄的 Python 搜尋管線

## 開發模式

在此目錄執行：

```bash
wails dev
```

這會啟動 Wails 開發模式與前端熱重載。

## 建置

在此目錄執行：

```bash
wails build
```

預設會產生桌面應用建置產物；實際輸出位置與版本資訊請以 `wails.json` 為準。

## 與根目錄 README 的分工

- 根目錄 `README.md`：整個專案的架構、快速開始、CLI 與資料檔說明
- 本檔：`wails-app/` 子目錄的開發與建置用途

## 釋出前提醒

建置 Wails 應用後，請另外確認專案根目錄中的下列檔案是否一併提供給使用者：

- `classifier.exe`
- `major_studios.json`
- `studios.json`
- Python 執行環境與 `requirements.txt` 依賴
