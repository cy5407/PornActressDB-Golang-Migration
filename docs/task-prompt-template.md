# Task Prompt 範本 — 明確邊界 + 可驗證完成

> 設計依據：[Lecture 06 — Why Initialization Needs Its Own Phase](https://walkinglabs.github.io/learn-harness-engineering/zh-TW/lectures/lecture-06-why-initialization-needs-its-own-phase/)
> 核心精神：把「完成」綁定在 **可執行的驗證命令** 上，而不是 agent 的主觀宣告。
> 適用對象：交給 Claude Code / Codex / 其他 coding agent 的具體實作任務。

---

## 使用方式

1. 複製下方「範本本體」整段。
2. 把所有 `<...>` 佔位符換成本次任務的具體內容。
3. 把 §4 Definition of Done 的命令字串寫成 **可直接複製貼上執行** 的形式（不要寫「跑相關測試」這種模糊話）。
4. 把 §2.3 受影響檔案白名單寫到「具體 file path」級別，不要寫「database 相關檔案」。
5. 範本不要刪減段落 — 若某段不適用，寫「N/A，原因：...」，保留結構讓 agent 知道是「故意不做」而非「漏掉」。

### 若 prompt 要套到 `/goal` autonomous 模式

`/goal` 是讓 agent 自動朝目標推進、沒有 human-in-the-loop turn-by-turn。撰寫時額外遵守：

- **不要設計需要 user 中途判斷的分歧點**。所有可預期歧義都要 pre-decide 寫進 prompt：
  - scope 外的 untracked 檔 → 「不動、在回報列出」
  - dirty cache / build artefact → 「加 .gitignore，獨立 commit」
  - hook 卡住 → DoD 不要寫會踩 hook 的全域要求
- **DoD 不要要求全域 repo 狀態**（如 `git status` 必須 clean）。範圍鎖在「本 task 改動是否 committed」+「scope 外項目逐一列出」即可。
- **不可預期歧義**：runtime 撞到時，agent 把它寫成 §7 Open question，**剩下 DoD 能跑就跑完**，最後 end turn 讓使用者重新下指令 — **不要連續暫停請使用者選 1/2/3/4**。

---

## 範本本體（複製這段）

````markdown
# 任務：<一句話標題>

## 1. 背景（Why）

<為什麼要做這件事，2-3 句。讓 agent 能判斷模糊情境。>
<上游決策、相關 issue、過去踩過的雷、相依的前置任務。>

## 2. 任務邊界（Scope）

### 2.1 In scope（必須完成）

- <具體動詞 + 具體檔案/模組，例如：修改 pkg/database/store_factory.go 的 bootstrap 失敗處理>
- <...>

### 2.2 Out of scope（這次不要碰）

明確列出 agent 容易順手「改善」的鄰近區域：

- <例：不要重構 sqlite_runtime.go、不要動既有測試命名>
- <例：不要動 schema、migration、CLI 子命令名稱>
- 不要新增未要求的抽象、設定項、feature flag
- 不要碰 wiki / README / CHANGELOG（除非本任務明列）
- 不要「順手」修 lint warning / typo / 排版

### 2.3 受影響檔案白名單

僅允許修改以下檔案（其他檔案要動須先停下來問）：

- `<path/to/file_1>`
- `<path/to/file_2>`
- `implementation-notes.md`（依 CLAUDE.md 規範強制追加）

## 3. 產出物（Deliverables）

完成這個任務後，repo 內應該存在以下「可驗證的具體物件」：

1. **程式碼變更**：<列點，每點對應一個檔案/函式/行為>
2. **測試**：<新增或修改的測試名稱，至少一個 fail→pass 的紅綠測試>
3. **手動驗證紀錄**：記錄在 `implementation-notes.md` 的本任務區段，含預期輸出
4. **commit 訊息草稿**：放在回報內，不要自己 `git commit`（除非任務明列）

## 4. Definition of Done（完成判定 — 全部要綠才算完）

不可主觀宣告「應該可以了」「邏輯上是對的」。完成 = 以下命令 **全部實際執行過** 並且結果符合預期。
回報時須貼出每條命令的最後 5–10 行輸出。

- [ ] **能編譯**：`<具體命令>` exit 0
  - 例：`go build -o classifier.exe .\cmd\scanner`
- [ ] **新增/修改的測試通過**：`<具體命令含 -run 過濾器>` 顯示 PASS
  - 例：`go test .\pkg\database -run TestNewStore_BootstrapFailureReturnsError -v -count=1`
- [ ] **同模組舊測試未壞**：`<具體命令>` 全綠
  - 例：`go test .\pkg\... -count=1`
- [ ] **跨層契約鎖未紅**：`<具體命令>` 全綠
  - 例：`python -m pytest tests\test_go_cli_contracts.py -q -p no:cacheprovider`
- [ ] **手動冒煙**：`<具體一條 CLI 或 GUI 操作>` + 預期觀察到的結果
  - 例：`.\classifier.exe db verify-sync -data-dir tests\fixtures\json_db_minimal` → exit 0、stdout 含 `verify-sync OK`
- [ ] **diff 範圍乾淨**：`git diff --stat` 只動到 §2.3 白名單檔案
- [ ] **scope 內改動已 commit**：本 task 涉及的檔案已進 commit；`git status` 中剩下的 untracked/dirty 必須全部是「scope 外、預先存在」，在回報逐項列出。**不要要求全域 `working tree clean`**——會被 scope 外的快取檔 / 別 session 留下的工作卡住 hook
- [ ] **`implementation-notes.md` 已追加本任務區段**
  - 含 Design decisions / Deviations / Tradeoffs / Open questions（依 global CLAUDE.md 規範）
  - 區段標題帶起訖時間：`## [YYYY-MM-DD HH:MM → HH:MM, Xh Ym] <任務名>`

## 5. 反「提早宣告完成」規則

以下情境 **不算完成**，即使程式碼寫完了：

- 「我相信這應該可以」但沒實際跑過驗證命令 → 未完成
- 測試有寫但沒跑 / 跑了沒貼結果 → 未完成
- 編譯通過但手動冒煙沒做 → 未完成
- 改了白名單外的檔案但沒回報 → 未完成
- 留下 `TODO` / `FIXME` / 註解掉的程式碼但沒在 Open questions 標註 → 未完成
- DoD 任一項打 ❌ 但你回報「完成」→ 視為違規，必須重做該項

**例外處理**：若某項 DoD 因環境限制無法驗證（例如沒有 Wails GUI 可開、沒有 Linux 環境），**明確說「這項我沒驗證，原因是 X」**，不要假裝跑過、也不要悄悄跳過。

## 6. 中途 checkpoint（防止「一口氣寫完才回報」）

每完成一個檔案或一個邏輯片段，**先停下來貼出**：

1. 剛改了什麼（一句話）
2. 對應 DoD 哪一項
3. 該項實際驗證命令的輸出（貼最後幾行）

不要等全部寫完才回報。中途 checkpoint 讓 user 能即時叫停或修正方向。

## 7. 回報格式（任務結束時）

```
## DoD 驗收

- [x] 能編譯 — `go build ...` exit 0
- [x] 新測試通過 — TestFoo PASS
  ```
  === RUN   TestFoo
  --- PASS: TestFoo (0.03s)
  PASS
  ok      actress-classifier/pkg/database 0.412s
  ```
- [x] 舊測試未壞 — `go test .\pkg\... -count=1` → ok, 41 packages
- [ ] 手動冒煙 — 未做，原因：<...>

## 範圍確認

`git diff --stat` 結果：
```
 pkg/database/store_factory.go | 12 ++++++++++--
 pkg/database/store_factory_test.go | 35 +++++++++++++++++++++++++++++++++++
 implementation-notes.md       |  8 ++++++++
 3 files changed, 53 insertions(+), 2 deletions(-)
```

白名單外的檔案：無 / <列出 + 理由>

## Commit 訊息草稿

```
<type>(<scope>): <subject>

<body>
```

## Open questions

- <任何要 user 決定的事；沒有就寫「無」>
```
````

---

## 為什麼這樣寫（對照第六講原則）

| 第六講原則 | 範本對應段落 |
|---|---|
| 初始化 ≠ 實作，目標不混 | §2.1 / §2.2 In scope vs Out of scope 把任務邊界鎖死，agent 不能順手做別的 |
| 「自舉契約」要可執行 | §4 每一項都是命令 + exit code，不是文字描述 |
| 至少一個示例測試通過 | §4 必含「新增/修改的測試通過」 |
| 顯式記錄決策 | §4 強制寫 `implementation-notes.md`（對應 global CLAUDE.md 的習慣） |
| 防止「未驗證的累積」 | §5 明確列出哪些情境不算完成 + §6 中途 checkpoint 強迫分段驗證 |
| 接手下一步 | §7 結尾的 Open questions 讓下一個 session 能銜接 |

---

## 兩個可選強化

1. **DoD 命令直接寫成可複製貼上**
   發任務時就把 `go test ...` 完整字串寫好（含 `-run`、`-count=1`、`-v`），agent 跑完直接貼輸出，比叫他「自己想驗證方式」更不會偷工。

2. **白名單用具體 path，不用語意描述**
   `pkg/database/store_factory.go` 比 `database 相關檔案` 嚴格 100 倍，agent 不容易藉「相關」二字擴張範圍。需要涵蓋多檔可用 glob：`pkg/database/store_factory{,_test}.go`。

---

## 常見反例（避免這樣寫）

| ❌ 反例 | ✅ 修正 |
|---|---|
| 「修一下 bootstrap 的 bug」 | 「修 `pkg/database/store_factory.go::NewStore` 在 bootstrap 失敗時靜默吞錯的問題；要改成 close store + return error」 |
| 「跑一下相關測試」 | `go test .\pkg\database -run TestNewStore_Bootstrap -v -count=1` |
| 「應該不會影響其他模組」 | DoD 加一條：`go test .\pkg\... -count=1` 全綠 |
| 「順便清理一下」 | §2.2 明列「不要重構 / 不要清 lint / 不要改命名」 |
| 「完成後幫我 commit」 | §3 改成「產出 commit 訊息草稿放回報內，不要自己 commit」 |
