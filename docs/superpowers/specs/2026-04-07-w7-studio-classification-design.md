# W7 片商分類移動功能設計規格

**日期**：2026-04-07  
**狀態**：已核准，待實作  
**分支**：wiki/wails-update

---

## 問題陳述

目前 Wails 的「移動」按鈕（T5）將番號整理到 `outputDir\女優名\番號.ext`，缺少片商層次。使用者需要在女優資料夾的上層加入片商資料夾，以便管理大量女優時快速找到特定片商的女優。

Python 版本有此功能（`analyze_actress_primary_studio`），Wails 版本尚未移植。

---

## 概念模型

**番號永遠跟著女優，片商只是組織女優資料夾的輔助層次。**

```
outputDir\
  S1\
    花蓮夏目\
      STARS-001.mp4
      STARS-002.mp4
  MOODYZ\
    某女優\
      MIAB-001.mp4
  單體企劃女優\
    跨片商女優\
      GANA-001.mp4
  未分類\
    NO-ACTRESS-001.mp4
```

---

## 片商判定邏輯

### 輸入資料
- 番號 → DB 查詢 → 取 `actresses[0]`（第一位女優）
- DB 中該女優所有作品的 `studio` 欄位
- `major_studios.json`（13 個大片商：S1、MOODYZ、PREMIUM、FALENO、KAWAII 等）

### 判定步驟

```
step 1: 從 DB 查番號，取 actresses[0]
         → 若無女優 → 目標資料夾 = "未分類"，結束

step 2: 掃描 DB 所有 videos，統計 actress 出現的 studio 分布
         → 按 studio 計 total_count

step 3: 取 total_count 最多的 max_studio
         → 若無任何 studio 記錄 → 目標資料夾 = "單體企劃女優"

step 4: 判斷 max_studio 是否在 major_studios 集合中
         → 是 → 目標資料夾 = max_studio
         → 否 → 目標資料夾 = "單體企劃女優"
```

### 最終路徑規則

| 情況 | 目標路徑 |
|------|---------|
| 有大片商 | `outputDir\{片商}\{女優名}\番號.ext` |
| 非大片商或跨多片商 | `outputDir\單體企劃女優\{女優名}\番號.ext` |
| DB 無女優資訊 | `outputDir\未分類\番號.ext` |

### 移籍自動處理

以 DB 中作品量最多的片商為準，無需特別處理移籍情況。每次按「片商分類」按鈕時重新計算，DB 資料更新後自然反映最新分類。

---

## 實作規格

### 層 1：Go DB 統計函式

**檔案**：`pkg/database/jsondb.go`

```go
// GetActressPrimaryStudio 統計 DB 中女優的主要片商
// 返回作品最多的片商名稱；若無片商記錄則返回空字串
func (db *JSONDatabase) GetActressPrimaryStudio(actressName string) string {
    studioCounts := map[string]int{}
    for _, video := range db.data.Videos {
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

**測試**：在 `pkg/database/jsondb_test.go` 新增：
- 單一片商（exclusive）→ 正確返回
- 多片商，其中一個最多 → 返回最多的
- 無 studio 欄位 → 返回 ""
- 空女優名 → 返回 ""

### 層 2：Wails Backend Binding

**檔案**：`wails-app/backend/app.go`

#### App struct 新增欄位
```go
majorStudios map[string]bool  // 從 major_studios.json 載入
```

#### Startup() 初始化
```go
a.majorStudios = a.loadMajorStudios()
```

#### 新增 loadMajorStudios()
```go
func (a *App) loadMajorStudios() map[string]bool {
    // 以 resolveConfigPath() 同邏輯找到 major_studios.json
    // 解析 JSON 字串陣列，返回 map[string]bool
}
```

#### 新增 Wails binding（查詢式，非移動式）
```go
// GetActressPrimaryStudios 批次查詢多位女優的主片商
// 返回 map[女優名]→片商資料夾（已套用 major_studios 判定）
//   大片商女優 → 片商名
//   非大片商   → "單體企劃女優"
//   無資料     → "" （由前端決定是否移動）
func (a *App) GetActressPrimaryStudios(actressNames []string) map[string]string {
    db, err := a.ensureDB()
    if err != nil { return map[string]string{} }

    result := map[string]string{}
    seen := map[string]bool{}
    for _, name := range actressNames {
        if seen[name] { continue }
        seen[name] = true
        studio := db.GetActressPrimaryStudio(name)
        if studio == "" || !a.majorStudios[studio] {
            if studio == "" {
                result[name] = ""
            } else {
                result[name] = "單體企劃女優"
            }
        } else {
            result[name] = studio
        }
    }
    return result
}
```

### 層 3：前端按鈕

**檔案**：`wails-app/frontend/src/App.tsx`

#### 新增 handleStudioMove
```tsx
const handleStudioMove = async () => {
  if (!outputDir.trim()) { setStatusMessage('請先設定輸出目錄', 'warning'); return; }
  const targets = scanResults.filter(r =>
    selectedCodes.size === 0 || selectedCodes.has(r.code)
  );
  if (targets.length === 0) { setStatusMessage('沒有可移動的項目', 'warning'); return; }
  setStatus('moving');

  // code → 女優名（從 searchResults）
  const codeToActress = new Map<string, string>(
    searchResults.map(sr => [sr.code, sr.actresses?.[0] ?? ''])
  );

  // 批次查詢女優→片商資料夾（呼叫後端，後端對照 DB + major_studios）
  const actressNames = [...new Set(targets.map(r => codeToActress.get(r.code) ?? '').filter(Boolean))];
  const studioMap = actressNames.length > 0
    ? await GetActressPrimaryStudios(actressNames)
    : {};

  const pathExt = (p: string) => {
    const lastDot = p.lastIndexOf('.');
    const lastSep = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'));
    return lastDot > lastSep ? p.slice(lastDot) : '';
  };

  const items = targets.map(r => {
    const actress = codeToActress.get(r.code) ?? '';
    let studioFolder = studioMap[actress] ?? '';
    // actress 無資料 → 未分類；studio 查不到 → 單體企劃女優（後端已判斷）
    if (!actress) studioFolder = '未分類';
    if (!studioFolder) studioFolder = '單體企劃女優';

    const dst = actress && studioFolder !== '未分類'
      ? `${outputDir}\\${studioFolder}\\${actress}\\${r.code}${pathExt(r.path)}`
      : `${outputDir}\\未分類\\${r.code}${pathExt(r.path)}`;
    return { source: r.path, destination: dst, on_conflict: conflictStrategy };
  });

  // 預覽
  const folderSet = new Set(items.map(i => i.destination.split('\\').slice(0, -1).join('\\')));
  pushEvent('info', `🏢 片商分類移動 ${targets.length} 個檔案 → ${folderSet.size} 個資料夾`);

  try {
    const result = await BatchMove(items, conflictStrategy);
    setLastBatchResult(result);
    const summary = `移動完成：${result.success_count} 成功 / ${result.failed_count} 失敗 / ${result.skipped_count} 略過`;
    setStatusMessage(summary, result.failed_count > 0 ? 'warning' : 'success');
    pushEvent(result.failed_count > 0 ? 'warning' : 'success', summary);

    // 清除已移動項目（同 T3）
    if (result.results) {
      const movedSources = new Set(result.results.filter(mv => mv.success).map(mv => mv.source));
      setScanResults(scanResults.filter(r => !movedSources.has(r.path)));
    }
  } catch (err) {
    setStatusMessage(`❌ 片商分類移動失敗：${err}`, 'error');
    pushEvent('error', `❌ 片商分類移動失敗：${err}`);
    setStatus('error');
    return;
  }
  setStatus('idle');
  resetProgress();
};
```

#### 新增按鈕（緊接現有「移動」按鈕之後）
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

---

## 測試計畫

### Go 單元測試
- `GetActressPrimaryStudio` 四個場景（同上）
- `StudioClassifyMove` 用 mock DB

### E2E 驗證
1. 掃描測試目錄 → 搜尋 → 片商分類按鈕
2. 確認 `outputDir\S1\某女優\` 結構建立
3. 確認跨片商女優落入 `單體企劃女優\`
4. 確認無女優番號落入 `未分類\`

---

## 排除範圍

- 不支援同時歸類到多個片商資料夾（一女優一資料夾）
- 不修改現有「移動（女優）」按鈕行為
- 不處理女優別名（別名統一問題另案）
- 不自動重新整理已移動到女優資料夾的檔案

---

## 相關文件

- `wiki/architecture/studio-classification.md`
- `src/models/json_database.py`（Python 參考實作）
- `major_studios.json`（大片商清單）
