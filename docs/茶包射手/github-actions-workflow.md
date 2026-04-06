# GitHub Actions Workflow 故障排除紀錄

> 本文記錄在建立 `copilot-refactor-go.yml` 自動化遷移排程期間遇到的所有問題、原因與解法。

---

## Issue 1：排程未自動觸發

### 狀況
在 `refactor/go-migration-phase2` 分支設定了 `schedule: cron: '*/30 * * * *'`，但等待超過 1 小時仍無任何自動執行紀錄。手動推送空 commit 也無法激活。

### 原因
GitHub Actions 的 `schedule` 事件**只在 default branch（main）上執行**。若 workflow 檔案只存在於非 default branch，排程設定完全無效。

### 排查結果
- 確認 GitHub UI 顯示 workflow 狀態為 active（未被停用）
- 確認 workflow YAML 語法無誤
- 關鍵發現：workflow 檔案在 `refactor/go-migration-phase2`，main 上的同名 workflow 沒有 `schedule` 區塊

### 解法
切換到 main branch，在 `on:` 區塊加入 `schedule`，push 到 main：

```yaml
on:
  workflow_dispatch:
  schedule:
    - cron: '*/30 * * * *'
```

---

## Issue 2：Cron 語法錯誤

### 狀況
設定「每 30 分鐘執行一次」時，誤用 `0 0,30 * * *`，導致語法不符預期。

### 原因
`0 0,30 * * *` 表示「每天的 00:00 和 00:30 執行」，不是「每 30 分鐘」。

### 解法
改為正確的步進語法：

```yaml
schedule:
  - cron: '*/30 * * * *'   # 每 30 分鐘
  # 或
  - cron: '0 * * * *'      # 每整點（每 60 分鐘）
```

---

## Issue 3：`schedule` 不支援 `branches` 過濾

### 狀況
嘗試用 `branches` 限制排程只在特定分支觸發：

```yaml
on:
  schedule:
    - cron: '*/30 * * * *'
      branches: [refactor/go-migration-phase2]  # ← 無效
```

加入後 workflow 依然在預期以外的分支執行，且 YAML 解析未報錯。

### 原因
GitHub Actions 的 `schedule` 事件**不支援 `branches` 過濾**。只有 `push` 和 `pull_request` 事件才支援 `branches` 過濾條件。schedule 永遠在 default branch 執行，無法限制。

### 解法
移除 `branches` 條件，schedule 本身已自動限定在 main（default branch）執行：

```yaml
on:
  workflow_dispatch:
  schedule:
    - cron: '*/30 * * * *'
```

---

## Issue 4：scope guard 偵測不到新建檔案（untracked files）

### 狀況
Run #17：AI 做了 +562 行改動（新增 `tests/test_go_api_move_scan_injection.py`，43 個測試全部通過），但 workflow 輸出 `has_changes=false`，所有改動被直接丟棄，未建立 PR 也未 commit。

### 原因
scope guard 使用 `git diff --name-only` 偵測變更。此指令**只顯示已追蹤（tracked）檔案的修改**，對新建的 untracked 檔案完全不可見。

### 排查結果
```bash
# 原始寫法（只偵測追蹤檔案修改）
git diff --name-only

# 輸出：空（因為新檔案是 untracked）
# → has_changes=false → 改動丟棄
```

### 解法
同時執行 `git ls-files --others --exclude-standard` 偵測未追蹤的新建檔案：

```bash
changed_files=$(
  git diff --name-only
  git ls-files --others --exclude-standard
)
```

---

## Issue 5：Bash 腳本中反引號（backtick）觸發命令替換

### 狀況
Workflow summary 輸出 step 出現 `Permission denied` 錯誤，與實際業務邏輯無關。

### 原因
在 GitHub Actions 的 bash 腳本中，若要輸出 Markdown code block（使用反引號 `` ` ``），未轉義的反引號會被 bash 解析為**命令替換**語法，嘗試執行不存在的命令，因此報錯。

### 解法
將 Markdown 程式碼區塊中的反引號全部轉義為 `` \` ``：

```yaml
# ❌ 錯誤
run: echo "變更檔案：`git diff`"

# ✅ 正確（使用 $()）
run: echo "變更檔案：$(git diff --name-only)"

# ✅ Markdown 輸出中轉義反引號
run: echo "\`\`\`" >> $GITHUB_STEP_SUMMARY
```

---

## Issue 6：Go 1.24 vs Go 1.26 API 不相容

### 狀況
CI 環境（Go 1.24.5）編譯 `pkg/safefile/safefile.go` 時失敗：

```
./safefile.go:xx: root.ReadFile undefined
./safefile.go:xx: root.WriteFile undefined
./safefile.go:xx: root.MkdirAll undefined
```

本機（Go 1.26）可正常編譯。

### 原因
`os.Root` 型別的便利方法（`ReadFile`、`WriteFile`、`MkdirAll`）在 **Go 1.26** 才新增。GitHub Actions runner 使用 Go 1.24.5，不支援這些方法。

### 解法
改用 Go 1.24 支援的低階 API 組合實作：

| 1.26 寫法 | 1.24 相容寫法 |
|-----------|--------------|
| `root.ReadFile(path)` | `f, _ := root.Open(path)` + `io.ReadAll(f)` |
| `root.WriteFile(path, data, perm)` | `f, _ := root.OpenFile(path, os.O_WRONLY\|os.O_CREATE\|os.O_TRUNC, perm)` + `f.Write(data)` |
| `root.MkdirAll(path, perm)` | 逐層 `root.Mkdir` + `OpenRoot` |

---

## Issue 7：Node.js 20 棄用警告

### 狀況
每次執行均出現警告：
```
Node.js 20 actions are deprecated ... will be removed September 16th, 2026
```

### 原因
workflow 中使用的 `actions/checkout@v4`、`actions/setup-go@v5` 等 Actions 仍基於 Node.js 20，GitHub 將於 2026-06-02 強制升級至 Node.js 24。

### 解法
在 workflow 環境變數中預先啟用 Node.js 24：

```yaml
env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true
```

或等待各 Action 官方發布支援 Node.js 24 的新版本後升級。

---

## Issue 8：scope guard regex 未涵蓋測試檔案

### 狀況
Run #16：scope guard 拒絕 AI 新增的 `src/services/go_bridge_test.py`，報 out-of-scope，導致整輪改動被丟棄。

### 原因
scope guard 的允許清單（regex）只包含主程式檔案名稱，未考慮對應的測試檔案。

### 解法
更新 scope guard regex，在每個模組名稱後加入可選的 `_test` 後綴，並包含 `tests/` 目錄：

```bash
# ❌ 舊寫法（漏掉測試檔）
(extractor|studio)\.py

# ✅ 新寫法
(extractor|studio)\.py|tests/test_(extractor|studio).*\.py
# 或使用更通用的 tests/ 目錄允許規則
tests/test_go_api.*\.py
```

---

## Issue 9：PR 堆積問題（多輪 AI 執行累積同一 PR）

### 狀況
多輪排程執行後，`peter-evans/create-pull-request@v8` 每次 force-push 到同一分支，導致同一 PR 越堆越大，包含多輪的改動混在一起，難以審查。且若 PR 未及時 merge，下一輪 AI 看到的任務清單不更新，可能重複執行同一個任務。

### 原因
`peter-evans/create-pull-request` 的設計：若指定的 branch 已存在，會直接 force-push 更新現有 PR，而非建立新 PR。

### 解法
廢棄 PR 模式，改為**直接 push 到專用工作分支** `copilot/migration-work`：

```yaml
# 移除 peter-evans/create-pull-request
# 改為直接 git commit + push
- name: Commit and push to work branch
  run: |
    git add [允許的檔案]
    git commit -m "refactor: advance python-to-go migration"
    git push origin copilot/migration-work
```

工作分支每次執行前先 rebase onto main，確保不落後。AI 透過讀取 `MIGRATION_STATUS.md`（只存在於工作分支）來得知目前進度，避免重複執行已完成任務。

---

## Issue 10：AI 產生超出 scope 的檔案（out-of-scope changes）

### 狀況
Run #37：scope guard 偵測到 AI 嘗試建立名為 `scanner` 的檔案，不在允許清單內，整輪改動被拒絕並以 exit code 1 終止。

### 原因
AI（Copilot CLI）在某些情況下會在 scope 之外建立輔助性的暫存或工具腳本。

### 排查結果
scope guard 正確地攔截了超出範圍的操作，工作分支未被污染。

### 解法
scope guard 設計本身正確，無需修改。下一輪（Run #38）AI 重試同一個任務時改動在允許範圍內，順利通過並 commit。

這也驗證了 scope guard 的必要性：**不論 AI 輸出什麼，最終能進入版本庫的只有明確允許的檔案**。

---

## Issue 11：Go Cache 委派後測試找不到快取檔案路徑

### 狀況
執行 `tests/test_cache_manager_security.py` 時，3 個測試失敗：

```
FAILED tests/test_cache_manager_security.py::test_disk_cache_uses_json_payload
FAILED tests/test_cache_manager_security.py::test_legacy_pickle_cache_is_ignored_and_removed
FAILED tests/test_cache_manager_security.py::test_compressed_json_cache_roundtrip
```

錯誤訊息為：
```
FileNotFoundError: No such file or directory: '...pytest-of-cy5407.../xxx.cache'
```

`manager.set()` 回傳 `True`（表示成功），但 Python 端用 `_get_file_path()` 計算的路徑上找不到實際檔案。

### 原因
`CacheManager` 在 Phase 4A 將 `set()`/`get()`/`delete()` 委派給 Go CLI（`classifier.exe cache set`）後，快取檔案由 **Go CLI 寫入 Go 自己計算的路徑**。然而測試中呼叫 `manager._get_file_path(cache_key)` 是 **Python 端計算的路徑**，兩者的雜湊/目錄邏輯不一致，導致 Python 算出的路徑上根本沒有檔案。

### 排查結果
- 確認該測試檔案是在 security 強化 commit（`8148592`）加入，早於 Phase 4A 委派改動
- 240 個其他測試全部通過，只有這 3 個路徑驗證型測試失敗
- `manager.set()` 本身功能正常，只是路徑計算邏輯 Python/Go 兩端尚未對齊

### 解法（待執行）
兩個方向擇一：

**方案 A（推薦）**：修改測試，改用 Go CLI 查詢確認快取是否存在，不直接操作 Python 端路徑：
```python
# 原本（直接讀取 Python 計算的路徑）
cache_path = manager._get_file_path(cache_key)
payload = json.loads(cache_path.read_text())

# 改為（透過 manager 公開 API 驗證）
assert manager.get("video:test") == value  # 用 Go CLI 查詢驗證
```

**方案 B**：讓 Go CLI 的路徑雜湊邏輯與 Python `_get_file_path()` 保持一致（修改 Go 端或 Python 端使兩者輸出相同路徑）。

> ⚠️ 目前此問題不影響應用程式實際功能，快取寫入/讀取均正常，只是測試的**白箱路徑驗證**失效。

---

## 附錄：重要的 GitHub Actions 行為差異

| 觸發類型 | 支援 `branches` 過濾 | 執行分支 |
|----------|---------------------|---------|
| `push` | ✅ | 被 push 的分支 |
| `pull_request` | ✅ | PR 的 head 分支 |
| `schedule` | ❌ | 永遠是 default branch（main） |
| `workflow_dispatch` | ❌（使用 inputs） | 觸發時選擇的分支 |

---

## Issue 12：JAVDB 搜尋 False Positive（WTB-045 錯誤匹配成 AWTB-005）

### 狀況
搜尋番號 `WTB-045` 時，JAVDB 搜尋結果頁回傳多筆相似結果（AWTB-005、KTB-045 等），程式錯誤地取用第一筆 `AWTB-005` 並將其資料存入資料庫。

### 原因
`safe_javdb_searcher.py` 的 `search_javdb()` 方法中有一段 fallback 邏輯：

```python
# 如果沒有找到完全匹配的，使用第一個結果  ← 問題所在
if not best_match_url:
    best_match_url = video_links[0].get("href")
```

當搜尋結果中沒有任何連結的文字精確包含 `WTB-045` 時，fallback 直接取第一筆（AWTB-005），完全繞過精確比對。

### 排查結果
- `_normalize_code_for_match()` 比對邏輯本身正確：`WTB045` 不會匹配 `AWTB005`
- 但 `best_match_url` 為空時，fallback 使第一筆錯誤結果進入詳情頁流程
- 詳情頁解析時直接以 `video_id` 當作 `code` 欄位（沒有驗證頁面實際番號），導致資料庫寫入錯誤女優資訊

### 解法
**修改 `src/services/safe_javdb_searcher.py`**：

1. **移除 fallback**：無精確匹配時直接回傳 `None`（視為未找到）

```python
# 修改後
if not best_match_url:
    logger.debug(f"🔍 JAVDB 未找到番號 {video_id} 的精確匹配結果，視為未找到")
    return None
```

2. **詳情頁二次驗證**：`_parse_detail_page()` 從頁面標題提取番號，與搜尋目標比對

```python
title_code_match = re.match(r"^([A-Z0-9]+-\d+)", info["title"], re.IGNORECASE)
if title_code_match:
    page_code = title_code_match.group(1).upper()
    if page_code != video_id.upper():
        logger.warning(f"⚠️ JAVDB 詳情頁番號不符: 搜尋 {video_id}，頁面顯示 {page_code}，視為未找到")
        return None
```

3. **新增測試**：`tests/test_safe_javdb_searcher.py` 覆蓋 false positive 場景
   - `test_search_javdb_no_fallback_on_mismatch`：無精確匹配時回傳 None，且不發出詳情頁請求
   - `test_search_javdb_detail_page_code_mismatch_returns_none`：詳情頁番號不符時回傳 None

> ℹ️ **WTB-045** 本身確實不存在於 JAVDB（本身就是無效番號）；**WTB-031** 同樣無效。這是程式應正常回報「未找到」的情況，而非誤匹配其他番號。

