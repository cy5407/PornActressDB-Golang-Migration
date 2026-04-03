# 2026-04-03 JAVDB 403 修復報告

## 本輪完成項目

### Task 0：引入 curl_cffi 取代 httpx 繞過 Cloudflare
- 已在 [`C:\Users\cy5407\.codex\worktrees\f9b0\PornActressDB-Golang-Migration\requirements.txt`](C:/Users/cy5407/.codex/worktrees/f9b0/PornActressDB-Golang-Migration/requirements.txt) 新增 `curl_cffi>=0.7.0`
- 已更新 [`C:\Users\cy5407\.codex\worktrees\f9b0\PornActressDB-Golang-Migration\src\services\safe_javdb_searcher.py`](C:/Users/cy5407/.codex/worktrees/f9b0/PornActressDB-Golang-Migration/src/services/safe_javdb_searcher.py)：
  - 優先使用 `curl_cffi.requests.Session`
  - fallback 保留 `httpx.Client`
  - 新增 `_session_type`、`_impersonate`
  - 新增 `_warmup()` 首頁暖機流程

### Task 1：修復 403/429 重試等待時間邏輯
- `max_retry_wait_seconds` 已調整為 `300.0`
- 403 重試等待改為 `30 + random(15, 45)`
- 429 重試等待改為 `20 + random(10, 30)`
- 新增 `consecutive_errors`
- 成功回應時會重設連續錯誤計數

### Task 2：移除級聯搜尋中的 JAVDB 階段
- [`C:\Users\cy5407\.codex\worktrees\f9b0\PornActressDB-Golang-Migration\src\services\web_searcher.py`](C:/Users/cy5407/.codex/worktrees/f9b0/PornActressDB-Golang-Migration/src/services/web_searcher.py)
  - `batch_cascade_search()` 已改為 AV-WIKI 單層批次搜尋
  - `cascade_search_single()` 預設來源改為僅 `avwiki`
- [`C:\Users\cy5407\.codex\worktrees\f9b0\PornActressDB-Golang-Migration\src\services\classifier_core.py`](C:/Users/cy5407/.codex/worktrees/f9b0/PornActressDB-Golang-Migration/src/services/classifier_core.py)
  - `process_and_search_cascade()` 已改為 AV-WIKI 批次搜尋流程
- [`C:\Users\cy5407\.codex\worktrees\f9b0\PornActressDB-Golang-Migration\src\ui\main_gui.py`](C:/Users/cy5407/.codex/worktrees/f9b0/PornActressDB-Golang-Migration/src/ui/main_gui.py)
  - `_japanese_search_worker()` 不再依賴級聯勾選切換
  - 保留獨立 JAVDB 搜尋按鈕

### Task 3：增加自適應速率控制
- `safe_request()` 已加入 `adaptive_multiplier = 2 ** min(self.consecutive_errors, 5)`
- 連續錯誤達 5 次時，會冷卻 300 秒、重建 session，並重設錯誤計數

### Task 4：更新 GUI 文字與搜尋選項
- 主視窗標題已改為「智慧搜尋版」
- 副標題已改為「AV-WIKI 批次搜尋 + JAVDB 獨立搜尋」
- 已移除「啟用級聯搜尋」勾選框

## 剩餘任務
- `docs/Tasks.md` 中列出的 Task 0～4，本輪已全部落地。

## 驗證結果
- `python -m py_compile src/services/safe_javdb_searcher.py src/services/web_searcher.py src/services/classifier_core.py src/ui/main_gui.py tests/test_safe_javdb_searcher.py`
  - 通過
- `python -c "from services.safe_javdb_searcher import SafeJAVDBSearcher ..."`
  - 通過，確認 `session_type` 可建立、`max_retry_wait_seconds=300.0`、`consecutive_errors=0`
- `python -c "from services.web_searcher import WebSearcher ... inspect.signature(...)"`
  - 通過，確認 `batch_cascade_search()` 已移除 JAVDB 相關參數
- 手動驗證腳本
  - 通過 4 項檢查：403 wait cap、403 retry、adaptive cooldown、create_session close
- `pytest`
  - 未能完成；目前環境對 pytest 臨時目錄建立/清理會拋出 `PermissionError`

## 阻塞與限制
- 目前 sandbox 禁止對桌面主 repo 工作樹寫入，因此無法直接寫入：
  - `C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\docs\20260403-fix-report.md`
- 本報告已寫入 worktree 對應路徑：
- [`C:\Users\cy5407\.codex\worktrees\f9b0\PornActressDB-Golang-Migration\docs\20260403-fix-report.md`](C:/Users/cy5407/.codex/worktrees/f9b0/PornActressDB-Golang-Migration/docs/20260403-fix-report.md)
- 目前執行環境禁止實際對外連線，JAVDB 真實連通性與 Cloudflare 繞過效果無法在本輪直接驗證

## 下輪建議
- 下一輪開始前，先檢閱本報告
- 若要驗證真實 403 是否解除，需要在允許外網的環境實測 `SafeJAVDBSearcher`
