# SQLite 遷移收尾 — 剩餘 Task

> 撰寫日期：2026-05-26
> 來源：`implementation-notes.md` L678-688（C2 後 5 個 open questions）+ 2026-05-26 對話中關於片商分類 follow-on 影響的討論 + 工作區未提交檔案盤點
> 範圍：SQLite-only 切換主幹完成後（commit `ac600e8` 為止）需要收的尾巴
> 日期欄為「建議完成於」，依實際步調調整即可

---

## 優先級總覽

| ID | P | 建議完成於 | 任務 |
|----|---|-----------|------|
| T1 | P0 | 2026-05-27 | 鎖住 BatchMove 序列執行（invariant 測試 + doc 更新） |
| T2 | P0 | 2026-05-29 | BatchMove skip 結果關聯成功 dest（修法 A） |
| T3 | P0 | 2026-05-30 | `handleStudioMove` 進入前 guard 未處理 skip（修法 B） |
| T4 | P1 | 2026-06-02 | `config.ini` `[go_integration]` duplicate write 追因 |
| T5 | P1 | 2026-06-03 | Python ConfigParser strict 模式觸發點審計 |
| T6 | P2 | 2026-06-04 | `tools-rs/Cargo.lock` 從 git 移除 |
| T7 | P2 | 2026-06-04 | 工作區未提交檔案決議（spec 刪除 + 兩份 untracked docs） |
| T8 | P3 | 待觸發 | ScanResult selection identity 重構（同名跨目錄選項 D 完整修） |

T2 → T3 強相依（T3 的 guard 需要 T2 產生的 success/skip 對應關係）。T1 是 T8 的 prereq。其餘可獨立進行。

---

## T1 — 鎖住 BatchMove 序列執行（invariant 測試 + doc 更新）

**P0 · 建議完成於 2026-05-27**

### Why

`implementation-notes.md` open question 3 擔心「BatchMove goroutine pool 並行兩個 worker 同時 stat 同 dest 都看不到對方」會在同名跨目錄場景下踩 race。

實測 `pkg/mover/batch.go:22` 是 `for i, item := range items` 序列執行，無 goroutine pool，**race 不存在**。但這個性質沒有測試鎖定，未來有人改成並行（為了效能）就會踩雷而沒人擋。

### 動作

1. 在 `pkg/mover/batch_test.go` 加 `TestBatchMove_SerialExecutionInvariant`：給定 N 筆 items，紀錄每筆 MoveFile 進入時間，驗證「第 k+1 筆開始時間 ≥ 第 k 筆結束時間」（嚴格序列）
2. `implementation-notes.md` open questions 區補一句「BatchMove 確認為序列（`pkg/mover/batch.go:22`）；同名跨目錄不踩 race，但 skip 後留檔仍是問題（見 T2/T3）」
3. `docs/茶包射手/scan-multi-part-and-same-name-cross-dir.md` 把「若並行會踩 race」段落更新為「目前序列不踩，T1 測試鎖住」

### 影響檔案

- `pkg/mover/batch_test.go`（新測試）
- `implementation-notes.md`（open question 3 收尾）
- `docs/茶包射手/scan-multi-part-and-same-name-cross-dir.md`

### 驗證

`go test .\pkg\mover -run TestBatchMove_SerialExecutionInvariant -v`

---

## T2 — BatchMove skip 結果關聯成功 dest（修法 A）

**P0 · 建議完成於 2026-05-29**

### Why

同名跨目錄場景下，`A\KUSE-042-1.mp4` 搬走後 `B\KUSE-042-1.mp4` 因 dest 撞而 skip。目前 batch result 只回 `Skipped=true`，**沒告訴 user 第一筆搬到哪**，user 無法手動把第二筆合併過去。

### 動作

兩種實作方向選一：

**方向 A1（後端紀錄）**：`mover.MoveResult` 加欄位 `SkippedReason string`，當 skip 因 dest 已存在時帶上「existing dest path」。`BatchResult` 內 post-process 把同 dest 的成功筆與 skip 筆配對，紀錄在 skip 筆的 `SkippedReason`。

**方向 A2（前端後處理）**：保持後端不動，frontend `App.tsx:765` 處理 BatchResult 時，把 `r.skipped && !r.success` 的紀錄與「同 destination 且 success」的紀錄做 map，顯示「`B\KUSE-042-1.mp4` 略過（同檔已搬至 `<output>\夏目響\KUSE-042-1.mp4`）」。

推薦 A2：純前端字串拼接、不動 contracts、回滾簡單。

### 影響檔案（A2 方向）

- `wails-app/frontend/src/App.tsx`（line 765 附近 skip 訊息生成）
- 視需要新增 `wails-app/frontend/src/utils/skipReason.ts` 抽出 mapping

### 驗證

手動：建兩個同 code 同 basename 跨目錄的測試檔，跑女優分類，看 GUI 略過訊息是否帶上成功檔的去向。

---

## T3 — `handleStudioMove` 進入前 guard 未處理 skip（修法 B）

**P0 · 建議完成於 2026-05-30 · 相依 T2**

### Why

T2 解決了「user 知道第一筆去哪」，但沒解決「user 直接按片商分類會誤搬」。

`App.tsx:633` `handleStudioMove` 用 `parentDir(r.path)` 分組，留在 `B\KUSE-042-1.mp4` 的 file B 的 `parentDir = B\`，會被當成「另一個女優資料夾 `B\`」處理 → DB 查 code 回「夏目響」→ 最終嘗試把整個 `B\` 目錄（含其他無關檔案）搬到 `<output>\SOD\夏目響\`。

### 動作

於 `handleStudioMove` 進入點（早期返回檢查之後、`setStatus('moving')` 之前）加 guard：若 `lastBatchResult.results` 內存在 `skipped === true` 且其 source path 仍出現在 `scanResults` 的紀錄，則阻擋本次片商分類並提示 user 先處理略過清單（或重新 scan）。不做隱式處理（不自動 skip、不自動合併），block 後維持 `status='idle'`，由 user 決定下一步。

### 影響檔案

- `wails-app/frontend/src/App.tsx::handleStudioMove`（加 guard）
- 視需要新增 `wails-app/frontend/src/lib/studioMoveGuard.ts` 抽出 guard 邏輯

### 驗證

手動：建 `A\KUSE-042-1.mp4` + `B\KUSE-042-1.mp4`（同 code 同 basename），衝突策略 = skip，先按「移動」再按「片商分類」，預期：guard 擋下、不進入 `BatchMoveDirs`。

---

## T4 — `config.ini` `[go_integration]` duplicate write 追因

**P1 · 建議完成於 2026-06-02**

### Why

`implementation-notes.md` open question 1：2026-05-25 修了損壞的 `config.ini`，但沒查出寫入來源。Wails `PreferencesDialog` 寫 config / Python 某 helper / 過去 commit 的 partial-write bug 殘留都是 candidate。不查不修，下次還會踩。

### 動作

1. `grep -rn "enable_operation_log" src/ tools/ wails-app/` 找寫入點
2. `grep -rn "configparser" src/ tools/` + 看是否有 `write(` / `set(` 沒先 `remove_option`
3. 開 Wails 預設值對話框點存檔幾次，diff `config.ini` 變化
4. 若找到 bug，修補 + 加 regression 測試
5. 若找不到，記錄 candidate 至 wiki pitfall

### 影響檔案

待調查後決定（可能 `src/utils/config.py`、Wails 前端 preferences、`tools/` 某 helper）

### 驗證

能 reproduce duplicate write 並修補；或在 wiki 留下調查紀錄

---

## T5 — Python ConfigParser strict 模式觸發點審計

**P1 · 建議完成於 2026-06-03 · 可與 T4 併進**

### Why

`implementation-notes.md` open question 2：只看到 search subprocess 的 stderr 報錯，`tools/`、`src/services/` 其他 `ConfigParser` 使用點未驗證是否會被 duplicate option 弄掛。

### 動作

1. `grep -rn "ConfigParser\|configparser" src/ tools/` 列出所有使用點
2. 對每個使用點：確認是否 `strict=True`（預設 True）、發生 `DuplicateOptionError` 時是否有 fallback、會不會把 helper 弄掛
3. 拿一份故意有 duplicate option 的 config.ini 跑全部 helper，記錄哪些會掛
4. 對「會掛但不該掛」的 helper 加 `strict=False` 或 try/except 包覆

### 影響檔案

待審計後決定

### 驗證

跑壞 config.ini 模擬 + 跑全部 Python 整合測試

---

## T6 — `tools-rs/Cargo.lock` 從 git 移除

**P2 · 建議完成於 2026-06-04**

### Why

`ac600e8` 引入 root `Cargo.toml` workspace 後，`tools-rs/Cargo.lock` 變成 vestigial（cargo 忽略它，只認 root lock）。`implementation-notes.md` open question 4 列為待清。

### 動作

```powershell
git rm tools-rs/Cargo.lock
cargo build --manifest-path tools-rs/Cargo.toml
go test ./...
```

若 `.gitignore` 未涵蓋，補一行 `tools-rs/Cargo.lock`。

### 影響檔案

- `tools-rs/Cargo.lock`（刪除）
- 可能 `.gitignore`

### 驗證

`cargo build` 仍 work、`Cargo.lock`（root）含 `db-tool` 所有 deps

---

## T7 — 工作區未提交檔案決議

**P2 · 建議完成於 2026-06-04**

### Why

目前 `git status` 顯示：

- `D docs/superpowers/specs/2026-05-23-sqlite-migration-design.md`（已刪除未 commit）
- `?? docs/agent-loop-demo.md`（untracked）
- `?? docs/supervisor-worktree-check.md`（untracked）

不收掉，下次 PR 會混進無關 diff。

### 動作

1. **spec 刪除**：確認 spec 內容已被 `implementation-notes.md` 取代後 commit 刪除；若仍有未轉移內容，先轉移再 commit
2. **`docs/agent-loop-demo.md`**：判斷是否屬於 repo 範疇 → commit / `.gitignore` / 刪除
3. **`docs/supervisor-worktree-check.md`**：同上

### 影響檔案

- `docs/superpowers/specs/2026-05-23-sqlite-migration-design.md`
- `docs/agent-loop-demo.md`
- `docs/supervisor-worktree-check.md`
- 可能 `.gitignore`

### 驗證

`git status` 在 codex/shadow-db-sqlite 上 clean

---

## T8 — ScanResult selection identity 重構（同名跨目錄選項 D 完整修）

**P3 · 待觸發 · 相依 T1 完成**

### Why

T2/T3 解決了「user 看得到 + 不誤搬」，但根因（scan 階段對「同 code 不同 path」沒區分）仍在。`docs/茶包射手/scan-multi-part-and-same-name-cross-dir.md` 列的選項 D 是完整修法：

- scan 維持全保留（已完成）
- `CheckConflicts` 加 in-batch dest 偵測
- `ConflictResolutionDialog` 區分 conflict type 顯示

### 觸發條件

- 真的有 user 回報踩雷（目前只在 release 前推演發現）
- 或要做的 follow-up：BatchMove dest 衝突的 UX 完整化

### 動作

依 `scan-multi-part-and-same-name-cross-dir.md` § 「未來修法選項 → 選項 D」執行：

1. `pkg/mover/types.go` 加 `ConflictType` 欄位（`disk_existing` / `in_batch_duplicate`）
2. `wails-app/backend/app.go::CheckConflicts` 加 `seenDest` map + `Reason` 帶上「首筆 source」
3. `wails-app/frontend/src/components/ConflictResolutionDialog.tsx` 對 in-batch 衝突顯示「N 個檔案指向同一目的地」+ 提供「全選 rename」快速選項
4. 回歸測試：`pkg/mover/batch_test.go` + `wails-app/backend/app_test.go::TestCheckConflicts_InBatchDestCollision`

### 影響檔案

- `pkg/mover/types.go`
- `wails-app/backend/app.go`（`CheckConflicts`）
- `wails-app/frontend/src/components/ConflictResolutionDialog.tsx`
- `pkg/mover/batch_test.go`、`wails-app/backend/app_test.go`

### 驗證

`scan-multi-part-and-same-name-cross-dir.md` § 「相關檔案」列的所有測試 + 手動跑同名跨目錄情境

---

## 完成標準

全部 P0+P1+P2 done 後：

- `implementation-notes.md` open questions 1-4 收掉
- `git status` clean
- 同名跨目錄場景：user 看得到 + 不誤搬
- SQLite 遷移可正式宣告「完成」並打 release tag

T8 是更完整的 UX，但不阻擋 release。
