# 女優分類未分類修復 Implementation Plan

> **For Hermes:** 先依 test-driven-development 補 failing tests，再直接實作；這次不強制使用 subagent-driven-development，避免把問題拆太久。完成後一定跑 requesting-code-review 流程。

**Goal:** 修正一般「女優分類 / 移動」按鈕過度依賴 `searchResults` 的問題，並在 DB fallback 失敗時中止移動且明確報錯，避免本來有女優資料的影片被錯誤移入 `未分類`。

**Architecture:** 保留已驗證的第一層修法：前端在 `handleMove()` 對缺席於 `searchResults` 的 code 呼叫 `DbGetVideo()` 補女優名。再補第二層可靠性：後端 `ensureDB()` 不再吞掉載入錯誤，前端若偵測 DB fallback 不可用，直接中止移動並顯示明確錯誤，而不是靜默落入 `未分類`。

**Tech Stack:** Wails backend (Go), React + TypeScript frontend, Node strip-types 測試、TypeScript `tsc`、Go `testing`

---

## 執行邊界

- 只修一般女優分類 `handleMove()` 與其依賴的 DB fallback
- 不處理 `handleStudioMove()`、`studios.json` 打包、Wails 完整 packaged E2E
- 只允許修改女優分類直接依賴到的 DB 入口：`ensureDB()`、`DbGetVideo()`、`DbListVideos()`
- 不把 `data.json` 當唯一真相；後端 DB API 讀的是 `data.json + journal` 合併後狀態
- 只要任一 fallback lookup error，就不得建立 move items、不得呼叫 `executeMoveWithConflictHandling()`、不得產生部分移動

## 工作樹注意事項

目前 repo 已有與本任務無關的既有變更：README / wiki / docs plan 等。實作與 commit 只限本任務相關檔案，避免把既有雜訊一起帶進去。

另外 `wails-app/frontend/package-lock.json` 目前有大量既有版本升級差異，不屬於這次 bugfix 範圍；除非本次實作真的需要新增/更新依賴，否則不要納入 commit。`package.json.md5` 若只是本地產物，也不要納入 commit。

## 檔案責任

- Create: `wails-app/frontend/src/lib/classification.ts`
  - 封裝 `searchResults + cachedVideos -> codeToActress` 的純函式邏輯
- Create: `wails-app/frontend/tests/classification.test.ts`
  - 驗證前端分類 helper 的回歸案例
- Modify: `wails-app/frontend/src/App.tsx`
  - `handleSourceSearch()` 去重補快取
  - `handleMove()` 在移動前補查 DB，並在 DB fallback 不可用時中止
- Modify: `wails-app/backend/app.go`
  - 讓 DB 初始化 / 載入失敗變成可觀測狀態
- Modify: `wails-app/backend/app_test.go`
  - 驗證 DB 載入失敗不再被靜默吞掉，且 `DbGetVideo()` 會回傳明確錯誤

---

### Task 1: 前端分類 helper 與第一層 fallback

**Files:**
- Create: `wails-app/frontend/src/lib/classification.ts`
- Create: `wails-app/frontend/tests/classification.test.ts`
- Modify: `wails-app/frontend/src/App.tsx`

- [ ] 寫前端純函式測試，覆蓋：
  - found source status 的 cached video 會補進 searchResults
  - searchResults 缺資料時，DB cached video 可補出 actress
  - not_found source status 不會被誤補
- [ ] 先跑 `node --experimental-strip-types tests/classification.test.ts`，確認在 helper 尚未完成前會 fail
- [ ] 建立 `classification.ts`，提供：
  - `isFoundSearchStatus`
  - `mergeSearchResultsWithCachedVideos`
  - `buildCodeToActressMap`
- [ ] 在 `App.tsx` 導入 helper，讓 `handleSourceSearch()` 與 `handleMove()` 共用邏輯
- [ ] 保留多女優選擇覆寫邏輯，不可被 helper 吃掉
- [ ] 跑 `./node_modules/.bin/tsc --noEmit` 與前端測試，確認 pass

### Task 2: 後端 DB 載入失敗可觀測性

**Files:**
- Modify: `wails-app/backend/app.go`
- Modify: `wails-app/backend/app_test.go`

- [ ] 先寫 Go failing tests：
  - `TestDbGetVideo_ReturnsEnsureDBLoadError`
  - `TestEnsureDB_ClearsInstanceWhenLoadFails`
- [ ] 先跑：
  - `cd wails-app && go test ./backend -run "TestDbGetVideo_ReturnsEnsureDBLoadError|TestEnsureDB_ClearsInstanceWhenLoadFails" -count=1 -v`
  確認現在會 fail
- [ ] 把 `ensureDB()` 改成 `error` 回傳，不再吞掉 `Load()` / `CompactIfNeeded()` 失敗
- [ ] 失敗時不可留下半初始化 `a.db`
- [ ] 只修改 `DbGetVideo()` 與 `DbListVideos()` 傳遞 `ensureDB()` 錯誤
- [ ] 不擴散修改 `GetActressPrimaryStudios()` / `GetStudiosByCodes()`，若發現需要同步改，先記錄 follow-up，不在本次擴大
- [ ] 跑 Go 測試：
  - `cd wails-app && go test ./backend -run "TestDbGetVideo_ReturnsEnsureDBLoadError|TestEnsureDB_ClearsInstanceWhenLoadFails|TestBatchSearchJAVDB_NotFoundPreservesExistingOverallSuccess" -count=1 -v`

### Task 3: 前端在 DB fallback 失敗時中止移動

**Files:**
- Modify: `wails-app/frontend/src/App.tsx`
- Optionally Modify: `wails-app/frontend/tests/classification.test.ts`

- [ ] `handleMove()` 的 fallback 查詢不可再吞錯；需收集 `{ code, error }`
- [ ] 只要有任一 fallback error：
  - 不建立 `items`
  - 不呼叫 `executeMoveWithConflictHandling()`
  - `setStatus('error')`
  - `resetProgress()`
  - 顯示明確錯誤訊息
- [ ] 錯誤訊息規格：
  - 使用者可見：`❌ 讀取資料庫失敗，已中止女優分類（N 筆）：CODE1、CODE2`
  - event log 再補一條 debug/detail，帶第一個或摘要錯誤原因
- [ ] 驗證只有「searchResults 無女優 + DbGetVideo 成功但仍無 actresses[0]」才允許落入 `未分類`
- [ ] 跑前端型別檢查與 strip-types 測試

### Task 4: 驗證與 pre-commit review

- [ ] 跑 backend tests：
  - `cd wails-app && go test ./backend -v`
- [ ] 跑 frontend checks：
  - `cd wails-app/frontend && ./node_modules/.bin/tsc --noEmit`
  - `node --experimental-strip-types tests/classification.test.ts`
- [ ] 做 smoke checklist：
  1. 掃描後直接按女優分類：若 DB 有 actress，不應進未分類
  2. AV-WIKI 搜尋後立刻分類：已快取 / 新搜尋結果都應正確分類
  3. 重開程式後直接分類：DB fallback 可補回女優名
  4. 壞掉的 `json_data_dir` 或壞 JSON：應中止移動並看到明確錯誤，不可靜默進未分類
  5. 驗證 backend API 決策依據包含 journal 狀態，不以 `data.json` 單檔內容做唯一判斷
- [ ] 依 requesting-code-review 跑 pre-commit 驗證與獨立 review
- [ ] commit 只納入本次相關檔案，不帶 README/wiki/docs 與大版 package-lock 雜訊

## 驗收條件

- `handleMove()` 在 `searchResults` 缺資料時，會用 `DbGetVideo()` 補 actress
- `DbGetVideo()` 若因 DB load/compact 失敗而不可用，前端會中止移動並顯示明確錯誤
- 不會出現部分成功移動
- 只有真的沒有 actress 資料時才會落入 `未分類`
- backend API 作為 fallback 時，可見的是 `data.json + journal` 合併後狀態，而不是單看 `data.json`
