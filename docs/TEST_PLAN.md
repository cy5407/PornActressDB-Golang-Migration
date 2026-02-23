# 測試計畫 — PornActressDB-Golang-Migration 修復驗證

**建立日期**: 2026-02-23
**適用版本**: Task.md 全部修復完成後
**目的**: 驗證 19 個修復項目的正確性，確保無回歸問題

---

## 一、自動化測試（Go 單元測試）

### 執行命令

```bash
# 執行所有套件測試
go test ./pkg/... -v -race -coverprofile=coverage.out

# 顯示覆蓋率報告
go tool cover -func=coverage.out

# 效能基準測試
go test ./pkg/database/... -bench=. -benchmem
```

### 測試套件與涵蓋項目

| 套件 | 測試檔案 | 涵蓋修復項目 |
|------|----------|-------------|
| `pkg/database` | `jsondb_test.go` | C-1, C-2, C-3, W-3, S-1 |
| `pkg/mover` | `mover_test.go` | C-4, W-3, W-5, S-6 |
| `pkg/cache` | `cache_test.go` | W-3, W-4, S-3 |
| `pkg/extractor` | `extractor_test.go` | W-1, S-5 |
| `pkg/studio` | `identifier_test.go` | S-4 |

### 預期測試結果

```
ok  actress-classifier/pkg/cache       (全 9 個測試通過)
ok  actress-classifier/pkg/database    (全 10 個測試通過)
ok  actress-classifier/pkg/extractor   (全 3 個測試通過)
ok  actress-classifier/pkg/mover       (全 11 個測試通過)
ok  actress-classifier/pkg/studio      (全 8 個測試通過)
```

---

## 二、Critical 修復驗證

### C-1: journal.go — f.Sync() 斷電保護

**測試目標**: 驗證 journal 寫入後立即同步至磁碟

**測試方法**:
```bash
# 執行 journal 相關測試
go test ./pkg/database/... -run TestJournal -v
```

**驗證點**:
- [ ] `TestJournal` 通過（5 筆記錄寫入並合併）
- [ ] journal 檔案在寫入後確實可讀取（非緩衝狀態）

**手動驗證**（可選）:
```bash
# 寫入一筆資料後立即中斷程序，重啟後確認資料不遺失
classifier.exe db update TEST-001 test_video.json
# 強制終止並重啟，執行：
classifier.exe db get TEST-001  # 應能取得資料
```

---

### C-2: jsondb.go — BatchUpdate 修復

**測試目標**: 驗證 BatchUpdate 正確更新 dirtyVideos、journalSize 和 saveIndex

**測試方法**:
```bash
go test ./pkg/database/... -run TestBatchUpdate -v
```

**驗證點**:
- [ ] `TestBatchUpdate` 通過（3 筆批次更新成功）
- [ ] 批次更新後 journalSize 增加（等於批次項目數）
- [ ] 批次更新後 index 檔案已更新

**測試腳本**:
```go
// 手動驗證
db, _ := database.NewJSONDatabase("data/json_db")
db.Load(context.Background())

before := db.journalSize  // 記錄更新前的 journalSize

updates := map[string]*database.Video{...}
db.BatchUpdate(updates)

// 驗證 journalSize 增加了 len(updates)
assert(db.journalSize == before + len(updates))
```

---

### C-3: jsondb.go — saveIndex() 錯誤處理

**測試目標**: 驗證所有 saveIndex() 呼叫點都有錯誤處理

**測試方法**:
```bash
# 靜態分析確認無未處理的錯誤
go vet ./pkg/database/...
```

**程式碼審查清單**:
- [ ] `UpdateVideo` (jsondb.go:295) — 已有 `if err := db.saveIndex()` 處理
- [ ] `UpdateVideoFields` (jsondb.go:337) — 已有處理
- [ ] `AddVideo` (jsondb.go:376) — 已有處理
- [ ] `CompactJournal` (jsondb.go:520) — 已有處理

---

### C-4: mover.go — copyFile 強化

**測試目標**: 驗證複製失敗時不留下不完整的目標檔案

**測試方法**:
```bash
go test ./pkg/mover/... -run TestMoveFile -v
```

**驗證點**:
- [ ] `TestMoveFile_Basic` 通過（跨磁碟複製場景）
- [ ] 複製失敗時目標檔案被清理
- [ ] `dstFile.Sync()` 確保磁碟寫入

**手動驗證**:
```bash
# 測試跨磁碟移動（會觸發 copyFile）
classifier.exe move -src "C:/test.mp4" -dst "D:/test.mp4"
```

---

### C-5: .gitignore — config.ini 保護

**測試目標**: 確認 config.ini 不會被提交到版本庫

**測試方法**:
```bash
# 確認 config.ini 在 .gitignore 中
git check-ignore -v config.ini  # 應輸出 .gitignore 規則

# 確認 config.ini.example 存在
ls config.ini.example  # 應存在
```

**驗證點**:
- [ ] `git status` 不顯示 config.ini（已被忽略）
- [ ] `config.ini.example` 存在且不含個人路徑
- [ ] `config.ini.example` 中的路徑使用 `YOUR_USERNAME` 佔位符

---

## 三、Warning 修復驗證

### W-1: extractor.go — 正規表達式預編譯

**測試目標**: 驗證 regex 只在初始化時編譯一次

**效能測試**:
```bash
go test ./pkg/extractor/... -bench=. -benchmem -count=5
```

**預期效能提升**: `ExtractCode` 效能應比修改前快 30-50%（避免重複編譯）

---

### W-2: main.go — ext 變數遮蔽修復

**測試方法**:
```bash
# go vet 的 shadow 偵測
go vet -shadow ./cmd/scanner/...

# 或 golangci-lint
golangci-lint run ./cmd/scanner/...
```

**驗證點**:
- [ ] `go vet` 不報告 `ext` 變數遮蔽警告
- [ ] `fileExt` 變數名稱出現在 `main.go` 的掃描邏輯中

---

### W-3: context.Context 整合

**測試目標**: 驗證 Load/BatchMove/AutoCleanup 接受 context 參數

**測試方法**:
```bash
go build ./...  # 確認所有呼叫端已更新
go test ./pkg/... -v  # 確認測試通過
```

**驗證點**:
- [ ] `db.Load(context.Background())` 在測試中使用
- [ ] `m.BatchMove(context.Background(), items)` 在測試中使用
- [ ] `cm.AutoCleanup(context.Background(), config)` 在 main.go 中使用

**未來擴展驗證**:
```go
// 驗證 context 取消可以傳入（即使目前不使用）
ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
defer cancel()
db.Load(ctx)
```

---

### W-4: cache.go — AutoCleanup TOCTOU 修復

**測試目標**: 驗證合併清理只讀取一次 index

**測試方法**:
```bash
go test ./pkg/cache/... -run TestAutoCleanup -v
```

**注意**: cache_test.go 目前未直接測試 AutoCleanup，建議新增：

```go
func TestAutoCleanup(t *testing.T) {
    dir := t.TempDir()
    cm := NewCacheManager(dir)

    now := float64(time.Now().Unix())
    // 建立過期 + 超大的測試條目
    entries := map[string]IndexEntry{
        "expired": {
            CreatedAt: now - 864000,  // 過期
            TTLSeconds: 86400,
            SizeBytes: 100 * 1024 * 1024,  // 100 MB
        },
    }
    createTestIndex(t, dir, entries)

    config := PruneConfig{
        TTLDays:   7,
        MaxSizeMB: 50,
        DryRun:    true,
    }

    result, err := cm.AutoCleanup(context.Background(), config)
    if err != nil {
        t.Fatalf("AutoCleanup 失敗: %v", err)
    }

    // 不應重複計算刪除（TOCTOU 修復的核心）
    if result.DeletedFiles != 1 {
        t.Errorf("期望刪除 1 個，實際 %d", result.DeletedFiles)
    }
}
```

---

### W-5: mover.go — loadOperationLog glob 優化

**測試目標**: 驗證 glob 直接定位日誌檔案

**測試方法**:
```bash
go test ./pkg/mover/... -run TestRollback -v
```

**效能驗證**: 當日誌目錄有大量操作記錄時，loadOperationLog 應比線性搜尋快

---

### W-6: flag.FlagSet 統一解析

**測試目標**: 驗證 `-log-dir` 和 `-data-dir` 可正確解析

**手動驗證**:
```bash
# historyCmd 使用 -log-dir
classifier.exe history list -log-dir custom/logs

# dbCmd 使用 -data-dir
classifier.exe db stats -data-dir custom/data
```

**驗證點**:
- [ ] `-log-dir` 參數正確覆蓋預設值 `logs`
- [ ] `-data-dir` 參數正確覆蓋預設值 `data/json_db`
- [ ] 無效參數會顯示適當錯誤訊息

---

## 四、Suggestion 修復驗證

### S-1: interface{} → any 替換

**測試方法**:
```bash
grep -rn "interface{}" pkg/ cmd/  # 應只剩下必要的舊版相容處
```

**驗證點**:
- [ ] `types.go` 中 `map[string]any` 使用
- [ ] `jsondb.go` 中 `applyVideoUpdates` 使用 `any`
- [ ] 編譯通過（`any` 是 Go 1.18+ 別名）

---

### S-2: TestField 隔離

**測試方法**:
```bash
grep -n "TestField" pkg/database/  # 確認有適當注記
```

**驗證點**:
- [ ] `TestField` 有明確的測試用途注記
- [ ] 生產環境可安全移除此欄位

---

### S-3: cache.New → cache.NewCacheManager

**測試方法**:
```bash
go test ./pkg/cache/... -run TestNew -v

# 確認舊名稱仍有向後相容別名
grep -n "func New\b" pkg/cache/cache.go
```

**驗證點**:
- [ ] `NewCacheManager` 正常運作
- [ ] `New`（Deprecated 別名）仍可使用（向後相容）
- [ ] `TestNew` 通過

---

### S-4: MajorStudios → major_studios.json

**測試方法**:
```bash
# 確認 major_studios.json 存在
ls major_studios.json

# 執行片商識別測試
go test ./pkg/studio/... -run TestIsMajorStudio -v
```

**驗證點**:
- [ ] `major_studios.json` 存在於專案根目錄
- [ ] `IsMajorStudio("S1")` 仍回傳 `true`
- [ ] 可透過修改 `major_studios.json` 新增大片商而無需重新編譯

---

### S-5: supportedFormats 整合

**測試方法**:
```bash
# 確認 extractor.SupportedFormats 被 main.go 使用
grep -n "SupportedFormats" cmd/scanner/main.go pkg/extractor/extractor.go
```

**驗證點**:
- [ ] `extractor.SupportedFormats` exported 變數存在
- [ ] `main.go` 使用此變數而非重複定義
- [ ] 兩者的格式清單一致

---

### S-6: generateUniqueName 上限

**測試方法**:
```bash
go test ./pkg/mover/... -run TestMoveFile_ConflictRename -v
```

**驗證點**:
- [ ] 正常情況下重命名仍正確（`dest_1.txt`）
- [ ] 超過 10000 次時不會無限迴圈
- [ ] 超過上限時回傳時間戳後綴的名稱

---

## 五、工具/流程驗證

### CI — golangci-lint

**測試方法**:
```bash
# 本機執行 golangci-lint（需先安裝）
golangci-lint run ./...

# 或使用 Docker
docker run --rm -v $(pwd):/app -w /app golangci/golangci-lint golangci-lint run
```

**驗證點**:
- [ ] `.github/workflows/go-lint.yml` 已建立
- [ ] `.golangci.yml` 已啟用 `govet` shadow 偵測
- [ ] `errcheck` 和 `ineffassign` 均已啟用

**現有 .golangci.yml 啟用的 linter**:
- [x] `gofmt` — 格式化
- [x] `goimports` — import 組織
- [x] `govet` — go vet 分析（含 shadow）
- [x] `errcheck` — 未處理錯誤
- [x] `staticcheck` — 靜態分析
- [x] `ineffassign` — 無效賦值

---

## 六、回歸測試

### Python GUI 啟動測試

**測試目標**: 確認 Go 修改不影響 Python 應用程式

**測試命令**:
```bash
python run.py  # GUI 應正常啟動
```

**驗證點**:
- [ ] GUI 正常啟動，無錯誤訊息
- [ ] GoBridge 可偵測到 `classifier.exe`
- [ ] 掃描功能可正常使用

### Go CLI 功能測試

```bash
# 基本功能測試
classifier.exe help
classifier.exe scan -dir "." -workers 4
classifier.exe db stats
classifier.exe cache stats
classifier.exe identify SONE-123
```

**驗證點**:
- [ ] 所有命令正常執行
- [ ] JSON 輸出格式與 Python 相容
- [ ] 無 panic 或未處理的 error

---

## 七、測試執行順序建議

```
1. go build ./...          # 確認編譯通過
2. go test ./pkg/... -race # 執行所有測試（含 race detector）
3. go vet ./...            # 靜態分析
4. 手動驗證 C-5（gitignore）
5. 手動驗證 W-6（flag 解析）
6. 手動驗證 S-4（major_studios.json）
7. python run.py           # Python GUI 啟動驗證
```

---

## 八、測試結果記錄模板

| 測試項目 | 狀態 | 執行日期 | 備注 |
|----------|------|----------|------|
| C-1 journal f.Sync() | ⬜ | | |
| C-2 BatchUpdate 修復 | ⬜ | | |
| C-3 saveIndex 錯誤處理 | ⬜ | | |
| C-4 copyFile 強化 | ⬜ | | |
| C-5 gitignore 保護 | ⬜ | | |
| W-1 regex 預編譯 | ⬜ | | |
| W-2 ext 變數遮蔽 | ⬜ | | |
| W-3 context.Context | ⬜ | | |
| W-4 AutoCleanup TOCTOU | ⬜ | | |
| W-5 glob 優化 | ⬜ | | |
| W-6 flag.FlagSet 解析 | ⬜ | | |
| S-1 any 替換 | ⬜ | | |
| S-2 TestField 隔離 | ⬜ | | |
| S-3 NewCacheManager | ⬜ | | |
| S-4 major_studios.json | ⬜ | | |
| S-5 SupportedFormats 整合 | ⬜ | | |
| S-6 generateUniqueName 上限 | ⬜ | | |
| CI golangci-lint | ⬜ | | |
| Python GUI 回歸測試 | ⬜ | | |
