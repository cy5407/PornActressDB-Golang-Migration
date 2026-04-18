# Agent Skills 實作任務清單

> 📅 **建立日期**: 2026-02-17  
> 📊 **基於**: [Skills 分析報告](./SKILLS_ANALYSIS_REPORT.md)  
> 🎯 **目標**: 完善專案 Agent Skills 配置，提升開發效率  

---

## 📋 任務總覽

| 階段 | 任務數 | 預估時間 | 狀態 |
|------|--------|----------|------|
| 🚨 **緊急修正** | 1 | 5 分鐘 | ⏳ 待執行 |
| 🔥 **高優先級** | 3 | 4-6 小時 | ⏳ 待執行 |
| 🌟 **中優先級** | 3 | 3-5 小時 | ⏳ 待執行 |
| 💡 **低優先級** | 2 | 2-3 小時 | ⏳ 待執行 |
| **總計** | **9** | **9-14 小時** | **0% 完成** |

---

## 🚨 階段 0：緊急修正（必須立即執行）

### Task 0.1: 修正現有 actress-classifier Skill

**優先級**: 🔴 P0 (最高)  
**預估時間**: 5 分鐘  
**狀態**: ⏳ 待執行  

#### 問題描述
- ❌ 缺少必填的 `name` 欄位
- ⚠️ `description` 缺少使用時機說明

#### 執行步驟

1. **編輯檔案**
   ```bash
   code .claude/skills/actress-classifier/SKILL.md
   ```

2. **修改 YAML Front Matter**
   
   將：
   ```yaml
   ---
   description: 女優分類系統開發指引 - 提供專案架構、程式碼規範、常用模式和術語對照
   ---
   ```
   
   改為：
   ```yaml
   ---
   name: actress-classifier
   description: 女優分類系統開發指引 - 提供專案架構、程式碼規範、常用模式和術語對照。使用於開發新功能、修改現有程式碼、或需要了解專案技術棧時。
   argument-hint: [功能名稱或問題描述]
   user-invokable: true
   ---
   ```

3. **驗證修正**
   - [ ] 儲存檔案
   - [ ] 在 VS Code Chat 輸入 `/` 確認 Skill 出現
   - [ ] 測試 `/actress-classifier` 命令

#### 驗收標準
- ✅ YAML Front Matter 包含 `name` 欄位
- ✅ `description` 包含使用時機說明
- ✅ Skill 在 VS Code Chat 的 `/` 選單中可見
- ✅ 執行 `/actress-classifier` 可正確載入指令

#### 相關檔案
- `.claude/skills/actress-classifier/SKILL.md`

---

## 🔥 階段 1：高優先級 Skills（本週內完成）

### Task 1.1: 建立 go-bridge-development Skill

**優先級**: 🔴 P0 (最高)  
**預估時間**: 2-3 小時  
**狀態**: ⏳ 待執行  
**重要性**: ⭐⭐⭐⭐⭐ 專案核心特色  

#### 為什麼重要
- ✅ Python + Go 混合架構是專案最獨特的技術
- ✅ 涉及複雜的 subprocess 呼叫、JSON 序列化、錯誤處理
- ✅ 有特定的開發模式和 fallback 機制

#### 執行步驟

1. **建立目錄結構**
   ```bash
   mkdir -p .github/skills/go-bridge-development
   mkdir -p .github/skills/go-bridge-development/examples
   mkdir -p .github/skills/go-bridge-development/templates
   mkdir -p .claude/skills/go-bridge-development  # 相容性
   ```

2. **建立 SKILL.md**
   ```bash
   touch .github/skills/go-bridge-development/SKILL.md
   ```
   
   內容參考範本（見下方詳細範本）

3. **建立範例檔案**
   - [ ] `examples/new-go-command.go` - Go CLI 新命令範例
   - [ ] `examples/python-bridge-call.py` - Python 呼叫範例
   - [ ] `examples/json-schema.json` - JSON 結構範例
   - [ ] `examples/test-integration.py` - 整合測試範例

4. **建立範本檔案**
   - [ ] `templates/go-cli-command-template.go`
   - [ ] `templates/python-bridge-method-template.py`
   - [ ] `templates/test-template.py`

5. **同步到 Claude**
   ```bash
   cp -r .github/skills/go-bridge-development .claude/skills/
   ```

#### SKILL.md 範本

```yaml
---
name: go-bridge-development
description: Python 與 Go 整合開發指南 - 涵蓋 GoBridge 使用、新命令建立、JSON 序列化、fallback 機制。使用於開發新的 Go 功能、整合 Python 橋接、或修改現有橋接層時。
argument-hint: [功能描述或問題]
user-invokable: true
---

# Go Bridge 開發指南

## 何時使用此 Skill

使用此 Skill 當您需要：
- 建立新的 Go CLI 命令並整合到 Python
- 修改現有的 Python ↔ Go 橋接功能
- 處理 JSON 序列化/反序列化問題
- 實作 fallback 機制
- 除錯 subprocess 呼叫問題

## 核心概念

### 架構設計

```
Python 層 (業務邏輯)
    ↓
GoBridge (src/services/go_bridge.py)
    ↓
subprocess 呼叫
    ↓
classifier.exe (Go CLI)
    ↓
Go 套件 (pkg/*)
```

### 關鍵原則

1. **JSON 一致性**: Python 和 Go 的 JSON 結構必須完全一致
2. **錯誤處理**: Go CLI 必須返回結構化錯誤
3. **Fallback 機制**: 永遠保留 Python 實作作為備援
4. **測試策略**: Go 單元測試 + Python 整合測試

## 開發新功能的標準流程

### 步驟 1: 實作 Go 功能

1. **建立 Go 套件**
   ```bash
   mkdir -p pkg/new-feature
   touch pkg/new-feature/feature.go
   touch pkg/new-feature/feature_test.go
   ```

2. **撰寫核心邏輯**
   參考 [new-go-command.go](./examples/new-go-command.go)

3. **撰寫單元測試**
   ```bash
   go test ./pkg/new-feature -v
   ```

### 步驟 2: 新增 CLI 命令

1. **編輯 cmd/scanner/main.go**
   ```go
   // 新增命令處理
   case "new-command":
       result := handleNewCommand(args)
       outputJSON(result)
   ```

2. **建構測試**
   ```bash
   go build -o classifier.exe ./cmd/scanner
   ./classifier.exe new-command --help
   ```

### 步驟 3: 建立 Python 橋接

1. **編輯 src/services/go_bridge.py**
   ```python
   def new_feature(self, params):
       """新功能描述"""
       if not self.is_available:
           return self._python_fallback(params)
       
       result = self._run_command([
           "new-command",
           "--param", params
       ])
       return self._parse_result(result)
   ```

2. **實作 Python fallback**
   ```python
   def _python_fallback(self, params):
       # Python 實作版本
       pass
   ```

### 步驟 4: 測試整合

1. **建立整合測試**
   參考 [test-integration.py](./examples/test-integration.py)

2. **執行測試**
   ```bash
   python test_go_db_bridge.py
   pytest tests/test_go_bridge.py -v
   ```

## JSON 結構規範

### Go 輸出格式

```go
type Result struct {
    Success bool        `json:"success"`
    Data    interface{} `json:"data,omitempty"`
    Error   string      `json:"error,omitempty"`
}
```

### Python 解析格式

```python
{
    "success": True,
    "data": {...},
    "error": None
}
```

**重要**: 欄位名稱必須完全一致（包括大小寫）

## 常見問題與解決方法

### 問題 1: JSON 解析失敗

**症狀**: `json.decoder.JSONDecodeError`

**解決方法**:
1. 檢查 Go 是否正確輸出 JSON
   ```bash
   ./classifier.exe command | python -m json.tool
   ```
2. 確認沒有額外的 stdout 輸出（如 debug 訊息）
3. 使用 `json.Marshal` 而非手動拼接字串

### 問題 2: subprocess 呼叫超時

**症狀**: `TimeoutExpired`

**解決方法**:
1. 增加 timeout 時間
2. 檢查 Go 程式是否有無限迴圈
3. 使用 `--verbose` 模式除錯

### 問題 3: Fallback 未觸發

**症狀**: Go 不可用時程式崩潰

**解決方法**:
1. 檢查 `is_available` 屬性
2. 確保 Python 實作存在
3. 加入 try-except 保護

## 效能基準

| 操作 | Python | Go | 提升倍數 |
|------|--------|----|---------|
| 掃描 1000 檔案 | ~2.5s | ~0.15s | 16.7x |
| 批次移動 100 檔 | ~3.0s | ~0.3s | 10x |
| 番號提取 | ~100μs | ~5μs | 20x |

## 範例程式碼

### 完整範例：新增掃描功能

參考檔案：
- Go 實作: [examples/new-go-command.go](./examples/new-go-command.go)
- Python 呼叫: [examples/python-bridge-call.py](./examples/python-bridge-call.py)
- 整合測試: [examples/test-integration.py](./examples/test-integration.py)

## 檢查清單

建立新功能前確認：
- [ ] Go 單元測試通過
- [ ] Go CLI 命令可獨立執行
- [ ] JSON 結構與 Python 一致
- [ ] Python fallback 實作完成
- [ ] 整合測試通過
- [ ] 文件已更新（CLAUDE.md）

## 相關資源

- [GoBridge 實作](../../src/services/go_bridge.py)
- [Go CLI 主程式](../../cmd/scanner/main.go)
- [專案架構文件](../../CLAUDE.md)
```

#### 驗收標準
- ✅ SKILL.md 包含完整指令
- ✅ 提供至少 3 個範例檔案
- ✅ 提供至少 2 個範本檔案
- ✅ Skill 可透過 `/go-bridge-development` 呼叫
- ✅ 在 `.github/skills/` 和 `.claude/skills/` 都有副本

#### 相關檔案
- `.github/skills/go-bridge-development/SKILL.md`
- `src/services/go_bridge.py`
- `cmd/scanner/main.go`
- `pkg/*`

---

### Task 1.2: 建立 database-operations Skill

**優先級**: 🔴 P0 (最高)  
**預估時間**: 1-2 小時  
**狀態**: ⏳ 待執行  
**重要性**: ⭐⭐⭐⭐⭐ 自製系統需標準化  

#### 為什麼重要
- ✅ 自製增量 JSON 資料庫有獨特設計（Journal 機制）
- ✅ Python 和 Go 雙重實作需要保持一致
- ✅ 錯誤操作可能導致資料損壞

#### 執行步驟

1. **建立目錄結構**
   ```bash
   mkdir -p .github/skills/database-operations/{examples,scripts}
   ```

2. **建立 SKILL.md**
   內容包含：
   - IncrementalJSONDB 使用指南
   - Journal 合併時機判斷
   - Go 加速資料庫 API
   - 常見錯誤和解決方法

3. **建立範例檔案**
   - [ ] `examples/python-db-usage.py`
   - [ ] `examples/go-db-usage.go`
   - [ ] `examples/journal-management.py`

4. **建立工具腳本**
   - [ ] `scripts/compact-database.py`
   - [ ] `scripts/backup-database.sh`
   - [ ] `scripts/verify-integrity.py`

#### SKILL.md 關鍵章節

```yaml
---
name: database-operations
description: 增量 JSON 資料庫操作指南 - 涵蓋 IncrementalJSONDB、Journal 機制、資料庫合併、Go 加速 API。使用於資料庫 CRUD 操作、效能優化、或資料維護時。
---

# 資料庫操作指南

## 核心概念

### 增量資料庫架構

```
data/json_db/
├── data.json       # 主資料檔案
├── data.journal    # 增量變更日誌
└── data.index      # Dirty keys 索引
```

### Journal 機制優勢

- ✅ 寫入速度提升 40 倍
- ✅ Dirty tracking 減少 I/O
- ✅ 自動合併機制

## 使用指南
[詳細內容...]
```

#### 驗收標準
- ✅ SKILL.md 包含完整操作指南
- ✅ 提供 Python 和 Go 範例
- ✅ 包含資料庫維護腳本
- ✅ 說明 Journal 合併時機
- ✅ Skill 可正確載入

---

### Task 1.3: 建立 testing-validation Skill

**優先級**: 🔴 P0 (最高)  
**預估時間**: 1-2 小時  
**狀態**: ⏳ 待執行  
**重要性**: ⭐⭐⭐⭐☆ 標準化測試流程  

#### 為什麼重要
- ✅ Python pytest 和 Go testing 雙重測試體系
- ✅ 需要特定的測試順序和驗證流程
- ✅ 涉及單元測試、整合測試、效能測試

#### 執行步驟

1. **建立目錄結構**
   ```bash
   mkdir -p .github/skills/testing-validation/{scripts,checklists}
   ```

2. **建立 SKILL.md**
   內容包含：
   - Python pytest 測試指南
   - Go 測試執行流程
   - 整合測試策略
   - 測試覆蓋率目標

3. **建立測試腳本**
   - [ ] `scripts/run-all-tests.sh`
   - [ ] `scripts/test-python.sh`
   - [ ] `scripts/test-go.sh`
   - [ ] `scripts/coverage-report.sh`

4. **建立檢查清單**
   - [ ] `checklists/pre-commit.md`
   - [ ] `checklists/pre-release.md`

#### 驗收標準
- ✅ SKILL.md 包含完整測試指南
- ✅ 提供自動化測試腳本
- ✅ 包含測試檢查清單
- ✅ 說明測試順序和依賴

---

## 🌟 階段 2：中優先級 Skills（本月內完成）

### Task 2.1: 建立 web-scraping-guide Skill

**優先級**: 🟡 P1 (中)  
**預估時間**: 1-2 小時  
**狀態**: ⏳ 待執行  

#### 執行步驟
1. 建立目錄結構
2. 撰寫爬蟲開發指南
3. 提供編碼處理範例
4. 包含速率限制器配置

#### 驗收標準
- ✅ 涵蓋 AV-WIKI、chiba-f、JAVDB 三個來源
- ✅ 包含日文編碼處理最佳實踐
- ✅ 提供級聯搜尋整合範例

---

### Task 2.2: 建立 gui-development Skill

**優先級**: 🟡 P1 (中)  
**預估時間**: 1-2 小時  
**狀態**: ⏳ 待執行  

#### 執行步驟
1. 建立目錄結構
2. 撰寫 Tkinter 開發規範
3. 提供執行緒安全範例
4. 包含 UI 更新模式指南

#### 驗收標準
- ✅ 說明背景執行緒使用規範
- ✅ 提供 `root.after()` 正確用法
- ✅ 包含進度回報實作範例

---

### Task 2.3: 建立 deployment-release Skill

**優先級**: 🟡 P1 (中)  
**預估時間**: 1-2 小時  
**狀態**: ⏳ 待執行  

#### 執行步驟
1. 建立目錄結構
2. 撰寫建構與部署指南
3. 提供打包腳本
4. 包含發布檢查清單

#### 驗收標準
- ✅ 涵蓋 classifier.exe 建構步驟
- ✅ 包含 Python 應用程式打包
- ✅ 提供版本更新流程

---

## 💡 階段 3：低優先級 Skills（有空時完成）

### Task 3.1: 建立 performance-optimization Skill

**優先級**: 🟢 P2 (低)  
**預估時間**: 1-2 小時  
**狀態**: ⏳ 待執行  

#### 執行步驟
1. 建立目錄結構
2. 撰寫效能分析指南
3. 提供基準測試腳本
4. 包含優化策略

---

### Task 3.2: 建立 documentation-guide Skill

**優先級**: 🟢 P2 (低)  
**預估時間**: 1 小時  
**狀態**: ⏳ 待執行  

#### 執行步驟
1. 建立目錄結構
2. 撰寫文件撰寫規範
3. 提供 Markdown 範本
4. 包含術語對照表

---

## 📊 進度追蹤

### 完成度統計

```
階段 0: 緊急修正    [ ] 0/1 (0%)
階段 1: 高優先級    [ ] 0/3 (0%)
階段 2: 中優先級    [ ] 0/3 (0%)
階段 3: 低優先級    [ ] 0/2 (0%)
─────────────────────────────────
總計:              [ ] 0/9 (0%)
```

### 時間投入

```
已投入時間: 0 小時
預估剩餘: 9-14 小時
─────────────────────
總預估: 9-14 小時
```

---

## ✅ 總體檢查清單

### 前置準備
- [ ] 閱讀 [VS Code Agent Skills 官方指南](./VSCODE_AGENT_SKILLS_GUIDE.md)
- [ ] 閱讀 [Skills 快速參考卡](./VSCODE_SKILLS_QUICK_REFERENCE.md)
- [ ] 閱讀 [Skills 分析報告](./SKILLS_ANALYSIS_REPORT.md)

### 每個 Skill 的標準流程
- [ ] 建立目錄結構（`.github/skills/` 和 `.claude/skills/`）
- [ ] 撰寫 SKILL.md（包含正確的 YAML Front Matter）
- [ ] 新增範例檔案（至少 2 個）
- [ ] 測試斜線命令（在 VS Code Chat 輸入 `/skill-name`）
- [ ] 測試自動載入（發送相關提示）
- [ ] 更新專案文件（README.md 或 CLAUDE.md）

### 最終驗證
- [ ] 所有 Skills 在 `/` 選單中可見
- [ ] 所有 Skills 可正確載入
- [ ] 所有範例程式碼可執行
- [ ] 文件已同步更新

---

## 🎯 成功指標

完成所有任務後應達到：

- ✅ 8-9 個專業 Skills 可用
- ✅ 開發效率提升 30% 以上
- ✅ 新人上手時間縮短 50%
- ✅ 標準化開發流程
- ✅ 減少重複說明

---

## 📝 更新記錄

| 日期 | 任務 | 狀態 | 備註 |
|------|------|------|------|
| 2026-02-17 | 建立任務清單 | ✅ 完成 | 初始版本 |
| - | - | - | - |

---

## 🔗 相關文件

- 📖 [VS Code Agent Skills 官方指南](./VSCODE_AGENT_SKILLS_GUIDE.md)
- ⚡ [Skills 快速參考卡](./VSCODE_SKILLS_QUICK_REFERENCE.md)
- 📊 [Skills 分析報告](./SKILLS_ANALYSIS_REPORT.md)
- 📚 [專案開發指引](../CLAUDE.md)

---

**任務清單版本**: 1.0  
**最後更新**: 2026-02-17  
**維護者**: Development Team
