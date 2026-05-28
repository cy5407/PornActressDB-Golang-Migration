# `mergeFromRoot` 拆解設計文件

**目標函式**：`pkg/database/sqlite_runtime.go` 的 `(*SQLiteStore).mergeFromRoot`
（goal 原稱「L596」；歷經 Phase 2 commits 後實際在 **L611**，gocognit 報 **CC 56**）。

**目標**：CC ≤ 15，行為等價，且維持與 JSON-side `JSONDatabase.MergeFromFile`
的視覺對齊（兩條 merge 路徑命名一致，便於對照閱讀）。

---

## 1. Responsibility 清單（SRP 角度）

讀完整個 86-line 函式，目前混合以下 **6 種職責**：

| # | Responsibility | 行 | 備註 |
|---|---|---|---|
| R1 | 產生 `now` 時間戳供本次 merge 用 | L613 | trivial setup |
| R2 | 迭代 `root.Actresses`，逐筆 nil/empty-ID 過濾 | L616-623 | 過濾 |
| R3 | 每筆 actress：lookup → 分支（existing/new）→ Upsert + 計數 | L624-650 | 核心 actress 流程 |
| R4 | 迭代 `root.Videos`，逐筆呼叫 `prepareVideoForMerge` 過濾 | L653-657 | 過濾 |
| R5 | 每筆 video：lookup → 分支（existing/new）→ Upsert + 計數 | L658-682 | 核心 video 流程 |
| R6 | Links: 開單一 transaction，呼叫 `applyLinkOverrides`，累計 `LinksAdded` | L687-706 | 唯一的 tx 邊界 |

> ⚠️ **重要交易邊界事實**：原函式 doc-comment（`MergeFromFile`，L595）說
> *"The whole import runs inside one SQLite transaction"*，**這個敘述是錯的**。
> 實際上 actresses / videos 路徑透過 `UpsertActress` / `UpsertVideo` 各自呼叫
> `s.db.Begin()`（見 `sqlite_crud.go:79, 32`），是 **per-row implicit tx**。
> 只有 links 區塊有明確 `tx := s.db.Begin() ... tx.Commit()`。
> 拆解時必須保留這個現狀（不是修 bug 也不是擴大 tx），但建議在拆解過程附帶
> 修正 MergeFromFile 的 doc-comment（已驗證的錯誤資訊）。

R3 / R5 結構幾乎完全相同：
1. 對應的 Get 查詢
2. `if err != nil && !errors.Is(err, ErrNotFound) → return`
3. 設定 `UpdatedAt = now`
4. `if existing != nil` → overwrite 分支（skip / preserve CreatedAt / Upsert / Updated++ 或 Skipped++）
5. `else` → new 分支（fallback CreatedAt = now / Upsert / Added++）

這個高度結構重複是拆解的關鍵 — JSON-side `JSONDatabase` 已經把同樣的形狀切成
`mergeVideoRecord` / `mergeActressRecord`（見 `jsondb.go:934, 954`）；SQLite-side
mirror 同一個 shape 是最自然的方向。

---

## 2. 拆解方案

### 方案 A：3 helper（每個 loop 整包抽一個）

抽出三個 method，每個處理一整個 loop：

```go
func (s *SQLiteStore) mergeActressesFromRoot(root *DatabaseData, overwrite bool, now string, stats *MergeStats) error
func (s *SQLiteStore) mergeVideosFromRoot(root *DatabaseData, overwrite bool, now string, stats *MergeStats) error
func (s *SQLiteStore) mergeLinksFromRoot(root *DatabaseData, stats *MergeStats) error
```

**call site 改動（mergeFromRoot）**：

```go
func (s *SQLiteStore) mergeFromRoot(root *DatabaseData, overwrite bool) (*MergeStats, error) {
    stats := &MergeStats{}
    now := time.Now().UTC().Format(ISODateTimeFormat)
    if err := s.mergeActressesFromRoot(root, overwrite, now, stats); err != nil {
        return nil, err
    }
    if err := s.mergeVideosFromRoot(root, overwrite, now, stats); err != nil {
        return nil, err
    }
    if err := s.mergeLinksFromRoot(root, stats); err != nil {
        return nil, err
    }
    return stats, nil
}
```

**Transaction 影響**：links helper 內部保留 `s.db.Begin()...Commit()`；actress / video
helper 仍呼叫公開的 `UpsertActress` / `UpsertVideo`（自帶 tx），邊界不變。

**估計 CC**：

| 函式 | 估計 CC | 風險 |
|------|---------|------|
| mergeFromRoot | ~4 | ✓ 遠低於 15 |
| mergeActressesFromRoot | **~14-16** | ⚠️ 邊界值；nested if 仍多（for + nil 過濾 + ID 過濾 + Get 錯誤 + existing + !overwrite + CreatedAt + Upsert err + new branch CreatedAt + new branch Upsert err） |
| mergeVideosFromRoot | **~13-15** | ⚠️ 同上 |
| mergeLinksFromRoot | ~6 | ✓ |

actress/video helper 仍可能 **剛好打到 15** 或 **略微超過**，要視 gocognit
nesting bonus 而定，是有風險的方案。

---

### 方案 B：2 層拆解（loop helper + per-record helper）— **推薦**

把每個 loop 切成兩層：

```go
func (s *SQLiteStore) mergeActressesFromRoot(root *DatabaseData, overwrite bool, now string, stats *MergeStats) error
func (s *SQLiteStore) mergeOneActress(id string, a *ActressData, overwrite bool, now string, stats *MergeStats) error

func (s *SQLiteStore) mergeVideosFromRoot(root *DatabaseData, overwrite bool, now string, stats *MergeStats) error
func (s *SQLiteStore) mergeOneVideo(mapCode string, video *VideoData, overwrite bool, now string, stats *MergeStats) error

func (s *SQLiteStore) mergeLinksFromRoot(root *DatabaseData, stats *MergeStats) error
```

外層 loop helper 只負責：iterate + nil-skip + 呼叫 per-record helper + propagate error。
所有「lookup / existing 分支 / Upsert / stats」邏輯落在 per-record helper。

**call site 改動（mergeFromRoot）**：與方案 A 完全相同（只是 helper 內部更深）。

**Transaction 影響**：同方案 A — 唯一 tx 邊界仍只在 `mergeLinksFromRoot`。actress /
video per-record helper 不開 tx（依賴 UpsertActress / UpsertVideo 自帶 tx），與
原行為一致。

**估計 CC**：

| 函式 | 估計 CC | 備註 |
|------|---------|------|
| mergeFromRoot | ~4 | ✓ |
| mergeActressesFromRoot | ~5 | ✓ for + nil-skip + err 三條分支 |
| mergeOneActress | ~12 | ✓ id-trim/skip + Get err + existing 分支（!overwrite / CreatedAt / Upsert）+ new 分支（CreatedAt / Upsert） |
| mergeVideosFromRoot | ~5 | ✓ for + prepareVideoForMerge `!ok` 過濾 + err |
| mergeOneVideo | ~13 | ✓ existing 分支多一個 `stats.VideosSkipped++`，比 actress 多 1 分支 |
| mergeLinksFromRoot | ~6 | ✓ |

所有子函式都安全落在 15 以下，且最大值 13 留下 ≥ 2 點 buffer 給未來小修改。

**與 JSON-side 對稱**：

| JSON-side（jsondb.go） | SQLite-side（本方案） |
|---|---|
| `mergeVideoRecord` | `mergeOneVideo` |
| `mergeActressRecord` | `mergeOneActress` |
| `mergeLinkRecords` | （內含於 mergeLinksFromRoot） |

命名上略偏離（JSON 用 `mergeXxxRecord`，本案用 `mergeOneXxx`）— 理由：JSON 版
是無 error return 的 mutation；SQLite 版有 `error` return，語意上更像
「處理一筆」而非「合併一筆 record」。如果想完全對稱，可改名 `mergeActressRecord`
/ `mergeVideoRecord` —  但屆時與 JSON 版的不同 receiver type（`*JSONDatabase`
vs `*SQLiteStore`）+ 不同 signature（err return）會混淆，反而較糟。**保留
`mergeOneXxx` 命名**。

---

## 3. 推薦方案 + 理由

**推薦：方案 B（2 層拆解）**

理由：

1. **CC 安全邊際足夠**：方案 A 最大子函式 ~14-16，在 gocognit 邊界遊走；方案 B
   最大 ~13，留 ≥ 2 點 buffer。

2. **per-record helper 可單獨測試**：未來如要為 `mergeOneActress` 寫單元測試
   （目前 jsondb_test.go 已有 `prepareVideoForMerge` 單測的先例），方案 B 直接
   支援；方案 A 必須走 `mergeFromRoot` 整條路徑才能觸發。

3. **對齊 JSON-side merge 結構**：jsondb.go 早就走 `mergeXxxRecord` 兩層分割。
   SQLite-side 對齊後，code-review 時兩條 merge 路徑可平行比對，差異一目了然。

4. **Transaction 邊界清晰**：方案 B 把 links（唯一的 tx 邊界）獨立成 helper，
   不再混在 86-line 的尾段。Codex review 看 tx 邊界時可直接定位到
   `mergeLinksFromRoot`。

5. **新增複雜度可控**：新增 4 個 helper + 沒有新型別。**沒有** new struct 需要
   passing-by-value/pointer 的權衡。stats 與 now 已經是 by-pointer / by-value
   原語，繼續沿用。

### 預期 diff 影響

- mergeFromRoot：~95 行 → ~15 行（－80）
- 新增 mergeActressesFromRoot / mergeOneActress / mergeVideosFromRoot /
  mergeOneVideo / mergeLinksFromRoot：合計 ~110 行（含 godoc 註解）
- MergeFromFile doc-comment 修正：－2 +2 行（移除「one SQLite transaction」誤述）
- **預估淨增：~30-40 行**，遠低於 Phase 2 的 ±500 行 budget

### 不在本次 scope

- 不修 actress / video upsert 不在同一 tx 的設計問題（這是另一個 ticket：
  「mergeFromRoot 應改成 single-transaction」涉及行為變更，不屬 CC 重構）
- 不抽 stats 為 struct receiver（如 `(*MergeStats).recordActressAdded()`）—
  call site 就 6 個位置，新增 receiver method 反而疊加 indirection 看不出收益
- 不調整 actresses-first-then-videos 順序（spec 第一段 comment 明示「Actresses
  first so videos can resolve their actresses[] names.」— SQLite 不需要這個
  ordering 約束因為 link 走 `applyLinkOverrides` 不靠 actress lookup，但保留
  ordering 與 JSON-side 行為一致才是低風險選擇）
