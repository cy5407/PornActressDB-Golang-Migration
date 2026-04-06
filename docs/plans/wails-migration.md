# Wails 遷移計畫

> **目標**：將 Python Tkinter GUI 重構為 Wails（Go + React/TypeScript）桌面應用程式  
> **建立**：2026-04-07  
> **狀態**：規劃中

---

## 一、背景與目標

### 現在的架構

```
Python Tkinter GUI (~2,588 行)
      ↓
Python 業務邏輯 + 爬蟲協調
      ↓
go_api/ 橋接層 (go_bridge.py, go_runner.py, go_api/*.py)
      ↓
Go CLI (classifier.exe) → pkg/ 後端
```

### 目標架構

```
Wails GUI (React + TypeScript 前端)
      ↓（直接 binding，零橋接）
Go 後端 (Wails app + 現有 pkg/ 全部功能)
      ↓（subprocess）
Python 爬蟲服務 (scrapers/ + services/web_searcher.py)
```

### 遷移後的效益

| 項目 | 現在 | 遷移後 |
|------|------|--------|
| Python 橋接層 | go_api/ 1,339 行 + go_bridge.py 248 行 | **完全消除** |
| GUI 語言 | Python Tkinter | React + TypeScript |
| 介面質感 | 2000 年代風格 | 現代 Web UI |
| 打包產物 | PyInstaller .exe（~42MB） + classifier.exe | 單一 Wails .exe（~15-20MB） |
| 維護複雜度 | Python + Go 雙語言橋接 | 純 Go 後端 |

---

## 二、技術選型確認

| 層次 | 技術 | 理由 |
|------|------|------|
| **桌面框架** | Wails v2 | Go 原生，與現有 pkg/ 直接整合 |
| **前端框架** | React 18 + TypeScript | 生態最大、類型安全、Wails 官方模板支援 |
| **UI 元件庫** | shadcn/ui + Tailwind CSS | 輕量、美觀、無需授權 |
| **Python 爬蟲整合** | subprocess（Go → python scraper.py） | 簡單、用完即棄 |
| **狀態管理** | Zustand（輕量 store） | 比 Redux 輕，適合桌面 App |
| **打包** | Wails build（NSIS installer） | 官方支援，輸出單一 .exe |

---

## 三、Phase 規劃

### Phase W1：環境建置 & PoC（1-2 週）

**目標**：驗證 Wails + React 可以呼叫現有 Go pkg/

**任務清單**：
- [ ] 安裝 Wails v2 CLI（`go install github.com/wailsapp/wails/v2/cmd/wails@latest`）
- [ ] 安裝前端依賴（Node.js 18+、npm）
- [ ] 在 `wails-app/` 子目錄建立新 Wails 專案（React + TypeScript 模板）
- [ ] 建立 `wails-app/backend/app.go`，暴露第一個 binding：`ScanDirectory(dir string)`
- [ ] React 前端呼叫 `ScanDirectory` 並顯示結果
- [ ] 執行 `wails dev` 確認熱重載正常
- [ ] 執行 `wails build` 確認產生 .exe

**驗收標準**：
- `wails dev` 可在開發模式啟動
- 點擊 React 按鈕 → 呼叫 Go `ScanDirectory` → 結果顯示在畫面

**相關檔案**：
```
wails-app/
├── wails.json          ← Wails 設定
├── main.go             ← 進入點
├── backend/
│   └── app.go          ← Wails binding（Phase W1 只有 ScanDirectory）
└── frontend/
    ├── src/
    │   ├── App.tsx
    │   └── components/
    └── package.json
```

---

### Phase W2：Go Backend Bindings（2-3 週）

**目標**：將所有 `go_api/` 的功能遷移為 Wails bindings

**函式對照表**：

| 現有 go_api/ 函式 | Wails binding 方法名 | 所屬 pkg/ |
|------------------|---------------------|----------|
| `scan_directory(dir)` | `ScanDirectory(dir string, workers int) []ScanResult` | pkg/app/scan_service |
| `move_file(src, dst)` | `MoveFile(src, dst, strategy string) MoveResult` | pkg/app/move_service |
| `batch_move(items)` | `BatchMove(items []MoveItem, strategy string) BatchResult` | pkg/app/move_service |
| `rollback_last()` | `RollbackLast() RollbackResult` | pkg/app/history_service |
| `db_get_video(code)` | `DbGetVideo(code string) VideoRecord` | pkg/database |
| `db_update_video(code, data)` | `DbUpdateVideo(code string, data map) error` | pkg/database |
| `db_list_videos()` | `DbListVideos() []VideoRecord` | pkg/database |
| `identify_studio(code)` | `IdentifyStudio(code string) StudioResult` | pkg/studio |
| `list_operations()` | `ListOperations() []OperationLog` | pkg/app/history_service |

**任務清單**：
- [ ] 建立 `wails-app/backend/app.go`，實作所有上表方法
- [ ] 建立 Go struct 型別對應（VideoRecord、MoveResult 等）
- [ ] 建立 Python subprocess wrapper：`PythonSearch(code string) SearchResult`
  - 呼叫 `python src/scrapers/run_search.py --code <code>`
  - 解析 JSON stdout
- [ ] 前端生成 TypeScript bindings（`wails generate module`）
- [ ] 單元測試：`wails-app/backend/app_test.go`

**新增的 Python 爬蟲入口**：
```python
# src/scrapers/run_search.py（新建）
# 接受 --code 參數，輸出 JSON 到 stdout
import sys, json
from scrapers.unified_scraper import UnifiedScraper

code = sys.argv[sys.argv.index('--code') + 1]
scraper = UnifiedScraper()
result = scraper.search(code)
print(json.dumps(result))
```

---

### Phase W3：核心 UI 元件（3-4 週）

**目標**：重現 `src/ui/main_gui.py` 的核心功能

**元件清單**：

| React 元件 | 對應現有 Python UI | 功能 |
|-----------|------------------|------|
| `<MainLayout>` | main_gui.py 主視窗 | 側邊欄 + 內容區 |
| `<DirectoryPicker>` | main_gui.py 輸入目錄選擇 | 選擇掃描目錄 |
| `<VideoList>` | main_gui.py 影片列表 | 顯示掃描結果、分頁 |
| `<VideoCard>` | 列表中的單一項目 | 縮圖、番號、女優名稱 |
| `<SearchPanel>` | 搜尋控制面板 | 搜尋、批次操作 |
| `<ProgressBar>` | main_gui.py 進度條 | 掃描/搜尋進度 |
| `<StatusBar>` | 狀態列 | 操作狀態訊息 |

**Wails 事件整合**：
```go
// 後端推送進度到前端（取代 tkinter after()）
runtime.EventsEmit(ctx, "scan:progress", ScanProgress{Current: i, Total: total})
```

```typescript
// 前端訂閱事件
useEffect(() => {
  EventsOn("scan:progress", (progress) => setProgress(progress))
  return () => EventsOff("scan:progress")
}, [])
```

**任務清單**：
- [ ] 設定 Tailwind CSS + shadcn/ui
- [ ] 建立 `<MainLayout>` 骨架（側邊欄 + 主內容區）
- [ ] 實作 `<DirectoryPicker>`（呼叫 Wails 原生檔案對話框）
- [ ] 實作 `<VideoList>` + `<VideoCard>`
- [ ] 實作進度條（Wails Events → React state）
- [ ] 實作 `<SearchPanel>` 基本搜尋功能
- [ ] 實作 `<StatusBar>`

---

### Phase W4：進階對話框（2-3 週）

**目標**：重現 3 個對話框視窗

| React 元件 | 對應現有檔案 | 行數 |
|-----------|------------|------|
| `<OperationHistoryDialog>` | operation_history_dialog.py | 451 行 |
| `<SearchResultDialog>` | search_result_dialog.py | 500 行 |
| `<PreferencesDialog>` | preferences_dialog.py | 462 行 |

**任務清單**：
- [ ] `<OperationHistoryDialog>`：列出操作記錄、支援回滾
- [ ] `<SearchResultDialog>`：顯示搜尋結果、確認/取消
- [ ] `<PreferencesDialog>`：設定管理（讀/寫 config.ini）
- [ ] 統一 Modal 元件（shadcn/ui Dialog）

---

### Phase W5：爬蟲整合（2-3 週）

**目標**：讓 Go 後端透過 subprocess 呼叫 Python 爬蟲

**設計**：

```
React 點擊「搜尋」
      ↓
Wails binding: PythonSearch(code)
      ↓
Go subprocess: python src/scrapers/run_search.py --code STARS-001
      ↓
Python 爬蟲執行（AV-WIKI → JAVDB 級聯）
      ↓
stdout: {"code":"STARS-001","actress":"...","title":"..."}
      ↓
Go 解析 JSON → 傳回 React
```

**任務清單**：
- [ ] 建立 `src/scrapers/run_search.py`（爬蟲 CLI 入口）
- [ ] Go subprocess wrapper（含超時、錯誤處理）
- [ ] 進度事件：爬蟲搜尋中顯示 spinner
- [ ] 批次搜尋：goroutine pool 並行呼叫 subprocess
- [ ] Python 環境偵測（找到 python.exe 路徑）

---

### Phase W6：打包 & 清理（1-2 週）

**目標**：生成單一 .exe，移除舊 Python GUI

**任務清單**：
- [ ] `wails build` Windows 設定（圖示、版本資訊、NSIS installer）
- [ ] 將 Python scrapers 打包進 Wails exe（或安裝時附帶）
- [ ] 移除 `src/ui/`（~2,588 行）
- [ ] 移除 `src/services/go_bridge.py`、`go_runner.py`、`go_api/`（~1,587 行）
- [ ] 更新 `run.py`（改為啟動 Wails exe 或直接刪除）
- [ ] 更新文件（README.md、MIGRATION_STATUS.md）
- [ ] 完整 E2E 測試

---

## 四、工程量估算

| Phase | 預估時間 | 主要風險 |
|-------|---------|---------|
| W1 環境 & PoC | 1-2 週 | Wails 安裝問題、CGO 環境 |
| W2 Go Bindings | 2-3 週 | JSON 型別對齊 |
| W3 核心 UI | 3-4 週 | React 狀態管理複雜度 |
| W4 進階對話框 | 2-3 週 | 資料流設計 |
| W5 爬蟲整合 | 2-3 週 | subprocess 穩定性、Python 路徑 |
| W6 打包清理 | 1-2 週 | PyInstaller → Wails 打包差異 |
| **總計** | **11-17 週** | — |

---

## 五、可刪除的程式碼（遷移完成後）

| 檔案/目錄 | 行數 | 移除時機 |
|-----------|------|---------|
| `src/ui/` | ~2,588 | Phase W6 |
| `src/services/go_bridge.py` | 146 | Phase W6 |
| `src/services/go_runner.py` | 102 | Phase W6 |
| `src/services/go_api/` | ~1,339 | Phase W6 |
| `run.py`（GUI 部分） | 部分 | Phase W6 |
| `classifier.exe`（獨立 CLI） | — | 保留（仍可作命令列工具） |
| **合計可刪除** | **~4,175 行** | — |

---

## 六、相依性與前置條件

### 環境需求（Phase W1 前必須安裝）

```powershell
# Wails v2
go install github.com/wailsapp/wails/v2/cmd/wails@latest

# 驗證
wails doctor

# Node.js（前端建置）
# 下載 https://nodejs.org/en/download — LTS 版
node --version   # 需要 18+
npm --version
```

### Wails Windows 額外需求
- WebView2 Runtime（Windows 11 內建，Windows 10 需手動安裝）
- CGO 支援（已有 Go 環境則通常 OK）

---

## 七、與現有架構的共存策略

遷移期間，新舊並行：

```
wails-app/        ← 新 Wails 專案（Phase W1 開始建立）
src/              ← 現有 Python（Phase W6 前保持可用）
pkg/              ← 共用 Go 後端（兩邊都用）
classifier.exe    ← 現有 CLI（保留）
```

- `pkg/` 不需修改，Wails binding 直接 import
- 爬蟲 `src/scrapers/` 完全保留，只新增 `run_search.py` 入口
- 測試 `tests/` 繼續跑，直到 Phase W6 確認功能完整後才移除 Python GUI 測試

---

## 八、參考資源

- [Wails v2 文件](https://wails.io/docs/introduction)
- [Wails + React 官方模板](https://wails.io/docs/gettingstarted/installation)
- [shadcn/ui](https://ui.shadcn.com/)
- [Zustand 狀態管理](https://github.com/pmndrs/zustand)
- [Wails Bindings 說明](https://wails.io/docs/howdoesitwork#method-binding)
