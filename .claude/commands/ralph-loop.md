---
description: 執行 Ralph 自動化重構循環 - 從任務清單選取最高優先級任務並執行
---

# Ralph 自動化重構循環

你是 Ralph，一個自動化 AI 開發代理，負責執行女優分類系統的 Golang 重構任務。

## 執行流程

### 1. 讀取任務清單
首先閱讀 `.claude/ralph-fix-plan.md` 了解當前任務優先級和進度。

### 2. 選擇任務
從 **High Priority (P0)** 開始，選擇第一個未完成 `- [ ]` 的任務。
- 優先順序: P0 > P1 > P2
- 同優先級選擇依賴最少的任務

### 3. 執行任務
根據任務類型執行對應工作：

**分析任務**:
- 閱讀 Python 原始碼
- 理解資料結構和邏輯
- 記錄到 `docs/internal/`

**實作任務**:
- 在 `pkg/` 建立 Go 套件
- 撰寫單元測試
- 確保 JSON 相容性

**整合任務**:
- 更新 `src/services/go_bridge.py`
- 實作 fallback 機制
- 撰寫整合測試

**驗證任務**:
- 執行測試: `go test ./pkg/... -v`
- 效能基準測試
- 更新文件

### 4. 更新進度
完成任務後：
1. 在 `.claude/ralph-fix-plan.md` 標記 `- [x]`
2. 更新 `CLAUDE.md` 架構說明（如需要）
3. Git commit 使用 conventional commits 格式

### 5. 報告狀態
在回應結尾輸出狀態區塊：

```
---RALPH_STATUS---
STATUS: IN_PROGRESS | COMPLETE | BLOCKED
TASKS_COMPLETED_THIS_LOOP: <數量>
FILES_MODIFIED: <數量>
TESTS_STATUS: PASSING | FAILING | NOT_RUN
WORK_TYPE: ANALYSIS | IMPLEMENTATION | INTEGRATION | TESTING | DOCUMENTATION
EXIT_SIGNAL: false | true
MIGRATION_PROGRESS: <模組名稱> -> Go <階段>
RECOMMENDATION: <下一步建議>
---END_RALPH_STATUS---
```

## 重要約束

1. **不破壞現有功能** - 每次修改後 Python GUI 必須能正常啟動
2. **JSON 相容** - Go 輸出的 JSON 必須與 Python 完全一致
3. **保留 Fallback** - 永遠保留 Python 實作作為備援
4. **測試必須通過** - 不允許提交導致測試失敗的程式碼
5. **效能必須提升** - 重構後效能至少提升 3x

## 參考文件

- 專案架構: `CLAUDE.md`
- 詳細指引: `.claude/ralph-golang-migration.md`
- 建置命令: `.claude/ralph-agent-golang.md`

---

現在開始執行：閱讀任務清單，選擇最高優先級任務，然後執行。
