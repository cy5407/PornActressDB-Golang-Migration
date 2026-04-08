# Wails 同路徑移動導致檔案被永久刪除

**日期**：2026-04-08  
**嚴重度**：🔴 高（資料永久遺失）

---

## 問題描述

當輸入目錄與輸出目錄**相同**時，對已分類過的檔案執行第二次「女優分類」，
會觸發衝突解決流程，若使用者選擇「覆蓋」，**原始檔案會被永久刪除**。

---

## 觸發路徑

```
設定：輸入目錄 = D:\Videos   輸出目錄 = D:\Videos

第一次移動（正常）
  src: D:\Videos\STARS-707.mp4
  dst: D:\Videos\田中夢乃\STARS-707.mp4  ✅ 成功

重新掃描（此時掃到新路徑）
  scanResults 現在包含：D:\Videos\田中夢乃\STARS-707.mp4

第二次移動（觸發 Bug）
  src: D:\Videos\田中夢乃\STARS-707.mp4
  dst: D:\Videos\田中夢乃\STARS-707.mp4   ← src == dst
  CheckConflicts 回傳：衝突（dst 存在）
  使用者選擇：覆蓋

replaceFileSafely(src, dst) 執行：
  1. copyFile(src, tmp)          ✅ 複製成功
  2. os.Rename(tmp, dst)         ✅ 覆蓋目標
  3. os.Remove(src)              💀 src == dst，刪除剛複製好的檔案！
```

---

## 根本原因

`replaceFileSafely` 在 `src == dst` 的情況下：

1. 先把 `src` 複製到暫存檔 `tmp`
2. 把 `tmp` Rename 覆蓋 `dst`（此時 src 已不見，因為 src==dst）
3. 呼叫 `os.Remove(src)` 刪除「來源」→ 實際上刪除的是剛蓋好的目標

`CheckConflicts` 也沒有排除 `src==dst` 的情況，導致偽衝突被回報給前端，
使用者被迫選擇處理方式。

---

## 修復方案

### 修復一：`pkg/mover/file_move.go` — 同路徑早期返回

```go
// MoveFile 最前方加入同路徑保護
absSrc, errSrc := filepath.Abs(src)
absDst, errDst := filepath.Abs(dst)
if errSrc == nil && errDst == nil && absSrc == absDst {
    result.Skipped, result.Success = true, true
    return result  // 不做任何操作，視為已完成
}
```

### 修復二：`wails-app/backend/app.go` — CheckConflicts 排除偽衝突

```go
func (a *App) CheckConflicts(items []MoveItemRequest) []ConflictItem {
    for _, item := range items {
        absSrc, errSrc := filepath.Abs(item.Source)
        absDst, errDst := filepath.Abs(item.Destination)
        if errSrc == nil && errDst == nil && absSrc == absDst {
            continue  // source == destination：不是真正衝突
        }
        if _, err := os.Stat(item.Destination); err == nil {
            conflicts = append(conflicts, ...)
        }
    }
}
```

> `filepath.Abs()` 確保相對路徑、大小寫差異（Windows 不分大小寫）不會造成誤判。

### 修復三：來源檔案刪除改走垃圾桶

即使未來有其他邏輯疏漏，至少來源檔案的刪除可以還原：

```go
// pkg/mover/recycle_windows.go
func recycleFile(path string) error {
    // 使用 SHFileOperationW + FOF_ALLOWUNDO 送入資源回收筒
    ...
}
```

`file_move.go` 中所有刪除**來源檔案**的 `os.Remove(src)` 改為 `recycleFile(src)`。

---

## 保留 os.Remove 的位置

以下位置**刻意不改**為垃圾桶，因為這些是刪除自己建立的暫存/失敗檔案：

```go
// copyFile 內部：寫入失敗時清理半成品目標檔
os.Remove(dst)   // ← 正確行為：清理 tmp 暫存

// Rename 失敗後清理暫存目標
os.Remove(tmpDst)  // ← 正確行為：清理 tmp 暫存
```

---

## 防護層次（修復後）

| 層次 | 位置 | 行為 |
|------|------|------|
| 1st | `CheckConflicts` | src==dst 不回報衝突，使用者看不到對話框 |
| 2nd | `MoveFile` 最前方 | src==dst 直接回傳 Skipped，不執行任何操作 |
| 3rd | `recycleFile` | 真正刪除來源時走垃圾桶，可還原 |

---

## 相關檔案

- `pkg/mover/file_move.go` — 同路徑保護 + recycleFile
- `pkg/mover/recycle_windows.go` — Windows 垃圾桶實作
- `pkg/mover/recycle_other.go` — 非 Windows fallback
- `pkg/mover/mover_test.go` — `TestMoveFile_SameSourceAndDestination`
- `wails-app/backend/app.go` — CheckConflicts 偽衝突排除

## 相關踩坑

- [wails-move-stale-paths.md](wails-move-stale-paths.md) — 移動後路徑未更新，重複移動會失敗
