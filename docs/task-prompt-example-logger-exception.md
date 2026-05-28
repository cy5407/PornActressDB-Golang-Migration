# 範例：logger.exception 補漏任務 prompt

> 對應範本：[`task-prompt-template.md`](./task-prompt-template.md)
> 日期：2026-05-29
> 背景：Phase 3 mergeFromRoot CC refactor 已 merge 到 main 後，SonarQube 再掃出 2 個 codemod 漏網的 `logger.error` 站點，需手改補上。

這份檔案保留兩個版本：

1. **完整版**（§A）— 完全照範本七段結構展開，給 agent 看的完整脈絡。
2. **壓縮版**（§B）— 套到 `/goal` 上時要在 4000 字元內，所以把背景與重複敘述濃縮，只留可執行邊界與 DoD。

兩版同義；正式發給 agent 用壓縮版，需要釐清脈絡時再回看完整版。

---

## A. 完整版（七段結構）

### 1. 背景（Why）

Phase 1 跑的 `scripts/migrate_log_exception.py` codemod 白名單只認 except 綁定變數 `{e}` / `{exc}` / `{err}` 三個名字，導致以下 2 個 except 區塊內、用其他變數名綁定的 `logger.error` 沒被遷移。SonarQube 在 push 後重新掃描標出這 2 處，是 Phase 1 沒覆蓋到的真 bug（不是 false positive，不是函式參數）。

要修而不擴 codemod 白名單，因為：

- 只有 2 處、手改 5 分鐘搞定，比改 codemod + 重跑安全；
- codemod 白名單是 Phase 1 凍結的 spec，擴它要另開議題評估副作用。

### 2. 任務邊界（Scope）

#### 2.1 In scope（必須完成）

- 手改 `src/models/json_database.py:292`
  原：`logger.error(f"❌ 資料儲存失敗（所有重試已用盡）: {pe}")`
  改：`logger.exception("❌ 資料儲存失敗（所有重試已用盡）")`
- 手改 `src/scrapers/cache_manager.py:141`
  原：`logger.error(f"建立備援索引失敗: {fallback_error}")`
  改：`logger.exception("建立備援索引失敗")`
- 跑 `ruff check src/ --fix` 處理副作用（F841 unused `as pe` / `as fallback_error`、F541 placeholderless f-string）

#### 2.2 Out of scope（這次不要碰）

- 不要擴 `scripts/migrate_log_exception.py` 的白名單
- 不要重跑 codemod
- 不要動 SonarQube 報的 schema NULL false positive（A 類）或 security hotspots（C/D 類）
- 不要碰 `implementation-notes.md` 以外的文件
- 不要重排 imports 或 reformat 其他不相關行

#### 2.3 受影響檔案白名單

僅允許修改以下檔案（其他要動先停下來問）：

- `src/models/json_database.py`
- `src/scrapers/cache_manager.py`
- `implementation-notes.md`（追加任務區段）

例外：若 `ruff --fix` 連動改到別的檔案（例如 import 排序），那檔案也算白名單，但要在回報明列。

### 3. 產出物（Deliverables）

1. **程式碼變更**：
   - `json_database.py:292`：`logger.error(f"...{pe}")` → `logger.exception("...")`
   - `cache_manager.py:141`：同上，處理 `fallback_error`
2. **驗證命令輸出**：見 §4 DoD
3. **`implementation-notes.md` 追加區段**：標題 `## [YYYY-MM-DD HH:MM] Phase 1.1 — logger.exception 補漏`，記錄為何選手改而非擴白名單（Deviations / Tradeoffs ≥ 1 項）

### 4. Definition of Done

不可主觀宣告。以下命令全部要實際跑過且符合預期：

- [ ] **目標行已遷移**：`rg -n "logger\.error.*\{(pe|fallback_error)\}" src/` → 0 matches
- [ ] **`exc_info=True` 仍是 0**：`rg -rn "exc_info=True" src/` → 0 matches（不退步）
- [ ] **ruff 清淨**：`ruff check src/` → `All checks passed!`
- [ ] **pytest 全綠**：`python -m pytest tests/ -q -p no:cacheprovider` → `≥1091 passed, 2 skipped`
- [ ] **手動冒煙**：構造觸發兩條 except 的小情境跑一次，目測 log 帶 traceback；無法重現則明寫「未冒煙，原因：X」，不要假跑
- [ ] **diff 乾淨**：`git diff --stat` 只動到 §2.3 白名單；意外檔案單獨列
- [ ] **implementation-notes.md 追加區段**已成立、含 timestamp heading 與 Deviations/Tradeoffs ≥ 1 項
- [ ] **git commit**：完成的改動已 commit，`git status` 顯示 `nothing to commit, working tree clean`

### 5. 反「提早宣告完成」規則

以下情境不算完成：

- 「我覺得 ruff fix 應該會處理掉」但沒實跑 `ruff check src/` 確認 → 未完成
- pytest 寫了沒跑、跑了沒貼結果 → 未完成
- 改了白名單外的檔案沒在回報列出 → 未完成
- 留下 `TODO` / `FIXME` / `# 之後再說` → 未完成
- DoD 任一項 ❌ 但宣稱完成 → 違規，必須補

冒煙若真的不能跑（兩條都是 except 路徑、要刻意觸發 `PermissionError` 或備援索引建立失敗），可寫「未冒煙，原因：要構造特定 IO 失敗條件」，但要明說。

### 6. 中途 checkpoint

每改一個檔案就停下來貼：

1. 改了什麼（一句話）
2. 對應 DoD 哪一項
3. 該項驗證命令的輸出（rg / ruff / pytest tail）

不要兩個檔案一起改完才回報。

### 7. 回報格式（結束時）

```
## DoD 驗收
- [x] 目標行已遷移 — `rg ... → 0 matches`
- [x] exc_info=True 仍 0 — `rg ... → 0 matches`
- [x] ruff 清淨 — `All checks passed!`
- [x] pytest — `1091 passed, 2 skipped`（或實際數字）
- [ ] 手動冒煙 — 未做，原因：<...>
- [x] implementation-notes 追加 — `## [...] Phase 1.1 ...`
- [x] git commit — `<hash>`

## 範圍確認
git diff --stat:
 src/models/json_database.py    | X +/-
 src/scrapers/cache_manager.py  | X +/-
 implementation-notes.md        | X +

白名單外的檔案：無 / <列出>

## Open questions
<例：ruff --fix 順手改了 imports 排序我保留還是 revert？>
```

---

## B. 壓縮版（套 `/goal` 用，<4000 字元）

````text
完成 logger.exception 補漏：手改 src/models/json_database.py:292 與
src/scrapers/cache_manager.py:141 兩處 except 區塊內遺漏的
logger.error → logger.exception（codemod 白名單只認 {e}/{exc}/{err}，這兩處用
{pe}/{fallback_error} 漏掃；只 2 處、手改 5 分鐘，不擴白名單）。

紀律：
- 不擴 scripts/migrate_log_exception.py 白名單
- 不重跑 codemod
- 不動 schema NULL false positive、security hotspot、其他 SonarQube false positive
- 不 reformat 不相關行、不重排 imports
- 每改一個檔案先 checkpoint（貼 rg/ruff/pytest 輸出），不要兩檔一起改完才回報

In scope（兩處編輯逐字）：
- json_database.py:292
  原：logger.error(f"❌ 資料儲存失敗（所有重試已用盡）: {pe}")
  改：logger.exception("❌ 資料儲存失敗（所有重試已用盡）")
- cache_manager.py:141
  原：logger.error(f"建立備援索引失敗: {fallback_error}")
  改：logger.exception("建立備援索引失敗")
- 跑 ruff check src/ --fix 收掉 F841 unused as pe/as fallback_error、F541
  placeholderless f-string

受影響檔案白名單（動其他檔先停問）：
- src/models/json_database.py
- src/scrapers/cache_manager.py
- implementation-notes.md（追加 ## [YYYY-MM-DD HH:MM] Phase 1.1 —
  logger.exception 補漏 區段，含 Deviations/Tradeoffs ≥1 項，記為何手改非擴白名單）
- ruff --fix 連動改到他檔（如 import 排序）也算白名單，但回報明列

DoD（命令必須實際跑過且輸出符合，不可主觀宣告）：
- [ ] rg -n "logger\.error.*\{(pe|fallback_error)\}" src/ → 0 matches
- [ ] rg -rn "exc_info=True" src/ → 0 matches（不退步）
- [ ] ruff check src/ → All checks passed!
- [ ] python -m pytest tests/ -q -p no:cacheprovider → ≥1091 passed, 2 skipped
- [ ] 手動冒煙：構造觸發兩條 except 的小情境跑一次目測 log 帶 traceback；無法重現
  則明寫「未冒煙，原因：X」不假跑
- [ ] git diff --stat 只動到白名單；意外檔案單獨列
- [ ] implementation-notes.md 追加區段含 timestamp heading
- [ ] 全部改動 git commit 後 git status 顯示 nothing to commit, working tree clean

不算完成：「ruff fix 應該會處理」但沒實跑 ruff 確認；pytest 寫了沒跑或跑了沒貼；
改白名單外檔案沒列；留 TODO/FIXME；DoD 任一 ❌ 卻宣稱完成。

回報格式：每 checkpoint 一句改了什麼 + 對應 DoD 項 + 該項驗證輸出 tail；結束逐項
DoD 標 ✅/❌ + git diff --stat + git status 結果 + Open questions。
````

---

## 完整版 → 壓縮版做了哪些刪減

| 完整版段落 | 壓縮版處理 | 原因 |
|---|---|---|
| §1 背景（Why） | 濃縮成首段一句 | `/goal` 不需要重述決策推導，agent 看 in scope 就懂 |
| §3 Deliverables | 併入 §2.1 In scope | 兩段內容重疊，留一份 |
| §5 反提早宣告完成 | 濃縮成「不算完成」一行 | 規則不變，敘述精簡 |
| §6 中途 checkpoint | 併入「回報格式」最後一段 | 兩段都在講何時回報，合併 |
| §7 回報格式 | 留 1 行歸納 | 結構由 checkpoint 規則隱含 |

刪減原則：**規則本身不刪，只刪重複敘述與動機鋪陳**。Agent 收到壓縮版仍能完整執行所有 DoD。

---

## 後續對應

- 範本本體：[`task-prompt-template.md`](./task-prompt-template.md)
- 範本設計依據：[Lecture 06 — Why Initialization Needs Its Own Phase](https://walkinglabs.github.io/learn-harness-engineering/zh-TW/lectures/lecture-06-why-initialization-needs-its-own-phase/)
- 本任務追蹤：執行後預期追加到 `implementation-notes.md` 的 `Phase 1.1` 區段
