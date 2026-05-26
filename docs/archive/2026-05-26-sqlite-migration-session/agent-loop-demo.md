# Agent Loop Demo

此文件是本次 Codex App outer driver 透過 `ask-supervisor.ps1` 驅動 Claude worker 的閉環產物。Round 1 先建立文件並留下 artifact placeholder；Round 2 由 worker 依 Round 1 artifacts 補齊內容；最後由 outer driver 在 Round 2 結束後，把「最後一輪」supervisor artifacts 的實際路徑與 JSON 欄位寫回本檔，因為這些路徑只有 worker 結束後才會生成。

本測試在開始前已觀察到 target repo 有兩個 baseline dirty files，這兩個檔案不是本輪變更，也沒有被還原、刪除、暫存或清理：

```text
 D docs/superpowers/specs/2026-05-23-sqlite-migration-design.md
?? docs/supervisor-worktree-check.md
```

## 1. Project summary

Target repo 是 `C:\Users\cy5407\.codex\worktrees\4238\PornActressDB-Golang-Migration`，目前工作分支用於 PornActressDB / Actress Classifier 的 Golang 與 SQLite migration 整合工作。專案包含 Go CLI / Wails GUI、Python scraper/search pipeline、Rust `db-tool` 與 SQLite runtime data store；本次 demo 不觸碰產品程式碼，只用 `docs/agent-loop-demo.md` 證明 Codex App 可以外層驅動 supervisor，讓 Claude worker 產生文件，外層再讀 artifacts、檢查缺口、發起下一輪修正並收斂。

本次 loop 實際執行兩輪 supervisor launcher。兩輪都使用 `-NoReviewer -BypassPermissions -Verify "git diff --check"`，所以 reviewer 判斷由 Codex outer driver 負責；`round-01-review.json` 則提供 worker exit code、timeout、commit、scope drift 與 verify 結果作為可機器讀取的證據。

## 2. Verified commands

最後一次 outer driver 驗收時，在 target repo 內實際執行以下命令。

```text
$ git diff --check
EXIT=0
OUTPUT=(no output)
```

`git diff --check` exit code 為 0，表示目前 diff 沒有 whitespace error 或 conflict marker。

```text
$ git status --short
 D docs/superpowers/specs/2026-05-23-sqlite-migration-design.md
?? docs/agent-loop-demo.md
?? docs/supervisor-worktree-check.md
EXIT=0
```

重點輸出是：兩個 baseline dirty files 仍維持原狀，本測試新增的唯一 target repo 檔案是 `?? docs/agent-loop-demo.md`。Round 2 supervisor JSON 內的 verify command 也記錄 `git diff --check`，exit code 為 0。

## 3. Remaining risks

Pre-existing dirty files 仍存在，且不屬於本輪變更：`D docs/superpowers/specs/2026-05-23-sqlite-migration-design.md` 是開始前就已刪除的 tracked file；`?? docs/supervisor-worktree-check.md` 是開始前就已存在的 untracked file。本測試刻意不清理它們，避免覆蓋使用者或其他 agent 的工作。

本次只驗證 supervisor worker loop 與文件 artifact，不驗證產品功能、SQLite migration correctness、Wails build、Go/Python/Rust test suites，也沒有進行 commit 或 push。最後一輪 artifact 路徑是本機絕對路徑，移到其他機器或其他 worktree 後不一定可解析。

## 4. Supervisor evidence

最後一輪 supervisor artifacts 的實際完整路徑如下：

```text
handoff.md:
C:\Users\cy5407\Desktop\程式語言\supervisor\output\agent-loop\20260526_140947_update-docs-agent-loop-demo-md-only-this\handoff.md

round-01-review.json:
C:\Users\cy5407\Desktop\程式語言\supervisor\output\agent-loop\20260526_140947_update-docs-agent-loop-demo-md-only-this\rounds\01\supervisor-runs\20260526_140947_update-docs-agent-loop-demo-md-only-this\round-01-review.json
```

從最後一輪 `round-01-review.json` 讀到的欄位如下：

```text
worker.exit_code: 0
worker.timed_out: false
git.worker_committed: false
git.scope_drift: []
verify[0].cmd: git diff --check
verify[0].exit_code: 0
```

最後一輪 handoff 顯示 worker completed 且 `exit=0`，狀態為 `needs_external_review`，這符合 `-NoReviewer` 模式：worker 產物完成後交回 Codex outer driver 驗收。最後一輪 JSON 同時顯示 `head_before` 與 `head_after` 相同、`files_committed` 為空、`scope_drift` 為空，沒有 worker self-commit 或額外 scope drift。

## 5. Acceptance checklist

| Item | Result | Evidence |
|---|---|---|
| file exists | PASS | `docs/agent-loop-demo.md` 存在，且 `git status --short` 顯示 `?? docs/agent-loop-demo.md`。 |
| required sections present | PASS | 本檔包含 `Project summary`、`Verified commands`、`Remaining risks`、`Supervisor evidence`、`Acceptance checklist`，每節都有具體內容。 |
| git diff --check passed | PASS | 最後一次 outer driver 驗收 `git diff --check` exit 0；最後一輪 supervisor verify 也記錄 `verify[0].exit_code: 0`。 |
| no worker self-commit | PASS | 最後一輪 JSON 顯示 `git.worker_committed: false`、`files_committed: []`、`head_before` 等於 `head_after`。 |
| no scope drift | PASS | 最後一輪 JSON 顯示 `git.scope_drift: []`；最後 `git status --short` 只有兩個 baseline dirty files 加本檔。 |
| only allowed file changed by this test | PASS | 開始前 baseline dirty files 是 `D docs/superpowers/specs/2026-05-23-sqlite-migration-design.md` 與 `?? docs/supervisor-worktree-check.md`；本測試唯一新增或修改的 target repo 檔案是 `docs/agent-loop-demo.md`。 |
| final supervisor artifact paths recorded | PASS | §4 已列出最後一輪 `handoff.md` 與 `round-01-review.json` 的完整絕對路徑，並列出指定 JSON 欄位。 |
