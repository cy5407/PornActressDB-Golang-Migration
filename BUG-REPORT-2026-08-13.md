# Bug Report — PornActressDB-Golang-Migration

**日期：** 2026-08-13
**方法：** 唯讀靜態調查（多個唯讀掃描器分割互斥證據面 + 編譯器/linter 基線），所有結論皆經人工複驗。
**未執行：** 任何測試套件。本輪為唯讀調查，未跑 `go test`，因此以下皆為靜態證據，無動態重現。

## 靜態分析基線

| 檢查 | 範圍 | 結果 |
|---|---|---|
| `go vet ./cmd/... ./pkg/...` | 全部非 vendor 套件 | 無輸出 |
| Go 版本 | `go.mod` 宣告 go 1.25，工具鏈 go1.26.5 | ≥1.22，無迴圈變數捕獲問題 |

環境未安裝 staticcheck / golangci-lint / gosec / errcheck。標準工具全綠，以下皆為語意層缺陷。

---

## P2 — `generateUniqueName` 的條件式是死碼，真實錯誤被完全吞掉

**位置：** `pkg/mover/file_move.go:158-176`

```go
func (m *Mover) generateUniqueName(path string) string {
	dir, fileExt, base := filepath.Dir(path), filepath.Ext(path), filepath.Base(path)
	name := base[:len(base)-len(fileExt)]
	for i := 1; i <= generateUniqueNameMaxAttempts; i++ {   // 10000
		candidatePath := filepath.Join(dir, fmt.Sprintf("%s_%d%s", name, i, fileExt))
		f, err := os.OpenFile(candidatePath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
		if err == nil {
			_ = f.Close()
			return candidatePath
		}
		if !os.IsExist(err) {
			continue          // ← 與不進入 if 的結果相同
		}
	}
	result := filepath.Join(dir, fmt.Sprintf("%s_%s%s", name, time.Now().Format("20060102150405"), fileExt))
	fmt.Fprintf(os.Stderr, "[WARNING] generateUniqueName: 達到最大嘗試次數 (%d)…\n", …)
	return result
}
```

`if !os.IsExist(err) { continue }` 的兩個分支結果相同（進入 if 會 continue，不進入 if 也會走到迴圈結尾 continue），因此這個條件式**沒有任何作用**。

**觸發情境：** 目標目錄不存在，或使用者對該目錄無寫入權限，或磁碟已滿。

**結果：**
1. `os.OpenFile` 每次都回傳 `ErrPermission` / `ErrNotExist`（非 `ErrExist`），但錯誤被完全忽略。
2. 迴圈跑滿 10000 次無效 syscall。
3. 最終回傳一個時間戳路徑，而該路徑在同樣的目錄下同樣建不出來。
4. 呼叫端（`file_move.go:144`）收到一個看似正常的路徑，實際失敗發生在下游，錯誤訊息與根因無關。

**正確意圖：** 非 `ErrExist` 的錯誤應終止迴圈並回報，而非重試。

**附帶問題：** 成功路徑會留下 0 bytes 佔位檔（註解說明這是刻意用來原子鎖定路徑、防 TOCTOU）。但若後續 `copyFile`／`os.Rename` 失敗，該空檔會殘留在使用者影片庫中。

**測試現況：** `pkg/mover/error_paths_test.go:640` `TestGenerateUniqueName_TimestampFallbackOnRepeatedFailure` 使用 bogusDir 走的正是這條 10000 次路徑，等於把此行為當作預期結果鎖定。修正時需一併調整該測試。

---

## P2 — `export_json` 直接繞過 `safefile`、非原子寫入

**位置：** `pkg/database/export_json.go:110-119`

```go
func writeJSONDatabaseRoot(path string, root *DatabaseData) error {
	raw, err := json.MarshalIndent(root, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal export: %w", err)
	}
	if err := os.WriteFile(path, raw, 0o600); err != nil {   // 直接 truncate 寫入
		return fmt.Errorf("write export %q: %w", path, err)
	}
	return nil
}
```

**兩個問題：**

1. **非原子寫入。** `os.WriteFile` 立即 truncate 目標檔。大型匯出遇到磁碟空間不足或行程中斷時，留下的是被截斷的 JSON —— 原檔已毀、新檔不完整。
2. **繞過路徑圍籬。** `pkg/safefile` 的所有函式都以 `os.OpenRoot(dir)` 建立目錄根並在其內操作（`safefile.go:69-99`），此處直接呼叫 `os` 套件，該防護完全不適用。

**對照：** 專案多數寫檔點走 `safefile`，且需要原子性的地方還額外自行實作 tmp+rename，但並非唯一寫法——`wails-app/backend/services/config.go:91`（`ConfigService.Save`）同樣直接呼叫 `os.WriteFile`：

| 位置 | 作法 |
|---|---|
| `pkg/cache/cache.go:97` | `safefile.WriteFile(tmpPath, …)` + rename |
| `pkg/database/jsonfixture/jsondb.go:233` | `safefile.WriteFile(tmpFile, …)` + rename |
| `pkg/database/jsonfixture/jsondb.go:1032` | `safefile.WriteFile(tempPath, …)` + rename |
| `pkg/database/export_json.go:115` | **直接 `os.WriteFile`** |
| `wails-app/backend/services/config.go:91` | **直接 `os.WriteFile`**（另一個既有直接寫入點） |
| `pkg/database/sqlite_backup.go:308` | **直接 `os.OpenFile(..., O_TRUNC, 0o600)`**（`copyFile` 備份/還原路徑） |
| `pkg/mover/file_move.go:163` | **直接 `os.OpenFile(..., O_CREATE\|O_EXCL, 0600)`**（`generateUniqueName` 的 0-byte 佔位檔；對比同檔 `copyFile:186` 走的是 `safefile.OpenFile`） |

以上四處為全庫（排除 `_test.go`）繞過 `safefile` 的直寫點全集，查證指令：
`grep -rn --include=*.go -E "\bos\.(WriteFile|Create|CreateTemp|OpenFile)\(" . | grep -v _test.go`

---

## P2（遺留面）— JSON 儲存層寫入失敗卻回報成功

**位置：** `JSONDatabase` 已搬到 `pkg/database/jsonfixture/jsondb.go`；對應方法約在 `UpdateVideo`（301 行一帶）、`SaveActress`（747 行一帶）、`DeleteActress`（776 行一帶）

三個方法都先修改記憶體狀態，接著在 journal / index 寫入失敗時吞掉錯誤並 `return nil`：

```go
// UpdateVideo — jsonfixture/jsondb.go:270-320 一帶
db.root.Videos[code] = video                       // 先改記憶體
entry, err := NewJournalEntry(op, TypeVideo, code, video)
if err != nil {
	fmt.Fprintf(os.Stderr, "Warning: failed to create journal entry: %v\n", err)
} else {
	if err := db.appendJournalEntry(entry); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: failed to write journal: %v\n", err)
	} else {
		db.dirtyVideos[code] = true
		…
	}
}
return nil                                          // 一律回報成功

// SaveActress — jsonfixture/jsondb.go:747 一帶 / DeleteActress — jsonfixture/jsondb.go:776 一帶
entry, err := NewJournalEntry(op, TypeActress, actress.ID, actress)
if err == nil {                                     // 錯誤連 warning 都沒有
	if db.appendJournalEntry(entry) == nil {        // 同上
		db.dirtyActresses[actress.ID] = true
		db.journalSize++
		_ = db.saveIndex() //nolint:errcheck
	}
}
return nil
```

**觸發情境：** 磁碟滿或權限不足時呼叫上述任一方法 → 記憶體已更新、journal 未寫入 → 呼叫端收到 `nil` 以為成功 → 行程結束前未 `Save()` 或崩潰，該筆寫入靜默消失。

**降級為 P2 的理由：** `pkg/database/store_factory.go:15-20` 明確記載 Phase C2 已將 runtime 收斂為 SQLite-only，`JSONDatabase` 型別僅保留作 import / export / legacy fixture helper：

> Phase C2 collapsed the runtime onto a SQLite-only path… the `JSONDatabase` type stays only as an import / export / legacy fixture helper.

已確認 `jsonfixture.JSONDatabase` 目前無生產路徑呼叫（僅 import / export / legacy fixture 測試使用），此為遺留面缺陷而非線上缺陷。

---

## P3 — `safefile.WriteFile` 缺少 `Sync()`

**位置：** `pkg/safefile/safefile.go:69-99`

```go
written, writeErr := file.Write(data)
closeErr := file.Close()          // 無 file.Sync()
```

**對照：** 同專案 `pkg/mover/file_move.go:195` 的 `copyFile` 有明確 `dstFile.Sync()` 並在失敗時清理目的檔。

**觸發情境：** 系統在 `Close()` 之後、OS 實際落盤之前當機，已「成功」寫入的內容遺失。

**備註：** `safefile.WriteFile` 本身也非原子操作（`O_TRUNC` 直接覆寫），這是為何各呼叫端需自行做 tmp+rename。

---

## 已查核並否決的疑似缺陷

以下項目在掃描中被提出，但經複驗後判定不成立，記錄於此以免日後重複調查：

| 宣稱 | 否決理由 |
|---|---|
| `jsondb.go:557` 呼叫不存在的 `appendJournal("update", code, video)`，會編譯失敗 | 呼叫點實際在 `pkg/database/jsonfixture/jsondb.go:549`（557 為空行）。`appendJournal(operation, code string, video *database.VideoData)` 定義於 `pkg/database/jsonfixture/journal.go:49`，`Video` 是 `pkg/database/jsondb.go:29` 對 `VideoData` 的別名故等價。且 `go vet` 通過即證明套件可編譯 |
| `safefile.OpenRead`／`OpenFile`／`ReadFile` 的 `defer root.Close()` 會使回傳的 `*os.File` 失效 | Go `os.Root.Open`／`Root.OpenFile` 回傳的 `*os.File` 持有自己的檔案 handle；關閉 Root 只影響 Root 本身的後續方法呼叫，不影響已開啟的檔案。這是 `os.Root` 的既定語意 |
| `journal.go:98-100`、`297`、`323`、`350` 靜默跳過損毀的 journal 行 | `pkg/database/jsonfixture/journal.go:98-100` 有印出 warning 並繼續，未靜默。**原掃描器引用的另外三行不存在或無關**：該檔共 297 行，`297` 是 `newJournalScanner` 的閉括號，`323`／`350` 超出檔尾（`pkg/database/journal.go` 更只有 129 行）。「屬同一策略的下游」是先前的推定，程式碼中沒有任何註解表達此意圖 |
| `actress_cleaner.go:173` 迴圈更新無交易保護 | **部分成立，先前的否決理由有誤。**這條路徑就是 SQLite runtime：`cmd/scanner/db_cmd.go:450` 的 `cleanActressesAction(db *database.SQLiteStore, …)` 於 `:470` 呼叫 `ApplyToDatabase`，迴圈層確實沒有交易，每筆 `UpdateVideo`（`pkg/database/sqlite_runtime.go:117`）各自成交，中途失敗會留下部分套用狀態。實際緩解是 `db_cmd.go:458-464` 在寫入前先 `BackupCreate()`，而非交易 |

**掃描乾淨的範圍：** `pkg/app`、`pkg/cache`、`pkg/contracts`、`cmd/scanner`、`wails-app` —— 併發（WaitGroup／Mutex／context 取消）、快取原子性、資源生命週期、路徑穿越防護皆複查無缺陷。

---

## 建議處理順序

1. **P2 `generateUniqueName`** —— 將 `if !os.IsExist(err) { continue }` 改為在非 `ErrExist` 時終止並回報錯誤；同步調整 `error_paths_test.go:640`。
2. **P2 `export_json`** —— 改用 `safefile.WriteFile` 寫 temp 後 rename，與 `pkg/database/jsonfixture/jsondb.go:233-238` 一致。
3. **P3 `safefile.WriteFile`** —— 補 `Sync()`。
4. **P2 JSON 儲存層** —— 先確認是否仍有 runtime 呼叫者，再決定修正或標記為 deprecated。

**補充驗證建議：** 執行 `go test ./pkg/... ./cmd/...` 以取得動態證據，本輪未進行。
