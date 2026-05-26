# Scan 階段去重邏輯：multi-part 切割檔 vs 同名跨目錄

> 歸檔日期：2026-05-25
> 觸發者：GUI 實測 — `KUSE-042` 被拆成 `KUSE-042-1.mp4` + `KUSE-042-2.mp4`，只有一個被搬走
> 影響範圍：`wails-app/backend/app.go::ScanDirectory`
> 狀態：multi-part 已修（commit pending），同名跨目錄為已知 latent edge case，未處理

---

## 問題簡述

`ScanDirectory` 走訪整個目錄樹，對每個影片檔用 `extractor.ExtractCode(filename)` 萃番號。原本邏輯（2026-05-25 前）：

```go
seen := make(map[string]bool) // 去重：相同番號只保留第一個路徑
...
if code != "" && !seen[code] {
    seen[code] = true
    results = append(results, ScanResult{Path: path, Code: code})
}
```

**「同番號只保留第一個」這個 invariant 蓋掉了兩個語意上不同的場景**：

1. **Multi-part 切割檔**（同一部影片，被切成多檔）
   - `KUSE-042-1.mp4` + `KUSE-042-2.mp4`
   - 兩個檔基底名不同（`-1`、`-2`），但 extractor 萃出來都是 `KUSE-042`
   - **使用者預期**：兩個檔都搬到同一個女優目錄
   - **舊行為**：只搬第一個，第二個被 scan 丟掉，連 GUI 都看不到第二個的存在

2. **同名跨目錄**（不同目錄但同檔名）
   - `A\KUSE-042-1.mp4` + `B\KUSE-042-1.mp4`
   - 兩個檔絕對路徑不同，但 basename 完全相同
   - **使用者預期**：可能想兩個都處理，也可能其中一個是備份
   - **舊行為**：只搬第一個

---

## 根因

Scan 階段做「去重」的時機點錯了。Scan 的職責是「列出磁碟上每個帶有番號的影片檔」，後續流程才應該對 `code` 做相應的 dedupe（例如 BatchSearch 對同 code 只 fetch 一次即可）。在 scan 階段直接 drop file path，是把資料丟在最上游，下游沒救。

`seen[code]` map 的設計動機應該是「避免同 code 多次送進爬蟲」，但這個目的應該由下游 BatchSearch 內部 cache 解決，不該由 scan 解決。

---

## 已採用的修法（commit pending，2026-05-25）

**移除 scan 階段的 code dedupe**，每個帶番號的影片檔各自一筆 `ScanResult`：

```go
// wails-app/backend/app.go:132 之後（修改後）
var results []ScanResult
supportedFormats := make(map[string]bool, len(extractor.SupportedFormats))
...
code := a.extractor.ExtractCode(filepath.Base(path))
if code != "" {
    results = append(results, ScanResult{Path: path, Code: code})
    a.emitEvent("scan:progress", len(results), code)
}
```

**為什麼安全**：

| 下游階段 | 對重複 code 的反應 |
|----------|------------------|
| 前端 `VideoList` React key | 用 `r.path`（不是 `r.code`），同 code 不同 path 無衝突 |
| 前端 selection | 用 `selectedCodes.has(r.code)` — multi-part 兩 part 一起選/取消（正好是想要的 UX）|
| `BatchSearch` | 每個 code 跑一次，第二次走 `db.GetVideo(code)` 命中 cache，不會 2× 爬蟲 |
| `BatchMove` | 兩個 path 各自一筆 `MoveItemRequest`，分別搬 |

**回歸測試**：`wails-app/backend/app_test.go::TestScanDirectory_KeepsMultiplePartsWithSameCode` 釘住新行為。

---

## 殘留的 latent edge case：同名跨目錄

修掉 multi-part 之後，下面這個場景變成 **dest 撞名** 的衝突：

```
C:\Downloads\AV\
  ├── A\KUSE-042-1.mp4   ← code = KUSE-042
  └── B\KUSE-042-1.mp4   ← code = KUSE-042（同檔名、不同層）
```

兩筆都會進 `ScanResult`，但 move 時 destination 都是 `<夏目響資料夾>\KUSE-042-1.mp4`，**dest 撞**。實際結果：

1. `CheckConflicts`（`app.go:316-329`）只用 `os.Stat(item.Destination)` 預檢「磁碟上 dest 是否已存在」
2. 預檢時兩筆 dest 都不存在 → **不認為 conflict** → 兩筆都進 `BatchMove`
3. `BatchMove` 並發或順序執行：
   - file A 先搬成功 → dest 出現
   - file B 開始搬 → 發現 dest 已存在 → 套用 `OnConflict`：

| 衝突策略 | file B 的下場 | 資料安全？ |
|----------|--------------|-----------|
| `skip`（GUI 預設） | 留在原地不搬 | ✅ 安全；user 看 log 才會知道 |
| `overwrite` | 覆蓋 file A 搬過去的檔 | ❌ **資料遺失** |
| `rename` | 自動 rename 成 `KUSE-042-1 (1).mp4` | ✅ 兩個都保留，但檔名變了 |

此外，理論上若 `BatchMove` 改走 goroutine pool 並行，兩個 worker 同時 `os.Stat` 都看不到對方 → 兩個都 `os.Rename` 到同 dest → 後者覆蓋前者，**即使 `skip` 也會踩到 race**。

**目前序列不踩**：實測 `pkg/mover/batch.go:22` 是 `for i, item := range items` 單迴圈，每筆呼叫一次 `MoveFile` 並等其回傳，無 goroutine pool。同名跨目錄場景下第一筆搬完成、dest 已落地，第二筆才進入 `MoveFile`，於 `os.Stat(dst)` 偵測到既有檔→套用 `skip` 留在原處；不存在 worker 並行的 race。此 invariant 由 `pkg/mover/batch_test.go::TestBatchMove_SerialExecutionInvariant` 鎖住（observer goroutine 確認 source 消失時間單調非遞減 + `result.Results` 與 input 同順序），若未來有人為了吞吐量改成 goroutine pool，會被測試擋下。

殘留問題不在 race，而在「skip 後 file B 留在原地、user 不知道第一筆搬到哪」與「直接按片商分類時誤搬留在原地的 file B」—— 已記在 `docs/sqlite-migration-tail-tasks.md` T2 / T3。

---

## 未來修法選項

按侵入度 / 完整度排序：

### 選項 A：不動，接受現狀

- **動作**：什麼都不做
- **理由**：
  - GUI 預設 `skip` 已保證資料不會遺失（最壞情況：file B 留在原地）
  - 同名跨目錄是 user 自己整理檔案的選擇，極少見
  - User 可以從 batch result log 看出哪些檔被 skip
- **代價**：
  - 使用 `overwrite` 模式的 user 可能踩雷（同 dest 後者會覆蓋前者，這是 `overwrite` 語意本身決定的，不是 race）
  - **目前序列實作下不存在 race condition** — `pkg/mover/batch.go:22` 為 `for i, item := range items` 單迴圈、每筆同步呼叫 `MoveFile` 並等回傳；同 dest 兩筆會以「第一筆完成、dest 落地 → 第二筆 `os.Stat(dst)` 偵測到既有檔 → 套用 `skip`/`overwrite`/`rename`」的順序進行，無「兩 worker 同時 stat 都看不到對方」的 race window。此 invariant 由 `pkg/mover/batch_test.go::TestBatchMove_SerialExecutionInvariant` 雙層鎖定（AST static guard 擋下 `go` 語句與非同步分派 + runtime observer 鎖完成時間單調非遞減）
  - **未來風險**：若有人為了吞吐量改成 goroutine pool / errgroup 並行而沒保留 T1 的序列 invariant，「同時 stat 看不到對方 → 兩個都 rename 到同 dest → 後者覆蓋前者，即使 `skip` 也救不了」這個 race 才會重新出現；屆時 T1 的測試會在 PR CI 直接擋下
- **檔案變動**：0

### 選項 B：`CheckConflicts` 增加 in-batch destination 偵測

```go
func (a *App) CheckConflicts(items []MoveItemRequest) []ConflictItem {
    conflicts := make([]ConflictItem, 0)
    seenDest := make(map[string]string) // dest absolute path → first source

    for _, item := range items {
        absDst, _ := filepath.Abs(item.Destination)

        // 1. 同批次內 dest 重複（in-batch collision）
        if firstSrc, dup := seenDest[absDst]; dup {
            conflicts = append(conflicts, ConflictItem{
                Source:      item.Source,
                Destination: item.Destination,
                Reason:      fmt.Sprintf("與同批次 %q 指向同一目的地", firstSrc),
            })
            continue
        }
        seenDest[absDst] = item.Source

        // 2. 既有邏輯：磁碟上 dest 是否已存在
        if _, err := os.Stat(item.Destination); err == nil {
            conflicts = append(conflicts, ConflictItem{
                Source:      item.Source,
                Destination: item.Destination,
            })
        }
    }
    return conflicts
}
```

- **動作**：`CheckConflicts` 預掃同批次內是否有兩個 source 指向同一 dest
- **優點**：在進入 BatchMove 之前就讓 user 看到衝突、選擇處理策略
- **代價**：`ConflictItem` 可能需要加 `Reason` / `ConflictType` 欄位區分「磁碟既有」vs「同批次衝突」，前端要對應顯示
- **影響檔案**：`wails-app/backend/app.go`、`pkg/mover/types.go`（如加欄位）、前端 `ConflictResolutionDialog.tsx`

### 選項 C：Scan 階段 dedupe 改成 `(directory, code)` 複合 key

```go
type scanKey struct {
    dir  string
    code string
}
seen := make(map[scanKey]bool)
...
key := scanKey{dir: filepath.Dir(path), code: code}
if code != "" && !seen[key] {
    seen[key] = true
    results = append(results, ScanResult{Path: path, Code: code})
}
```

- **動作**：同目錄內 multi-part 保留（`A\KUSE-042-1.mp4` + `A\KUSE-042-2.mp4` 都進來），跨目錄退回「第一個 wins」
- **優點**：自動處理「兩個目錄都放同番號」的場景（其中一個會被視為重複而 drop）
- **代價**：
  - User 如果故意把同番號擺在兩個目錄（例如 `已分類\` 與 `待整理\`）會踩到「為什麼第二個沒被掃進來」
  - 「同目錄內 multi-part」的判定假設 user 命名習慣固定（`-1`、`-2`），但有些命名方式（`.cd1.mp4`、`.part1.mp4`）也是 multi-part 但需要 extractor 配合
- **影響檔案**：`wails-app/backend/app.go::ScanDirectory`

### 選項 D：完整修法 — Scan 全保留 + CheckConflicts 預警同 dest

組合「選項目前現狀（multi-part 已保留）」+「選項 B（in-batch dest 偵測）」。

- **動作**：
  1. 維持 scan 全保留所有 path（=今天已 commit 的修法）
  2. `CheckConflicts` 加 in-batch dest 重複偵測（=選項 B）
  3. `ConflictResolutionDialog` 加 conflict type 區分顯示
- **優點**：所有 multi-part 與同名跨目錄都正確處理，user 都能看到衝突、自主決定
- **代價**：最完整，改動最多
- **影響檔案**：`wails-app/backend/app.go`、`pkg/mover/types.go`、`wails-app/frontend/src/components/ConflictResolutionDialog.tsx`、回歸測試

---

## 決策軌跡（2026-05-25）

| 階段 | 採用 | 原因 |
|------|------|------|
| 立即修 multi-part bug | ❌ Scan dedupe（舊） | bug 主因，必修 |
| 未來改 | ⏸️ 選項 A（接受現狀） | GUI 預設 skip 安全；user 還沒主動回報同名跨目錄踩雷 |
| 若未來踩雷 | 選項 D（完整修法） | 一次解掉 batch 內所有 destination collision，前端 UX 對齊 |

---

## 相關檔案

- `wails-app/backend/app.go::ScanDirectory`（~ line 117）
- `wails-app/backend/app.go::CheckConflicts`（~ line 314）
- `wails-app/backend/app.go::BatchMove`（~ line 345）
- `wails-app/backend/app_test.go::TestScanDirectory_KeepsMultiplePartsWithSameCode`
- `wails-app/frontend/src/App.tsx::executeMoveWithConflictHandling`
- `wails-app/frontend/src/components/ConflictResolutionDialog.tsx`
- `wails-app/frontend/src/components/VideoList.tsx`（React key + selection）
- `pkg/mover/batch.go::BatchMove`

---

## 相關 wiki

- [`wiki/pitfalls/scan-same-filename-cross-dir-conflict.md`](../../wiki/pitfalls/scan-same-filename-cross-dir-conflict.md) — wiki 簡要條目
- [`wiki/pitfalls/wails-scan-duplicate.md`](../../wiki/pitfalls/wails-scan-duplicate.md) — scan dedupe 的歷史背景（為什麼當時加上 `seen[]` map）
