# Wails 掃描重複番號問題

## 問題描述

執行 `ScanDirectory` 掃描大型目錄時，**同一番號可能出現多次**：

```
掃描進度：8 / EBON-004
掃描進度：52 / EBON-004   ← 重複
掃描進度：78 / CEMD-818
掃描進度：88 / CEMD-818   ← 重複
```

掃描 99 個檔案後產出 65 筆結果，但其中有重複番號，導致搜尋也重複執行，浪費網路請求。

## 根本原因

`filepath.WalkDir` 會遍歷所有檔案。如果：
- 同一番號的影片存在於**不同子資料夾**（例如原始版 + 字幕版）
- 或影片與外掛字幕（`.srt`、`.ass`）都被 extractor 提取出相同番號

同番號就會出現多次。這是正確的掃描行為（兩個路徑確實都存在），但對搜尋而言是重複浪費。

## 解決方案

在 `ScanDirectory` 中加入 `seen` map，**相同番號只保留第一個路徑**：

```go
seen := make(map[string]bool)

_ = filepath.WalkDir(dir, func(path string, d os.DirEntry, err error) error {
    // ...
    code := a.extractor.ExtractCode(filepath.Base(path))
    if code != "" && !seen[code] {
        seen[code] = true
        results = append(results, ScanResult{Path: path, Code: code})
        wailsRuntime.EventsEmit(a.ctx, "scan:progress", len(results), code)
    }
    return nil
})
```

同時修正 progress counter：改用 `len(results)` 而非已掃描檔案數，讓進度編號直接等於找到的番號序號（更直觀）。

## 修復位置

`wails-app/backend/app.go` — `ScanDirectory()` 函數

## 效能影響（E2E 實測資料）

| 指標 | 修復前 | 修復後 |
|------|--------|--------|
| 掃描 99 個檔案 | < 1 秒 | < 1 秒（不變）|
| 有效番號（去重後）| 65 筆（含 2 重複）| 63 筆（唯一）|
| 搜尋次數 | 65 次 | 63 次 |
| 搜尋總耗時（估）| 75 秒 | ~73 秒 |

## 搜尋效能分析（2026-04-07 實測）

掃描目錄：`C:\Users\cy5407\Downloads\AV`

| 指標 | 數值 |
|------|------|
| 掃描 99 個檔案耗時 | < 1 秒（純 Go WalkDir）|
| 有效番號（去重）| 63 筆 |
| 搜尋開始 | 09:17:17 |
| 搜尋結束 | 09:18:32 |
| 搜尋總耗時 | **75 秒** |
| 每筆平均 | **~1.15 秒/筆** |
| 並行 workers | 5 |
| 成功率 | 65/65（修復前）→ 預計 63/63 |

**搜尋瓶頸**：Python subprocess 啟動開銷 + HTTP 網路往返延遲（AV-WIKI / JAVDB）。  
**優化方向**：提高 workers 數（建議 10-15），但需注意目標網站速率限制。

## 相關文件

- [Wails GUI 架構](../architecture/wails-gui.md)
- [搜尋引擎架構](../architecture/search-engine.md)
