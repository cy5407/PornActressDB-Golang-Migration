# 片商分類架構（W7）

> 功能狀態：設計中（W7，2026-04-07）

## 概念

番號永遠跟著女優（女優是主分類），片商資料夾只是幫女優分組的輔助層次。

**目標路徑**：`outputDir\片商名\女優名\番號.ext`

## 片商判定邏輯

### 輸入
- 女優名稱（從 DB 中取得）
- DB 中該女優所有影片的 `studio` 欄位
- `major_studios.json`（13 個大片商清單）

### 三種情況

| 情況 | 條件 | 目標資料夾 |
|------|------|-----------|
| 大片商女優 | DB 作品最多的片商在大片商清單中 | `片商名\女優名\` |
| 單體企劃女優 | DB 作品最多的片商不在大片商清單中 | `單體企劃女優\女優名\` |
| 無女優資訊 | 番號在 DB 完全無女優記錄 | `未分類\` |

### 判定流程

```
1. 從 DB 查出番號對應的女優名（actresses[0]）
   → 無女優 → 放到「未分類\番號.ext」

2. 掃描 DB 所有影片，找出該女優出現的影片
   → 按 studio 欄位分組，統計每個片商的作品數

3. 取作品數最多的片商（max_studio）
   → 若多個片商作品數相同，取名稱字典序較小者

4. 判斷 max_studio 是否在 major_studios.json 中
   → 是 → 放到「max_studio\女優名\番號.ext」
   → 否 → 放到「單體企劃女優\女優名\番號.ext」
```

### 移籍處理

不需要特別處理。因為以 DB 中**作品量最多的片商**為準：

- 若 A 女優從 S1（30 部）跳槽到 Moodyz（5 部）→ 歸 S1
- 若之後 Moodyz 作品累積超過 S1 → 自動改歸 Moodyz

每次按「片商分類移動」按鈕都會即時重新計算，無需手動更新。

## 大片商清單

`major_studios.json`（13 個，位於專案根目錄）：S1、MOODYZ、PREMIUM、FALENO、KAWAII 等。

Go 後端在啟動時載入，存為 `App.majorStudios map[string]bool`。

## 實作架構

### Go DB 層

```go
// pkg/database/jsondb.go
func (db *JSONDatabase) GetActressPrimaryStudio(actressName string) (studio string, count int) {
    // 掃描所有 videos，統計 actressName 出現的片商
    // 返回作品最多的 studio 名稱與數量
}
```

### Wails Backend

```go
// wails-app/backend/app.go
func (a *App) StudioClassifyMove(codes []string, outputDir string, workers int) BatchResult {
    // 1. 對每個 code 查 DB → 取得 actress 和 file path
    // 2. 呼叫 db.GetActressPrimaryStudio(actress)
    // 3. 依 major_studios 判斷 → 決定 target folder
    // 4. 組合 move items → 呼叫 BatchMoveFiles
}
```

### 前端

```tsx
// App.tsx
const handleStudioMove = async () => {
  // 1. 計算目標資料夾分佈（預覽）
  // 2. pushEvent 顯示「N 個檔案 → 大片商 M 個、單體企劃 K 個」
  // 3. 呼叫 StudioClassifyMove(codes, outputDir, 0)
  // 4. 成功後清除 scanResults 已移動項目
};
```

## 與現有「移動」的差異

| 按鈕 | 路徑 | 片商邏輯 |
|------|------|---------|
| 移動（T5） | `outputDir\女優名\番號.ext` | 無 |
| 片商分類（W7） | `outputDir\片商\女優名\番號.ext` | 查 DB 統計 + major_studios |

## 相關檔案

- `major_studios.json` — 大片商清單
- `pkg/database/jsondb.go` — DB 查詢層
- `wails-app/backend/app.go` — Wails binding
- `wails-app/frontend/src/App.tsx` — 前端觸發
