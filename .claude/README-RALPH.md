# Ralph 配置 - 女優分類系統 Golang 重構專案

> 🤖 自動化 Golang 重構工作流程

## 📁 配置檔案

| 檔案 | 說明 | 對應標準檔案 |
|------|------|-------------|
| `ralph-golang-migration.md` | Ralph 核心指令 | `PROMPT.md` |
| `ralph-fix-plan.md` | 任務優先級清單 | `@fix_plan.md` |
| `ralph-agent-golang.md` | 建置和測試指令 | `@AGENT.md` |
| `RALPH_USAGE_GUIDE.md` | 完整使用指南 | - |
| `README-RALPH.md` | 本檔案（快速開始） | - |

---

## 🚀 5 分鐘快速開始

### 步驟 1: 複製配置檔案到專案根目錄

```bash
# 進入專案根目錄
cd /c/Users/cy540/OneDrive/桌面/PornActressDB-Golang-Migration

# 複製 Ralph 配置檔案
cp .claude/ralph-golang-migration.md PROMPT.md
cp .claude/ralph-fix-plan.md @fix_plan.md
cp .claude/ralph-agent-golang.md @AGENT.md
```

### 步驟 2: 啟動 Ralph

```bash
# 使用監控模式啟動（推薦）
~/.local/bin/ralph --monitor

# 或基本模式
~/.local/bin/ralph
```

### 步驟 3: 觀察 Ralph 執行

Ralph 會自動：
1. 讀取 `@fix_plan.md` 中的任務清單
2. 選擇最高優先級的待辦任務
3. 執行重構工作（分析 → 設計 → 實作 → 測試 → 文件）
4. 報告狀態並進入下一循環

---

## 📋 當前任務優先級

### 🔴 P0 - High Priority (最優先)

1. **資料庫層重構** (`src/models/incremental_json_database.py` → `pkg/database/`)
   - 目標效能提升: **40x**
   - 預估複雜度: ⭐⭐⭐⭐⭐

2. **掃描器完整整合** (驗證 `src/utils/scanner.py` 整合狀態)
   - Go 部分已完成 ✅
   - 需補充整合測試

### 🟡 P1 - Medium Priority

1. **片商識別器整合** (`pkg/studio/` → Python 整合)
   - Go 模組已完成 ✅
   - 需整合到 `src/models/studio.py`

2. **快取管理器重構** (`src/scrapers/cache_manager.py` → `pkg/cache/`)
   - 目標效能提升: **5x**

### 🟢 P2 - Low Priority

- CLI 功能增強（進度條、彩色輸出）
- 效能監控和分析
- 文件和範例

---

## ✅ 已完成項目

- ✅ **MVP-1 到 MVP-5**: Python-Go 橋接層完整整合
- ✅ **Go 核心模組**: 番號提取器、檔案移動器、片商識別器
- ✅ **統一 CLI**: `classifier.exe` 支援多種命令

**效能提升統計**:
- 檔案掃描: **16.7x** 提升
- 批次移動: **10x** 提升
- 番號提取: **20x** 提升

---

## 🎯 Ralph 第一次執行會做什麼？

根據 `@fix_plan.md`，Ralph 會執行第一個 High Priority 任務：

**任務**: 分析 `src/models/incremental_json_database.py` 架構

**執行步驟**:
1. 閱讀 Python 原始碼
2. 理解 Journal 增量機制
3. 理解 Compact 合併邏輯
4. 記錄 JSON 格式定義
5. 撰寫分析報告到 `docs/design/database-analysis.md`
6. 更新 `@fix_plan.md` 標記完成

**預計時間**: 1-2 個 Ralph 循環（約 30-60 分鐘）

---

## 📊 監控 Ralph 進度

### 即時監控

```bash
# 使用 tmux 監控模式（推薦）
~/.local/bin/ralph --monitor

# 查看即時日誌
tail -f logs/ralph-*.log

# 查看狀態
~/.local/bin/ralph --status
```

### 檢查完成進度

```bash
# 查看任務清單
cat @fix_plan.md

# 統計完成數量
grep "\[x\]" @fix_plan.md | wc -l

# 查看 Git commit 歷史
git log --oneline --since="1 day ago"
```

---

## 🛠️ 常用命令

### Ralph 控制

```bash
# 基本執行
~/.local/bin/ralph

# 監控模式
~/.local/bin/ralph --monitor

# 限制 API 呼叫（30 次/小時）
~/.local/bin/ralph --calls 30

# 設定逾時（30 分鐘）
~/.local/bin/ralph --timeout 30

# 顯示詳細進度
~/.local/bin/ralph --verbose

# 查看狀態
~/.local/bin/ralph --status

# 重置會話
~/.local/bin/ralph --reset-session
```

### 驗證和測試

```bash
# 執行 Go 測試
go test ./pkg/... -v

# 執行 Python 測試
pytest tests/ -v

# 建置 Go CLI
go build -o classifier.exe cmd/scanner/main.go

# 驗證 Go CLI 可用
classifier.exe --help

# 測試 GoBridge
python -c "from src.services.go_bridge import GoBridge; print(GoBridge().is_available)"
```

---

## 🎓 客製化 Ralph

### 調整任務優先級

編輯 `@fix_plan.md`：

```markdown
## 🔴 High Priority

### 我想優先做這個
- [ ] 任務描述

### 原本的任務
- [ ] ...
```

### 修改 Ralph 行為

編輯 `PROMPT.md`：

- 調整測試比例（預設 20%）
- 修改退出條件
- 新增約束規則

### 新增自訂命令

編輯 `@AGENT.md`：

```markdown
## 🔧 自訂命令

### 我的常用命令
```bash
./my-script.sh
```
```

---

## 🚨 注意事項

### Ralph 會做什麼
- ✅ 閱讀 Python 程式碼並理解邏輯
- ✅ 撰寫 Go 程式碼實作功能
- ✅ 撰寫單元測試和整合測試
- ✅ 更新 Python 橋接層
- ✅ 執行效能基準測試
- ✅ 更新文件和任務清單
- ✅ Git commit（使用 Conventional Commits）

### Ralph 不會做什麼
- ❌ 破壞現有 Python 功能
- ❌ 移除 Python fallback 機制
- ❌ 修改 GUI 層（`src/ui/`）
- ❌ 修改爬蟲層（`src/scrapers/sources/`）
- ❌ 提交測試失敗的程式碼
- ❌ 產生效能未提升的重構

### 安全機制
- 🔒 永遠保留 Python fallback
- 🔒 所有測試必須通過才能 commit
- 🔒 效能必須提升 3x+ 否則回退
- 🔒 JSON 格式必須與 Python 相容

---

## 📖 完整文件

### 必讀文件
1. **RALPH_USAGE_GUIDE.md** - 完整使用指南
   - 詳細的執行流程
   - 常見問題解答
   - 最佳實踐
   - 進階技巧

2. **ralph-golang-migration.md (PROMPT.md)** - Ralph 核心指令
   - 專案背景和目標
   - 重構原則和規範
   - 狀態報告格式
   - 退出場景

3. **ralph-fix-plan.md (@fix_plan.md)** - 任務清單
   - 優先級劃分
   - 詳細子任務
   - 完成進度

4. **ralph-agent-golang.md (@AGENT.md)** - 建置指令
   - Go 建置和測試
   - Python 測試
   - 整合測試流程
   - 完成清單

### 專案文件
- `CLAUDE.md` - 專案架構和開發規範
- `GO_MIGRATION_TODO.md` - 原始重構任務清單
- `QUICK_START_GUIDE.md` - 專案快速開始指南

---

## 🎯 成功指標

你可以透過以下指標判斷 Ralph 是否成功：

### 每日檢查
```bash
# 1. 檢查任務完成數量
grep "\[x\]" @fix_plan.md | wc -l

# 2. 檢查 Git commit 數量
git log --oneline --since="1 day ago" | wc -l

# 3. 檢查測試狀態
go test ./pkg/... && pytest tests/
```

### 每週檢查
- ✅ P0 任務進度（目標: 每週完成 1-2 個子任務）
- ✅ 效能提升驗證（基準測試結果）
- ✅ 文件更新狀態（CLAUDE.md, GO_MIGRATION_TODO.md）
- ✅ 程式碼品質（測試覆蓋率 80%+）

---

## 🐛 遇到問題？

### 快速診斷

```bash
# 1. 檢查 Ralph 狀態
~/.local/bin/ralph --status

# 2. 查看最近的日誌
tail -100 logs/ralph-*.log

# 3. 檢查環境
go version          # 應為 1.24.5+
python --version    # 應為 3.8+
classifier.exe --help  # 應能正常執行

# 4. 重置 Ralph
~/.local/bin/ralph --reset-session
~/.local/bin/ralph --reset-circuit
```

### 常見問題

1. **Ralph 卡住不動**
   - 將大任務拆分成更小的子任務
   - 檢查 `logs/ralph-*.log` 看錯誤訊息

2. **測試失敗**
   - 手動執行測試找出問題: `go test ./pkg/... -v`
   - 查看 Ralph 的錯誤處理邏輯

3. **效能未提升**
   - 使用 Go profiling: `go test -cpuprofile=cpu.prof`
   - 檢查並發數設定

4. **GoBridge 不可用**
   - 重新編譯: `go build -o classifier.exe cmd/scanner/main.go`
   - 測試: `python -c "from src.services.go_bridge import GoBridge; print(GoBridge().is_available)"`

---

## 📞 支援

如需協助：

1. **閱讀完整指南**: `RALPH_USAGE_GUIDE.md`
2. **查看日誌**: `logs/ralph-*.log`
3. **檢查狀態**: `~/.local/bin/ralph --status`
4. **手動驗證**: 確認 Go 和 Python 環境正常
5. **重置並重試**: `~/.local/bin/ralph --reset-session`

---

## 🎉 準備好了嗎？

現在你可以開始使用 Ralph 自動化你的 Golang 重構工作：

```bash
# 1. 複製配置檔案
cp .claude/ralph-golang-migration.md PROMPT.md
cp .claude/ralph-fix-plan.md @fix_plan.md
cp .claude/ralph-agent-golang.md @AGENT.md

# 2. 啟動 Ralph（監控模式）
~/.local/bin/ralph --monitor

# 3. 觀察並學習 Ralph 的工作方式

# 4. 定期檢查進度
cat @fix_plan.md
```

祝 Golang 重構順利！🚀

---

**最後更新**: 2025-01-11
**Ralph 版本**: 基於 frankbria/ralph-claude-code
**專案**: 女優分類系統 Golang 重構
