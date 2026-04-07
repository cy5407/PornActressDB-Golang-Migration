# Wails 掃描重複番號 & E2E 效能記錄

> 歸檔日期：2026-04-07  
> 來源：Wails GUI E2E 實測（用戶手動掃描 `C:\Users\cy5407\Downloads\AV`）

---

## 踩到的坑

### 坑 1：同番號重複出現在掃描結果

**症狀**

執行 Wails GUI 掃描後，進度列表出現同番號多次：

```
掃描進度：8 / EBON-004
...
掃描進度：52 / EBON-004    ← 重複
```

已確認重複的番號（E2E 實測）：
- `EBON-004`（進度 #8 和 #52）
- `CEMD-818`（進度 #78 和 #88）

**根本原因**

同一番號的影片或相關檔案（字幕、NFO）分散在不同子資料夾，`filepath.WalkDir` 各找一次，沒有去重。

**修法（2026-04-07 已修）**

在 `wails-app/backend/app.go` 的 `ScanDirectory()` 加入 `seen map`：

```go
seen := make(map[string]bool)
// 找到 code 後：
if code != "" && !seen[code] {
    seen[code] = true
    results = append(results, ScanResult{Path: path, Code: code})
}
```

**教訓**

掃描去重應在 Go 端做（扁平化結果），不應讓前端或搜尋端處理重複。

---

### 坑 2：進度計數器顯示「掃描幾個檔案」而非「找到幾筆」

**症狀**

`掃描進度：52 / EBON-004`——52 是已掃描的原始檔案數，但使用者更想看「第幾筆有效番號」。

**修法**

progress counter 改用 `len(results)` 取代 `scanned` 變數：

```go
wailsRuntime.EventsEmit(a.ctx, "scan:progress", len(results), code)
```

---

## E2E 效能數據（2026-04-07 實測）

環境：Windows 11、`C:\Users\cy5407\Downloads\AV`、Wails exe 直接執行

| 步驟 | 耗時 | 備註 |
|------|------|------|
| 掃描 99 個檔案 | **< 1 秒** | 純 Go `filepath.WalkDir` |
| 辨識有效番號 | — | 65 筆（修復前含 2 重複）|
| 去重後番號數 | — | 63 筆 |
| 搜尋 65 筆（修復前）| **75 秒** | 09:17:17 → 09:18:32 |
| 搜尋平均每筆 | **~1.15 秒** | 含 Python subprocess 啟動 |
| 搜尋成功率 | **65/65 = 100%** | AV-WIKI 為主要來源 |
| 並行 workers | **5** | config 可調高到 10-15 |

**效能瓶頸**：Python subprocess 啟動 + HTTP 往返延遲  
**優化建議**：把 workers 調高到 10-15（需留意 AV-WIKI 速率限制）

---

## 其他實測發現（非坑，但值得記錄）

| 功能 | 狀態 | 說明 |
|------|------|------|
| 目錄瀏覽 📂 | ✅ 正常 | 修復 `SelectDirectory` binding 後 |
| 掃描遞迴 | ✅ 全深度 | 改用 `filepath.WalkDir` |
| CMD 視窗彈出 | ✅ 已消除 | `proc_windows.go` `CREATE_NO_WINDOW` |
| 中文日誌亂碼 | ✅ 已修 | `-X utf8` + `PYTHONIOENCODING` |
| 取消操作 | ✅ 有取消按鈕 | `CancelOperation()` + `context.CancelFunc` |
| 資料庫讀取 | ✅ 正常 | 需從專案根目錄啟動 exe（相對路徑 `data/json_db`）|

---

## 延伸閱讀

- [wiki/pitfalls/wails-scan-duplicate.md](../../wiki/pitfalls/wails-scan-duplicate.md)
- [wiki/architecture/wails-gui.md](../../wiki/architecture/wails-gui.md)
