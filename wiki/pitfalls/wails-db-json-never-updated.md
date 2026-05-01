---
category: Wails
date: 2026-04-08
---
# Wails DB data.json 從未更新

> 歸檔日期：2026-04-07

---

## 症狀

- 搜尋完成後，`data.journal` 有內容、`data.index` 有更新，但 `data.json` 永遠是舊的（空資料庫或初始狀態）
- 理論上快取應命中的番號（前一輪已搜尋），下一輪還是重新發 HTTP 請求
- 快取機制從頭到尾完全失效

---

## 根本原因

Wails backend (`app.go`) 的 `BatchSearch()` 在每筆搜尋完成後呼叫了 `AddVideo()`，但**從未呼叫 `CompactIfNeeded()` 或 `Compact()`**。

DB 的三檔結構：

| 檔案 | 寫入時機 |
|------|---------|
| `data.journal` | `AddVideo()` 每次呼叫立即 append |
| `data.index` | `AddVideo()` 每次呼叫立即更新 |
| `data.json` | **只在 `Compact()` 時合併寫入** |

`CompactIfNeeded()` 的觸發條件（任一即觸發）：
- journal 累積 ≥ **1000 筆**
- journal 建立後 ≥ **1 小時**（timestamp 存在 data.index，跨重啟保留）

正常使用每次搜尋 63 筆，永遠不會到 1000 筆；程式不持續開著也不會到 1 小時。因此 `data.json` 永遠不會更新，快取完全無效。

---

## 修正做法（完整版）

**三個地方都需要補上 compact 呼叫**，缺一不可：

### 1. `BatchSearch()` 結束後強制 compact
```go
// wails-app/backend/app.go — BatchSearch() 末尾
cmd.Wait()

// 搜尋完成後強制 compact：無論 journal 大小，立即合併進 data.json
if a.db != nil {
    _ = a.db.Compact()
}
```

### 2. `BatchSearch()` 全快取命中早期返回路徑（原本缺少）
```go
// 全部都在快取中
if len(codesToSearch) == 0 {
    // journal 有未合併資料時，趁機寫入 data.json
    if a.db != nil {
        _, _ = a.db.CompactIfNeeded()
    }
    ...
    return results
}
```

### 3. `ensureDB()` 啟動時（原本缺少）
```go
func (a *App) ensureDB() {
    ...
    _ = a.db.Load(context.Background())
    // 啟動時若 journal 有未合併資料，立即寫入 data.json
    _, _ = a.db.CompactIfNeeded()
}
```

> **修 1** 處理正常搜尋流程。  
> **修 2** 處理「全部命中快取」的早期返回，這是原本 bug 的核心路徑。  
> **修 3** 處理 App 啟動時 journal 有殘留資料的情況（防禦性）。

---

## 快取生效流程（修復後）

```
第一次搜尋 63 筆
  → 每筆寫入 data.journal（立即）
  → BatchSearch 結束 → Compact() 強制執行
  → data.json 更新（含 63 筆記錄）✅

重啟 App，第二次搜尋同 63 筆
  → ensureDB() Load() 讀取 data.json（63 筆已在 data.json）
  → CompactIfNeeded()：journal 為空，無需 compact
  → BatchSearch 過濾：63 筆全部命中 → codesToSearch = []
  → CompactIfNeeded()（早期返回路徑）：journal 為空，略過
  → 0 筆 HTTP 請求，63 筆直接從快取回傳 ✅
```

---

## 注意事項

- `data.json` 的 1 小時計時器是**跨重啟保留**的（timestamp 存在 data.index），不是「程式開著一小時」
- 修 1 使用 `Compact()`（強制），修 2/3 使用 `CompactIfNeeded()`（條件）
- commits: `ad7d278`（2026-04-08）

---

## 驗證 fix 是否在你的 build

```powershell
# 三處 Compact 呼叫都應命中
Select-String "a\.db\.Compact\(\)|a\.db\.CompactIfNeeded\(\)|db\.CompactIfNeeded\(\)" wails-app\backend\app.go
# 期望輸出 ≥ 3 行：BatchSearch 末尾、早期返回、ensureDB 啟動
```

## 涉及檔案

- `wails-app/backend/app.go`：`BatchSearch()` 末尾 + 早期返回 + `ensureDB()`
- `pkg/database/jsondb.go`：`CompactIfNeeded()` / `Compact()` / `CompactJournal()` 實作
