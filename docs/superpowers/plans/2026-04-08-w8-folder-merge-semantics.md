# W8 Folder Merge Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將「同名女優資料夾」的行為改成 Windows 式資料夾合併：同名資料夾直接合併，只有同名檔案才做 `skip / overwrite / rename` 衝突處理。

**Architecture:** 後端 `MoveDir()` 不再把整個資料夾 rename 成 `ABC_1`，而是固定合併到既有目標資料夾；`rename` 僅套用在裡面的檔案衝突。前端片商分類流程則改成：新目標資料夾仍走 `BatchMoveDirs`，已存在的女優資料夾改展開成 file move items，重用既有的檔案衝突對話框與兩階段移動邏輯。

**Tech Stack:** Go 1.21+、Wails backend (`wails-app/backend/app.go`) 、React 18 + TypeScript (`wails-app/frontend/src/App.tsx`)、Go 單元測試 (`pkg/mover/mover_test.go`, `wails-app/backend/app_test.go`)、TypeScript 型別檢查 (`npx tsc --noEmit`)

---

## Scope

這份計畫針對你剛澄清的產品語意：

1. 來源有 `女優ABC`
2. 目標也有 `女優ABC`
3. 行為應該像 Windows：**合併同名資料夾**
4. 只有裡面的**同名檔案**才需要 `skip / overwrite / rename`
5. 不應把整個來源資料夾改名成 `女優ABC_1`

本計畫會修正：

- `pkg/mover/dir_move.go`：取消 whole-directory rename 語意
- `pkg/mover/batch.go`：directory batch 的結果與註解回到 merge 語意
- `wails-app/backend/app.go`：新增「把同名資料夾展開成檔案 move items」的 API
- `wails-app/frontend/src/App.tsx`：片商分類時，同名女優資料夾改走 file-level conflict flow
- `docs/plans/Tasks.md`：同步這份計畫

不在本計畫範圍內：

- 不改女優分類的單檔搬移流程
- 不新增前端測試框架（專案目前沒有 Vitest/Jest）
- 不重構整個 mover 套件

---

## Files

| 操作 | 檔案 | 說明 |
|------|------|------|
| Modify | `pkg/mover/dir_move.go` | 改回資料夾合併語意；資料夾不 rename，檔案衝突才吃策略 |
| Modify | `pkg/mover/batch.go` | 調整註解與 directory batch 結果，移除「whole-dir rename」假設 |
| Modify | `pkg/mover/mover_test.go` | 以測試固定「同名資料夾合併、同名檔案 rename」行為 |
| Modify | `wails-app/backend/app.go` | 新增 `PlanDirMergeMoves()`，把來源資料夾展開成 file move items |
| Modify | `wails-app/backend/app_test.go` | 補 `PlanDirMergeMoves()` 的測試 |
| Modify | `wails-app/frontend/src/App.tsx` | 同名女優資料夾改走 file-level conflict flow；不再把資料夾 rename 當成選項語意 |
| Modify | `wails-app/frontend/src/components/ConflictResolutionDialog.tsx` | 收斂 directory mode 文案，改回只描述「檔案衝突」 |
| Modify | `docs/plans/Tasks.md` | 加上未完成的 W8 merge 語意修正計畫 |

---

## Implementation Decisions

### 1. 同名女優資料夾 = merge，不 rename

`MoveDir(src, dst, Rename)` 在新的規格下，不再代表：

```text
dst = D:\SOD\ABC
rename -> D:\SOD\ABC_1
```

而是：

```text
dst = D:\SOD\ABC
來源 D:\Input\ABC 與目標 D:\SOD\ABC 合併
若裡面有同名檔案，才套用 Rename，產生 file_1.ext
```

### 2. 片商分類的「同名資料夾衝突」其實是「檔案衝突」

前端不應在目標資料夾已存在時，直接彈出 directory-level rename/overwrite 對話框。  
正確做法是：

- 新資料夾 → 直接 `BatchMoveDirs`
- 已存在的女優資料夾 → 展開成 file move items
- 然後重用既有 `executeMoveWithConflictHandling()`：
  - 先搬 non-conflict files
  - 再對 conflicting files 顯示檔案衝突對話框

### 3. 來源資料夾清除條件維持嚴格

只有在：

```go
result.Errors == 0
result.FilesSkipped == 0
os.RemoveAll(src) 成功
```

時，來源女優資料夾才算完整搬走。

---

### Task 1: 修正 `MoveDir` 回到資料夾合併語意

**Files:**
- Modify: `pkg/mover/mover_test.go`
- Modify: `pkg/mover/dir_move.go`

- [ ] **Step 1: 在 `pkg/mover/mover_test.go` 新增與更新失敗中的回歸測試**

```go
func TestMoveDir_ConflictRenameMergesIntoExistingDirectory(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "ABC")
	dstDir := filepath.Join(tempDir, "studio", "ABC")

	createTestFile(t, filepath.Join(srcDir, "new.txt"), "new")
	createTestFile(t, filepath.Join(dstDir, "existing.txt"), "existing")

	m := NewMover("")
	result := m.MoveDir(srcDir, dstDir, Rename)

	if !result.Success {
		t.Fatalf("MoveDir 應成功，errors=%v", result.Errors)
	}
	if result.DestDir != dstDir {
		t.Fatalf("DestDir = %s, want %s", result.DestDir, dstDir)
	}
	if !fileExists(filepath.Join(dstDir, "new.txt")) {
		t.Fatal("來源檔案應合併進既有女優資料夾")
	}
	if !fileExists(filepath.Join(dstDir, "existing.txt")) {
		t.Fatal("既有目標資料夾內容應保留")
	}
}

func TestMoveDir_ConflictRenameRenamesFilesNotDirectory(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "ABC")
	dstDir := filepath.Join(tempDir, "studio", "ABC")

	createTestFile(t, filepath.Join(srcDir, "same.txt"), "src")
	createTestFile(t, filepath.Join(dstDir, "same.txt"), "dst")

	m := NewMover("")
	result := m.MoveDir(srcDir, dstDir, Rename)

	if !result.Success {
		t.Fatalf("MoveDir 應成功，errors=%v", result.Errors)
	}
	if result.DestDir != dstDir {
		t.Fatalf("DestDir = %s, want %s", result.DestDir, dstDir)
	}
	if !fileExists(filepath.Join(dstDir, "same.txt")) {
		t.Fatal("原本既有檔案應保留")
	}
	if !fileExists(filepath.Join(dstDir, "same_1.txt")) {
		t.Fatal("來源同名檔案應改名後合併進目標資料夾")
	}
}

func TestBatchMoveDirs_RenameKeepsMergedDestination(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "Julia")
	dstDir := filepath.Join(tempDir, "studio", "Julia")

	createTestFile(t, filepath.Join(srcDir, "same.txt"), "src")
	createTestFile(t, filepath.Join(dstDir, "same.txt"), "dst")

	m := NewMover(tempDir)
	result := m.BatchMoveDirs(context.Background(), []MoveItem{
		{Source: srcDir, Destination: dstDir, OnConflict: Rename},
	})

	if len(result.Results) != 1 {
		t.Fatalf("len(results) = %d, want 1", len(result.Results))
	}
	if result.Results[0].Destination != dstDir {
		t.Fatalf("Destination = %s, want %s", result.Results[0].Destination, dstDir)
	}
	if !fileExists(filepath.Join(dstDir, "same_1.txt")) {
		t.Fatal("批次目錄移動應保留目標資料夾，僅改名衝突檔案")
	}
}
```

並將現有舊語意測試：

- `TestMoveDir_ConflictRenameRenamesWholeDirectory`
- `TestBatchMoveDirs_RenameStoresActualDestination`

改名並改斷言成新的 merge 語意，避免完整 `go test ./pkg/mover -v` 仍被舊期待卡住。

- [ ] **Step 2: 執行測試，確認目前會失敗**

Run:

```powershell
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration
go test ./pkg/mover -run "TestMoveDir_ConflictRename(MergesIntoExistingDirectory|RenamesFilesNotDirectory)" -v
```

Expected:

```text
FAIL
- DestDir 仍被改成 ABC_1
- 或來源檔案沒有合併進既有目標資料夾
```

- [ ] **Step 3: 在 `pkg/mover/dir_move.go` 移除 whole-directory rename 邏輯**

把目前這段：

```go
actualDst := dst
if strategy == Rename {
    if _, err := os.Stat(dst); err == nil {
        actualDst = m.generateUniqueDirName(dst)
    } else if err != nil && !os.IsNotExist(err) {
        ...
    }
}
result.DestDir = actualDst
```

改成：

```go
if _, err := os.Stat(dst); err != nil && !os.IsNotExist(err) {
    result.Errors = append(result.Errors, MoveResult{
        Source: src,
        Error:  fmt.Sprintf("無法檢查目標目錄: %v", err),
    })
    return result
}
result.DestDir = dst
actualDst := dst
```

並刪除 `generateUniqueDirName()` 整段 helper，讓 `Rename` 只透過 `MoveFile()` 的既有檔案 rename 機制生效。

- [ ] **Step 4: 重跑目標測試與完整 mover 測試**

Run:

```powershell
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration
go test ./pkg/mover -run "TestMoveDir_ConflictRename(MergesIntoExistingDirectory|RenamesFilesNotDirectory)" -v
go test ./pkg/mover -v
```

Expected:

```text
PASS
```

- [ ] **Step 5: Commit**

```bash
git add pkg/mover/dir_move.go pkg/mover/mover_test.go
git commit -m "fix(mover): merge same-name actress folders instead of renaming directories"
```

### Task 2: 新增 backend API，將同名資料夾展開成 file move items

**Files:**
- Modify: `wails-app/backend/app.go`
- Modify: `wails-app/backend/app_test.go`
- Modify: `wails-app/frontend/wailsjs/go/backend/App.d.ts`
- Modify: `wails-app/frontend/wailsjs/go/backend/App.js`

- [ ] **Step 1: 在 `wails-app/backend/app_test.go` 加入 `PlanDirMergeMoves()` 測試**

```go
func TestPlanDirMergeMoves(t *testing.T) {
    app := newTestApp(t)

    tempDir := t.TempDir()
    srcDir := filepath.Join(tempDir, "ABC")
    dstDir := filepath.Join(tempDir, "out", "SOD", "ABC")

    if err := os.MkdirAll(filepath.Join(srcDir, "sub"), 0o755); err != nil {
        t.Fatal(err)
    }
    if err := os.WriteFile(filepath.Join(srcDir, "video.mp4"), []byte("video"), 0o644); err != nil {
        t.Fatal(err)
    }
    if err := os.WriteFile(filepath.Join(srcDir, "sub", "note.txt"), []byte("note"), 0o644); err != nil {
        t.Fatal(err)
    }

    items := []DirMoveItem{
        {Source: srcDir, Destination: dstDir},
    }

    got := app.PlanDirMergeMoves(items)

    if len(got) != 2 {
        t.Fatalf("len(got) = %d, want 2", len(got))
    }
    want := map[string]string{
        filepath.Join(srcDir, "video.mp4"): filepath.Join(dstDir, "video.mp4"),
        filepath.Join(srcDir, "sub", "note.txt"): filepath.Join(dstDir, "sub", "note.txt"),
    }
    for _, item := range got {
        if want[item.Source] != item.Destination {
            t.Fatalf("unexpected mapping: %s -> %s", item.Source, item.Destination)
        }
    }
}
```

- [ ] **Step 2: 執行測試，確認目前失敗**

Run:

```powershell
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\wails-app
go test ./backend/... -run TestPlanDirMergeMoves -v
```

Expected:

```text
FAIL — undefined: (*App).PlanDirMergeMoves
```

- [ ] **Step 3: 在 `wails-app/backend/app.go` 新增 `PlanDirMergeMoves()` binding**

```go
func (a *App) PlanDirMergeMoves(items []DirMoveItem) []MoveItemRequest {
    results := make([]MoveItemRequest, 0)
    for _, item := range items {
        if err := filepath.Walk(item.Source, func(path string, info os.FileInfo, err error) error {
            if err != nil {
                return err
            }
            if info.IsDir() {
                return nil
            }
            rel, relErr := filepath.Rel(item.Source, path)
            if relErr != nil {
                return relErr
            }
            results = append(results, MoveItemRequest{
                Source:      path,
                Destination: filepath.Join(item.Destination, rel),
                OnConflict:  item.OnConflict,
            })
            return nil
        }); err != nil {
            a.logger.Printf("⚠️ PlanDirMergeMoves walk failed: %s -> %s (%v)", item.Source, item.Destination, err)
        }
    }
    return results
}
```

> 保持 `MoveItemRequest` 形狀，這樣前端可以直接交給既有 `CheckConflicts()` / `BatchMove()` / `executeMoveWithConflictHandling()`。

- [ ] **Step 4: 重新產生 Wails bindings，並重跑 backend 測試**

Run:

```powershell
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\wails-app
wails generate module
go test ./backend/... -run TestPlanDirMergeMoves -v
go build ./backend/...
```

Expected:

```text
PASS
```

- [ ] **Step 5: Commit**

```bash
git add wails-app/backend/app.go wails-app/backend/app_test.go wails-app/frontend/wailsjs/go/backend/App.d.ts wails-app/frontend/wailsjs/go/backend/App.js
git commit -m "feat(backend): expose planned file moves for directory merges"
```

### Task 3: 前端片商分類改成「新資料夾走 BatchMoveDirs、同名資料夾走 file conflict flow」

**Files:**
- Modify: `wails-app/frontend/src/App.tsx`
- Modify: `wails-app/frontend/src/components/ConflictResolutionDialog.tsx`
- Modify: `docs/plans/Tasks.md`

- [ ] **Step 1: 在 `App.tsx` 將同名資料夾拆成 mergeDirs，並呼叫 `PlanDirMergeMoves()`**

在 import 區補上：

```ts
import {
  ScanDirectory,
  BatchSearch,
  BatchMove,
  BatchMoveDirs,
  PlanDirMergeMoves,
  CheckDirConflicts,
  CancelOperation,
  GetActressPrimaryStudios,
  GetStudiosByCodes,
  CheckConflicts,
} from '../wailsjs/go/backend/App';
```

在 `handleStudioMove()` 中，把：

```ts
const conflicts = await CheckDirConflicts(dirItems);
```

後續流程改成：

```ts
const dirConflicts = await CheckDirConflicts(dirItems);
const mergeDirKeys = new Set(dirConflicts.map((c) => normalizeDirKey(c.destination)));

const cleanDirItems = dirItems.filter((i) => !mergeDirKeys.has(normalizeDirKey(i.destination)));
const mergeDirItems = dirItems.filter((i) => mergeDirKeys.has(normalizeDirKey(i.destination)));
```

- [ ] **Step 2: 新資料夾繼續用 `BatchMoveDirs`，同名資料夾改展開成 file move items**

```ts
let dirBatchResult = emptyBatchResult();
if (cleanDirItems.length > 0) {
  pushEvent('info', `📦 先移動 ${cleanDirItems.length} 個全新女優資料夾…`);
  dirBatchResult = await BatchMoveDirs(cleanDirItems, conflictStrategy);
}

let mergeFileResult = emptyBatchResult();
if (mergeDirItems.length > 0) {
  pushEvent('info', `📂 發現 ${mergeDirItems.length} 個同名女優資料夾，改用資料夾合併模式…`);
  const mergeMoveItems = await PlanDirMergeMoves(mergeDirItems);
  mergeFileResult = await executeMoveWithConflictHandling(
    mergeMoveItems.map((i) => ({
      source: i.source,
      destination: i.destination,
      on_conflict: i.on_conflict || conflictStrategy,
    }))
  );
}

const result = mergeBatchResults(
  dirItems.length,
  dirBatchResult,
  mergeFileResult
);
```

- [ ] **Step 3: 更新 scanResults 清除邏輯**

只有完整資料夾 batch 成功的項目才直接移除整個資料夾；  
merge mode 的 file moves 只移除已完成搬移的那些檔案，保留來源仍殘留 skipped 檔案的女優資料夾。

```ts
if (dirBatchResult.results) {
  const movedDirs = new Set(
    dirBatchResult.results
      .filter((r) => r.success && !r.skipped)
      .map((r) => normalizeDirKey(r.source))
  );
  setScanResults(removeMovedDirectories(useTaskStore.getState().scanResults, movedDirs));
}

if (mergeFileResult.results) {
  const movedFiles = new Set(
    mergeFileResult.results
      .filter((r) => r.success && !r.skipped)
      .map((r) => normalizeDirKey(r.source))
  );
  setScanResults(
    useTaskStore.getState().scanResults.filter((r) => !movedFiles.has(normalizeDirKey(r.path)))
  );
}
```

- [ ] **Step 4: 收斂 `ConflictResolutionDialog.tsx` 文案**

把 directory mode 的重點改成：

```tsx
{itemKind === 'directory'
  ? ' 同名資料夾會直接合併；只有其中的同名檔案才會套用你選的衝突策略。'
  : ' 會永久取代目的地的同名檔案。'}
```

並移除或停用「整個資料夾重新命名（例如 Julia_1）」這類文案，避免再次誤導。

- [ ] **Step 5: 更新 `docs/plans/Tasks.md`**

在最上方新增一節：

```md
## W8 同名女優資料夾合併語意修正（待實作）

- [ ] 同名女優資料夾不再整個 rename，改為直接合併
- [ ] `rename` 僅套用在資料夾內部的同名檔案
- [ ] 片商分類的同名資料夾改走 file-level conflict flow
- [ ] Wails backend 新增 `PlanDirMergeMoves()` binding
- [ ] 前端 summary / `lastBatchResult` / `scanResults` 維持正確
```

- [ ] **Step 6: 執行驗證**

Run:

```powershell
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration
go test ./pkg/mover -v

cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\wails-app
go test ./backend/... -v
go build ./backend/...

cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\wails-app\frontend
npx tsc --noEmit
```

手動驗證：

1. 來源有 `ABC\new.txt`，目標已有 `ABC\existing.txt` → 最終應是 `ABC\existing.txt + new.txt`
2. 來源與目標皆有 `ABC\same.txt`，選 `rename` → 最終應是 `ABC\same.txt + same_1.txt`
3. 選 `skip` → skipped 檔案留在來源資料夾，其餘檔案已搬走
4. 片商分類 summary / `lastBatchResult` 仍正確合併 new-dir batch 與 merge-file batch

- [ ] **Step 7: Commit**

```bash
git add wails-app/frontend/src/App.tsx wails-app/frontend/src/components/ConflictResolutionDialog.tsx docs/plans/Tasks.md
git commit -m "fix(frontend): merge same-name actress folders using file-level conflicts"
```

---

## Self-Review

### Spec coverage

- 同名女優資料夾不 rename → Task 1
- 同名檔案才吃 `skip / overwrite / rename` → Task 1 + Task 3
- 片商分類比照 Windows 同名資料夾移動 → Task 2 + Task 3
- `Tasks.md` 要寫出來 → Task 3, Step 5

沒有遺漏你剛剛澄清的產品語意。

### Placeholder scan

- 沒有 `TBD` / `TODO`
- 所有程式碼步驟都有實際 code block
- 所有驗證步驟都有具體命令

### Type consistency

- Go backend 新 API 固定使用 `[]MoveItemRequest`
- 前端繼續重用既有 `executeMoveWithConflictHandling()`
- 沒有引入新的前端測試框架或未定義型別
