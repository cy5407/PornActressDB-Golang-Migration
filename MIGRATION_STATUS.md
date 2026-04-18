# Migration Status

## 目前狀態

專案已完成 **Wails + Go-only（非爬蟲層）** 遷移。

- **桌面 GUI**：`actress-classifier.exe`（Wails / Go + React）
- **Go CLI**：`classifier.exe`
- **Python 保留範圍**：搜尋與爬蟲管線（AV-WIKI、JAVDB、快取與搜尋器）
- **非爬蟲層**：掃描、搬移、資料庫、操作歷史、CLI 契約皆以 Go 為唯一正式實作

## 已完成項目

### 架構

- [x] 移除 Python GUI；目前 GUI 由 `wails-app\frontend\` + `wails-app\backend\` 提供
- [x] `run.py` 改為優先啟動 Wails 執行檔
- [x] `src/services/go_cli.py` 成為 Python 呼叫 `classifier.exe` 的正式入口

### DB / CLI 契約

- [x] 修正 `db compact` / `db merge` / backup family 的 Python ↔ Go 契約漂移
- [x] `JSONDBManager` 與 `IncrementalJSONDB` 改為直接委派 Go CLI
- [x] 非爬蟲層不再保留 ImportError stub 與靜默 Python fallback

### 測試與 CI

- [x] DB 測試改為 hermetic，不再碰 `data\json_db`
- [x] integration workflow 改為執行真實 smoke / contract tests
- [x] Python 測試目前基線：`120 passed`

### 搜尋穩定性

- [x] `AVWikiScraper` 共享 semaphore，實際併發受 `max_concurrent` 控制
- [x] `SafeJAVDBSearcher` retry / cooldown 不再把整段流程鎖住
- [x] `SafeSearcher` 補上預設 timeout、同 URL request 序列化與 atomic cache save

### 路徑與執行檔解析

- [x] `pkg/pathutil.IsSameOrNestedPath()` 統一 mover / Wails backend 的巢狀路徑判定
- [x] `src/services/go_cli.py`、`src/utils/scanner.py` 對齊 `exe_path` 解析邏輯

## 目前有效的核心檔案

```text
run.py
src/services/go_cli.py
src/models/json_database.py
src/models/incremental_json_database.py
src/utils/scanner.py
src/scrapers/
wails-app/backend/app.go
wails-app/frontend/src/
```

## 驗證命令

```powershell
go build -o classifier.exe .\cmd\scanner
python -m pytest tests\ -q -p no:cacheprovider
python -m pytest tests\integration\ -v --tb=short -p no:cacheprovider

Set-Location wails-app
go test .\backend -v
```

## 待確認項目

以下兩項仍屬決策閘門，尚未視為已完成：

1. 是否還需要保留舊版 `video_actress_links` 正規化支援
2. 搜尋 URL 是否要在 log 中預設脫敏
