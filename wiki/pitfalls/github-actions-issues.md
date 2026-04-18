---
category: CI/CD
date: 2026-04-06
---
# GitHub Actions 故障排除紀錄

> 來源：`docs/茶包射手/github-actions-workflow.md`  
> 記錄建立 `copilot-refactor-go.yml` 期間遇到的所有問題。

---

## Issue 1：排程未自動觸發

**原因**：`schedule` 事件**只在 default branch（main）上執行**。workflow 在非 main 的分支上，排程完全無效。

**解法**：切到 main branch 再設定 schedule。

---

## Issue 2：Cron 語法錯誤

**原因**：`0 0,30 * * *` 是「每天 00:00 和 00:30 各一次」，不是每 30 分鐘。

**解法**：`*/30 * * * *`（每 30 分鐘）或 `0 * * * *`（每整點）

---

## Issue 3：`schedule` 不支援 `branches` 過濾

**原因**：只有 `push` 和 `pull_request` 支援 `branches`，schedule 永遠在 default branch 執行。

**解法**：移除 `branches` 條件。

---

## Issue 4：scope guard 偵測不到新建檔案（untracked files）

**原因**：`git diff --name-only` 只偵測已追蹤檔案的修改，新建的 untracked 檔案完全不可見。

**解法**：
```bash
changed_files=$(
  git diff --name-only
  git ls-files --others --exclude-standard
)
```

---

## Issue 5：Bash 腳本中反引號觸發命令替換

**原因**：未轉義的反引號被 bash 解析為命令替換語法。

**解法**：使用 `$()` 替代反引號；Markdown 輸出中轉義為 `` \` ``。

---

## Issue 6：Go 1.24 vs Go 1.26 API 不相容

**原因**：`os.Root` 的 `ReadFile`/`WriteFile`/`MkdirAll` 在 Go 1.26 才新增，CI 使用 Go 1.24.5。

**解法**：改用低階 API：
| 1.26 寫法 | 1.24 相容寫法 |
|-----------|--------------|
| `root.ReadFile(path)` | `f, _ := root.Open(path)` + `io.ReadAll(f)` |
| `root.WriteFile(path, data, perm)` | `root.OpenFile(...)` + `f.Write(data)` |
| `root.MkdirAll(path, perm)` | 逐層 `root.Mkdir` |

---

## Issue 7：Node.js 20 棄用警告

**原因**：`actions/checkout@v4`、`actions/setup-go@v5` 仍基於 Node.js 20，將於 2026-06-02 移除。

**解法**：
```yaml
env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true
```

---

## Issue 8：scope guard regex 未涵蓋測試檔案

**原因**：允許清單只列主程式檔名，未含對應的 `_test.py` 或 `tests/` 目錄。

**解法**：正則加入 `tests/test_go_api.*\.py` 或各模組的可選 `_test` 後綴。

---

## Issue 9：PR 堆積問題

**原因**：`peter-evans/create-pull-request` 在同一分支 force-push，每輪 PR 越堆越大。

**解法**：廢棄 PR 模式，改為直接 push 到專用工作分支 `copilot/migration-work`。

---

## Issue 10：AI 產生超出 scope 的檔案

**結論**：scope guard 設計正確，AI 重試時自行改回範圍內。此紀錄驗證 scope guard 的必要性。

---

## Issue 11：Go Cache 委派後測試找不到快取路徑

**原因**：Python `_get_file_path()` 計算的路徑與 Go CLI 寫入路徑不一致（雜湊/目錄邏輯不同）。

**解法（待執行）**：
- 方案 A（推薦）：修改測試，改用 `manager.get()` 驗證，不直接操作路徑
- 方案 B：讓 Go/Python 兩端路徑邏輯對齊

---

## Issue 12：JAVDB 搜尋 False Positive

→ 詳見 [wiki/pitfalls/javdb-false-positive.md](javdb-false-positive.md)

**核心**：移除 `best_match_url` 的 fallback（取第一筆），改為無精確匹配時直接回傳 `None`；詳情頁加二次番號驗證。

---

## Issue 13：GUI「修正片商資料」按鈕出現「Go CLI 不可用」

→ 詳見 [wiki/pitfalls/gui-bridge-wrong-access.md](gui-bridge-wrong-access.md)

**核心**：`UnifiedClassifierCore` 沒有 `go_bridge` 屬性，改用 `from services.go_bridge import get_bridge`。

---

## Issue 14：`db_fix_studios` 未在 `go_api/__init__.py` 匯出

→ 詳見 [wiki/pitfalls/go-api-export-missing.md](go-api-export-missing.md)

**核心**：新增 go_api 函式必須同步更新三處：`db.py` 實作 → `__init__.py` import → `__init__.py` `__all__` → `go_bridge.py` 重匯出。

---

## Issue 15：Go CLI `fix-studios` 未定義 `-json` flag

→ 詳見 [wiki/pitfalls/go-cli-json-flag-missing.md](go-cli-json-flag-missing.md)

**核心**：所有 Go 子命令必須宣告 `_ = fs.Bool("json", false, "...")` no-op flag。

---

## Issue 16：Guard 誤判 Go 二進位檔（`classifier` 無副檔名）

**症狀**：Copilot agent 在 Linux runner 執行 `go build` 後，workflow 被 Guard 攔截並中止（`out-of-scope`），即使程式碼改動完全正確。

**原因**：
- Go build 在 Linux 產生 `classifier`（無副檔名）
- `.gitignore` 只忽略 `classifier.exe`，`classifier` 沒有被忽略
- `git ls-files --others --exclude-standard` 偵測到 `classifier` 為新建 untracked 檔案
- Guard regex 未預期此檔名，判定為 out-of-scope

**解法**：雙重防護

```yaml
# 1. Guard 步驟前加 cleanup
- name: 🧹 Cleanup Go build artifacts
  shell: bash
  run: rm -f classifier classifier.exe

# 2. Guard regex 白名單加入 classifier
allowed_pattern="(src/.*\.py|pkg/.*\.go|cmd/.*\.go|\.github/prompts/.*\.md|tests/.*\.py|classifier(\.exe)?$)"
```

**教訓**：跨平台 binary 名稱不同（Linux: `classifier` / Windows: `classifier.exe`），`.gitignore` 與 scope guard 都要同時處理兩種名稱。

---

## Issue 17：`git add <path>` 無法 stage 已刪除的檔案

**症狀**：Phase 6C 需要整檔刪除（如 `go_accelerated_db.py`），但 `git add src/models/go_accelerated_db.py` 對不存在的路徑**靜默成功但不 stage 任何東西**，commit 後刪除未被記錄。

**原因**：`git add <path>` 對已刪除的路徑不報錯，直接跳過。Workflow 原本只有 `git add src/ pkg/ cmd/`，等效於 `git add` 已存在的目錄，刪除操作不被捕捉。

**解法**：改用 `git add -u` 追蹤刪除

```bash
# ❌ 錯誤：刪除檔案後這樣做沒有效果
git add src/models/go_accelerated_db.py

# ✅ 正確：-u 旗標會追蹤所有修改（含刪除）
git add -u src/
git add src/ pkg/ cmd/ .github/prompts/  # 再補上新建檔案
```

**YML 實作**：

```yaml
- name: Stage changes
  shell: bash
  run: |
    git add -u src/ pkg/ cmd/ .github/prompts/  # stage 修改+刪除
    git add src/ pkg/ cmd/ .github/prompts/      # stage 新建
```

---

## Issue 18：Copilot Agent 執行時間與深度不足

**症狀**：每次 workflow 執行只完成一個小任務（如 extractor.py 改動 +18 -183），Phase 6 共 9 個任務需要執行 9 次，且每次 agent 思考步驟有限。

**原因**：
- `timeout-minutes: 45` — 單次執行最多 45 分鐘
- `--max-autopilot-continues 5` — agent 最多 5 步思考迴圈
- prompt 指示「每次只做一個任務」

**解法**：三項並行提升

| 設定 | 舊值 | 新值 | 效果 |
|------|------|------|------|
| `timeout-minutes` | 45 | **90** | 允許更複雜修改 |
| `--max-autopilot-continues` | 5 | **20** | agent 思考步驟 4x |
| prompt 每次任務數 | 1 | **同 Phase 最多 3** | 減少觸發次數 |

```yaml
# YML 修改
timeout-minutes: 90

run: |
  copilot agent run \
    --max-autopilot-continues 20 \
    ...
```

```markdown
<!-- prompt 修改 -->
You may complete **up to 3 tasks in one run** if they are in the same Phase
and all tests pass after each task.
```

---

## Issue 19：每次 Workflow 需手動觸發，Phase 6 無法自動完成

**症狀**：9 個 Phase 6 任務每次只做 1-3 個，需要人工盯著手動觸發下一次，效率低。

**解法**：自鏈式觸發（Self-chaining Workflow）

在 workflow 最後新增步驟，成功完成任務後自動觸發下一次執行：

```yaml
- name: 🔁 Auto-trigger next run if tasks remain
  if: steps.scope.outputs.has_changes == 'true'
  env:
    GH_TOKEN: ${{ secrets.PERSONAL_ACCESS_TOKEN }}
  shell: bash
  run: |
    remaining=$(grep -c "^\- \[ \] TODO:" .github/prompts/refactor-python-to-go-migration.md 2>/dev/null || echo "0")
    echo "Remaining TODO tasks: $remaining"
    if [ "$remaining" -gt 0 ]; then
      gh workflow run copilot-refactor-go.yml --ref main
      echo "Next run triggered"
    else
      echo "All tasks completed!"
    fi
```

**終止條件**：prompt 中 `[ ] TODO:` 數量歸零，自動停止。

**必要前提**：

```yaml
permissions:
  contents: write
  pull-requests: write
  actions: write    # ← 必須加這行才能呼叫 gh workflow run
```

**觸發失敗保護**：若任務失敗 → Guard 偵測無 changes → `has_changes != 'true'` → **不觸發下一次**，自動停止迴圈。

---

## Issue 20：Go Bridge 在 Linux CI 上找不到 `classifier` binary，導致 Phase 6 fallback 移除後全部測試失敗

**症狀**：Phase 6A-1 agent 移除 Python fallback 後，CI 上 16 個 extractor 測試全部回傳 `None`（應回傳番號）。只有「預期 `None`」的 FC2/PPV 和無效檔名測試通過。

**根本原因鏈**：

```
Linux CI builds → classifier (無 .exe)
  ↓ 
GoBridge._find_exe() 只找 classifier.exe
  ↓
Path.cwd() / "classifier.exe" 不存在
shutil.which("classifier") 只搜 PATH（project root 不在 PATH）
  ↓
is_available = False
  ↓
_extract_code_via_go() 回傳 None
  ↓
Python fallback 已被 Phase 6A-1 移除
  ↓
extract_code() 回傳 None（所有有效番號）
```

**修正**：`go_bridge.py` `_find_exe()` 改為跨平台搜尋

```python
# 修正前：只找 classifier.exe
possible_paths = [
    Path(__file__).parent.parent.parent / "classifier.exe",
    Path.cwd() / "classifier.exe",
    ...
]

# 修正後：Windows 優先 .exe，Linux 優先無副檔名
exe_names = ["classifier.exe", "classifier"] if is_windows else ["classifier", "classifier.exe"]
search_dirs = [Path(__file__).parent.parent.parent, Path.cwd(), ...]
for name in exe_names:
    for base in search_dirs:
        if (base / name).exists():
            return str((base / name).resolve())
```

**`.gitignore` 補充**：

```gitignore
# Linux/macOS Go build artifacts (no extension)
classifier
scanner
ralph-loop
```

**教訓**：
- `.gitignore` 只寫 `*.exe` 不夠，Linux CI 產生的無副檔名 binary 也需要忽略
- Go bridge `is_available` 失效時，刪除 Python fallback 會造成「靜默失敗」（全部回傳 `None`，無錯誤訊息）
- Phase 6 移除 Python fallback 前，必須先確認 Go bridge 在目標平台（Linux CI）上正確工作

---

## Issue 21：Guard step 刪除 classifier.exe 後 Test step 找不到 Go binary

**症狀**：Phase 6A-1 移除 Python fallback 後，CI Test step 中所有 `extract_code` 測試回傳 `None`（15 個失敗），但 FC2/PPV 和無效檔名測試通過。Issue 20 的 `go_bridge.py` 修正未能解決此問題。

**根本原因**：

```
Build step:  go build -o classifier.exe   → binary 存在
              ↓
Agent step:  agent 可用 classifier.exe    → extract_code 正確
              ↓
Guard step:  rm -f classifier classifier.exe  ← 刪除 binary！
              ↓
Test step:   pytest tests/
              GoBridge._find_exe() 找不到 binary
              is_available = False
              _extract_code_via_go() → None
              Python fallback 已被 Phase 6A-1 移除
              ↓
              all extract_code() → None（15 個測試失敗）
```

**為什麼 Guard 要刪除 binary？** 防止 `git ls-files --others --exclude-standard` 偵測到 `classifier`（Linux 無副檔名）而誤判為 out-of-scope 新建檔案。

**修正**：在 Test step 前重新 build binary

```yaml
- name: Verify migration tests after refactor
  run: |
    # Guard step 已刪除 classifier.exe，此處重新 build
    go build -o classifier.exe ./cmd/scanner
    go test ./pkg/... -v
    python -m pytest tests/ -v --tb=short
```

**教訓**：「Guard step 的清理行為影響後續步驟」是容易忽略的副作用。刪除 binary 是必要的（防誤判），但後續步驟需要知道 binary 已消失。在 Test step 加一行 `go build` 即可解決。

---

## Issue 22：Workflow 缺少 Python 環境設定

**症狀**：CI workflow 失敗，錯誤訊息為 `ModuleNotFoundError: No module named 'aiohttp'`（或 `orjson`、`httpx`、`bs4`），即使 Go 測試全部通過。

**根本原因**：`copilot-refactor-go.yml` 設定了 Go 和 Node.js 環境，但**沒有設定 Python 環境**，直接執行 `pytest` 時找不到相依套件。

**修復**：在 workflow 中明確加入以下步驟：

```yaml
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: '3.11'

- name: Install Python dependencies
  run: |
    sudo apt-get install -y python3-tk  # tkinter（apt 安裝，pip 不含）
    pip install -r requirements.txt

- name: Set PYTHONPATH
  run: echo "PYTHONPATH=${{ github.workspace }}/src" >> $GITHUB_ENV
```

**教訓**：混合語言 workflow（Python + Go）必須明確設定**每一種**語言的環境。Go 和 Node.js 的 setup action 不會自動帶上 Python；tkinter 需要透過 `apt-get` 安裝，無法用 `pip` 取得。

---

## 附錄：GitHub Actions 觸發類型差異

| 觸發類型 | 支援 `branches` 過濾 | 執行分支 |
|----------|---------------------|---------|
| `push` | ✅ | 被 push 的分支 |
| `pull_request` | ✅ | PR 的 head 分支 |
| `schedule` | ❌ | 永遠是 default branch（main） |
| `workflow_dispatch` | ❌ | 觸發時選擇的分支 |
