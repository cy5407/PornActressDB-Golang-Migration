---
name: performance-optimization
description: 效能優化指引 - 用於分析效能瓶頸、優化 Python 程式碼、善用 Go 加速、減少記憶體使用和提升響應速度
argument-hint: "[optimization-area]"
---

# 效能優化 Skill

## 何時使用此 Skill

當需要：
1. **分析效能瓶頸**（找出慢速操作）
2. **優化 Python 程式碼**（改善演算法）
3. **遷移到 Go**（10-78000x 加速）
4. **減少記憶體使用**
5. **提升 GUI 響應速度**

## 效能分析

### Python Profiling

```python
import cProfile
import pstats

# 分析函式
cProfile.run('my_function()', 'profile.stats')

# 查看結果
p = pstats.Stats('profile.stats')
p.sort_stats('cumulative')
p.print_stats(20)
```

### Go Benchmarking

```bash
# 執行基準測試
go test ./pkg/extractor -bench=. -benchmem

# 輸出：
# BenchmarkExtractCode-8    5000000    250 ns/op    64 B/op    2 allocs/op
```

## 優化策略

### 1. 使用 Go 加速

| 操作 | Python | Go | 提升 |
|------|--------|----|-----|
| 檔案掃描 | 2.5s | 0.15s | 16.7x |
| 批次移動 | 3.0s | 0.3s | 10x |
| 番號提取 | 100μs | 5μs | 20x |

### 2. 資料庫優化

- 使用 IncrementalJSONDB（40x 寫入加速）
- 批次處理後一次合併
- 定期清理 Journal

### 3. 併發處理

```python
# AV-WIKI 支援高併發
results = await scraper.batch_search_concurrent(
    codes,
    max_concurrent=15  # 15 個並發請求
)
```

## 相關檔案

- `CLAUDE.md` - 效能基準參考
- `GO_MIGRATION_TODO.md` - Go 遷移建議
