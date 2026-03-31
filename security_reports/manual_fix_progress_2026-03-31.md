# 手動修復進度

更新時間：2026-03-31 23:15 (Asia/Taipei)

## Round 1

- 建立 `pkg/safefile/safefile.go`，集中處理較安全的檔案讀寫與目錄建立。
- `cmd/scanner/main.go`
  - 改用安全檔案讀取 helper 處理批次檔與 JSON 檔讀取
  - 補上 `FlagSet.Parse` 錯誤處理
- `pkg/studio/identifier.go`
  - 改用安全檔案讀取 helper
- `pkg/database/jsondb.go`
  - 改用安全檔案讀寫 helper
  - 目錄與檔案權限收緊為 `0700` / `0600`
  - 補上暫存檔清理錯誤忽略的明確處理
- `pkg/database/journal.go`
  - Journal 開啟方式改為較安全權限
- `pkg/cache/cache.go`
  - 索引檔改為較安全權限寫入
- `pkg/mover/mover.go`
  - 檔案開啟/建立改走 helper
  - 日誌目錄與日誌檔權限收緊
  - 多個清理動作改為明確忽略錯誤

驗證結果：
- `go test ./pkg/...`：通過
- `gosec ./...`：由 39 項降到 3 項

## Round 2

- `cmd/scanner/main.go`
  - 補上預掃描 `filepath.WalkDir` 的錯誤處理
- `pkg/mover/mover.go`
  - 補上 `saveOperationLog` 的錯誤處理與 warning 訊息

目前狀態：
- `gosec`：預期剩餘 0 項，待本輪重新驗證
- `Bandit`
  - `src/scrapers/cache_manager.py`：0 項
  - `src/services/safe_searcher.py`：剩 2 項 `B311` 低風險告警

## Round 3

- `src/services/safe_searcher.py`
  - 將 `random.choice` 改為 `secrets.choice`
  - 將 `random.uniform` 改為基於 `secrets.randbelow` 的區間隨機等待

驗證結果：
- `python -m bandit -r src/services/safe_searcher.py src/scrapers/cache_manager.py`：0 項
- `gosec ./...`：0 項
- `go test ./pkg/...`：通過
- `go build ./cmd/scanner`：通過
- `./classifier.exe help`：通過
- GUI 啟動層檢查：`GUI_STARTUP_OK UnifiedActressClassifierGUI`

本輪結束後：
- Python 端已確認修復 `B324`、`B301`、`B311`
- Go 端 `gosec` 掃描結果為 0

## 後續建議

- 若要提交，可搭配 `security_fix_summary_2026-03-31.md` 一起納入 commit
- 若要維持完整追蹤，可在下一次修復後追加本檔案而非另開新報告
