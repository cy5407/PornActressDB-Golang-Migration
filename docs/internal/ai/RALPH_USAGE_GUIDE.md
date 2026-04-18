# Ralph 使用指南 - 女優分類系統

> **Ralph** 是一個自主式 AI 開發代理工具，能夠根據 Todo List 自動執行程式碼分析、實作、測試和文件更新等開發任務。

---

## 📋 目錄

1. [Ralph 是什麼？](#ralph-是什麼)
2. [安裝與設定](#安裝與設定)
3. [基本使用流程](#基本使用流程)
4. [指令參考](#指令參考)
5. [實際範例](#實際範例)
6. [監控與除錯](#監控與除錯)
7. [最佳實踐](#最佳實踐)

---

## 🤖 Ralph 是什麼？

Ralph 是一個**自動化開發代理工具**，專門用於：

- ✅ 自動執行多步驟的開發任務
- ✅ 根據 Todo List 規劃和執行工作
- ✅ 自動撰寫、測試和驗證程式碼
- ✅ 產生詳細的執行報告和進度追蹤
- ✅ 在背景持續工作，釋放開發者時間

**特色**：
- 🔄 **循環執行**：持續工作直到任務完成
- 📊 **進度追蹤**：即時更新狀態和統計資訊
- 🛡️ **錯誤處理**：遇到問題自動重試或調整策略
- 📝 **詳細日誌**：記錄所有操作和決策過程

---

## 🔧 安裝與設定

### 前置需求

- **作業系統**：Linux / macOS (建議)
- **Python 3.8+**
- **Git**
- **Go 1.21+** (本專案需要)

### 安裝 Ralph

```bash
# 使用 pip 安裝
pip install ralph-claude-code

# 或從原始碼安裝
git clone https://github.com/frankbria/ralph-claude-code.git
cd ralph-claude-code
pip install -e .
```

### 驗證安裝

```bash
ralph --version
ralph --help
```

---

## 📖 基本使用流程

### **步驟 1：準備 Todo List**

Ralph 需要一個清晰的任務清單來規劃工作。在專案根目錄建立或編輯以下檔案之一：

- `@fix_plan.md` - 修復計畫
- `@AGENT.md` - 開發指引
- `todo.md` - 通用待辦事項

**Todo List 範例格式**：

```markdown
# 開發任務清單

## 🔥 高優先級

- [ ] 修復 classifier_core.py 中的 Path 未定義錯誤
- [ ] 實作 Go 資料庫層的增量寫入功能
- [ ] 更新 Python-Go 橋接層以支援新的 DB 操作

## 📦 中優先級

- [ ] 重構 studio.py 並遷移至 Go
- [ ] 最佳化檔案掃描效能
- [ ] 新增單元測試覆蓋率至 80%

## 📝 低優先級

- [ ] 更新 README.md 文件
- [ ] 清理未使用的程式碼
```

---

### **步驟 2：設定專案 Prompt**

建立或更新 `PROMPT.md` 檔案，告訴 Ralph 專案的背景和規範：

```markdown
# Ralph Development Instructions

## Context
You are Ralph, working on the Actress Classifier Golang Migration project.

## Objectives
1. 閱讀 GO_MIGRATION_TODO.md 了解進度
2. 選擇最高優先級任務
3. 實作並測試
4. 更新文件

## Key Principles
- 漸進式重構
- 功能等價性驗證
- 自動測試驗證
```

---

### **步驟 3：啟動 Ralph**

```bash
# 基本啟動（文字輸出）
ralph --output-format text

# 詳細模式（推薦）
ralph --output-format text --verbose

# 背景執行
nohup ralph --output-format text --verbose > ralph_output.log 2>&1 &
```

---

### **步驟 4：監控執行進度**

Ralph 會在背景自動工作，你可以透過以下方式監控：

```bash
# 查看即時輸出
tail -f /tmp/claude/<project-path>/tasks/*.output

# 查看狀態
ralph --status

# 使用專案提供的監控腳本
bash monitor_ralph.sh
```

---

### **步驟 5：檢查執行結果**

Ralph 完成後會產生：

1. **修改的檔案** - 自動提交到 Git
2. **執行報告** - `RALPH_EXECUTION_REPORT.md`
3. **更新的狀態** - `status.json`, `progress.json`
4. **測試結果** - 測試日誌和覆蓋率報告

---

## 📚 指令參考

### 啟動 Ralph

```bash
# 標準啟動
ralph

# 文字模式（更易讀）
ralph --output-format text

# 詳細日誌
ralph --verbose

# 指定專案目錄
ralph --project-dir /path/to/project

# 背景執行
ralph --output-format text --verbose &
```

### 監控與控制

```bash
# 查看狀態
ralph --status

# 停止 Ralph
pkill -f ralph

# 查看日誌
tail -100 logs/ralph-*.log
```

### Ralph 狀態檢查

```bash
# 使用 monitor_ralph.sh (專案提供)
bash monitor_ralph.sh

# 手動檢查進度
grep "\[x\]" @fix_plan.md | wc -l    # 已完成任務
grep "\[ \]" @fix_plan.md | wc -l    # 待辦任務
```

---

## 🎯 實際範例

### 範例 1：修復 Import 錯誤

**情境**：發現 `classifier_core.py` 缺少 `Path` 匯入

#### 步驟 1：建立 Todo List

在 `@fix_plan.md` 中新增：

```markdown
## 緊急修復

- [ ] 修復 classifier_core.py 中的 NameError: Path 未定義
  - 檢查檔案的 import 區塊
  - 新增 `from pathlib import Path`
  - 執行語法檢查驗證
  - 執行相關單元測試
```

#### 步驟 2：啟動 Ralph

```bash
cd /path/to/PornActressDB-Golang-Migration
ralph --output-format text --verbose
```

#### 步驟 3：Ralph 自動執行

Ralph 會：
1. 📖 讀取 `@fix_plan.md`
2. 🔍 分析 `classifier_core.py` 檔案
3. ✏️ 新增 `from pathlib import Path`
4. ✅ 執行 `python -m py_compile src/services/classifier_core.py`
5. 📝 更新 Todo List，標記 `[x]` 已完成
6. 📊 產生執行報告

#### 步驟 4：檢查結果

```bash
# 檢查修改
git diff src/services/classifier_core.py

# 驗證修復
python -m py_compile src/services/classifier_core.py

# 查看 Ralph 報告
cat RALPH_EXECUTION_REPORT.md
```

---

### 範例 2：實作 Go 資料庫層

**情境**：將 Python 的 `incremental_json_database.py` 遷移至 Go

#### 步驟 1：建立詳細 Todo List

在 `GO_MIGRATION_TODO.md` 中新增：

```markdown
## P0: 資料庫層遷移 (最高優先)

### 任務分解

- [ ] **階段 1：分析與設計**
  - [ ] 分析 `src/models/incremental_json_database.py` 功能
  - [ ] 設計 Go 資料結構 (struct tags 確保 JSON 相容)
  - [ ] 規劃 Python-Go 橋接介面
  - [ ] 撰寫設計文件至 `docs/internal/`（必要時自行建立子目錄）

- [ ] **階段 2：Go 實作**
  - [ ] 建立 `pkg/database/` 目錄結構
  - [ ] 實作 `jsondb.go` - 核心 CRUD 操作
  - [ ] 實作 `journal.go` - 增量寫入機制
  - [ ] 實作 `types.go` - 資料模型定義
  - [ ] 新增 `jsondb_test.go` - 單元測試 (目標 80%+ 覆蓋率)

- [ ] **階段 3：CLI 整合**
  - [ ] 在 `cmd/scanner/main.go` 新增 DB 子命令
    - `db get <code>` - 查詢影片資料
    - `db update <code> <json>` - 更新資料
    - `db list` - 列出所有影片
    - `db stats` - 顯示統計資訊
  - [ ] 確保輸出 JSON 格式與 Python 版本一致

- [ ] **階段 4：Python 橋接**
  - [ ] 在 `src/services/go_bridge.py` 新增方法
    - `db_get_video(code: str) -> dict`
    - `db_update_video(code: str, data: dict) -> bool`
    - `db_delete_video(code: str) -> bool`
    - `db_list_videos() -> list`
  - [ ] 實作 fallback 機制 (Go 失敗時呼叫 Python)
  - [ ] 更新 `IncrementalJSONDB` 類別以支援 Go 加速

- [ ] **階段 5：測試與驗證**
  - [ ] 執行 Go 單元測試 `go test ./pkg/database -v`
  - [ ] 執行整合測試 `python test_go_db_bridge.py`
  - [ ] 效能基準測試 (目標：30x-40x 提升)
  - [ ] 等價性測試 (Python vs Go 輸出一致性)

- [ ] **階段 6：文件更新**
  - [ ] 更新 `@AGENT.md` - Go 建置指令
  - [ ] 更新 `CLAUDE.md` - 架構圖
  - [ ] 更新 `README.md` - 使用說明
  - [ ] 新增 `docs/go_database_migration.md` - 遷移指南
```

#### 步驟 2：設定專案 Prompt

確保 `PROMPT.md` 包含：

```markdown
## Current Objectives

1. 閱讀 `GO_MIGRATION_TODO.md` 了解資料庫層遷移任務
2. 遵循 4 階段流程：分析 → 實作 → 整合 → 驗證
3. 確保 JSON 格式與 Python 版本完全一致
4. 撰寫完整的單元測試 (80%+ 覆蓋率)
5. 更新所有相關文件

## Testing Requirements

- Go 單元測試必須通過
- Python 整合測試必須通過
- 效能提升至少 30x
```

#### 步驟 3：啟動 Ralph 並監控

```bash
# 啟動 Ralph（背景執行）
nohup ralph --output-format text --verbose > logs/ralph_db_migration.log 2>&1 &

# 記錄 PID
echo $! > /tmp/ralph.pid

# 監控進度（另一個終端）
watch -n 5 'tail -30 logs/ralph_db_migration.log'

# 或使用監控腳本
bash monitor_ralph.sh
```

#### 步驟 4：Ralph 自動執行流程

Ralph 會自動循環執行：

**Loop #1: 分析階段**
- 讀取 `src/models/incremental_json_database.py`
- 分析資料結構和 JSON 格式
- 撰寫設計文件
- 更新 Todo: `[x] 階段 1：分析與設計`

**Loop #2: 實作階段**
- 建立 `pkg/database/` 結構
- 實作 `jsondb.go`, `journal.go`, `types.go`
- 撰寫測試 `jsondb_test.go`
- 執行 `go test ./pkg/database -v`
- 更新 Todo: `[x] 階段 2：Go 實作`

**Loop #3: 整合階段**
- 更新 `cmd/scanner/main.go`
- 更新 `src/services/go_bridge.py`
- 執行整合測試
- 更新 Todo: `[x] 階段 3 & 4`

**Loop #4: 驗證與文件**
- 執行完整測試套件
- 效能基準測試
- 更新所有文件
- 產生最終報告

#### 步驟 5：檢查結果

```bash
# 查看修改的檔案
git status
git diff --stat

# 驗證 Go 模組
cd pkg/database
go test -v -cover

# 驗證 Python 橋接
python test_go_db_bridge.py

# 查看 Ralph 報告
cat RALPH_EXECUTION_REPORT.md

# 查看效能提升
grep "Performance" RALPH_EXECUTION_REPORT.md
```

---

### 範例 3：批次修復程式碼品質問題

**情境**：修復多個檔案的 linting 警告

#### 步驟 1：建立 Todo List

```markdown
## 程式碼品質改善

- [ ] 修復 pylint 警告
  - [ ] classifier_core.py - 移除未使用的 import
  - [ ] web_searcher.py - 修正變數命名
  - [ ] file_mover.py - 新增缺少的 docstring

- [ ] 格式化 Go 程式碼
  - [ ] 執行 `go fmt ./...`
  - [ ] 執行 `golangci-lint run`

- [ ] 更新測試覆蓋率
  - [ ] 新增遺失的單元測試
  - [ ] 目標：Python 70%+, Go 80%+
```

#### 步驟 2：啟動 Ralph

```bash
ralph --output-format text --verbose
```

Ralph 會自動：
- 執行 `pylint src/` 分析問題
- 逐一修復警告
- 執行 `go fmt` 和 `golangci-lint`
- 撰寫遺失的測試
- 驗證所有測試通過

---

## 🔍 監控與除錯

### 即時監控

#### 方法 1：使用專案監控腳本

```bash
bash monitor_ralph.sh
```

輸出範例：
```
========================================
  Ralph 監控面板
========================================

📄 即時輸出 (最後 50 行):
[Loop #2] 正在實作 pkg/database/jsondb.go...
[Loop #2] 執行測試: go test ./pkg/database -v
[Loop #2] ✅ 所有測試通過 (覆蓋率 87%)

📊 當前狀態:
STATUS: IN_PROGRESS
TASKS_COMPLETED_THIS_LOOP: 3
FILES_MODIFIED: 8

✅ 已完成任務數量: 12
⏳ 待辦任務數量: 8
```

#### 方法 2：手動監控

```bash
# 查看即時輸出
tail -f /tmp/claude/-c-Users-cy540-OneDrive----PornActressDB-Golang-Migration/tasks/*.output

# 查看最新日誌
tail -100 logs/ralph-*.log

# 查看狀態檔案
cat status.json
cat progress.json
```

### 常見問題除錯

#### 問題 1：Ralph 卡住不動

**解決方法**：

```bash
# 檢查是否還在執行
ps aux | grep ralph

# 查看最後輸出
tail -50 /tmp/claude/*/tasks/*.output

# 檢查錯誤訊息
tail -100 logs/ralph-*.log | grep ERROR

# 重新啟動
pkill -f ralph
ralph --output-format text --verbose
```

#### 問題 2：測試失敗

**解決方法**：

```bash
# 查看測試日誌
grep "FAILED" logs/ralph-*.log

# 手動執行失敗的測試
python -m pytest tests/test_xxx.py -v
go test ./pkg/xxx -v

# 修正後重新啟動 Ralph
ralph --output-format text --verbose
```

#### 問題 3：檔案衝突

**解決方法**：

```bash
# 檢查 Git 狀態
git status

# 查看衝突
git diff

# 解決衝突後
git add .
git commit -m "Resolve Ralph conflicts"

# 重新啟動 Ralph
ralph --output-format text --verbose
```

---

## 💡 最佳實踐

### 1. **Todo List 撰寫原則**

✅ **好的範例**：
```markdown
- [ ] 修復 classifier_core.py 的 Path 未定義錯誤
  - 檢查 import 區塊
  - 新增 `from pathlib import Path`
  - 執行 `python -m py_compile src/services/classifier_core.py`
  - 確認無其他相依問題
```

❌ **不好的範例**：
```markdown
- [ ] 修 bug
```

**原則**：
- 具體描述問題和預期結果
- 列出明確的驗證步驟
- 包含相關檔案路徑
- 分解為可執行的子任務

---

### 2. **分階段執行大型任務**

對於複雜任務（如 Go 遷移），分成多個階段：

```markdown
## 階段 1：分析 (20% 時間)
- [ ] 讀取原始碼
- [ ] 設計 Go 架構
- [ ] 撰寫設計文件

## 階段 2：實作 (40% 時間)
- [ ] 實作核心邏輯
- [ ] 撰寫單元測試

## 階段 3：整合 (20% 時間)
- [ ] 更新 CLI
- [ ] 更新 Python 橋接

## 階段 4：驗證 (20% 時間)
- [ ] 執行所有測試
- [ ] 更新文件
```

---

### 3. **善用 PROMPT.md 引導 Ralph**

在 `PROMPT.md` 中提供：

```markdown
## Key Principles
- 漸進式重構：一次一個模組
- 自動測試：每次修改後立即驗證
- 文件同步：程式碼和文件一起更新

## Testing Requirements
- Python: pytest 必須通過
- Go: go test 覆蓋率 >80%
- 整合測試必須驗證 Python-Go 互通

## Error Handling
- Import Error → 檢查相依性並修復
- Test Failure → 分析失敗原因並重構
- Build Error → 修正編譯錯誤
```

---

### 4. **定期檢查點**

設定檢查點讓 Ralph 報告進度：

```markdown
## Milestone 1: 資料庫層 Go 遷移 (本週)
- [ ] 完成 pkg/database 實作
- [ ] 通過所有測試
- [ ] 效能提升 >30x

---CHECKPOINT---

## Milestone 2: 片商識別器遷移 (下週)
- [ ] 完成 pkg/studio 實作
- [ ] 整合至 CLI
- [ ] 更新文件
```

---

### 5. **保持 Ralph 專注**

避免：
```markdown
- [ ] 重構所有程式碼
- [ ] 優化效能
- [ ] 修復所有 bug
```

改為：
```markdown
- [ ] 重構 classifier_core.py 的檔案移動邏輯
- [ ] 優化 pkg/database 的 JSON 解析效能（目標減少 50% 記憶體使用）
- [ ] 修復 #123: interactive_move_files 的 Path 未定義錯誤
```

---

### 6. **備份與版本控制**

在啟動 Ralph 前：

```bash
# 建立備份分支
git checkout -b backup-before-ralph-$(date +%Y%m%d)
git push origin backup-before-ralph-$(date +%Y%m%d)

# 切回主分支
git checkout main

# 啟動 Ralph
ralph --output-format text --verbose
```

---

### 7. **檢視執行報告**

Ralph 完成後：

```bash
# 查看完整報告
cat RALPH_EXECUTION_REPORT.md

# 查看統計資訊
grep "總循環數\|修改檔案數\|完成任務數" RALPH_EXECUTION_REPORT.md

# 查看修改的檔案
git diff --stat main HEAD

# 查看具體變更
git log --oneline -10
```

---

## 📊 Ralph 工作流程總結

```
┌─────────────────────────────────────────────────────────┐
│                  1. 準備 Todo List                       │
│            (@fix_plan.md / GO_MIGRATION_TODO.md)        │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              2. 設定專案 Prompt (PROMPT.md)              │
│        (定義原則、測試需求、錯誤處理策略)                │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│         3. 啟動 Ralph                                    │
│    $ ralph --output-format text --verbose               │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│         4. Ralph 自動循環執行                            │
│    Loop #1: 分析 → 規劃 → 實作                          │
│    Loop #2: 測試 → 修正 → 整合                          │
│    Loop #3: 驗證 → 文件 → 報告                          │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│         5. 監控進度                                      │
│    $ bash monitor_ralph.sh                              │
│    $ tail -f logs/ralph-*.log                           │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│         6. 檢查結果                                      │
│    - 查看 RALPH_EXECUTION_REPORT.md                     │
│    - 驗證測試通過                                        │
│    - 檢視 Git 變更                                      │
└─────────────────────────────────────────────────────────┘
```

---

## 🎓 進階技巧

### 多任務並行

Ralph 支援多個 Todo List：

```bash
# 主要開發任務
ralph --todo-file @fix_plan.md &

# 文件更新任務（另一個 Ralph 實例）
ralph --todo-file docs/TODO.md &
```

### 自訂 Ralph 行為

在 `PROMPT.md` 中加入：

```markdown
## Ralph Custom Behavior

### Code Style
- Python: 使用 Black 格式化 (line length: 88)
- Go: 遵循標準 Go fmt
- 所有註解使用繁體中文

### Commit Strategy
- 每完成一個任務就 commit
- Commit message 格式: `[Ralph] <type>: <description>`
  - type: feat, fix, refactor, test, docs

### Testing Priority
1. 先執行快速測試 (單元測試)
2. 再執行慢速測試 (整合測試)
3. 最後執行效能測試

### Error Recovery
- Build 失敗 → 回退到上一個 commit
- Test 失敗 → 最多重試 3 次
- Timeout → 分解任務為更小單位
```

---

## 📚 相關資源

### 文件
- [Ralph 官方文件](https://github.com/frankbria/ralph-claude-code)
- [專案 PROMPT.md](../PROMPT.md) - Ralph 專案設定
- [GO_MIGRATION_TODO.md](../GO_MIGRATION_TODO.md) - Go 遷移進度
- [RALPH_EXECUTION_REPORT.md](../RALPH_EXECUTION_REPORT.md) - 最新執行報告

### 工具腳本
- [`monitor_ralph.sh`](../monitor_ralph.sh) - 監控腳本
- [`@fix_plan.md`](../@fix_plan.md) - 修復計畫
- [`@AGENT.md`](../@AGENT.md) - Agent 建置指引

---

## ❓ 常見問題 FAQ

### Q1: Ralph 和 GitHub Copilot 有什麼不同？

**A**:
- **Copilot**: 即時程式碼補全、單行/片段建議
- **Ralph**: 自主式長時間執行、多檔案修改、完整任務流程（分析→實作→測試→文件）

兩者可以互補使用！

---

### Q2: Ralph 會覆蓋我的程式碼嗎？

**A**: Ralph 會修改檔案，但所有變更都會記錄在 Git 中。建議：
1. 使用前建立備份分支
2. 定期檢查 `git diff`
3. 使用 `git revert` 回退不需要的變更

---

### Q3: 如何讓 Ralph 停止執行？

**A**:
```bash
# 找到 Ralph 進程
ps aux | grep ralph

# 停止 Ralph
pkill -f ralph

# 或使用 PID 停止
kill <PID>
```

---

### Q4: Ralph 執行多久會自動結束？

**A**: Ralph 會在以下情況自動結束：
- ✅ 所有 Todo 任務完成
- ✅ 達到 `EXIT_SIGNAL: true` 條件
- ❌ 遇到無法解決的錯誤（超過重試次數）
- ⏱️ 達到設定的 timeout（如有設定）

通常執行時間：10 分鐘 ~ 2 小時（取決於任務複雜度）

---

### Q5: 如何提高 Ralph 的執行效率？

**A**:
1. **明確的 Todo List** - 避免模糊的任務描述
2. **分解大任務** - 每個任務 <30 分鐘
3. **提供範例** - 在 PROMPT.md 提供程式碼範例
4. **快速回饋** - 設定自動測試快速驗證

---

## 🎉 總結

Ralph 是一個強大的自動化開發工具，特別適合：

✅ 重複性開發任務（重構、遷移、測試）
✅ 多檔案修改（架構調整、依賴更新）
✅ 長時間執行任務（完整模組實作）
✅ 需要嚴格測試驗證的工作（品質保證）

**記住**：
1. 📋 準備詳細的 Todo List
2. 📝 設定清晰的 PROMPT.md
3. 🚀 啟動 Ralph 並監控
4. ✅ 驗證結果並檢查報告

---

**祝你使用 Ralph 愉快！🎊**

有問題？查看 [RALPH_EXECUTION_REPORT.md](../RALPH_EXECUTION_REPORT.md) 了解實際執行範例。
