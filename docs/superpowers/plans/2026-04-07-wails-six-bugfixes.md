# Wails 六大問題修復計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修復 Wails GUI（actress-classifier.exe）在 code review 後發現的 6 個設計/邏輯問題，包含 4 個 Bug Fix 和 2 個功能補全。

**Architecture:** Bug Fix 以最小侵入原則修改，每個 Task 可獨立 commit；Feature Task 5/6 依賴 Task 1-4 完成後的穩定快取，以及 taskStore 的 searchResults 資料。

**Tech Stack:** Go（backend/app.go）、React + TypeScript（frontend/src/App.tsx、taskStore.ts、SearchResultDialog.tsx）

---

## 問題清單

| # | 類型 | 問題 | 修改檔案 |
|---|------|------|---------|
| 1（Task 1） | Bug | getStatus 前端判定靠 actresses.length，標題有但無女優的片顯示失敗 | SearchResultDialog.tsx |
| 2（Task 2） | Bug | BatchSearch workers 寫死 5，忽略 config thread_count | app.go + App.tsx |
| 3（Task 3） | Bug | 移動成功後 scanResults 路徑不清空，再次移動會找不到舊路徑 | App.tsx |
| 4（Task 4） | Bug | dbOnce 無法重置，設定 DB 路徑後需重啟 | app.go |
| 5（Task 5） | Feature | 移動路徑只有 `outputDir/番號.ext`，沒有按女優分資料夾 | App.tsx |
| 6（Task 6） | Feature | 移動前沒有預覽「誰 → 哪裡」的確認步驟 | App.tsx + VideoList.tsx |

---

## 修改的檔案

| 檔案 | 責任 | 涉及 Task |
|------|------|----------|
| `wails-app/frontend/src/components/SearchResultDialog.tsx` | 修 getStatus | T1 |
| `wails-app/backend/app.go` | workers 讀 config；dbOnce → mutex | T2, T4 |
| `wails-app/frontend/src/App.tsx` | workers 傳 0；移動後清空；女優分資料夾 | T2, T3, T5, T6 |

---

## Task 1：修正前端 getStatus 判定邏輯（Bug 6）

**檔案：**
- Modify: `wails-app/frontend/src/components/SearchResultDialog.tsx:121-123`

**背景：**
`getStatus()` 要求 `actresses.length > 0` 才算成功。但無女優的合法作品（如 MOOK 系列）已有 title 資料，也會被標成失敗。

- [ ] **Step 1：修改 getStatus 函式**

開啟 `wails-app/frontend/src/components/SearchResultDialog.tsx`，找到 L121-123：

```typescript
// 修改前
function getStatus(r: SearchResult): 'success' | 'failed' {
  return !r.error && r.actresses?.length > 0 ? 'success' : 'failed';
}

// 修改後：有 title 或有女優 → 成功
function getStatus(r: SearchResult): 'success' | 'failed' {
  const hasContent = (r.actresses?.length ?? 0) > 0 || Boolean(r.title);
  return !r.error && hasContent ? 'success' : 'failed';
}
```

- [ ] **Step 2：驗證 build**

```powershell
cd wails-app
wails build -skipbindings 2>&1 | Select-Object -Last 5
```

Expected：`Build completed in ...s`，無 TypeScript error。

- [ ] **Step 3：Commit**

```bash
git add wails-app/frontend/src/components/SearchResultDialog.tsx
git commit -m "fix(wails): getStatus 改用 title 判斷，修正無女優作品顯示失敗"
```

---

## Task 2：BatchSearch workers 讀取 config.thread_count（Bug 4）

**檔案：**
- Modify: `wails-app/backend/app.go:425-428`（BatchSearch 起始處）
- Modify: `wails-app/frontend/src/App.tsx:86`（BatchSearch 呼叫處）

**背景：**
前端寫死 `BatchSearch(codes, 5)`，後端若 workers <= 0 用預設 20。應讓後端從 config.ini 的 `thread_count` 讀取，前端傳 0 表示「用 config」。

- [ ] **Step 1：修改 app.go BatchSearch 起始邏輯**

找到 `wails-app/backend/app.go` 中 `func (a *App) BatchSearch(codes []string, workers int)` 的開頭：

```go
// 修改前
func (a *App) BatchSearch(codes []string, workers int) []SearchResult {
	if workers <= 0 {
		workers = 20
	}

// 修改後：workers <= 0 時從 config 讀取 thread_count
func (a *App) BatchSearch(codes []string, workers int) []SearchResult {
	if workers <= 0 {
		prefs, _ := a.cfgSvc.Load()
		workers = prefs.ThreadCount
		if workers <= 0 {
			workers = 20 // 最終 fallback
		}
	}
```

- [ ] **Step 2：修改前端傳 0**

開啟 `wails-app/frontend/src/App.tsx`，找到 L86：

```typescript
// 修改前
const results = await BatchSearch(codes, 5);

// 修改後：傳 0 讓後端自行讀 config
const results = await BatchSearch(codes, 0);
```

- [ ] **Step 3：驗證 build**

```powershell
cd wails-app
wails build -skipbindings 2>&1 | Select-Object -Last 5
```

Expected：`Build completed`

- [ ] **Step 4：Commit**

```bash
git add wails-app/backend/app.go wails-app/frontend/src/App.tsx
git commit -m "fix(wails): BatchSearch workers 改從 config.thread_count 讀取"
```

---

## Task 3：移動成功後清空 scanResults（Bug 3）

**檔案：**
- Modify: `wails-app/frontend/src/App.tsx:140-154`（handleMove 成功後）

**背景：**
`handleMove()` 成功後沒有更新 `scanResults`，下次再按移動會嘗試從已移走的舊路徑搬檔案，導致 `stat: no such file or directory`。

- [ ] **Step 1：在 handleMove 成功後清空 scanResults**

找到 `handleMove()` 中 try 區塊裡成功路徑（result.failed_count 判斷後）：

```typescript
// 修改前（約 L141-154）
try {
  const result = await BatchMove(items, conflictStrategy);
  setLastBatchResult(result);
  const summary = `移動完成：${result.success_count} 成功 / ${result.failed_count} 失敗 / ${result.skipped_count} 略過`;
  setStatusMessage(summary, result.failed_count > 0 ? 'warning' : 'success');
  pushEvent(result.failed_count > 0 ? 'warning' : 'success', summary);
} catch (err) {

// 修改後：成功移動的項目要從 scanResults 移除
try {
  const result = await BatchMove(items, conflictStrategy);
  setLastBatchResult(result);
  const summary = `移動完成：${result.success_count} 成功 / ${result.failed_count} 失敗 / ${result.skipped_count} 略過`;
  setStatusMessage(summary, result.failed_count > 0 ? 'warning' : 'success');
  pushEvent(result.failed_count > 0 ? 'warning' : 'success', summary);
  // 移除已成功移動的項目，避免重複移動舊路徑
  if (result.success_count > 0) {
    const movedSources = new Set(
      (result.items ?? []).filter((i) => i.success).map((i) => i.source)
    );
    setScanResults(scanResults.filter((r) => !movedSources.has(r.path)));
  }
} catch (err) {
```

> **注意：** `result.items` 為 `mover.BatchResult` 的 items 欄位。確認 `wailsjs/go/models.ts` 中 `BatchResult.items` 存在且每個 item 有 `source` 和 `success` 欄位。如果 items 不存在則用 `setScanResults([])` 全清。

- [ ] **Step 2：確認 BatchResult 型別**

```powershell
Select-String "items" "wails-app\wailsjs\go\models.ts" | Select-Object -First 5
```

若 items 存在繼續用上述寫法；若不存在，改成：

```typescript
setScanResults([]);
```

- [ ] **Step 3：Validate build**

```powershell
cd wails-app
wails build -skipbindings 2>&1 | Select-Object -Last 5
```

- [ ] **Step 4：Commit**

```bash
git add wails-app/frontend/src/App.tsx
git commit -m "fix(wails): 移動成功後從 scanResults 移除已移動項目"
```

---

## Task 4：dbOnce 改為 mutex+nil，設定變更後重置 DB（Bug 5）

**檔案：**
- Modify: `wails-app/backend/app.go`（App struct + ensureDB + UpdatePreferences/ResetPreferences）

**背景：**
`sync.Once` 一旦執行後無法逆轉。用戶在 PreferencesDialog 修改 `json_data_dir` 後，`ensureDB()` 不會重新初始化，DB 仍然指向舊路徑。

- [ ] **Step 1：修改 App struct**

找到 app.go L27-38，將 `dbOnce sync.Once` 改為 `dbMu sync.Mutex`：

```go
// 修改前
type App struct {
	ctx        context.Context
	extractor  *extractor.CodeExtractor
	mover      *mover.Mover
	db         *database.JSONDatabase
	studio     *studio.StudioIdentifier
	cfgSvc     *services.ConfigService
	cfgPath    string
	dbOnce     sync.Once
	cancelScan context.CancelFunc
	cancelMu   sync.Mutex
}

// 修改後
type App struct {
	ctx        context.Context
	extractor  *extractor.CodeExtractor
	mover      *mover.Mover
	db         *database.JSONDatabase
	studio     *studio.StudioIdentifier
	cfgSvc     *services.ConfigService
	cfgPath    string
	dbMu       sync.Mutex // 替換 dbOnce，支援重置
	cancelScan context.CancelFunc
	cancelMu   sync.Mutex
}
```

- [ ] **Step 2：修改 Startup 初始化**

找到 `func (a *App) Startup(ctx context.Context)` L81-88：

```go
// 修改前
func (a *App) Startup(ctx context.Context) {
	a.ctx = ctx
	a.dbOnce.Do(func() {
		dataDir := resolveDataDir(a.cfgPath)
		a.db = database.NewJSONDatabase(dataDir)
		_ = a.db.Load(ctx)
	})
}

// 修改後
func (a *App) Startup(ctx context.Context) {
	a.ctx = ctx
	a.ensureDB()
}
```

- [ ] **Step 3：修改 ensureDB 改用 mutex**

找到 `func (a *App) ensureDB()` L553-558：

```go
// 修改前
func (a *App) ensureDB() {
	a.dbOnce.Do(func() {
		dataDir := resolveDataDir(a.cfgPath)
		a.db = database.NewJSONDatabase(dataDir)
		_ = a.db.Load(context.Background())
	})
}

// 修改後
func (a *App) ensureDB() {
	a.dbMu.Lock()
	defer a.dbMu.Unlock()
	if a.db != nil {
		return
	}
	dataDir := resolveDataDir(a.cfgPath)
	a.db = database.NewJSONDatabase(dataDir)
	_ = a.db.Load(context.Background())
}

// 新增 resetDB
func (a *App) resetDB() {
	a.dbMu.Lock()
	defer a.dbMu.Unlock()
	a.db = nil
}
```

- [ ] **Step 4：UpdatePreferences 後呼叫 resetDB**

找到 `func (a *App) UpdatePreferences(prefs Preferences) error`：

```go
// 修改前
func (a *App) UpdatePreferences(prefs Preferences) error {
	return services.NewConfigService(a.cfgPath).Save(prefs)
}

// 修改後
func (a *App) UpdatePreferences(prefs Preferences) error {
	err := services.NewConfigService(a.cfgPath).Save(prefs)
	if err == nil {
		a.resetDB() // 讓下次操作重新讀取新的 DB 路徑
	}
	return err
}
```

同理 `ResetPreferences`：

```go
// 修改後
func (a *App) ResetPreferences() error {
	err := services.NewConfigService(a.cfgPath).Reset()
	if err == nil {
		a.resetDB()
	}
	return err
}
```

- [ ] **Step 5：確認 Go 編譯**

```powershell
cd "C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration"
go build ./wails-app/backend/... 2>&1
```

Expected：無錯誤輸出。

- [ ] **Step 6：Wails build**

```powershell
cd wails-app
wails build -skipbindings 2>&1 | Select-Object -Last 5
```

- [ ] **Step 7：Commit**

```bash
git add wails-app/backend/app.go
git commit -m "fix(wails): dbOnce 改為 mutex+nil，UpdatePreferences 後自動重置 DB"
```

---

## Task 5：移動路徑改按女優分資料夾（Feature 1）

**檔案：**
- Modify: `wails-app/frontend/src/App.tsx`（handleMove）

**背景：**
目前目標路徑為 `outputDir\番號.mp4`（平鋪）。應改為 `outputDir\女優名\番號.mp4`。
女優名從 `searchResults`（taskStore）查找，code → actresses[0]。
若搜尋結果無女優或無搜尋記錄，fallback 到 `outputDir\未分類\番號.mp4`。
若多個女優，只取 `actresses[0]`（主要女優）。

- [ ] **Step 1：在 handleMove 中加入查找女優的映射**

找到 `App.tsx` 中 `handleMove()` 的 `const items = targets.map(...)` 區塊：

```typescript
// 修改前
const items = targets.map((r) => ({
  source: r.path,
  destination: `${outputDir}\\${r.code}${pathExt(r.path)}`,
  on_conflict: conflictStrategy,
}));

// 修改後：建立 code → actress 映射，按女優名分資料夾
const codeToActress = new Map<string, string>(
  searchResults
    .filter((sr) => (sr.actresses?.length ?? 0) > 0)
    .map((sr) => [sr.code, sr.actresses[0]])
);

const items = targets.map((r) => {
  const actress = codeToActress.get(r.code) ?? '未分類';
  // 過濾掉 Windows 檔名不合法的字元
  const safeActress = actress.replace(/[\\/:*?"<>|]/g, '_');
  return {
    source: r.path,
    destination: `${outputDir}\\${safeActress}\\${r.code}${pathExt(r.path)}`,
    on_conflict: conflictStrategy,
  };
});
```

> **注意：** `searchResults` 需從 `useTaskStore()` 解構（確認 `handleMove` 所在的 `ActionToolbar` 元件已從 taskStore 取得 `searchResults`）。

- [ ] **Step 2：確認 searchResults 已加入 useTaskStore 解構**

找到 `ActionToolbar` 開頭的 `useTaskStore()` 解構（約 L21-38），確認包含 `searchResults`：

```typescript
const {
  inputDir,
  outputDir,
  status,
  scanResults,
  searchResults,      // ← 確認已加入
  selectedCodes,
  conflictStrategy,
  scanWorkers,
  recursive,
  setScanResults,
  setStatus,
  setStatusMessage,
  pushEvent,
  resetProgress,
  clearSearchResults,
  setLastBatchResult,
  setShowSearchResults,
} = useTaskStore();
```

若沒有 `searchResults`，加入。

- [ ] **Step 3：Build 驗證**

```powershell
cd wails-app
wails build -skipbindings 2>&1 | Select-Object -Last 5
```

Expected：`Build completed`，無 TS 型別錯誤。

- [ ] **Step 4：手動測試**

啟動 `wails-app/build/bin/actress-classifier.exe`，掃描目錄 → 搜尋（確保至少有搜尋結果）→ 移動。
驗證：
1. 有女優的番號 → `outputDir\女優名\番號.mp4` 
2. 無搜尋結果的番號 → `outputDir\未分類\番號.mp4`

- [ ] **Step 5：Commit**

```bash
git add wails-app/frontend/src/App.tsx
git commit -m "feat(wails): 移動路徑改為 outputDir/女優名/番號.ext，無女優落到未分類"
```

---

## Task 6：移動前顯示路徑預覽（Feature 2）

**檔案：**
- Modify: `wails-app/frontend/src/App.tsx`（handleMove + 新增 confirm toast/dialog 步驟）

**背景：**
用戶按「移動」後直接執行，不清楚每個番號會移到哪個資料夾。加入一個簡單的 confirm toast（非 modal），顯示「將移動 N 筆到 M 個女優資料夾，繼續？」。

- [ ] **Step 1：在 handleMove 中加入計數確認訊息**

找到 `handleMove()` 中 `setStatus('moving')` 之前，加入統計：

```typescript
async function handleMove() {
  const targets = scanResults.filter(
    (r) => selectedCodes.size === 0 || selectedCodes.has(r.code)
  );
  if (targets.length === 0) {
    setStatusMessage('沒有可移動的項目', 'warning');
    return;
  }
  if (!outputDir.trim()) {
    setStatusMessage('請先設定輸出目錄', 'warning');
    return;
  }

  // 計算要移到幾個女優資料夾
  const codeToActress = new Map<string, string>(
    searchResults
      .filter((sr) => (sr.actresses?.length ?? 0) > 0)
      .map((sr) => [sr.code, sr.actresses[0]])
  );
  const folders = new Set(targets.map((r) => codeToActress.get(r.code) ?? '未分類'));
  const noSearchCount = targets.filter((r) => !codeToActress.has(r.code)).length;

  pushEvent(
    'info',
    `📦 即將移動 ${targets.length} 個檔案 → ${folders.size} 個資料夾${noSearchCount > 0 ? `（${noSearchCount} 個未搜尋 → 未分類）` : ''}`
  );

  setStatus('moving');
  resetProgress();
  // ... (以下不變)
```

> 這個修改不加 modal，只在日誌面板顯示預覽訊息。若未來需要 modal 確認，可建立新 component。

- [ ] **Step 2：去掉之前 handleMove 重複的 pushEvent 行**

找到原本的：
```typescript
pushEvent('info', `📦 開始移動 ${targets.length} 個檔案 → ${outputDir}`);
```
用 Step 1 的新版取代（已包含更詳細資訊），刪除舊行。

- [ ] **Step 3：Build 驗證**

```powershell
cd wails-app
wails build -skipbindings 2>&1 | Select-Object -Last 5
```

- [ ] **Step 4：Commit**

```bash
git add wails-app/frontend/src/App.tsx
git commit -m "feat(wails): 移動前顯示資料夾分配預覽（N 個檔案 → M 個資料夾）"
```

---

## 完成後

- [ ] 推送所有 commit

```bash
git push origin wiki/wails-update
```

- [ ] 更新 wiki/log.md 記錄此次修復
- [ ] 執行 `python wiki/gen_data.py` 重新產生 wiki-data.js

---

## 自我審查

**Spec coverage：**
- ✅ Bug 1（getStatus） → Task 1
- ✅ Bug 2（workers） → Task 2
- ✅ Bug 3（stale paths） → Task 3
- ✅ Bug 4（dbOnce） → Task 4
- ✅ Feature 1（女優分資料夾） → Task 5
- ✅ Feature 2（移動預覽） → Task 6

**Placeholder scan：** 無 TBD / TODO / 後補

**Type consistency：**
- `setScanResults` 一致使用 `backend.ScanResult[]`
- `searchResults` 型別為 `backend.SearchResult[]`，`actresses` 為 `string[]`
- `mover.BatchResult.items` 需在 Step 3 確認是否存在（有備案：全清）
