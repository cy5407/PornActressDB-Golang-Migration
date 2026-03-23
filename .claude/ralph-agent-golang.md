# Agent Build Instructions - 女優分類系統 Golang 重構

## 🏗️ 專案設定

### 環境需求
- Go 1.24.5+ (必須)
- Python 3.8+ (必須)
- Git (必須)

### 目錄結構
```
專案根目錄/
├── src/              # Python 原始碼
├── pkg/              # Go 套件（重構後的模組）
├── cmd/scanner/      # Go CLI 主程式
├── tests/            # 測試檔案
├── config.ini        # 設定檔
└── classifier.exe    # 編譯後的 Go CLI (Windows)
```

---

## 🔧 Go 開發命令

### 建置 Go CLI
```bash
# 從專案根目錄執行
go build -o classifier.exe ./cmd/scanner

# 或使用標準 Go 工具鏈
cd cmd/scanner
go build -o ../../classifier.exe
```

### 執行 Go 測試
```bash
# 執行所有 Go 單元測試
go test ./pkg/... -v

# 測試特定套件
go test ./pkg/extractor -v
go test ./pkg/mover -v
go test ./pkg/studio -v

# 顯示測試覆蓋率
go test ./pkg/... -cover

# 產生覆蓋率報告
go test ./pkg/... -coverprofile=coverage.out
go tool cover -html=coverage.out
```

### Go 效能測試
```bash
# 執行基準測試
go test ./pkg/extractor -bench=. -benchmem

# 效能分析
go test ./pkg/database -cpuprofile=cpu.prof
go tool pprof cpu.prof
```

### Go 程式碼檢查
```bash
# 格式化程式碼
go fmt ./pkg/...
go fmt ./cmd/...

# Lint 檢查（需安裝 golangci-lint）
golangci-lint run ./pkg/...

# Vet 檢查
go vet ./pkg/...
```

---

## 🐍 Python 開發命令

### 安裝 Python 相依套件
```bash
pip install -r requirements.txt
```

### 執行 Python 測試
```bash
# 執行所有測試
pytest

# 執行特定測試檔案
pytest tests/test_go_integration.py

# 顯示詳細輸出
pytest -v

# 顯示測試覆蓋率
pytest --cov=src tests/
```

### 執行主程式
```bash
# 啟動 GUI
python run.py

# 或直接執行
python -m src.ui.main_gui
```

---

## 🔗 Python-Go 整合測試

### 驗證 Go CLI 可用性
```bash
# 檢查 classifier.exe 是否存在
classifier.exe --help

# 測試掃描功能
classifier.exe scan -dir "測試目錄" -workers 10

# 測試移動功能
classifier.exe move -src "source.mp4" -dst "dest/source.mp4"

# 測試操作歷史
classifier.exe history list
```

### 執行整合測試
```bash
# 測試 Python 呼叫 Go CLI
python -c "from src.services.go_bridge import GoBridge; print(GoBridge().is_available)"

# 執行完整整合測試
pytest tests/test_go_integration.py -v

# 測試 Scanner 整合
python tools/manual_tests/test_go_scanner.py

# 測試 Mover 整合
python tools/manual_tests/test_go_mover.py
```

---

## 📊 效能基準測試

### Go 基準測試
```bash
# 掃描效能
go test ./pkg/extractor -bench=BenchmarkExtractCode

# 移動效能
go test ./pkg/mover -bench=BenchmarkMoveFile

# 資料庫效能（待實作）
go test ./pkg/database -bench=BenchmarkUpdateVideo
```

### Python vs Go 對比測試
```bash
# 執行對比腳本
python tools/benchmark/compare_scanner.py
python tools/benchmark/compare_mover.py

# 預期輸出範例:
# Python 掃描 1000 檔案: 2.5s
# Go 掃描 1000 檔案: 0.15s
# 提升倍數: 16.7x ✅
```

---

## 🧪 測試策略

### 單元測試（Go）
**目標覆蓋率**: 80%+
- `pkg/extractor/extractor_test.go` - 14 個測試 ✅
- `pkg/mover/mover_test.go` - 11 個測試 ✅
- `pkg/studio/identifier_test.go` - 8 個測試 ✅
- `pkg/database/*_test.go` - 待實作

### 整合測試（Python）
**目標**: 確保 Python-Go 互通性
- `tests/test_go_integration.py` - Go Bridge 整合測試
- `tests/test_scanner_integration.py` - Scanner 整合測試
- `tests/test_mover_integration.py` - Mover 整合測試

### 回歸測試（Python）
**目標**: 確保現有功能不受影響
```bash
# 執行完整回歸測試套件
pytest tests/test_incremental_db.py
pytest tests/test_json_statistics.py
python tools/diagnostics/check_db_quality.py
```

### 效能測試
**目標**: 驗證重構後效能提升
- 掃描 1000+ 檔案: 目標 10x+ 提升
- 批次移動 100+ 檔案: 目標 10x+ 提升
- 資料庫更新: 目標 40x+ 提升

---

## 🚀 開發工作流程

### 1. 開始新的 Go 模組重構
```bash
# 1. 閱讀 Python 原始碼
less src/models/incremental_json_database.py

# 2. 建立 Go 套件目錄
mkdir -p pkg/database

# 3. 建立測試檔案
touch pkg/database/database_test.go

# 4. 撰寫測試案例（TDD）
# 編輯 pkg/database/database_test.go

# 5. 實作功能
touch pkg/database/database.go
# 編輯 pkg/database/database.go

# 6. 執行測試
go test ./pkg/database -v

# 7. 整合到 CLI
# 編輯 cmd/scanner/main.go
```

### 2. 整合 Python 橋接層
```bash
# 1. 更新 GoBridge
# 編輯 src/services/go_bridge.py

# 2. 撰寫整合測試
# 編輯 tests/test_go_integration.py

# 3. 執行測試
pytest tests/test_go_integration.py -v

# 4. 更新使用位置
# 編輯 src/services/classifier_core.py
```

### 3. 驗證和提交
```bash
# 1. 執行完整測試套件
go test ./pkg/... -v
pytest tests/ -v

# 2. 效能基準測試
python tools/benchmark/compare_*.py

# 3. 格式化程式碼
go fmt ./...
black src/ tests/

# 4. Git 提交
git add .
git commit -m "feat(database): 實作 Go 資料庫核心模組 (P0 Phase 1)"
```

---

## 🎯 Feature Development Quality Standards

### 🧪 Testing Requirements

**Minimum Coverage**:
- Go 套件: 80% 程式碼覆蓋率
- Python 整合: 85% 覆蓋率

**Test Pass Rate**: 100% - 所有測試必須通過

**Required Test Types**:
1. **Go 單元測試** (`*_test.go`)
   - 核心邏輯測試
   - 邊界條件測試
   - 錯誤處理測試
   - 並發安全測試

2. **Python 整合測試** (`test_*_integration.py`)
   - GoBridge 呼叫測試
   - JSON 格式相容性測試
   - Fallback 機制測試

3. **回歸測試**
   - 現有 Python 功能不受影響
   - GUI 正常啟動和運作

4. **效能測試**
   - 基準測試顯示明顯提升（3x-10x）
   - 無記憶體洩漏

### 📋 Git Workflow Requirements

**Conventional Commits 格式**:
```bash
# 新功能
git commit -m "feat(database): 實作增量資料庫核心功能"

# 錯誤修復
git commit -m "fix(bridge): 修正 JSON 解析錯誤"

# 測試
git commit -m "test(mover): 新增批次移動測試案例"

# 文件
git commit -m "docs(migration): 更新 Go 重構進度"

# 重構
git commit -m "refactor(extractor): 優化番號提取效能"
```

**Commit 前檢查清單**:
- [ ] 所有 Go 測試通過 (`go test ./pkg/...`)
- [ ] 所有 Python 測試通過 (`pytest`)
- [ ] 程式碼已格式化 (`go fmt`, `black`)
- [ ] 無 lint 警告
- [ ] 更新相關文件

### 📝 Documentation Requirements

**必須更新的文件**:
1. **GO_MIGRATION_TODO.md** - 標記任務完成進度
2. **CLAUDE.md** - 更新架構圖和模組說明
3. **ralph-fix-plan.md** - 更新 Ralph 任務清單
4. **Python docstrings** - 標註已有 Go 加速版本
5. **Go package docs** - 新增套件級說明

**文件範例**:
```python
# Python 模組標註 Go 加速
def scan_directory(path: str) -> List[str]:
    """掃描目錄並返回檔案列表

    注意: 此函式已有 Go 加速版本 (pkg/extractor)
    透過 GoBridge 呼叫可獲得 16x 效能提升
    """
```

```go
// Go 套件文件
// Package database 提供高效能 JSON 資料庫操作
//
// 這個套件實作了增量更新機制，相較於 Python 版本
// (src/models/incremental_json_database.py) 提供 40x 效能提升。
//
// 使用範例:
//   db, _ := database.New("data/json_db")
//   db.UpdateVideo("SONE-123", data)
package database
```

---

## 🔗 Feature Completion Checklist

在標記任何 Go 重構任務為完成前，驗證：

### Go 模組完成清單
- [ ] 所有 Go 單元測試通過（目標 80%+ 覆蓋率）
- [ ] 基準測試顯示效能提升（3x-10x）
- [ ] 程式碼格式化 (`go fmt`)
- [ ] 通過 `go vet` 檢查
- [ ] JSON 輸出格式與 Python 版本完全相容
- [ ] 錯誤處理完整（不使用 panic）
- [ ] 並發安全（如適用）
- [ ] CLI 命令整合完成

### Python 整合完成清單
- [ ] `go_bridge.py` 新增對應方法
- [ ] 實作 fallback 機制
- [ ] Python 整合測試通過
- [ ] 現有功能回歸測試通過
- [ ] `config.ini` 更新（如需要）
- [ ] 使用位置已替換（記錄在 GO_MIGRATION_TODO.md）

### 文件和提交清單
- [ ] `GO_MIGRATION_TODO.md` 標記完成 [x]
- [ ] `CLAUDE.md` 更新架構說明
- [ ] `ralph-fix-plan.md` 移至 Completed 區塊
- [ ] Go 套件文件完整
- [ ] Python docstrings 更新
- [ ] Git commit 使用 conventional commits 格式
- [ ] Commit message 說明 WHAT 和 WHY

### 效能驗證清單
- [ ] 執行效能基準測試
- [ ] 記錄 Python 基準時間
- [ ] 記錄 Go 實測時間
- [ ] 計算提升倍數
- [ ] 更新效能統計表

---

## 🚨 Critical Constraints

### 絕對不可違反的規則
1. ❌ **不破壞現有功能**: 每次 commit 後 `python run.py` 必須正常啟動
2. ❌ **不移除 Python fallback**: Go 不可用時必須能降級到 Python
3. ❌ **不修改 JSON 格式**: Go 輸出必須與 Python 完全相容
4. ❌ **不重構 GUI**: `src/ui/` 永遠保留 Python (tkinter)
5. ❌ **不重構爬蟲**: `src/scrapers/sources/` 保留 Python (BeautifulSoup)
6. ❌ **不提交失敗的測試**: 所有測試必須通過才能 commit
7. ❌ **效能必須提升**: 重構後效能至少提升 3x，否則回退

### 安全檢查清單
```bash
# 在每次 commit 前執行
./scripts/pre-commit-check.sh  # 或手動執行以下命令:

# 1. Go 測試
go test ./pkg/... -v

# 2. Python 測試
pytest tests/ -v

# 3. 啟動測試
python run.py --test-mode  # 驗證 GUI 能啟動

# 4. 格式檢查
go fmt ./...
black --check src/ tests/

# 5. 效能回歸檢查（如修改效能關鍵路徑）
python tools/benchmark/compare_all.py
```

---

## 📚 Key Learnings

### Go 開發最佳實踐
- **錯誤處理**: 永遠明確返回錯誤，使用 `fmt.Errorf("...: %w", err)` 包裝
- **JSON 標籤**: 使用 `json:"field_name"` 確保與 Python 相容
- **並發安全**: 使用 `sync.Mutex` 或 channel 保護共享資源
- **測試命名**: `TestFunctionName_Scenario` 格式
- **基準測試**: 使用 `testing.B` 和 `-bench` 旗標

### Python-Go 整合技巧
- **subprocess 呼叫**: 永遠使用 `subprocess.run()` 並檢查返回碼
- **JSON 解析**: 使用 `json.loads()` 解析 stdout 輸出
- **錯誤處理**: stderr 輸出視為錯誤訊息
- **路徑處理**: Windows 路徑需要轉義或使用 raw string
- **自動偵測**: 優先使用 `shutil.which()` 尋找執行檔

### 效能優化經驗
- **檔案掃描**: 使用 `filepath.WalkDir` + goroutines 並發處理
- **批次操作**: worker pool 模式，預設 10-20 個 workers
- **JSON 序列化**: 使用 `json.NewEncoder(os.Stdout)` 串流輸出
- **記憶體管理**: 避免一次載入大檔案，使用串流處理

### 常見陷阱
- ⚠️ Windows 路徑分隔符混用（`\` vs `/`）
- ⚠️ JSON 欄位大小寫不一致
- ⚠️ Goroutine 洩漏（忘記關閉 channel）
- ⚠️ 競爭條件（多個 goroutine 存取共享資源）
- ⚠️ Python subprocess 編碼問題（需要 UTF-8）

---

## 🎓 進階主題

### Go 效能分析
```bash
# CPU profiling
go test ./pkg/database -cpuprofile=cpu.prof
go tool pprof -http=:8080 cpu.prof

# Memory profiling
go test ./pkg/database -memprofile=mem.prof
go tool pprof -http=:8080 mem.prof

# Race detection
go test ./pkg/... -race
```

### Go 模組依賴管理
```bash
# 新增依賴
go get github.com/some/package

# 整理依賴
go mod tidy

# 查看依賴樹
go mod graph

# 升級依賴
go get -u github.com/some/package
```

### 交叉編譯
```bash
# 編譯 Windows 版本（從 Linux/macOS）
GOOS=windows GOARCH=amd64 go build -o classifier.exe

# 編譯 Linux 版本
GOOS=linux GOARCH=amd64 go build -o classifier

# 編譯 macOS 版本
GOOS=darwin GOARCH=amd64 go build -o classifier
```

---

## 📞 Troubleshooting

### Go CLI 找不到
```bash
# 檢查是否編譯
ls classifier.exe

# 重新編譯
go build -o classifier.exe ./cmd/scanner

# 檢查 PATH
echo $PATH
```

### Python 無法呼叫 Go
```python
# 測試 GoBridge
from src.services.go_bridge import GoBridge
bridge = GoBridge()
print(f"Go available: {bridge.is_available}")
print(f"Go path: {bridge.exe_path}")
```

### 測試失敗
```bash
# 清理快取
go clean -testcache

# 重新執行
go test ./pkg/... -v

# 顯示詳細錯誤
go test ./pkg/extractor -v -run TestSpecificTest
```

### 效能未達標
```bash
# 執行 profiling
go test ./pkg/database -bench=. -cpuprofile=cpu.prof

# 分析瓶頸
go tool pprof cpu.prof
# 在 pprof 互動模式輸入: top, list FunctionName
```

---

## 🎯 Ralph Integration

### Ralph 自動化建議
當 Ralph 執行 Go 重構任務時，應該：

1. **分析階段**：
   - 閱讀 Python 原始碼
   - 執行現有測試確認行為
   - 記錄 JSON 格式和 API

2. **實作階段**：
   - TDD 方式撰寫測試
   - 實作 Go 核心邏輯
   - 確保測試通過

3. **整合階段**：
   - 更新 `go_bridge.py`
   - 實作 fallback
   - 撰寫整合測試

4. **驗證階段**：
   - 執行完整測試套件
   - 效能基準測試
   - 更新文件

5. **提交階段**：
   - Git commit（conventional commits）
   - 更新任務清單
   - 標記完成狀態

### Ralph 狀態報告範例
```
---RALPH_STATUS---
STATUS: IN_PROGRESS
TASKS_COMPLETED_THIS_LOOP: 2
FILES_MODIFIED: 5
TESTS_STATUS: PASSING
WORK_TYPE: IMPLEMENTATION
EXIT_SIGNAL: false
MIGRATION_PROGRESS: incremental_json_database.py -> Go Phase 2/4 (Implementation)
RECOMMENDATION: Continue with Go unit tests for IncrementalDB
---END_RALPH_STATUS---
```

---

**Remember**:
- Quality over speed - 確保重構後的程式碼品質優於原版本
- Test thoroughly - 整合測試比單元測試更重要
- Document everything - 設計決策和 API 變更都要記錄
- Keep Python working - 永遠保持 Python 路徑可用
