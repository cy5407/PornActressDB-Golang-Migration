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

## 附錄：GitHub Actions 觸發類型差異

| 觸發類型 | 支援 `branches` 過濾 | 執行分支 |
|----------|---------------------|---------|
| `push` | ✅ | 被 push 的分支 |
| `pull_request` | ✅ | PR 的 head 分支 |
| `schedule` | ❌ | 永遠是 default branch（main） |
| `workflow_dispatch` | ❌ | 觸發時選擇的分支 |
