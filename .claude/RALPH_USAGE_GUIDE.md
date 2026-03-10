# Ralph 使用指南 - 女優分類系統 Golang 重構

> 如何使用 Ralph 自動化執行 Golang 重構任務

## 📋 檔案清單

我已經為你的專案建立了以下 Ralph 配置檔案：

| 檔案 | 用途 | 對應標準檔案 |
|------|------|-------------|
| `.claude/ralph-golang-migration.md` | Ralph 核心指令 | `PROMPT.md` |
| `.claude/ralph-fix-plan.md` | 任務優先級清單 | `@fix_plan.md` |
| `.claude/ralph-agent-golang.md` | 建置和測試指令 | `@AGENT.md` |

---

## 🚀 快速開始

### 方式 1: 在當前專案中使用 Ralph

```bash
# 1. 進入專案根目錄
cd /c/Users/cy540/OneDrive/桌面/PornActressDB-Golang-Migration

# 2. 將 Ralph 配置檔案複製到專案根目錄（或建立符號連結）
cp .claude/ralph-golang-migration.md PROMPT.md
cp .claude/ralph-fix-plan.md @fix_plan.md
cp .claude/ralph-agent-golang.md @AGENT.md

# 3. 啟動 Ralph（使用監控模式）
~/.local/bin/ralph --monitor
```

### 方式 2: 建立專用的 Ralph 工作目錄

```bash
# 1. 建立 Ralph 專案目錄（軟連結到原專案）
mkdir ~/ralph-actress-migration
cd ~/ralph-actress-migration

# 2. 連結配置檔案
ln -s /c/Users/cy540/OneDrive/桌面/PornActressDB-Golang-Migration/.claude/ralph-golang-migration.md PROMPT.md
ln -s /c/Users/cy540/OneDrive/桌面/PornActressDB-Golang-Migration/.claude/ralph-fix-plan.md @fix_plan.md
ln -s /c/Users/cy540/OneDrive/桌面/PornActressDB-Golang-Migration/.claude/ralph-agent-golang.md @AGENT.md

# 3. 連結專案檔案
ln -s /c/Users/cy540/OneDrive/桌面/PornActressDB-Golang-Migration/src src
ln -s /c/Users/cy540/OneDrive/桌面/PornActressDB-Golang-Migration/pkg pkg
ln -s /c/Users/cy540/OneDrive/桌面/PornActressDB-Golang-Migration/cmd cmd
ln -s /c/Users/cy540/OneDrive/桌面/PornActressDB-Golang-Migration/GO_MIGRATION_TODO.md specs/migration.md

# 4. 啟動 Ralph
~/.local/bin/ralph --monitor
```

---

## 📖 Ralph 配置詳解

### 1. PROMPT.md (ralph-golang-migration.md)

這是 Ralph 的「大腦」，包含：

- **專案背景**: 女優分類系統架構和重構目標
- **重構原則**: 漸進式、功能等價性、fallback 機制
- **執行流程**: 分析 → 設計 → 實作 → 整合 → 驗證
- **Go 程式碼標準**: 錯誤處理、JSON 相容、並發安全
- **測試策略**: 單元測試、整合測試、效能測試
- **狀態報告格式**: Ralph 專用的 `---RALPH_STATUS---` 區塊

**關鍵特性**:
- ✅ 針對 Golang 重構工作流程客製化
- ✅ 包含 Python-Go 整合規範
- ✅ 強調效能驗證（目標 3x-10x 提升）
- ✅ 詳細的退出場景（知道何時完成）

### 2. @fix_plan.md (ralph-fix-plan.md)

任務優先級清單，基於 `GO_MIGRATION_TODO.md` 整理：

**優先級劃分**:
- 🔴 **High Priority (P0)**: 資料庫層重構、掃描器完整整合
- 🟡 **Medium Priority (P1)**: 片商識別器、快取管理器
- 🟢 **Low Priority (P2)**: CLI 功能增強、文件範例
- ✅ **Completed**: MVP-1 到 MVP-5 已完成項目

**任務細分**:
每個大任務都拆分成可執行的小步驟，例如「資料庫層重構」包含：
1. 分析 Python 架構
2. 設計 Go 介面
3. 實作核心功能
4. 撰寫測試
5. CLI 整合
6. Python 橋接
7. 效能驗證

### 3. @AGENT.md (ralph-agent-golang.md)

建置和測試指令大全：

**包含內容**:
- Go 建置命令（`go build`, `go test`）
- Python 測試命令（`pytest`）
- 整合測試流程
- 效能基準測試
- 程式碼檢查（`go fmt`, `go vet`）
- Git workflow 規範
- 完成清單（Feature Completion Checklist）

**關鍵清單**:
- 🧪 測試要求（80%+ 覆蓋率）
- 📋 Git 提交規範（Conventional Commits）
- 📝 文件更新要求
- 🚨 絕對不可違反的規則

---

## 🎯 Ralph 執行流程

### 典型的 Ralph 循環

```
┌─────────────────────────────────────────┐
│ 1. Ralph 讀取 PROMPT.md 和 @fix_plan.md │
└───────────┬─────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│ 2. 選擇最高優先級任務                    │
│    (例如: 分析 incremental_json_database.py) │
└───────────┬─────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│ 3. 執行任務                              │
│    - 閱讀 Python 程式碼                  │
│    - 設計 Go 介面                        │
│    - 撰寫測試                            │
│    - 實作功能                            │
└───────────┬─────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│ 4. 報告狀態                              │
│    ---RALPH_STATUS---                    │
│    STATUS: IN_PROGRESS                   │
│    ...                                   │
│    EXIT_SIGNAL: false                    │
│    ---END_RALPH_STATUS---                │
└───────────┬─────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│ 5. Ralph 判斷是否繼續                    │
│    - EXIT_SIGNAL: false → 繼續下一循環   │
│    - EXIT_SIGNAL: true → 完成退出        │
└─────────────────────────────────────────┘
```

### 第一次執行 Ralph 會做什麼？

根據 `@fix_plan.md` 的優先級，Ralph 會：

1. **閱讀任務清單** - 從 `@fix_plan.md` 找到第一個待辦任務
   - 當前最高優先級: 「分析 incremental_json_database.py 架構」

2. **執行分析任務**:
   ```bash
   # Ralph 會自動執行類似這樣的工作:
   - 閱讀 src/models/incremental_json_database.py
   - 理解 Journal 增量機制
   - 理解 Compact 合併邏輯
   - 記錄 JSON 格式定義
   - 撰寫分析報告到 docs/internal/design/database-analysis.md
   ```

3. **報告狀態**:
   ```
   ---RALPH_STATUS---
   STATUS: IN_PROGRESS
   TASKS_COMPLETED_THIS_LOOP: 1
   FILES_MODIFIED: 1
   TESTS_STATUS: NOT_RUN
   WORK_TYPE: ANALYSIS
   EXIT_SIGNAL: false
   MIGRATION_PROGRESS: incremental_json_database.py -> Go Phase 1/4 (Analysis)
   RECOMMENDATION: Next: Design Go database package interface
   ---END_RALPH_STATUS---
   ```

4. **進入下一循環** - 執行下一個任務「設計 Go 資料庫套件」

---

## 🎛️ Ralph 執行參數

### 基本執行
```bash
# 預設執行（100 calls/hour, JSON 輸出）
~/.local/bin/ralph

# 監控模式（推薦 - 顯示即時進度）
~/.local/bin/ralph --monitor
```

### 自訂參數
```bash
# 限制 API 呼叫次數
~/.local/bin/ralph --calls 30

# 設定逾時時間（30 分鐘）
~/.local/bin/ralph --timeout 30

# 顯示詳細進度
~/.local/bin/ralph --verbose

# 使用文字輸出格式
~/.local/bin/ralph --output-format text

# 禁用會話連續性（每次重新開始）
~/.local/bin/ralph --no-continue
```

### 狀態查詢
```bash
# 查看當前狀態
~/.local/bin/ralph --status

# 查看斷路器狀態
~/.local/bin/ralph --circuit-status
```

### 重置和修復
```bash
# 重置會話狀態
~/.local/bin/ralph --reset-session

# 重置斷路器
~/.local/bin/ralph --reset-circuit
```

---

## 📊 監控 Ralph 執行

### 使用 tmux 監控模式

```bash
~/.local/bin/ralph --monitor
```

這會啟動一個 tmux session，分為兩個窗格：
- **左窗格**: Ralph 執行輸出
- **右窗格**: 即時監控儀表板

監控儀表板顯示：
```
╔══════════════════════════════════════════╗
║  Ralph Loop Monitor                      ║
╠══════════════════════════════════════════╣
║ Status: IN_PROGRESS                      ║
║ API Calls: 15/100                        ║
║ Files Modified: 5                        ║
║ Tests: PASSING                           ║
║ Work Type: IMPLEMENTATION                ║
║ Circuit: CLOSED                          ║
╠══════════════════════════════════════════╣
║ Current Task:                            ║
║ incremental_json_database.py -> Go       ║
║ Phase 2/4 (Implementation)               ║
╚══════════════════════════════════════════╝
```

### 查看日誌

```bash
# 即時查看 Ralph 日誌
tail -f logs/ralph-*.log

# 查看狀態檔案
cat status.json

# 查看會話歷史
cat .ralph_session_history
```

---

## 🛠️ 調整和客製化

### 修改任務優先級

編輯 `@fix_plan.md`，調整任務順序或優先級：

```markdown
## 🔴 High Priority

### 我想先做這個任務
- [ ] 任務描述
- [ ] 子任務 1
- [ ] 子任務 2

### 原本的第一優先任務降級
- [ ] ...
```

Ralph 會自動從頂部開始執行最高優先級的未完成任務。

### 修改 Ralph 行為

編輯 `PROMPT.md`，調整：

1. **測試比例**: 修改 "LIMIT testing to ~20%" 為你想要的比例
2. **並發數**: 修改 "max 100 concurrent" 為你的 API 限制
3. **退出條件**: 調整 "When to set EXIT_SIGNAL: true" 的條件

### 新增自訂命令

編輯 `@AGENT.md`，新增你的常用命令：

```markdown
## 🔧 自訂命令

### 快速建置和測試
```bash
# 一鍵建置和測試
./scripts/build-and-test.sh
```
```

---

## 🎓 最佳實踐

### 1. 讓 Ralph 小步快跑

❌ **不好的任務**:
```markdown
- [ ] 完成整個資料庫層重構
```

✅ **好的任務**:
```markdown
- [ ] 分析 incremental_json_database.py 架構
- [ ] 設計 Go 資料庫套件介面
- [ ] 實作 UpdateVideo() 函式
- [ ] 實作 GetVideo() 函式
- [ ] 撰寫資料庫單元測試
```

### 2. 清晰的任務描述

❌ **不好**:
```markdown
- [ ] 做點什麼
```

✅ **好**:
```markdown
- [ ] 實作 Go IncrementalDB.UpdateVideo() 方法
  - 讀取現有 data.json
  - 寫入 data.journal (JSON Lines)
  - 更新 data.index (Dirty keys)
```

### 3. 定期檢查進度

```bash
# 每天開始前檢查 Ralph 狀態
~/.local/bin/ralph --status

# 查看 @fix_plan.md 的完成進度
grep -E "\[x\]|\[ \]" @fix_plan.md | wc -l
```

### 4. 驗證 Ralph 的工作

```bash
# Ralph 完成一個任務後，手動驗證
go test ./pkg/database -v
pytest tests/test_database_integration.py

# 確認 Git commit 品質
git log --oneline -5
```

---

## 🐛 常見問題

### Q1: Ralph 一直卡在同一個任務上

**原因**: 任務可能太大或太模糊

**解決**:
1. 將大任務拆分成更小的子任務
2. 在 `@fix_plan.md` 中提供更具體的步驟
3. 檢查 `logs/ralph-*.log` 看 Ralph 遇到什麼問題

### Q2: Ralph 執行了不該做的事情

**原因**: `PROMPT.md` 的指令不夠明確

**解決**:
1. 編輯 `PROMPT.md`，在「Critical Constraints」中明確禁止
2. 使用 `--reset-session` 重置 Ralph 狀態
3. 手動回退錯誤的更改

### Q3: Ralph 說任務完成了，但測試失敗

**原因**: Ralph 的完成條件設定不當

**解決**:
1. 編輯 `PROMPT.md` 的「重構完成條件」
2. 加入更嚴格的檢查（例如強制執行測試）
3. 在 `@AGENT.md` 中加入 pre-commit 檢查

### Q4: Ralph 效能測試顯示沒有提升

**原因**:
- Go 實作可能有效能瓶頸
- 基準測試方法不正確

**解決**:
1. 使用 Go profiling 工具分析瓶頸
2. 檢查是否有不必要的記憶體分配
3. 驗證並發數設定是否合理

### Q5: Ralph 不使用 Go CLI，一直用 Python

**原因**: GoBridge 偵測不到 `classifier.exe`

**解決**:
```bash
# 確認 classifier.exe 存在
ls classifier.exe

# 重新編譯
go build -o classifier.exe cmd/scanner/main.go

# 測試 GoBridge
python -c "from src.services.go_bridge import GoBridge; print(GoBridge().is_available)"
```

---

## 📚 進階技巧

### 技巧 1: 使用 Ralph 會話連續性

Ralph 預設會保持會話連續性，讓每次循環都能記住上次的上下文：

```bash
# 啟用會話連續性（預設）
~/.local/bin/ralph

# 查看會話歷史
cat .ralph_session_history

# 如果要重新開始，禁用連續性
~/.local/bin/ralph --no-continue
```

### 技巧 2: 並行執行多個 Ralph

如果有多個獨立的重構任務，可以同時執行多個 Ralph：

```bash
# Terminal 1: 資料庫層重構
cd ~/ralph-database
~/.local/bin/ralph --monitor

# Terminal 2: 快取層重構
cd ~/ralph-cache
~/.local/bin/ralph --monitor
```

### 技巧 3: 自訂斷路器閾值

修改 `PROMPT.md` 中的退出場景，調整 Ralph 的容錯性：

```markdown
### Scenario 3: Stuck on Recurring Error
**Given**:
- Same error appears in last 5 consecutive loops  # 改為 3 或 7
```

### 技巧 4: 整合到 CI/CD

```bash
# 建立自動化腳本
#!/bin/bash
# scripts/ralph-auto-refactor.sh

~/.local/bin/ralph --calls 30 --timeout 60 --no-continue

# 檢查結果
if [ $? -eq 0 ]; then
    echo "Ralph completed successfully"
    # 執行測試
    go test ./pkg/...
    pytest tests/
else
    echo "Ralph failed"
    exit 1
fi
```

---

## 🎯 成功指標

你可以透過以下指標判斷 Ralph 是否正常工作：

### 進度指標
- ✅ `@fix_plan.md` 中的任務逐步被標記為 [x]
- ✅ `pkg/` 目錄中出現新的 Go 套件
- ✅ `GO_MIGRATION_TODO.md` 的完成進度更新

### 品質指標
- ✅ 所有 Go 測試通過 (`go test ./pkg/...`)
- ✅ 所有 Python 測試通過 (`pytest`)
- ✅ Git commit 使用 Conventional Commits 格式
- ✅ 效能基準測試顯示提升

### 文件指標
- ✅ `CLAUDE.md` 架構圖持續更新
- ✅ Go 套件有完整的 package 文件
- ✅ Python 模組標註 Go 加速版本

---

## 📞 需要協助？

如果遇到問題：

1. **檢查日誌**: `logs/ralph-*.log`
2. **查看狀態**: `~/.local/bin/ralph --status`
3. **閱讀文件**: 重新閱讀 `PROMPT.md` 和 `@AGENT.md`
4. **手動驗證**: 確認 Go 和 Python 環境正常
5. **重置狀態**: `~/.local/bin/ralph --reset-session`

---

## 🎉 下一步

你現在可以：

1. **立即開始**: `~/.local/bin/ralph --monitor`
2. **測試配置**: 先在測試專案中試用 Ralph
3. **客製化**: 根據你的需求調整 PROMPT.md
4. **監控進度**: 定期檢查 @fix_plan.md 的完成狀態

祝 Golang 重構順利！🚀
