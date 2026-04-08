---
category: Wails
date: 2026-04-08
---
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

## 搜尋效能分析（2026-04-07 實測，完整四輪優化）

掃描目錄：`C:\Users\cy5407\Downloads\AV`，63 個唯一番號

| 輪次 | 總耗時 | 啟動耗時 | 搜尋耗時 | Workers | 優化描述 |
|------|--------|----------|----------|---------|---------|
| 第一輪（原始）| **75 秒** | ~32 秒 | ~43 秒 | 5 | 每筆獨立啟動 Python process |
| 第二輪（batch）| **39 秒** | ~5 秒 | ~34 秒 | 15 | 單一 process + ThreadPoolExecutor |
| 第三輪（反效果）| **50 秒** | ~14 秒 | ~36 秒 | 20 | 主 thread 預建 searcher（串行反慢）|
| **第四輪（最終）**| **🚀 10 秒** | ~3 秒 | ~7 秒 | 20 | thread-local 並行初始化 + 停用 rate limiter |

**整體加速：75s → 10s（**7.5x**），成功率 63/63 = 100%**

### 第四輪核心優化：停用 Rate Limiter

`SafeSearcher` 的 `japanese_searcher.config`：`min_interval=0.5s, max_interval=1.5s`  
批次模式中每個 thread 有獨立 `SafeSearcher`（`_thread_local`），`last_request_time` 不跨 thread 共用，rate limiter 只會白白 sleep。

修法（`run_batch_search.py`）：
```python
searcher.japanese_searcher.config.min_interval = 0.0
searcher.japanese_searcher.config.max_interval = 0.0
searcher.safe_searcher.config.min_interval = 0.0
searcher.safe_searcher.config.max_interval = 0.0
```

### 踩坑：主 thread 預建 searcher 反效果

試圖串行預建 20 個 WebSearcher 以「避免 GIL 競爭」：啟動從 5s 惡化到 14s。  
原因：Python GIL 在 I/O（讀 cache、import）時自動讓步，threads 並行初始化反而更快。  
**教訓**：I/O 密集操作交給 threads 並行，強制串行只會更慢。

## 相關文件

- [Wails GUI 架構](../architecture/wails-gui.md)
- [搜尋引擎架構](../architecture/search-engine.md)
