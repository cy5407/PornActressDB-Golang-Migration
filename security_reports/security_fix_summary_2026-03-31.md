# 安全修復摘要

更新時間：2026-03-31 23:22 (Asia/Taipei)

## 本次修復範圍

- Python
  - `src/scrapers/cache_manager.py`
  - `src/services/safe_searcher.py`
- Go
  - `cmd/scanner/main.go`
  - `pkg/cache/cache.go`
  - `pkg/database/journal.go`
  - `pkg/database/jsondb.go`
  - `pkg/mover/mover.go`
  - `pkg/studio/identifier.go`
  - `pkg/safefile/safefile.go`
- 測試與進度文件
  - `tests/test_cache_manager_security.py`
  - `security_reports/manual_fix_progress_2026-03-31.md`

## 主要修復內容

- 移除磁碟快取中的 `pickle` 反序列化，改用 JSON 載荷格式
- `safe_searcher.py` 的 MD5 快取鍵明確標示為非安全用途
- `safe_searcher.py` 的一般亂數改為 `secrets` 來源
- Go 端新增 `pkg/safefile`，統一路徑存取，降低 path traversal 類風險
- Go 端多處檔案與目錄權限收緊為 `0600` / `0700`
- 補齊 `FlagSet.Parse`、日誌儲存、暫存檔清理等錯誤處理

## 驗證結果

### Python

```text
python -m bandit -r src/services/safe_searcher.py src/scrapers/cache_manager.py
結果：No issues identified.
```

```text
python -m py_compile run.py
python -m py_compile src/services/safe_searcher.py src/scrapers/cache_manager.py
結果：通過
```

### Go

```text
go test ./pkg/...
結果：通過
```

```text
gosec ./...
結果：Issues : 0
```

```text
go build ./cmd/scanner
go build -o classifier.exe ./cmd/scanner
./classifier.exe help
結果：通過
```

### GUI 啟動層

```text
以接近 run.py 的流程建立 Tk / ttkbootstrap / UnifiedActressClassifierGUI
結果：GUI_STARTUP_OK UnifiedActressClassifierGUI
```

## 結論

- 目前本次修復涵蓋的 Python 安全項目已清零
- 目前 `gosec` 掃描結果為 0
- Go CLI 可正常建置與執行
- GUI 啟動層檢查通過
