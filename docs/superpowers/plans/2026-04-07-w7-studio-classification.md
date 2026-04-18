# W7 片商分類移動功能實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Wails GUI 新增「🏢 片商分類」按鈕，依 DB 中女優的主要片商將番號整理到 `outputDir\{片商}\{女優}\番號.ext` 三層路徑。

**Architecture:** Go DB 層新增 `GetActressPrimaryStudio()` 統計函式 → Wails Backend 新增 `GetActressPrimaryStudios()` binding（批次查詢 + major_studios 判定）→ 前端新增 `handleStudioMove()` + 「🏢 片商分類」按鈕。

**Tech Stack:** Go 1.24.5、Wails v2、React 18 + TypeScript、`major_studios.json`（13 個大片商）

---

## 受影響的檔案

| 檔案 | 操作 |
|------|------|
| `pkg/database/jsondb.go` | 新增 `GetActressPrimaryStudio()` |
| `pkg/database/jsondb_test.go` | 新增 4 個測試案例 |
| `wails-app/backend/app.go` | 新增 `majorStudios` 欄位、`loadMajorStudios()`、`GetActressPrimaryStudios()` binding |
| `wails-app/frontend/wailsjs/go/backend/App.js` | 手動新增 `GetActressPrimaryStudios` export（Wails 自動生成檔案，需手動補） |
| `wails-app/frontend/wailsjs/go/backend/App.d.ts` | 手動新增 TypeScript 型別宣告 |
| `wails-app/frontend/src/App.tsx` | 新增 `handleStudioMove()` + 「🏢 片商分類」按鈕 + import |

---

## Task 1：Go DB 函式（TDD）

**Files:**
- Modify: `pkg/database/jsondb_test.go`
- Modify: `pkg/database/jsondb.go`

- [ ] **Step 1：在 jsondb_test.go 新增 4 個失敗測試**

在 `pkg/database/jsondb_test.go` 的最後加入：

```go
// ─── GetActressPrimaryStudio 測試 ────────────────────────────────────────────

func TestGetActressPrimaryStudio_SingleStudio(t *testing.T) {
	db, _ := setupTestDB(t)

	// 同一片商 3 部作品
	for i, code := range []string{"STARS-001", "STARS-002", "STARS-003"} {
		v := NewVideo(code)
		v.Actresses = []string{"花蓮夏目"}
		v.Studio = "S1"
		_ = i
		if err := db.UpdateVideo(code, v); err != nil {
			t.Fatalf("UpdateVideo failed: %v", err)
		}
	}

	got := db.GetActressPrimaryStudio("花蓮夏目")
	if got != "S1" {
		t.Errorf("expected S1, got %q", got)
	}
}

func TestGetActressPrimaryStudio_MostFrequentWins(t *testing.T) {
	db, _ := setupTestDB(t)

	// MOODYZ 2 部、S1 1 部 → 應返回 MOODYZ
	for code, studio := range map[string]string{
		"MIAB-001": "MOODYZ",
		"MIAB-002": "MOODYZ",
		"STARS-099": "S1",
	} {
		v := NewVideo(code)
		v.Actresses = []string{"某女優"}
		v.Studio = studio
		if err := db.UpdateVideo(code, v); err != nil {
			t.Fatalf("UpdateVideo failed: %v", err)
		}
	}

	got := db.GetActressPrimaryStudio("某女優")
	if got != "MOODYZ" {
		t.Errorf("expected MOODYZ, got %q", got)
	}
}

func TestGetActressPrimaryStudio_NoStudio(t *testing.T) {
	db, _ := setupTestDB(t)

	v := NewVideo("GANA-001")
	v.Actresses = []string{"素人女優"}
	v.Studio = "" // 無 studio 欄位
	if err := db.UpdateVideo("GANA-001", v); err != nil {
		t.Fatalf("UpdateVideo failed: %v", err)
	}

	got := db.GetActressPrimaryStudio("素人女優")
	if got != "" {
		t.Errorf("expected empty string, got %q", got)
	}
}

func TestGetActressPrimaryStudio_EmptyName(t *testing.T) {
	db, _ := setupTestDB(t)

	got := db.GetActressPrimaryStudio("")
	if got != "" {
		t.Errorf("expected empty string, got %q", got)
	}
}
```

- [ ] **Step 2：執行測試，確認失敗（函式尚未定義）**

```bash
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration
go test ./pkg/database/... -run TestGetActressPrimaryStudio -v
```

預期輸出：`undefined: db.GetActressPrimaryStudio` 之類的編譯錯誤。

- [ ] **Step 3：在 jsondb.go 實作 `GetActressPrimaryStudio`**

在 `pkg/database/jsondb.go` 末尾新增（位於最後一個 `}` 之前）：

```go
// GetActressPrimaryStudio 統計 DB 中女優出現最多的片商名稱。
// actressName 為空或無任何有效 studio 記錄時返回空字串。
// 同票數時取字典序較小的片商名。
func (db *JSONDatabase) GetActressPrimaryStudio(actressName string) string {
	if actressName == "" {
		return ""
	}
	db.mu.RLock()
	defer db.mu.RUnlock()

	studioCounts := map[string]int{}
	for _, video := range db.root.Videos {
		for _, a := range video.Actresses {
			if a == actressName {
				if video.Studio != "" && video.Studio != "UNKNOWN" {
					studioCounts[video.Studio]++
				}
			}
		}
	}
	if len(studioCounts) == 0 {
		return ""
	}
	maxStudio, maxCount := "", 0
	for s, c := range studioCounts {
		if c > maxCount || (c == maxCount && s < maxStudio) {
			maxStudio, maxCount = s, c
		}
	}
	return maxStudio
}
```

> **注意**：`db.data` 在此檔案中應寫 `db.root`（JSONDatabase 的主資料欄位名稱）。若 IDE 提示欄位名稱不對，請查閱同檔案的 `struct JSONDatabase` 定義確認。

- [ ] **Step 4：執行測試，確認全部通過**

```bash
go test ./pkg/database/... -run TestGetActressPrimaryStudio -v
```

預期輸出：
```
--- PASS: TestGetActressPrimaryStudio_SingleStudio
--- PASS: TestGetActressPrimaryStudio_MostFrequentWins
--- PASS: TestGetActressPrimaryStudio_NoStudio
--- PASS: TestGetActressPrimaryStudio_EmptyName
PASS
```

- [ ] **Step 5：確認既有測試不受影響**

```bash
go test ./pkg/database/... -v
```

預期：所有測試通過（包括既有的 TestUpdateVideo、TestGetVideo_NotFound 等）。

- [ ] **Step 6：Commit**

```bash
git add pkg/database/jsondb.go pkg/database/jsondb_test.go
git commit -m "feat(db): add GetActressPrimaryStudio for studio classification"
```

---

## Task 2：Wails Backend Binding

**Files:**
- Modify: `wails-app/backend/app.go`

- [ ] **Step 1：在 `App` struct 新增 `majorStudios` 欄位**

找到 `app.go` 的 `App` struct（約 L27-38）：

```go
type App struct {
	ctx        context.Context
	extractor  *extractor.CodeExtractor
	mover      *mover.Mover
	db         *database.JSONDatabase
	studio     *studio.StudioIdentifier
	cfgSvc     *services.ConfigService
	cfgPath    string
	dbMu       sync.Mutex
	cancelScan context.CancelFunc
	cancelMu   sync.Mutex
}
```

改為：

```go
type App struct {
	ctx          context.Context
	extractor    *extractor.CodeExtractor
	mover        *mover.Mover
	db           *database.JSONDatabase
	studio       *studio.StudioIdentifier
	cfgSvc       *services.ConfigService
	cfgPath      string
	dbMu         sync.Mutex
	cancelScan   context.CancelFunc
	cancelMu     sync.Mutex
	majorStudios map[string]bool // 從 major_studios.json 載入
}
```

- [ ] **Step 2：在 `NewApp()` 呼叫 `loadMajorStudios()`**

找到 `NewApp()` 函式（約 L41-58），在 `return &App{...}` 之前加入賦值，或在 return 的 struct literal 內加入：

```go
func NewApp() *App {
	cfgPath := resolveConfigPath()
	cfgSvc := services.NewConfigService(cfgPath)
	si, _ := studio.NewStudioIdentifier(resolveStudiosPath())
	logDir := resolveLogDir(cfgPath)

	app := &App{
		extractor: extractor.NewCodeExtractor(),
		mover:     mover.NewMover(logDir),
		studio:    si,
		cfgSvc:    cfgSvc,
		cfgPath:   cfgPath,
	}
	app.majorStudios = app.loadMajorStudios()
	return app
}
```

- [ ] **Step 3：新增 `loadMajorStudios()` 函式**

在 `app.go` 的 `resolveStudiosPath()` 函式之後新增：

```go
// resolveMajorStudiosPath 以與 resolveStudiosPath 相同邏輯尋找 major_studios.json。
func resolveMajorStudiosPath() string {
	exe, err := os.Executable()
	if err == nil {
		candidate := filepath.Join(filepath.Dir(exe), "major_studios.json")
		if _, err2 := os.Stat(candidate); err2 == nil {
			return candidate
		}
	}
	return "major_studios.json"
}

// loadMajorStudios 載入 major_studios.json，返回片商名稱 set。
// 若檔案不存在或解析失敗，返回空 map（不 fatal）。
func (a *App) loadMajorStudios() map[string]bool {
	path := resolveMajorStudiosPath()
	data, err := os.ReadFile(path)
	if err != nil {
		return map[string]bool{}
	}
	var names []string
	if err := json.Unmarshal(data, &names); err != nil {
		return map[string]bool{}
	}
	result := make(map[string]bool, len(names))
	for _, name := range names {
		result[name] = true
	}
	return result
}
```

- [ ] **Step 4：新增 `GetActressPrimaryStudios()` Wails binding**

在 `app.go` 末尾（Move 區塊之後）新增：

```go
// ============================================================================
// Studio Classification
// ============================================================================

// GetActressPrimaryStudios 批次查詢女優的主要片商資料夾名稱。
//
// 返回 map[女優名] → 片商資料夾：
//   - 大片商（major_studios.json 內）→ 片商名（如 "S1"）
//   - 非大片商或跨多片商（作品最多但不是大片商）→ "單體企劃女優"
//   - 無任何 studio 記錄 → ""（前端應歸入「未分類」）
func (a *App) GetActressPrimaryStudios(actressNames []string) map[string]string {
	db, err := a.ensureDB()
	if err != nil {
		return map[string]string{}
	}

	result := make(map[string]string, len(actressNames))
	seen := map[string]bool{}
	for _, name := range actressNames {
		if seen[name] {
			continue
		}
		seen[name] = true
		studio := db.GetActressPrimaryStudio(name)
		switch {
		case studio == "":
			result[name] = "" // 無資料，前端決定路徑
		case a.majorStudios[studio]:
			result[name] = studio // 大片商
		default:
			result[name] = "單體企劃女優" // 非大片商
		}
	}
	return result
}
```

- [ ] **Step 5：確認 app.go 可編譯**

```bash
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration
go build ./wails-app/...
```

預期：無錯誤輸出。若有錯誤，根據編譯器訊息修正欄位名稱或 import。

- [ ] **Step 6：Commit**

```bash
git add wails-app/backend/app.go
git commit -m "feat(backend): add GetActressPrimaryStudios binding for W7 studio classification"
```

---

## Task 3：更新 Wails 前端 Binding Stubs

> Wails 在 `wails dev` 或 `wails build` 時會自動重新生成 `wailsjs/` 下的 JS/TS stubs。  
> 在尚未 build 的情況下，手動補充 stubs 以便 TypeScript 通過型別檢查。

**Files:**
- Modify: `wails-app/frontend/wailsjs/go/backend/App.js`
- Modify: `wails-app/frontend/wailsjs/go/backend/App.d.ts`

- [ ] **Step 1：在 App.js 新增 export**

在 `wails-app/frontend/wailsjs/go/backend/App.js` 末尾（最後一個 `}` 之後）新增：

```js
export function GetActressPrimaryStudios(arg1) {
  return window['go']['backend']['App']['GetActressPrimaryStudios'](arg1);
}
```

- [ ] **Step 2：在 App.d.ts 新增型別宣告**

在 `wails-app/frontend/wailsjs/go/backend/App.d.ts` 末尾新增（在最後一個 `export function` 之後）：

```typescript
export function GetActressPrimaryStudios(arg1:Array<string>):Promise<Record<string,string>>;
```

- [ ] **Step 3：確認 TypeScript 可通過（稍後 Step 4 一起驗證）**

暫時跳過，下一個 Task 完成後執行 `npx tsc --noEmit`。

---

## Task 4：前端新增 `handleStudioMove` + 按鈕

**Files:**
- Modify: `wails-app/frontend/src/App.tsx`

- [ ] **Step 1：更新 import 加入 `GetActressPrimaryStudios`**

找到 App.tsx 的 import 行（約 L14）：

```typescript
import { ScanDirectory, BatchSearch, BatchMove, CancelOperation } from '../wailsjs/go/backend/App';
```

改為：

```typescript
import { ScanDirectory, BatchSearch, BatchMove, CancelOperation, GetActressPrimaryStudios } from '../wailsjs/go/backend/App';
```

- [ ] **Step 2：在 `ActionToolbar` 函式內新增 `handleStudioMove`**

找到 `handleMove` 函式結束的 `}` 之後（約 L179 `setStatus('idle'); resetProgress(); }` 的後一行），新增以下函式：

```typescript
  async function handleStudioMove() {
    if (!outputDir.trim()) {
      setStatusMessage('請先設定輸出目錄', 'warning');
      return;
    }
    const targets = scanResults.filter(
      (r) => selectedCodes.size === 0 || selectedCodes.has(r.code)
    );
    if (targets.length === 0) {
      setStatusMessage('沒有可移動的項目', 'warning');
      return;
    }
    setStatus('moving');

    // code → 第一位女優名（從 searchResults）
    const codeToActress = new Map<string, string>(
      searchResults.map((sr) => [sr.code, sr.actresses?.[0] ?? ''])
    );

    // 批次查詢女優主片商（去重）
    const actressNames = [
      ...new Set(
        targets.map((r) => codeToActress.get(r.code) ?? '').filter(Boolean)
      ),
    ];
    const studioMap: Record<string, string> =
      actressNames.length > 0
        ? await GetActressPrimaryStudios(actressNames)
        : {};

    const pathExt = (p: string) => {
      const lastDot = p.lastIndexOf('.');
      const lastSep = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'));
      return lastDot > lastSep ? p.slice(lastDot) : '';
    };

    const items = targets.map((r) => {
      const actress = codeToActress.get(r.code) ?? '';
      let studioFolder = actress ? (studioMap[actress] ?? '') : '';
      // 後端返回 "" 代表無 studio 資料 → 歸入未分類
      if (!actress || studioFolder === '') {
        studioFolder = '未分類';
      }

      const dst =
        studioFolder === '未分類'
          ? `${outputDir}\\未分類\\${r.code}${pathExt(r.path)}`
          : `${outputDir}\\${studioFolder}\\${actress}\\${r.code}${pathExt(r.path)}`;

      return { source: r.path, destination: dst, on_conflict: conflictStrategy };
    });

    const folderSet = new Set(
      items.map((i) => i.destination.split('\\').slice(0, -1).join('\\'))
    );
    pushEvent(
      'info',
      `🏢 片商分類移動 ${targets.length} 個檔案 → ${folderSet.size} 個資料夾`
    );

    try {
      const result = await BatchMove(items, conflictStrategy);
      setLastBatchResult(result);
      const summary = `移動完成：${result.success_count} 成功 / ${result.failed_count} 失敗 / ${result.skipped_count} 略過`;
      setStatusMessage(summary, result.failed_count > 0 ? 'warning' : 'success');
      pushEvent(result.failed_count > 0 ? 'warning' : 'success', summary);

      // 清除已移動項目（同 handleMove T3 邏輯）
      if (result.results) {
        const movedSources = new Set(
          result.results.filter((mv) => mv.success).map((mv) => mv.source)
        );
        setScanResults(scanResults.filter((r) => !movedSources.has(r.path)));
      }
    } catch (err) {
      const msg = `❌ 片商分類移動失敗：${err}`;
      setStatusMessage(msg, 'error');
      pushEvent('error', msg);
      setStatus('error');
      return;
    }
    setStatus('idle');
    resetProgress();
  }
```

- [ ] **Step 3：新增「🏢 片商分類」按鈕**

找到 `return (` 內的 `<div className="flex items-center gap-2 flex-wrap">` 區塊，在「移動」Button 之後、`{isRunning && ...}` 之前新增：

```tsx
      <Button
        onClick={handleStudioMove}
        disabled={isRunning || scanResults.length === 0}
        size="sm"
        variant="outline"
      >
        🏢 片商分類{selectedCodes.size > 0 ? ` (${selectedCodes.size})` : '全部'}
      </Button>
```

- [ ] **Step 4：TypeScript 型別檢查**

```bash
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\wails-app\frontend
npx tsc --noEmit
```

預期：無錯誤。若有 `GetActressPrimaryStudios` 相關錯誤，回到 Task 3 確認 stub 正確。

- [ ] **Step 5：Commit**

```bash
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration
git add wails-app/frontend/wailsjs/go/backend/App.js
git add wails-app/frontend/wailsjs/go/backend/App.d.ts
git add wails-app/frontend/src/App.tsx
git commit -m "feat(frontend): add studio classification move button (W7)"
```

---

## Task 5：完整建置驗證

**Files:** 無（只驗證）

- [ ] **Step 1：Go 全套測試**

```bash
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration
go test ./pkg/... -v 2>&1 | tail -30
```

預期：全部 PASS，尤其包含新的 `TestGetActressPrimaryStudio_*` 測試。

- [ ] **Step 2：wails build**

```bash
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\wails-app
wails build
```

預期：輸出 `Build complete!` 且無錯誤。  
若出現「undefined: GetActressPrimaryStudio」等錯誤，回到 Task 1 Step 3 確認函式已正確加入 `jsondb.go`。  
若出現 TypeScript 錯誤，回到 Task 3 確認 stub 宣告正確。

> **注意**：`wails build` 會重新生成 `wailsjs/` stubs，Task 3 手動加入的內容可能被覆蓋，這是正常的。Wails 會從 Go 的 binding 方法自動生成正確的 stub。

- [ ] **Step 3：啟動 wails dev 快速確認 UI**

```bash
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\wails-app
wails dev
```

確認：
- [ ] 「🏢 片商分類全部」按鈕出現在「移動全部」按鈕之後
- [ ] 按鈕在 `scanResults.length === 0` 時呈現 disabled 狀態

---

## Task 6：E2E 測試 + Wiki 更新 + 最終 Commit

**Files:**
- Modify: `wiki/log.md`
- Modify: `wiki/wiki-data.js`（執行 gen_data.py）

- [ ] **Step 1：E2E 功能測試**

在 `wails dev` 下手動驗證以下場景：

**場景 A：有大片商女優**
1. 掃描含 `STARS-001.mp4`（女優：花蓮夏目）的目錄
2. 搜尋（確認搜尋結果含 studio=S1）
3. 設定 outputDir
4. 點「🏢 片商分類全部」
5. 確認檔案移動到 `outputDir\S1\花蓮夏目\STARS-001.mp4`

**場景 B：非大片商女優**
1. 掃描含 GANA-XXX.mp4（GG 系素人）的目錄
2. 搜尋（studio = "Gachinco"，不在 major_studios）
3. 點「🏢 片商分類全部」
4. 確認移動到 `outputDir\單體企劃女優\女優名\GANA-XXX.mp4`

**場景 C：無女優資訊的番號**
1. 確認移動到 `outputDir\未分類\番號.mp4`（無女優名層次）

- [ ] **Step 2：更新 wiki/log.md**

在 `wiki/log.md` 最前面（`## 最新更新` 之後）新增一條記錄：

```markdown
### 2026-04-07 W7 片商分類移動功能完成

- `pkg/database/jsondb.go`：新增 `GetActressPrimaryStudio()` Go DB 函式
- `wails-app/backend/app.go`：新增 `GetActressPrimaryStudios()` Wails binding + `loadMajorStudios()`
- `wails-app/frontend/src/App.tsx`：新增 `handleStudioMove()` + 「🏢 片商分類」按鈕
- 路徑規則：大片商→`outputDir\{片商}\{女優}\番號.ext`；非大片商→`單體企劃女優\`；無女優→`未分類\`
```

- [ ] **Step 3：重新產生 wiki-data.js**

```bash
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration
python wiki/gen_data.py
```

預期：`✅ 已產生 wiki-data.js（N 個頁面）`

- [ ] **Step 4：最終 Commit + Push**

```bash
git add wiki/log.md wiki/wiki-data.js
git commit -m "docs(wiki): W7 片商分類功能完成記錄"

git push origin main
```

---

## 快速參考

### DB struct 欄位確認

`JSONDatabase` 的主資料欄位在 `jsondb.go` 中是 `db.root`（型別 `*DatabaseData`），而非 `db.data`。`DatabaseData.Videos` 是 `map[string]VideoData`。

### major_studios.json 路徑

| 環境 | 路徑 |
|------|------|
| 開發（wails dev） | 專案根目錄 `major_studios.json` |
| 打包後（wails build） | 與 EXE 同目錄的 `major_studios.json` |

`resolveMajorStudiosPath()` 先找 exe 同目錄，fallback 到 `"major_studios.json"`（cwd），與 `resolveStudiosPath()` 邏輯完全相同。

### 前端 studioMap 邏輯對照

| `studioMap[actress]` 值 | 目標資料夾 |
|------------------------|-----------|
| `"S1"`（大片商名）       | `outputDir\S1\actress\code.ext` |
| `"單體企劃女優"`         | `outputDir\單體企劃女優\actress\code.ext` |
| `""`（無 studio 記錄）   | `outputDir\未分類\code.ext` |
| actress 為空字串         | `outputDir\未分類\code.ext` |
