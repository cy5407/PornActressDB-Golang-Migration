# Copilot Agent Instructions - 女優分類系統

## 🤖 Agent 自動化模式設定

### 自主執行準則
作為 AI Agent，你應該**主動循環執行**以下流程，直到任務完全達成：

1. **理解需求** → 分析使用者意圖與專案結構
2. **規劃步驟** → 列出具體執行計畫（包含測試驗證）
3. **實作代碼** → 修改/建立檔案
4. **執行驗證** → 主動執行測試與檢查
5. **自動修復** → 若失敗，分析錯誤並重新修改
6. **重複步驟 4-5** → 直到所有測試通過

### 終端機權限
你被授權在必要時**直接執行**以下指令，無需額外詢問：

#### Python 驗證
```bash
# 語法檢查
python -m py_compile src/**/*.py

# 單元測試
python -m pytest tests/ -v

# 特定模組測試
python -m pytest tests/test_incremental_db.py -v

# 啟動主程式（手動驗證）
.\actress-classifier.exe
```

#### Go 驗證
```bash
# 編譯檢查
go build ./...

# 執行測試
go test ./... -v

# 特定套件測試
go test ./pkg/extractor -v

# 建構 CLI
go build -o classifier.exe ./cmd/scanner

# 測試 CLI
./classifier.exe scan ./test_data
```

#### 程式碼品質
```bash
# Python Lint (若安裝)
pylint src/ --disable=C,R

# Go 格式化
go fmt ./...

# Go Lint
golangci-lint run
```

### 錯誤處理自動化
遇到以下錯誤時，**自動執行修復循環**：

1. **Import Error** → 檢查相依性，執行 `pip install -r requirements.txt`
2. **Syntax Error** → 分析堆疊追蹤，修正語法後重新測試
3. **Test Failure** → 讀取失敗訊息，修改邏輯，再次執行測試
4. **Build Error (Go)** → 修正編譯錯誤，執行 `go build` 確認
5. **Runtime Error** → 加入錯誤處理與日誌，重新測試

---

## 🌐 語言規範
- 所有回應一律使用繁體中文 (zh-TW)
- 預設回應語言為繁體中文，不使用簡體中文
- 除非使用者明確指定其他語言，否則所有說明、回覆、註解與文件內容皆以繁體中文撰寫
- 術語對照：create=建立, object=物件, code=程式碼, library=函式庫, package=套件, class=類別, function=函式

---

## 📦 專案資訊

### 技術棧
- **Python 3.11+** - 主程式邏輯與 GUI
- **Go 1.21+** - 效能關鍵模組（檔案掃描、移動）
- **Tkinter** - 桌面 GUI 介面
- **主進入點**：`actress-classifier.exe`（Wails 桌面 GUI）
- **Go CLI**：`cmd/scanner/main.go` → 編譯為 `classifier.exe`
- **版本**：v5.4.3

### 目錄架構
```
src/
├── models/          # 資料模型（IncrementalJSONDB）
├── services/        # 業務邏輯（ClassifierCore, WebSearcher, GoBridge）
├── scrapers/        # 爬蟲（AVWikiScraper, ChibafScraper, JAVDBScraper）
├── ui/              # GUI 介面
└── utils/           # 工具函式

pkg/                 # Go 模組
├── extractor/       # 番號提取器
├── mover/           # 檔案移動器
├── database/        # 資料庫操作
└── studio/          # 片商處理

cmd/
└── scanner/         # Go CLI 主程式

tests/               # Python 測試
```

### 關鍵檔案
- `src/services/go_bridge.py` - Python ↔ Go 橋接層
- `pkg/extractor/extractor.go` - 番號提取核心
- `pkg/mover/mover.go` - 檔案移動核心
- `GO_MIGRATION_TODO.md` - Go 遷移進度追蹤

---

## ⚙️ 開發規範

### Python 編碼標準
1. **執行緒安全**：長時間操作必須使用背景執行緒
2. **GUI 更新**：所有 UI 操作使用 `root.after()` 回主執行緒
3. **日誌格式**：使用 emoji 前綴
   - 🚀 開始操作
   - ✅ 成功完成
   - ❌ 失敗錯誤
   - ⚠️ 警告訊息
   - 📊 統計資料
4. **錯誤處理**：所有外部呼叫（網路、檔案）必須使用 try-except
5. **搜尋順序**：AV-WIKI → JAVDB（chiba-f 已移除）

### Go 編碼標準
1. **錯誤處理**：所有 `error` 必須檢查，使用 `fmt.Errorf` 包裝錯誤鏈
2. **測試覆蓋率**：新功能必須附帶測試（目標 >80%）
3. **並發安全**：共用資源使用 `sync.Mutex` 保護
4. **CLI 輸出**：使用 JSON 格式，便於 Python 解析
5. **效能優先**：使用 `sync.WaitGroup` 實現並發處理

### Git Commit 規範
```
feat: 新增功能
fix: 修復錯誤
refactor: 重構代碼
test: 新增測試
docs: 更新文件
perf: 效能優化
```

---

## 🔄 典型工作流程範例

### 範例 1：新增 Go 功能並整合至 Python

1. **實作 Go 模組**
   ```bash
   # 建立檔案：pkg/newfeature/feature.go
   # 撰寫測試：pkg/newfeature/feature_test.go
   go test ./pkg/newfeature -v  # 確保測試通過
   ```

2. **更新 CLI**
   ```bash
   # 修改：cmd/scanner/main.go，加入新指令
   go build -o classifier.exe ./cmd/scanner
   ./classifier.exe newfeature --help  # 驗證指令
   ```

3. **建立 Python 橋接**
   ```bash
   # 修改：src/services/go_bridge.py，加入新方法
   python -m pytest tests/test_go_bridge.py -v  # 測試橋接
   ```

4. **整合至 GUI**
   ```bash
   # 修改：wails-app/frontend/src/ 或 wails-app/backend/app.go
   .\actress-classifier.exe  # 手動測試 UI
   ```

### 範例 2：修復 Python 錯誤

1. **重現錯誤**
   ```bash
   python -m pytest tests/test_incremental_db.py::test_failing -v
   ```

2. **分析堆疊追蹤** → 定位問題程式碼

3. **修改邏輯** → 更新 `src/models/incremental_json_db.py`

4. **重新測試**
   ```bash
   python -m pytest tests/test_incremental_db.py -v
   ```

5. **確認無副作用**
   ```bash
   python -m pytest tests/ -v  # 執行完整測試套件
   ```

---

## 🚨 關鍵約束

### 絕對禁止
- ❌ 不得刪除測試檔案
- ❌ 不得提交未通過測試的程式碼
- ❌ 不得在主執行緒執行 I/O 阻塞操作（Python GUI）
- ❌ 不得直接操作 `data/json_db/data.json`（必須透過 IncrementalJSONDB）

### 必須執行
- ✅ 修改程式碼後立即執行相關測試
- ✅ 發現測試失敗時主動修復（不要只報告）
- ✅ 新增功能時同步更新文件（README.md / docs/）
- ✅ Go 與 Python 互操作時確保 JSON 結構一致

---

## 📚 快速參考

### Python 重要模組
- `src.models.incremental_json_db.IncrementalJSONDB` - 資料庫操作
- `src.services.classifier_core.ClassifierCore` - 分類邏輯
- `src.services.go_bridge.GoBridge` - Go CLI 呼叫
- `src.scrapers.javdb_scraper.JAVDBScraper` - 網站爬蟲

### Go 重要套件
- `pkg/extractor.ExtractCode()` - 提取番號
- `pkg/mover.Move()` - 移動檔案
- `pkg/mover.BatchMove()` - 批次移動
- `pkg/studio.Classify()` - 片商分類

### 測試指令速查
```bash
# Python 快速測試
python -m pytest tests/ -x --tb=short

# Go 快速測試
go test ./... -short

# 整合測試
python test_go_db_bridge.py
```

---

**Agent 使命宣言**：  
我將主動、持續、迭代地完成任務，每次修改後自動驗證，發現問題立即修復，絕不將半成品交付給使用者。
