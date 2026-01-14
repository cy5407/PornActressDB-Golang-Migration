# Phase 2 實作任務清單 - Go 資料庫模組

> **前置條件**: Phase 1 分析已完成 ✅
> **文件參考**: `docs/DATABASE_ANALYSIS.md`, `docs/database-design.md`
> **目標模組**: `pkg/database/`
> **預期效能**: 10-40x 提升

---

## 🎯 Phase 2 核心任務

### 任務 1: 實作 CompactIfNeeded() 自動合併判斷

**檔案**: `pkg/database/jsondb.go`

**需求說明**:
- 實作自動判斷是否需要執行 Compact 的方法
- 根據 Python 版本的雙閾值策略：
  - Journal 記錄數 >= 1000 條
  - Journal 年齡 >= 1 小時（3600 秒）

**實作步驟**:
1. [ ] 新增 `journalSize int` 和 `journalCreatedAt time.Time` 欄位到 JSONDatabase struct
2. [ ] 在 `Load()` 方法中初始化這些欄位
3. [ ] 實作 `CompactIfNeeded() (bool, error)` 方法
   - 檢查 journal 檔案是否存在
   - 計算 journal 記錄數（讀取 data.index 或掃描檔案）
   - 計算 journal 年齡（當前時間 - 建立時間）
   - 如果滿足任一條件，自動呼叫 `CompactJournal()`
   - 返回 (是否執行了合併, 錯誤)
4. [ ] 在 `UpdateVideo()` 後自動呼叫 `CompactIfNeeded()`（可選）

**驗收標準**:
- CompactIfNeeded() 正確判斷是否需要合併
- 滿足條件時自動執行合併
- 不滿足條件時不執行合併
- 有明確的日誌輸出

**程式碼範例** (參考):
```go
func (db *JSONDatabase) CompactIfNeeded() (bool, error) {
    db.mu.Lock()
    defer db.mu.Unlock()

    if !db.loaded {
        return false, ErrDatabaseNotLoaded
    }

    // 檢查 journal 是否存在
    stat, err := os.Stat(db.journalFile)
    if os.IsNotExist(err) {
        return false, nil // 沒有 journal，不需合併
    }

    // 計算 journal 記錄數
    journalSize, err := db.getJournalSizeUnsafe()
    if err != nil {
        return false, fmt.Errorf("failed to get journal size: %w", err)
    }

    // 計算 journal 年齡
    journalAge := time.Since(stat.ModTime())

    // 判斷是否需要合併（雙閾值）
    needsCompact := journalSize >= 1000 || journalAge >= time.Hour

    if needsCompact {
        fmt.Fprintf(os.Stderr, "Compacting journal (size=%d, age=%s)\n", journalSize, journalAge)
        if err := db.compactJournalUnsafe(); err != nil {
            return false, fmt.Errorf("compact failed: %w", err)
        }
        return true, nil
    }

    return false, nil
}
```

---

### 任務 2: 實作 Dirty Tracking Index

**檔案**: `pkg/database/index.go` (新建)

**需求說明**:
實作 `data.index` 檔案的讀寫，用於追蹤哪些實體被修改過，加速查找和合併判斷。

**Index 檔案格式** (JSON):
```json
{
  "videos": ["SONE-123", "MIDV-456"],
  "actresses": [],
  "links": [],
  "journal_size": 15,
  "created_at": "2026-01-12T10:00:00Z"
}
```

**實作步驟**:
1. [ ] 建立 `pkg/database/index.go` 檔案
2. [ ] 定義 `IndexData` struct
   ```go
   type IndexData struct {
       Videos      []string  `json:"videos"`
       Actresses   []string  `json:"actresses"`
       Links       []string  `json:"links"`
       JournalSize int       `json:"journal_size"`
       CreatedAt   time.Time `json:"created_at"`
   }
   ```
3. [ ] 實作 `loadIndex() (*IndexData, error)` - 載入索引
4. [ ] 實作 `saveIndex(index *IndexData) error` - 儲存索引
5. [ ] 實作 `addDirtyKey(entityType, entityID string)` - 新增 dirty key
6. [ ] 實作 `clearIndex()` - 清空索引（合併後）
7. [ ] 在 `UpdateVideo()` 中更新索引
8. [ ] 在 `CompactJournal()` 中清空索引
9. [ ] 在 `CompactIfNeeded()` 中使用 journal_size

**驗收標準**:
- Index 檔案正確讀寫
- UpdateVideo 後 index 正確更新
- CompactJournal 後 index 正確清空
- journal_size 正確追蹤

**程式碼範例** (參考):
```go
// index.go
package database

import (
    "encoding/json"
    "os"
    "path/filepath"
    "time"
)

type IndexData struct {
    Videos      []string  `json:"videos"`
    Actresses   []string  `json:"actresses"`
    Links       []string  `json:"links"`
    JournalSize int       `json:"journal_size"`
    CreatedAt   time.Time `json:"created_at"`
}

func (db *JSONDatabase) loadIndex() (*IndexData, error) {
    indexFile := filepath.Join(filepath.Dir(db.dataFile), "data.index")

    data, err := os.ReadFile(indexFile)
    if os.IsNotExist(err) {
        // 不存在則返回空索引
        return &IndexData{
            Videos:    []string{},
            Actresses: []string{},
            Links:     []string{},
            CreatedAt: time.Now(),
        }, nil
    }
    if err != nil {
        return nil, err
    }

    var index IndexData
    if err := json.Unmarshal(data, &index); err != nil {
        return nil, err
    }

    return &index, nil
}

func (db *JSONDatabase) saveIndex(index *IndexData) error {
    indexFile := filepath.Join(filepath.Dir(db.dataFile), "data.index")

    data, err := json.MarshalIndent(index, "", "  ")
    if err != nil {
        return err
    }

    return os.WriteFile(indexFile, data, 0644)
}
```

---

### 任務 3: 補充單元測試

**檔案**: `pkg/database/jsondb_test.go`, `pkg/database/index_test.go` (新建)

**需求說明**:
撰寫完整的單元測試，確保功能正確性和達到 80%+ 覆蓋率。

**測試清單**:

#### CompactIfNeeded 測試
1. [ ] `TestCompactIfNeeded_NoJournal` - 沒有 journal 時不執行合併
2. [ ] `TestCompactIfNeeded_SizeThreshold` - Journal 達到 1000 條時自動合併
3. [ ] `TestCompactIfNeeded_TimeThreshold` - Journal 超過 1 小時時自動合併
4. [ ] `TestCompactIfNeeded_BothThresholds` - 同時滿足兩個閾值
5. [ ] `TestCompactIfNeeded_BelowThreshold` - 未達閾值時不合併

#### Index 測試
6. [ ] `TestLoadIndex_NotExists` - 索引不存在時返回空索引
7. [ ] `TestLoadIndex_Exists` - 正確載入現有索引
8. [ ] `TestSaveIndex` - 正確儲存索引
9. [ ] `TestAddDirtyKey_Video` - 新增影片 dirty key
10. [ ] `TestAddDirtyKey_Duplicate` - 重複新增同一個 key
11. [ ] `TestClearIndex` - 清空索引

#### 整合測試
12. [ ] `TestUpdateVideo_UpdatesIndex` - UpdateVideo 自動更新索引
13. [ ] `TestCompactJournal_ClearsIndex` - CompactJournal 清空索引
14. [ ] `TestAutoCompact_Integration` - 完整的自動合併流程

**驗收標準**:
- 所有測試通過
- 測試覆蓋率 >= 80%
- 包含正常和異常情況
- 有並發安全測試

**測試範例**:
```go
func TestCompactIfNeeded_SizeThreshold(t *testing.T) {
    // 設定測試環境
    tempDir := t.TempDir()
    db := NewJSONDatabase(tempDir)

    // 初始化空資料庫
    if err := db.Load(); err != nil {
        t.Fatalf("Failed to load: %v", err)
    }

    // 寫入 1000 筆資料
    for i := 0; i < 1000; i++ {
        code := fmt.Sprintf("TEST-%04d", i)
        video := &VideoData{
            Code:  code,
            Title: fmt.Sprintf("Test Video %d", i),
        }
        if err := db.UpdateVideo(video); err != nil {
            t.Fatalf("Failed to update video: %v", err)
        }
    }

    // 檢查 journal 檔案存在
    journalFile := filepath.Join(tempDir, "data.journal")
    if _, err := os.Stat(journalFile); os.IsNotExist(err) {
        t.Fatal("Journal file should exist")
    }

    // 執行 CompactIfNeeded
    compacted, err := db.CompactIfNeeded()
    if err != nil {
        t.Fatalf("CompactIfNeeded failed: %v", err)
    }

    // 驗證結果
    if !compacted {
        t.Error("Should have compacted (size threshold)")
    }

    // 檢查 journal 已被清空
    if _, err := os.Stat(journalFile); !os.IsNotExist(err) {
        t.Error("Journal file should be removed after compact")
    }
}
```

---

### 任務 4: 效能基準測試

**檔案**: `pkg/database/benchmark_test.go` (新建)

**需求說明**:
撰寫效能基準測試，驗證是否達到預期的 10-40x 提升。

**基準測試清單**:
1. [ ] `BenchmarkUpdateVideo` - 單一影片更新效能
2. [ ] `BenchmarkUpdateVideo_Batch` - 批次更新效能（100 筆）
3. [ ] `BenchmarkCompactJournal_1000` - 合併 1000 條記錄
4. [ ] `BenchmarkReplayJournal` - 重播 journal 效能
5. [ ] `BenchmarkLoadDatabase` - 載入大型資料庫

**驗收標準**:
- UpdateVideo 單次操作 < 1ms
- 批次更新 100 筆 < 50ms
- Compact 1000 條 < 2s
- 有記憶體使用統計

**基準測試範例**:
```go
func BenchmarkUpdateVideo(b *testing.B) {
    tempDir := b.TempDir()
    db := NewJSONDatabase(tempDir)

    if err := db.Load(); err != nil {
        b.Fatalf("Failed to load: %v", err)
    }

    video := &VideoData{
        Code:  "BENCH-001",
        Title: "Benchmark Video",
    }

    b.ResetTimer()
    for i := 0; i < b.N; i++ {
        if err := db.UpdateVideo(video); err != nil {
            b.Fatalf("Update failed: %v", err)
        }
    }
}

func BenchmarkCompactJournal_1000(b *testing.B) {
    tempDir := b.TempDir()
    db := NewJSONDatabase(tempDir)

    if err := db.Load(); err != nil {
        b.Fatalf("Failed to load: %v", err)
    }

    // 準備 1000 筆資料
    for i := 0; i < 1000; i++ {
        video := &VideoData{
            Code:  fmt.Sprintf("BENCH-%04d", i),
            Title: fmt.Sprintf("Video %d", i),
        }
        if err := db.UpdateVideo(video); err != nil {
            b.Fatalf("Update failed: %v", err)
        }
    }

    b.ResetTimer()
    for i := 0; i < b.N; i++ {
        if err := db.CompactJournal(); err != nil {
            b.Fatalf("Compact failed: %v", err)
        }
    }
}
```

---

## 📋 Phase 2 完成清單

### 程式碼實作
- [ ] CompactIfNeeded() 實作完成
- [ ] Dirty tracking index 讀寫完成
- [ ] 所有輔助函式實作完成
- [ ] 程式碼格式化 (`go fmt`)
- [ ] 通過 `go vet` 檢查

### 測試
- [ ] 13+ 個單元測試全部通過
- [ ] 測試覆蓋率 >= 80%
- [ ] 5+ 個基準測試完成
- [ ] 並發安全測試通過

### 文件
- [ ] 函式 docstring 完整
- [ ] 更新 `@fix_plan.md` 標記 Phase 2 完成
- [ ] 更新 `CLAUDE.md` 記錄新增的功能
- [ ] Git commit (conventional commits 格式)

### 效能驗證
- [ ] UpdateVideo < 1ms
- [ ] Batch update (100 筆) < 50ms
- [ ] Compact (1000 條) < 2s
- [ ] 記憶體使用合理

---

## 🚀 執行指南

### 1. 開始實作
```bash
# 確認 Go 環境
go version  # 應為 1.24.5+

# 執行現有測試
go test ./pkg/database -v

# 查看測試覆蓋率
go test ./pkg/database -cover
```

### 2. 實作順序建議
1. 先實作 Index 讀寫（獨立功能）
2. 再實作 CompactIfNeeded（依賴 Index）
3. 撰寫單元測試（TDD）
4. 撰寫基準測試
5. 效能調優

### 3. 驗證流程
```bash
# 執行所有測試
go test ./pkg/database -v

# 查看覆蓋率
go test ./pkg/database -cover

# 執行基準測試
go test ./pkg/database -bench=. -benchmem

# 程式碼檢查
go fmt ./pkg/database
go vet ./pkg/database
```

### 4. Git 提交
```bash
git add pkg/database/
git commit -m "feat(database): 實作 CompactIfNeeded 和 dirty tracking (P0 Phase 2/7)

- 實作 CompactIfNeeded() 自動合併判斷（雙閾值）
- 實作 dirty tracking index 讀寫
- 新增 13+ 個單元測試（覆蓋率 85%+）
- 新增 5+ 個基準測試
- UpdateVideo 效能 < 1ms
- Compact 1000 條 < 2s

Co-Authored-By: Ralph (Claude Code Agent) <noreply@anthropic.com>"
```

---

## 📚 參考文件

- `docs/DATABASE_ANALYSIS.md` - Python 版本完整分析
- `docs/database-design.md` - Go 實作設計方案
- `pkg/database/jsondb.go` - 現有實作
- `src/models/incremental_json_database.py` - Python 參考實作

---

## ⚠️ 注意事項

1. **JSON 相容性**: 確保所有 JSON 格式與 Python 版本完全一致
2. **並發安全**: 使用 mutex 保護所有共享資源
3. **錯誤處理**: 明確返回錯誤，不使用 panic
4. **效能優先**: 記住目標是 10-40x 提升
5. **測試驅動**: 先寫測試，再實作功能

---

**Phase 2 預計完成時間**: 2-3 個 Ralph 循環（或 2-3 小時手動實作）
**Phase 2 完成標準**: 所有勾選框 ✅ + 所有測試通過 + 效能達標
