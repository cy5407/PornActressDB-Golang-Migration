/goal 完成 target repo 的 T2 + T3 兩個 task 並通過全部 verify commands。

Target repo:
<USER_HOME>\.codex\worktrees\<WORKTREE_ID>\PornActressDB-Golang-Migration

Worktree branch:
codex/shadow-db-sqlite （已跟 origin 同步，PR #19 已 merge 進 main）
建議：本場開新 branch `codex/sqlite-tail-t2-t3` 從 `codex/shadow-db-sqlite` 拉出，跑完後 PR 進 main。

Task spec:
docs/20260526-sqlite-tail-t2-t3-Task.md
（這份文件是 self-contained spec，請完整讀完再開工，包含 T2 / T3 / Acceptance / Verify / 不可動的範圍 / 對照組）

Supervisor launcher:
<SUPERVISOR_PATH>\ask-supervisor.ps1

Loop protocol:
1. 開工前讀 Task spec 與 PR #19 merge 後的 git log 了解現況
2. 每輪只呼叫一次 supervisor，格式：
   <SUPERVISOR_PATH>\ask-supervisor.ps1 "<本輪 worker task>" `
     -Repo "<USER_HOME>\.codex\worktrees\<WORKTREE_ID>\PornActressDB-Golang-Migration" `
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