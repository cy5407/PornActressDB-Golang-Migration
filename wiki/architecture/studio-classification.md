# 片商分類架構（W7 / W8）

> 功能狀態：**已完成實作**（W7 初版：2026-04-08；W8 番號前綴直查：2026-04-11）

## 概念

番號永遠跟著女優（女優是主分類），片商資料夾只是幫女優分組的輔助層次。

**目標路徑**：`outputDir\片商名\女優名\番號.ext`

---

## 真實來源檔案（Source of Truth）

### `studios.json`（番號前綴 → 片商名）

位置：專案根目錄 `studios.json`（`dist/studios.json` 為同步副本）。

格式：`{ "片商名": ["前綴1", "前綴2", ...] }`

完整映射表：

| 片商 | 番號前綴 |
|------|---------|
| S1 | SSIS、SSNI、SNIS、SONE、ONEZ、OFJE、SNOS、SIVR |
| MOODYZ | MIRD、MIDD、MIDV、MIDE、MIAB、MIAE、MIAD、MIFD、MIBB、MIDA、MDVR、MIKR、MIMK、MIZD、MNGS |
| PREMIUM | IPX、IPZ、IPZZ、IDEA、IPN、IDEAPOCKET、PRED、IPBZ、IPVR |
| FALENO | FSDSS、FNS、FADSS、MGOLD |
| KAWAII | KAWD、CAWD、KWBD、KAVR |
| ATTACKERS | SHKD、ADN、ATID、RBD、SSPD、JBD、RBK、SAME、YUJ |
| E-BODY | EBWH、EBOD、EBVR、EYAN、MKCK、NTRH |
| FITCH | JUFD、JUNY、JUFE、DEAB、FCVR、NIMA |
| MADONNA | JUQ、JUL、JUX、JUC、JUKD、JUR、ACHJ、JUVR、ROE |
| PRESTIGE | ABW、ABP、ABS、BGN、CHN、ABF、FPRE、FIG、PASN、PPR |
| SOD | SDJS、SDMF、SDNM、SDDE、SDMU、SDAB、SDMS、SDMT、SDSH、SDSD、SDAM、START、STARS、STAR、SACE、SDMUA、HJMO、KUSE、MOGI、SDMM |
| V&R | VEC、VICD、VAGU、VSPDS |

> **注意**：`studios.json` 目前有 12 個片商（不含 OPPAI、WANZ）。這些是已知的大片商，若需擴充請直接編輯 `studios.json`，後端重啟後即生效。

### `major_studios.json`（大片商名單）

位置：專案根目錄 `major_studios.json`（`dist/major_studios.json` 為同步副本）。

格式：`["S1", "MOODYZ", "PREMIUM", ...]` 共 13 個。

完整清單：S1、MOODYZ、PREMIUM、FALENO、KAWAII、ATTACKERS、E-BODY、SOD、PRESTIGE、MADONNA、OPPAI、FITCH、WANZ。

> **注意**：`major_studios.json` 有 13 個（含 OPPAI、WANZ），但 `studios.json` 目前沒有這兩個片商的番號前綴對應。若之後新增，請同步更新 `studios.json`。

---

## 片商判定邏輯（雙層判斷）

### 第一層：番號前綴 → 片商名（優先，無需 DB）

```
番號 MIDA-583 → 前綴 "MIDA" → 查 studios.json → "MOODYZ"
番號 CAWD-942 → 前綴 "CAWD" → 查 studios.json → "KAWAII"
番號 START-538 → 前綴 "START" → 查 studios.json → "SOD"
番號 DASS-917 → 前綴 "DASS" → 查 studios.json → 未收錄 → 進第二層
```

### 第二層：女優→DB 統計 → 片商名（fallback，需 DB 有資料）

```
未命中的番號 → 取女優名 → 掃描 DB 所有影片
→ 統計該女優各片商作品數 → 取最多的片商
```

### 大/小片商分類（第三層判斷）

```
片商名 → 查 major_studios.json
  → 在清單中（如 "MOODYZ"）→ 大片商 → 資料夾名用大寫英文片商名
  → 不在清單中（如 "V&R"） → 單體企劃女優
  → 兩層都查不到  → 未分類
```

### 最終目標路徑

**移動單位：整個女優資料夾**（不是個別檔案）

```
來源：inputDir\田中花子\           ← 整個資料夾
目的：outputDir\MOODYZ\田中花子\  ← 移動到片商子目錄下
```

| 情況 | 條件 | 目標路徑 |
|------|------|---------|
| 大片商 | 前綴查到 + 在 major_studios | `outputDir\片商名\女優資料夾名\` |
| 單體企劃女優 | 前綴查到 + 不在 major_studios | `outputDir\單體企劃女優\女優資料夾名\` |
| 未分類 | 兩層都查不到 | `outputDir\未分類\女優資料夾名\` |

> **注意**：資料夾下的所有檔案（影片、字幕、封面等）全部一起移動，不只是 scanResults 中的 `.mp4`。

---

## 移籍處理

以番號前綴直查為優先：前綴對應片商是固定的（番號由發行片商決定），不受女優移籍影響。

若使用 DB 統計 fallback：以作品量最多的片商為準（同票取字典序小者，空片商與 "UNKNOWN" 忽略）。

---

## 實作架構

### Go 後端（app.go）

```go
// App struct 含兩個片商資料載入
type App struct {
    majorStudios  map[string]bool   // major_studios.json → 大片商 set
    codeStudioMap map[string]string // studios.json 反向映射 → prefix(uppercase) → 片商名
}

// 載入時機：NewApp() 時同步呼叫
app.majorStudios = app.loadMajorStudios()
app.codeStudioMap = loadCodeStudioMap(resolveStudiosPath())
```

```go
// GetStudiosByCodes(codes []string) → map[code → studio]
// 單次 IPC 批次查詢所有番號，無需 DB
func (a *App) GetStudiosByCodes(codes []string) map[string]string

// GetStudioByCode(code string) → studio or ""
// 單番號查詢（前綴 → studios.json → major_studios.json）
func (a *App) GetStudioByCode(code string) string

// GetActressPrimaryStudios(actressNames []string) → map[actress → studio]
// 女優→DB 統計（fallback 使用）
func (a *App) GetActressPrimaryStudios(actressNames []string) map[string]string
```

### Go 輔助函式

```go
// extractCodePrefix("MIDA-583") → "MIDA"
func extractCodePrefix(code string) string

// loadCodeStudioMap(path) → map[UPPERCASE_PREFIX → studioName]
func loadCodeStudioMap(path string) map[string]string
```

### 前端（App.tsx — handleStudioMove）

```
1. 以女優資料夾分組（parentDir(r.path)）
   → folderToCodes: Map<女優資料夾, [番號…]>

2. 每個資料夾取代表番號 → GetStudiosByCodes([repCodes])
   → 一次 IPC 批次查所有代表番號前綴

3. 對 codeStudioMap[repCode] == "" 的，補查 GetActressPrimaryStudios

4. 決定每個資料夾的 studio：
   優先 codeStudioMap[repCode]
   → actressStudioMap[actress]
   → "未分類"

5. 建立 dirItems: [{source: 女優資料夾, destination: outputDir\studio\actressName}]

6. 輸出統計日誌：🏢 N 個女優資料夾 → M 個片商；📊 MOODYZ(5)、KAWAII(3)...

7. BatchMoveDirs(dirItems, strategy)
   → 每個女優資料夾整體移動（含資料夾下所有檔案）
   → 成功後從 scanResults 移除該資料夾下的所有記錄
```

---

## 與現有「移動」的差異

| 按鈕 | 路徑 | 片商邏輯 |
|------|------|---------|
| 移動 | `outputDir\女優名\番號.ext` | 無 |
| 🏢 片商分類 | `outputDir\片商\女優資料夾\`（整個資料夾） | 番號前綴查 + DB fallback + major_studios 判定 |

---

## 相關檔案

| 檔案 | 用途 |
|------|------|
| `studios.json` | **真實來源**：番號前綴 → 片商名 |
| `major_studios.json` | **真實來源**：大片商名單 |
| `dist/studios.json` | 同步副本（PyInstaller 打包用） |
| `dist/major_studios.json` | 同步副本（PyInstaller 打包用） |
| `pkg/database/jsondb.go` | `GetActressPrimaryStudio` DB 查詢層 |
| `wails-app/backend/app.go` | `GetStudiosByCodes`、`GetActressPrimaryStudios`、`BatchMoveDirs` Wails binding |
| `wails-app/frontend/src/App.tsx` | `handleStudioMove` 雙層查詢 + 整資料夾移動流程 |

