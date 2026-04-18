# W8 Directory Move Follow-up Bugfix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修復 W8 片商分類後續的 6 個目錄移動問題，讓女優資料夾移動在資料安全、衝突處理、根目錄防護與前端結果顯示上都一致可靠。

**Architecture:** 這次修復把「目錄移動是否完成」的判準統一成：**只有來源資料夾已完全清空並刪除，才算整個女優資料夾移動完成**。Go `MoveDir()` 會改成真正遞迴建立子目錄、保留空資料夾、在 `rename` 衝突策略下改名整個目標資料夾，且只要來源還殘留 skipped 檔案就絕不刪除來源；前端 `handleStudioMove()` 會改成先正規化路徑避免把 `inputDir` 當女優資料夾搬走，並像檔案移動流程一樣合併兩階段批次結果。

**Tech Stack:** Go 1.21+、Wails backend (`wails-app/backend/app.go`)、React 18 + TypeScript + Zustand (`wails-app/frontend/src/App.tsx`)、既有 Go 單元測試 (`pkg/mover/mover_test.go`)、TypeScript 型別檢查 (`npx tsc --noEmit`)

---

## Scope

本計畫覆蓋以下 issue：

- `D1`：部分 moved + 部分 skipped 時仍會刪來源目錄
- `D8`：`MoveDir` 不保留空子目錄
- `D9`：部分完成的女優資料夾被前端當成完整成功而從列表移除
- `D10`：`inputDir` / `scanResults` 路徑分隔符不一致時，可能把整個輸入根目錄搬走
- `D11`：目錄衝突的 `rename` UI/後端語意不一致
- `D12`：兩階段目錄移動最後只回報第二批衝突結果

不在本計畫範圍內：

- 不重構整個 mover package
- 不新增前端單元測試框架（目前專案沒有 Vitest/Jest）
- 不改動與本次問題無關的 Go/Wails API

---

## Files

| 操作 | 檔案 | 說明 |
|------|------|------|
| Modify | `pkg/mover/dir_move.go` | 重新定義目錄移動流程：保留空子目錄、真正的資料夾 rename、只在完整搬空時刪來源 |
| Modify | `pkg/mover/batch.go` | 讓目錄批次結果以「資料夾是否完整移走」決定 success/skipped，並記錄實際目的地 |
| Modify | `pkg/mover/mover_test.go` | 加入目錄移動/批次目錄移動/rename 回歸測試 |
| Modify | `wails-app/frontend/src/App.tsx` | 新增路徑正規化 helper、合併兩階段目錄移動結果、只移除完整搬走的女優資料夾 |
| Modify | `wails-app/frontend/src/components/ConflictResolutionDialog.tsx` | 讓共用衝突對話框能區分檔案/資料夾情境，說明 directory rename 的真實行為 |
| Modify | `docs/plans/Tasks.md` | 補上這批問題的實作/驗證狀態 |
| Modify | `security_reports/code_review_tracking.md` | 將 D1/D8/D9/D10/D11/D12 的修復狀態從待處理更新為已完成 |

---

## Implementation Decisions

### 1. 目錄批次項目的完成定義

一個 `BatchMoveDirs` item 只有在下列條件全部成立時才算完整成功：

```go
mr.Success && mr.FilesSkipped == 0 && mr.DeletedSrc
```

只要來源目錄仍然存在（例如部分檔案 skip），整個女優資料夾就仍屬於「未完整搬走」，前端不能把它從 `scanResults` 移除。

### 2. directory rename 的語意

這次不採用「合併到既有資料夾後，把衝突檔案逐一 rename」。
改成真正對目標資料夾改名，例如：

```text
原目標：C:\AV\S1\Julia
rename 後：C:\AV\S1\Julia_1
```

這樣才和 UI 的「重新命名」文案一致，也更符合「整個女優資料夾移動」需求。

### 3. Windows 路徑比較

前端只用字串比較目錄時，必須先正規化：

```ts
function normalizeDirKey(p: string): string {
  return p.replace(/\//g, '\\').replace(/[\\]+$/, '').toLowerCase();
}
```

用這個 key 比較 `inputDir`、`parentDir(r.path)`、`movedDirs`，避免 `/` 與 `\` 導致誤判。

---

### Task 1: 修復 `MoveDir` 的資料安全與整個資料夾語意

**Files:**
- Modify: `pkg/mover/mover_test.go`
- Modify: `pkg/mover/dir_move.go`

- [ ] **Step 1: 在 `pkg/mover/mover_test.go` 加入 3 個失敗中的回歸測試**

```go
func TestMoveDir_PartialSkipKeepsSource(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "source")
	dstDir := filepath.Join(tempDir, "dest")

	createTestFile(t, filepath.Join(srcDir, "a.txt"), "A")
	createTestFile(t, filepath.Join(srcDir, "b.txt"), "B-src")
	createTestFile(t, filepath.Join(dstDir, "b.txt"), "B-dst")

	m := NewMover("")
	result := m.MoveDir(srcDir, dstDir, Skip)

	if !result.Success {
		t.Fatalf("MoveDir 應成功，errors=%v", result.Errors)
	}
	if result.FilesMoved != 1 {
		t.Fatalf("FilesMoved = %d, want 1", result.FilesMoved)
	}
	if result.FilesSkipped != 1 {
		t.Fatalf("FilesSkipped = %d, want 1", result.FilesSkipped)
	}
	if result.DeletedSrc {
		t.Fatal("來源目錄不應被刪除，因為仍有 skipped 檔案留在來源")
	}
	if !fileExists(filepath.Join(srcDir, "b.txt")) {
		t.Fatal("skipped 的來源檔案必須保留")
	}
}

func TestMoveDir_PreservesEmptySubdirs(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "source")
	dstDir := filepath.Join(tempDir, "dest")

	if err := os.MkdirAll(filepath.Join(srcDir, "empty", "nested"), 0755); err != nil {
		t.Fatal(err)
	}
	createTestFile(t, filepath.Join(srcDir, "has-file", "video.txt"), "ok")

	m := NewMover("")
	result := m.MoveDir(srcDir, dstDir, Skip)

	if !result.Success {
		t.Fatalf("MoveDir 應成功，errors=%v", result.Errors)
	}
	if _, err := os.Stat(filepath.Join(dstDir, "empty", "nested")); err != nil {
		t.Fatalf("空子目錄應該被保留到目標: %v", err)
	}
}

func TestMoveDir_ConflictRenameRenamesWholeDirectory(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "Julia")
	dstDir := filepath.Join(tempDir, "studio", "Julia")

	createTestFile(t, filepath.Join(srcDir, "a.txt"), "src")
	createTestFile(t, filepath.Join(dstDir, "existing.txt"), "dst")

	m := NewMover("")
	result := m.MoveDir(srcDir, dstDir, Rename)

	wantRenamedDir := filepath.Join(tempDir, "studio", "Julia_1")
	if !result.Success {
		t.Fatalf("Rename 應成功，errors=%v", result.Errors)
	}
	if result.DestDir != wantRenamedDir {
		t.Fatalf("DestDir = %s, want %s", result.DestDir, wantRenamedDir)
	}
	if !fileExists(filepath.Join(wantRenamedDir, "a.txt")) {
		t.Fatal("來源檔案應該移進改名後的資料夾")
	}
	if !fileExists(filepath.Join(dstDir, "existing.txt")) {
		t.Fatal("原本已存在的目標資料夾應保留不變")
	}
}
```

- [ ] **Step 2: 執行測試確認目前會失敗**

Run:

```powershell
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration
go test ./pkg/mover -run "TestMoveDir_(PartialSkipKeepsSource|PreservesEmptySubdirs|ConflictRenameRenamesWholeDirectory)" -v
```

Expected:

```text
FAIL
- PartialSkipKeepsSource: result.DeletedSrc 為 true 或來源檔案消失
- PreservesEmptySubdirs: 目標空資料夾不存在
- ConflictRenameRenamesWholeDirectory: DestDir 仍是原目標，或檔案被合併進既有資料夾
```

- [ ] **Step 3: 在 `pkg/mover/dir_move.go` 實作真正的目錄級移動**

```go
func (m *Mover) MoveDir(src, dst string, strategy ConflictStrategy) MergeResult {
	result := MergeResult{SourceDir: src, DestDir: dst}

	srcInfo, err := os.Stat(src)
	if os.IsNotExist(err) {
		result.Errors = append(result.Errors, MoveResult{Source: src, Error: "來源目錄不存在"})
		return result
	}
	if err != nil || !srcInfo.IsDir() {
		result.Errors = append(result.Errors, MoveResult{Source: src, Error: "來源不是目錄"})
		return result
	}

	actualDst := dst
	if dstInfo, err := os.Stat(dst); err == nil && dstInfo.IsDir() && strategy == Rename {
		actualDst = m.generateUniqueDirName(dst)
	}
	result.DestDir = actualDst

	walkErr := filepath.Walk(src, func(path string, info os.FileInfo, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		rel, _ := filepath.Rel(src, path)
		target := filepath.Join(actualDst, rel)

		if info.IsDir() {
			if path == src {
				if !m.DryRun {
					return os.MkdirAll(actualDst, 0700)
				}
				return nil
			}
			if !m.DryRun {
				return os.MkdirAll(target, 0700)
			}
			return nil
		}

		result.FilesTotal++
		moveResult := m.MoveFile(path, target, strategy)
		if moveResult.Success {
			if moveResult.Skipped {
				result.FilesSkipped++
			} else {
				result.FilesMoved++
			}
			return nil
		}
		result.Errors = append(result.Errors, moveResult)
		return nil
	})
	if walkErr != nil {
		result.Errors = append(result.Errors, MoveResult{Source: src, Error: fmt.Sprintf("掃描目錄失敗: %v", walkErr)})
	}

	if !m.DryRun && len(result.Errors) == 0 && result.FilesSkipped == 0 {
		if err := os.RemoveAll(src); err == nil {
			result.DeletedSrc = true
		}
	}

	result.Success = len(result.Errors) == 0
	return result
}

func (m *Mover) generateUniqueDirName(path string) string {
	dir := filepath.Dir(path)
	base := filepath.Base(path)
	for i := 1; i <= generateUniqueNameMaxAttempts; i++ {
		candidate := filepath.Join(dir, fmt.Sprintf("%s_%d", base, i))
		if _, err := os.Stat(candidate); os.IsNotExist(err) {
			return candidate
		}
	}
	return filepath.Join(dir, fmt.Sprintf("%s_%s", base, time.Now().Format("20060102150405")))
}
```

- [ ] **Step 4: 重新執行目標測試確認通過**

Run:

```powershell
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration
go test ./pkg/mover -run "TestMoveDir_(PartialSkipKeepsSource|PreservesEmptySubdirs|ConflictRenameRenamesWholeDirectory)" -v
```

Expected:

```text
PASS
```

- [ ] **Step 5: Commit**

```bash
git add pkg/mover/dir_move.go pkg/mover/mover_test.go
git commit -m "fix(mover): make directory moves safe and preserve folder semantics"
```

### Task 2: 讓 `BatchMoveDirs` 只把「完整搬走的資料夾」當成功

**Files:**
- Modify: `pkg/mover/mover_test.go`
- Modify: `pkg/mover/batch.go`

- [ ] **Step 1: 在 `pkg/mover/mover_test.go` 加入批次目錄移動回歸測試**

```go
func TestBatchMoveDirs_PartialDirectoryMarkedSkipped(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "Julia")
	dstDir := filepath.Join(tempDir, "studio", "Julia")

	createTestFile(t, filepath.Join(srcDir, "a.txt"), "A")
	createTestFile(t, filepath.Join(srcDir, "b.txt"), "B-src")
	createTestFile(t, filepath.Join(dstDir, "b.txt"), "B-dst")

	m := NewMover(tempDir)
	result := m.BatchMoveDirs(context.Background(), []MoveItem{
		{Source: srcDir, Destination: dstDir, OnConflict: Skip},
	})

	if result.SuccessCount != 0 {
		t.Fatalf("SuccessCount = %d, want 0", result.SuccessCount)
	}
	if result.SkippedCount != 1 {
		t.Fatalf("SkippedCount = %d, want 1", result.SkippedCount)
	}
	if len(result.Results) != 1 || !result.Results[0].Skipped {
		t.Fatalf("目錄項目應標記為 skipped/incomplete")
	}
}

func TestBatchMoveDirs_RenameStoresActualDestination(t *testing.T) {
	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	srcDir := filepath.Join(tempDir, "Julia")
	dstDir := filepath.Join(tempDir, "studio", "Julia")

	createTestFile(t, filepath.Join(srcDir, "a.txt"), "src")
	createTestFile(t, filepath.Join(dstDir, "existing.txt"), "dst")

	m := NewMover(tempDir)
	result := m.BatchMoveDirs(context.Background(), []MoveItem{
		{Source: srcDir, Destination: dstDir, OnConflict: Rename},
	})

	wantActualDst := filepath.Join(tempDir, "studio", "Julia_1")
	if len(result.Results) != 1 {
		t.Fatalf("len(results) = %d, want 1", len(result.Results))
	}
	if result.Results[0].Destination != wantActualDst {
		t.Fatalf("Destination = %s, want %s", result.Results[0].Destination, wantActualDst)
	}
}
```

- [ ] **Step 2: 執行測試確認目前失敗**

Run:

```powershell
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration
go test ./pkg/mover -run "TestBatchMoveDirs_(PartialDirectoryMarkedSkipped|RenameStoresActualDestination)" -v
```

Expected:

```text
FAIL
- PartialDirectoryMarkedSkipped: SuccessCount 仍為 1 或 results[0].Skipped == false
- RenameStoresActualDestination: results[0].Destination 仍是原始 dst
```

- [ ] **Step 3: 在 `pkg/mover/batch.go` 讓批次結果以資料夾完整性為準，並記錄實際目的地**

```go
mr := m.MoveDir(item.Source, item.Destination, strategy)
moveResult := MoveResult{
	Source:      item.Source,
	Destination: mr.DestDir,
	Success:     mr.Success,
}
if mr.DestDir != item.Destination {
	moveResult.Renamed = mr.DestDir
}

dirFullyMoved := mr.Success && mr.FilesSkipped == 0 && mr.DeletedSrc

switch {
case !mr.Success:
	result.FailedCount++
	moveResult.Error = firstDirError(mr)
	opLog.Items[i].Status = "failed"
	opLog.Items[i].Error = moveResult.Error
case dirFullyMoved:
	result.SuccessCount++
	opLog.Items[i].Status = "success"
	opLog.Items[i].Destination = mr.DestDir
default:
	result.SkippedCount++
	moveResult.Skipped = true
	opLog.Items[i].Status = "skipped"
	opLog.Items[i].Destination = mr.DestDir
}
result.Results = append(result.Results, moveResult)
```

> `firstDirError(mr)` 可以是 `batch.go` 內的小 helper，避免重複組裝錯誤字串。

- [ ] **Step 4: 執行目標測試與既有 mover 測試**

Run:

```powershell
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration
go test ./pkg/mover -run "Test(BatchMoveDirs_(PartialDirectoryMarkedSkipped|RenameStoresActualDestination)|MoveDir_.*|Rollback_.*)" -v
```

Expected:

```text
PASS
```

- [ ] **Step 5: Commit**

```bash
git add pkg/mover/batch.go pkg/mover/mover_test.go
git commit -m "fix(mover): treat incomplete directory batches as skipped"
```

### Task 3: 修復前端 `handleStudioMove` 的根目錄防護與兩階段結果合併

**Files:**
- Modify: `wails-app/frontend/src/App.tsx`

- [ ] **Step 1: 在 `App.tsx` 抽出 3 個 helper，先讓程式碼有可重用的判斷基礎**

```ts
function normalizeDirKey(p: string): string {
  return p.replace(/\//g, '\\').replace(/[\\]+$/, '').toLowerCase();
}

function mergeBatchResults(
  totalItems: number,
  first: mover.BatchResult,
  second: mover.BatchResult
): mover.BatchResult {
  return mover.BatchResult.createFrom({
    operation_id: second.operation_id || first.operation_id,
    total_items: totalItems,
    success_count: (first.success_count ?? 0) + (second.success_count ?? 0),
    failed_count: (first.failed_count ?? 0) + (second.failed_count ?? 0),
    skipped_count: (first.skipped_count ?? 0) + (second.skipped_count ?? 0),
    results: [...(first.results ?? []), ...(second.results ?? [])],
    status: second.status || first.status,
    summary: second.summary || first.summary,
    duration: second.duration || first.duration,
  });
}

function removeMovedDirectories(
  allResults: backend.ScanResult[],
  movedDirs: Set<string>
): backend.ScanResult[] {
  return allResults.filter((r) => !movedDirs.has(normalizeDirKey(parentDir(r.path))));
}
```

- [ ] **Step 2: 用正規化後的 key 保護 `inputDir`，避免搬走整個輸入根目錄**

```ts
const inputDirKey = normalizeDirKey(inputDir);

for (const r of targets) {
  const folder = parentDir(r.path);
  if (normalizeDirKey(folder) === inputDirKey) {
    rootLevelCodes.push(r.code);
    continue;
  }
  if (!folderToCodes.has(folder)) folderToCodes.set(folder, []);
  folderToCodes.get(folder)!.push(r.code);
}
```

- [ ] **Step 3: 讓目錄衝突流程像 `executeMoveWithConflictHandling()` 一樣合併 partial + conflict 結果**

```ts
let partialResult = mover.BatchResult.createFrom({
  operation_id: '',
  total_items: 0,
  success_count: 0,
  failed_count: 0,
  skipped_count: 0,
  results: [],
  status: '',
  summary: '',
  duration: '',
});

if (nonConflictItems.length > 0) {
  partialResult = await BatchMoveDirs(nonConflictItems, conflictStrategy);
  if (partialResult.results) {
    const movedDirs = new Set(
      partialResult.results
        .filter((r) => r.success && !r.skipped)
        .map((r) => normalizeDirKey(r.source))
    );
    setScanResults(removeMovedDirectories(useTaskStore.getState().scanResults, movedDirs));
  }
}

const conflictResult = await BatchMoveDirs(finalDirItems, conflictStrategy);
const result = mergeBatchResults(dirItems.length, partialResult, conflictResult);
```

- [ ] **Step 4: 只在資料夾完整搬走時才從畫面移除**

```ts
if (result.results) {
  const movedDirs = new Set(
    result.results
      .filter((r) => r.success && !r.skipped)
      .map((r) => normalizeDirKey(r.source))
  );
  setScanResults(removeMovedDirectories(useTaskStore.getState().scanResults, movedDirs));
}
setLastBatchResult(result);
```

- [ ] **Step 5: 執行前端/後端編譯驗證**

Run:

```powershell
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\wails-app
go build ./backend/...

cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\wails-app\frontend
npx tsc --noEmit
```

Expected:

```text
兩個指令都 exit code 0
```

- [ ] **Step 6: Commit**

```bash
git add wails-app/frontend/src/App.tsx
git commit -m "fix(frontend): merge studio move batches and normalize directory guards"
```

### Task 4: 對齊目錄衝突對話框文案，並補齊追蹤文件

**Files:**
- Modify: `wails-app/frontend/src/App.tsx`
- Modify: `wails-app/frontend/src/components/ConflictResolutionDialog.tsx`
- Modify: `docs/plans/Tasks.md`
- Modify: `security_reports/code_review_tracking.md`

- [ ] **Step 1: 讓衝突對話框能區分 file / directory 模式**

```ts
interface ConflictResolutionDialogProps {
  open: boolean;
  conflictItems: ConflictItem[];
  movedCount: number;
  itemKind?: 'file' | 'directory';
  onConfirm: (strategies: Record<string, ConflictStrategy>) => void;
  onCancel: () => void;
}

export function ConflictResolutionDialog({
  open,
  conflictItems,
  movedCount,
  itemKind = 'file',
  onConfirm,
  onCancel,
}: ConflictResolutionDialogProps) {
  const itemLabel = itemKind === 'directory' ? '資料夾' : '檔案';
```

- [ ] **Step 2: 在資料夾模式下調整標題/欄位/說明文字**

```tsx
title={`⚠️ 發現 ${conflictItems.length} 個${itemLabel}衝突`}
description={
  movedCount > 0
    ? `其他 ${movedCount} 個${itemLabel}已完成移動。以下${itemLabel}的目的地已存在，請選擇處理方式：`
    : `以下 ${conflictItems.length} 個${itemLabel}的目的地已存在，請選擇處理方式：`
}

<th>{itemKind === 'directory' ? '來源資料夾' : '來源檔名'}</th>

<span>
  <span className="text-red-400 font-medium">覆蓋</span>
  {itemKind === 'directory'
    ? ' 會將來源資料夾內容覆蓋到既有目標資料夾。'
    : ' 會永久取代目的地的同名檔案。'}
  <span className="text-amber-400 font-medium ml-2">重新命名</span>
  {itemKind === 'directory'
    ? ' 會把整個來源資料夾改名後再移動（例如 Julia_1）。'
    : ' 會自動在檔名後加上數字後綴。'}
</span>
```

- [ ] **Step 3: 在 `App.tsx` 中為片商分類衝突流程傳入 `itemKind="directory"`**

```tsx
<ConflictResolutionDialog
  open={conflictDialogOpen}
  conflictItems={conflictItems}
  movedCount={movedCount}
  itemKind={conflictDialogMode}
  onConfirm={handleConflictConfirm}
  onCancel={handleConflictCancel}
/>
```

```ts
const [conflictDialogMode, setConflictDialogMode] = useState<'file' | 'directory'>('file');

async function waitForConflictResolution(
  conflicts: ConflictItem[],
  movedCount: number,
  mode: 'file' | 'directory' = 'file'
) {
  setConflictDialogMode(mode);
  setConflictItems(conflicts);
  setMovedCount(movedCount);
  setConflictDialogOpen(true);
  return new Promise<Record<string, ConflictStrategy> | null>((resolve) => {
    conflictResolveRef.current = resolve;
  });
}
```

- [ ] **Step 4: 更新任務/追蹤文件**

在 `docs/plans/Tasks.md` 補一段本次修復項目，例如：

```md
## W8 片商分類後續修復

- [x] D1：部分 moved + skipped 不再刪除來源
- [x] D8：MoveDir 保留空子目錄
- [x] D9：部分完成的女優資料夾不再從 scanResults 提前移除
- [x] D10：inputDir 根目錄比較改用正規化路徑
- [x] D11：directory rename 改成整個資料夾改名，UI 文案同步
- [x] D12：兩階段目錄移動結果合併到最終 summary / lastBatchResult
```

在 `security_reports/code_review_tracking.md` 將這 6 個 issue 的狀態改成已修復，附上實際 commit hash。

- [ ] **Step 5: 執行最終驗證**

Run:

```powershell
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration
go test ./pkg/mover -v

cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\wails-app
go build ./backend/...

cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\wails-app\frontend
npx tsc --noEmit
```

手動驗證：

1. 以手動輸入 `C:/Users/.../AV` 作為 `inputDir`，掃描根目錄檔案後按「片商分類」，確認不會搬走整個 inputDir。
2. 準備已存在的 `S1\Julia`，再搬另一個 `Julia` 女優資料夾並選 `rename`，確認產生 `S1\Julia_1`。
3. 製造部分 skip 的資料夾衝突，確認畫面 summary 會顯示 skipped，且該女優資料夾仍留在列表。
4. 製造「先搬無衝突，再搬衝突」情境，確認最終 summary 與 `lastBatchResult` 包含兩批結果。

- [ ] **Step 6: Commit**

```bash
git add wails-app/frontend/src/App.tsx wails-app/frontend/src/components/ConflictResolutionDialog.tsx docs/plans/Tasks.md security_reports/code_review_tracking.md
git commit -m "fix(w8): align directory conflict flow and tracking docs"
```

---

## Self-Review

### Spec coverage

- D1：Task 1
- D8：Task 1
- D9：Task 2 + Task 3
- D10：Task 3
- D11：Task 1 + Task 4
- D12：Task 3

沒有遺漏需求。

### Placeholder scan

- 沒有使用 `TBD`、`TODO`、`implement later`
- 每個修改步驟都有具體程式碼片段
- 每個驗證步驟都有精確命令

### Type consistency

- Go 端仍沿用 `MoveResult` / `MergeResult` / `BatchResult`
- 前端仍沿用 `mover.BatchResult.createFrom(...)`
- `itemKind` 僅新增到 `ConflictResolutionDialog` props，不改動既有 `ConflictItem` 型別

