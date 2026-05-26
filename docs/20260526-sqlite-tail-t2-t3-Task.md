# Task — SQLite tail T2 + T3（同名跨目錄 UX 完整化）

> 撰寫日期：2026-05-26（PR #19 merge 後）
> 來源：`docs/archive/2026-05-26-sqlite-migration-session/sqlite-migration-tail-tasks.md` 中的 T2 / T3
> 兼用途：實測 supervisor pitfall 救法方案 A（Codex `/goal` 開新獨立 session 當 driver）
> 對照：見本檔末尾「實測對照組」

---

## 背景

PR #19（`fix: preserve basename for actress classification moves`）已 merge。SQLite 遷移主幹完成，剩 SQLite tail backlog 中的 P0 兩個 task：T2 + T3。兩者**強相依**（T3 的 guard 需要 T2 產生的 success/skip 對應關係），所以**同一場 supervisor 內一起做**。

### 觸發場景（同名跨目錄）

```
C:\Downloads\AV\
  ├── A\KUSE-042-1.mp4   ← code = KUSE-042
  └── B\KUSE-042-1.mp4   ← code = KUSE-042（同檔名、不同層）
```

兩筆都進 `ScanResult`，但兩筆 dest 都是 `<output>\<actress>\KUSE-042-1.mp4`。

1. **女優分類後**：file A 成功搬走，file B dest 撞被 `skip` 留在 `B\`。GUI 略過清單只說「N 略過」**沒講第一筆去向**——user 無法手動合併
2. **接著按片商分類**：`handleStudioMove`（`App.tsx:633`）用 `parentDir(r.path)` 分組，留在 `B\` 的 file B 的 `parentDir = B\`，會被當成「另一個女優資料夾 `B\`」處理——DB 查 code 回正確女優名 → **整個 `B\` 目錄被嘗試搬到 `<output>\SOD\<actress>\`**，含其他無關檔案

---

## T2 — BatchMove skip 結果關聯成功 dest（修法 A）

### Why

略過清單目前只說「這筆 skip 了」，沒告訴 user「成功的同 code 已搬至 `<dest>`」。沒這個對應，user 無法手動合併 file B。

### 動作

**純前端後處理**，不動 backend contracts：

`wails-app/frontend/src/App.tsx` 第 765 行附近（BatchResult 處理區），把：

- `r.skipped && !r.success` 的紀錄
- 同一 `BatchResult.Results[]` 中「`destination` 完全相同 且 `success && !skipped`」的紀錄

做 mapping。pushEvent 訊息改為：

```
B\KUSE-042-1.mp4 略過（同檔已搬至 <output>\夏目響\KUSE-042-1.mp4）
```

若 skip 筆找不到對應的 success 筆（例如所有同 dest 的都 skip 了），保持原有「N 略過」訊息。

### 影響檔案

- `wails-app/frontend/src/App.tsx`（line 765 附近）
- 視情況新增 `wails-app/frontend/src/utils/skipReason.ts`（抽出 mapping 邏輯）

### Acceptance

1. 開兩個同 code 同 basename 跨目錄的測試檔（`A\KUSE-042-1.mp4` + `B\KUSE-042-1.mp4`）
2. 跑女優分類
3. GUI 略過訊息**必須**包含「同檔已搬至 `<具體 dest 路徑>`」
4. 同 code 但**不同 basename** 的 skip 場景（罕見）—— 訊息不能誤指向不存在的對應

---

## T3 — `handleStudioMove` 進入前 guard（修法 B，相依 T2）

### Why

T2 解決「user 知道第一筆去哪」，但沒解決「user 直接按片商分類會誤搬」。要主動 block 不合理的片商分類操作。

### 動作

`App.tsx:607` `handleStudioMove` 開頭加 guard：

1. 算出「上一輪女優分類成功移動到的女優資料夾集合」`movedActressDirs`
   - 從 `outputDir` 推導（list 直接子目錄）
   - 或從前一次 BatchResult 記憶（state）
2. 對 `scanResults` 每一筆 `r`，若 `parentDir(r.path)` **不在** `movedActressDirs` 內，視為「未進入女優目錄」
3. 若有任一未進入的紀錄：
   - 中斷流程（不要往下走 `folderToCodes`、不要 BatchMoveDirs）
   - `setStatusMessage('偵測到 N 個檔案未進入女優目錄（同名跨目錄略過？），請先處理略過清單或重新 scan。詳見「上次移動結果」對話框', 'warning')`
   - 不要隱式 skip / 隱式合併——讓 user 主動決定

### 影響檔案

- `wails-app/frontend/src/App.tsx::handleStudioMove`（line 607 附近）
- 視情況新增 `wails-app/frontend/src/utils/scanResultGuard.ts`

### Acceptance

1. T2 完成後，同名跨目錄情境跑女優分類
2. 接著直接按片商分類——**必須** 被 block + 顯示具體未進入女優目錄的數量
3. 「正常情況」（所有檔都已搬進女優目錄）——不會被 guard 誤擋，可正常進入 BatchMoveDirs

---

## 共通 Verify Commands

```powershell
# 前端
Set-Location wails-app\frontend
npm run test:guard
npm run build
Set-Location ..\..

# 後端（確認沒誤動 backend）
go test ./pkg/mover -count=1
go test ./wails-app/backend -count=1

# 範圍檢查
git diff --check
```

三個 verify 全部 exit code 0 才算通過。

---

## 不可動的範圍

| 範圍 | 原因 |
|------|------|
| `pkg/` 全部 Go 後端邏輯 | T2/T3 是純前端，不該觸發 backend 改動 |
| `cmd/` Go CLI | 同上 |
| `pkg/database/sqlite_schema.sql` | SQLite schema 鎖死 |
| `tools-rs/` Rust crate | 與本 task 無關 |
| `data/` / `tests/fixtures/` | 不該動測試 fixture |
| 任何 wiki / docs 之外的檔（除本 Task md） | scope drift |

允許的檔案改動：
- `wails-app/frontend/src/App.tsx`
- `wails-app/frontend/src/utils/*.ts`（新增 skipReason.ts / scanResultGuard.ts）
- 對應的 frontend 測試（若有）
- 本 Task md（worker 可在末尾追加 implementation note）

---

## 實測對照組（supervisor 方案 A 驗證用）

這場 task 的另一個用途是**實測 `supervisor/docs/pitfall-codex-driver-thread-cache.md` 提到的方案 A**——以 Codex `/goal` 開新獨立 session 當 driver，取代 Codex App driver mode + 長 thread 延續。

對照數據（單位：tokens）：

| 場次 | Driver mode | Reviewer total | Worker total | Reviewer/Worker ratio |
|------|------------|---------------|--------------|---------------------|
| 下午 2026-05-26 /goal 5 task（slim packet 前） | `/goal` 新 session | 18,990,599 | 31,150,843 | **0.61** |
| 晚上 2026-05-26 supervisor 3 task（slim packet + Codex App driver） | thread 延續 | 25,716,235 | 11,707,156 | **2.20** |
| **本場（預期）** | `/goal` 新 session + slim packet | **≤ 14M** | ≈ 6–10M | **≤ 0.61** |

跑完後請在本 task md 末尾追加：

```
## 實測結果
- 開始時間（台灣）：
- 結束時間（台灣）：
- 用了幾輪 supervisor：
- 對應的 Codex thread id：
- 對應的 ~/.codex/sessions/ jsonl 路徑：
- Reviewer total tokens：
- Worker total tokens：
- Reviewer/Worker ratio：
- 週用量起始 %：
- 週用量結束 %：
- 對照預期是否達成：
```

---

## Prompt — 貼進 Codex 新 chat 的 `/goal`

> **重要**：開 **Codex App 新 chat**，不要在現有任何 thread 內繼續（特別是 `019e50ad-...`）。新 chat + `/goal` 才能達到方案 A「獨立 session driver」效果。

```text
/goal 完成 target repo 的 T2 + T3 兩個 task 並通過全部 verify commands。

Target repo:
C:\Users\cy5407\.codex\worktrees\4238\PornActressDB-Golang-Migration

Worktree branch:
codex/shadow-db-sqlite （已跟 origin 同步，PR #19 已 merge 進 main）
建議：本場開新 branch `codex/sqlite-tail-t2-t3` 從 `codex/shadow-db-sqlite` 拉出，跑完後 PR 進 main。

Task spec:
docs/20260526-sqlite-tail-t2-t3-Task.md
（這份文件是 self-contained spec，請完整讀完再開工，包含 T2 / T3 / Acceptance / Verify / 不可動的範圍 / 對照組）

Supervisor launcher:
C:\Users\cy5407\Desktop\程式語言\supervisor\ask-supervisor.ps1

Loop protocol:
1. 開工前讀 Task spec 與 PR #19 merge 後的 git log 了解現況
2. 每輪只呼叫一次 supervisor，格式：
   C:\Users\cy5407\Desktop\程式語言\supervisor\ask-supervisor.ps1 "<本輪 worker task>" `
     -Repo "C:\Users\cy5407\.codex\worktrees\4238\PornActressDB-Golang-Migration" `
     -BypassPermissions `
     -Verify "Set-Location wails-app\frontend; npm run test:guard; npm run build; Set-Location ..\..", `
             "go test ./pkg/mover ./wails-app/backend -count=1", `
             "git diff --check" `
     -Timeout 1800 -NoOutputTimeout 600
3. 每輪結束後讀：
   - launcher 輸出的 handoff.md
   - rounds\NN\driver-packet.json （優先看這份 slim 摘要）
   - rounds\NN\supervisor-runs\<run>\round-NN-review.json
4. 依 Task spec § Acceptance 判斷：
   - T2 acceptance 3 條全綠 + T3 acceptance 3 條全綠 + 三個 verify command exit 0 → 完成
   - 任一條不滿足 → 寫下一輪 worker task 修補
5. 最多 5 輪。超過停止並回報 fail，列出未達成項目。

Reviewer rules:
- worker exit_code=0 不等於完成，必須讀 round review 確認 acceptance
- 不可放行：scope_drift 非空、worker_committed=true、改到「不可動的範圍」清單內的檔
- 全部完成後：不要自動 push、不要自動開 PR。回報結果，列最終 run dir。

完成後在 docs/20260526-sqlite-tail-t2-t3-Task.md 末尾追加「實測結果」區塊（範本見 Task spec 末段），含 thread id / jsonl 路徑 / token 統計 / ratio。
```

---

## 跑完後我這邊要做的（reviewer 端配額分析）

1. 從 `~/.codex/sessions/YYYY/MM/DD/` 找出本場新 jsonl（應為**新檔**而非延續 `019e50ad`）
2. 跑 token aggregation：reviewer total / fresh / cached_input
3. 抓對應 Claude Code worker session（依時間 bin）
4. 算 Reviewer/Worker ratio，對比預期 ≤ 0.61
5. 更新 `supervisor/docs/pitfall-codex-driver-thread-cache.md` 加實測結果
