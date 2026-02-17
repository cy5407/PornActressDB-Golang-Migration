# 跨平台 AI Agent 技能範本庫 🌐

基於 **Anthropic Agent Skills 開放標準** 和多平台支援現況的完整範本庫。

## 📊 平台支援矩陣

| 平台 | 目錄位置 | 基礎功能 | 進階功能 | 部署方式 |
|------|----------|----------|----------|----------|
| **Claude Code** | `.claude/skills/` | ✅ | ✅ 鉤子、子代理、動態上下文 | 直接部署 |
| **GitHub Copilot** | `.github/skills/` `.claude/skills/` | ✅ | ❌ 只支援基礎標準 | 多位置同步 |  
| **VS Code Insiders** | `.claude/skills/` `.github/skills/` | ✅ | ❌ 基礎 Agent Skills | 雙位置部署 |
| **Copilot CLI** | `~/.copilot/skills/` | ✅ | ❌ 基礎 Agent Skills | 全域安裝 |
| **Codex CLI** | `~/.codex/skills/` | ✅ | ❌ 基礎 Agent Skills | 全域安裝 |

### 🔧 相容性策略
- **通用基礎**: 所有平台支援 YAML 前置資料 + Markdown 內容
- **平台特有**: Claude Code 獨有的進階功能 (鉤子、子代理)
- **智能降級**: 自動移除不相容功能以提升跨平台可用性

## 🌐 跨平台通用範本

### 基礎通用技能範本
適用於所有支援 Agent Skills 標準的平台：

```yaml
---
name: ${SKILL_NAME}
description: ${SKILL_DESCRIPTION}
---

# ${SKILL_TITLE}

${SKILL_CONTENT}

## 使用方式
執行任務：$ARGUMENTS

## 範例
- 範例使用 1
- 範例使用 2

## 指導原則
- 原則 1
- 原則 2

## 支援平台
- ✅ Claude Code
- ✅ GitHub Copilot Chat  
- ✅ VS Code Insiders
- ✅ Copilot CLI
- ✅ Codex CLI
```

### API 文檔助手範本
```yaml
---
name: api-docs-helper
description: 協助建立和維護 API 文檔，支援多種格式和平台
---

# API 文檔助手

協助開發者建立標準化的 API 文檔。

## 支援格式
- OpenAPI/Swagger 3.0
- REST API 文檔
- GraphQL Schema
- JSON Schema

## 功能特性
- 自動生成 API 範例
- 驗證 API 規格正確性
- 產生互動式文檔
- 支援多語言程式碼範例

## 使用指南
建立 API 文檔：$ARGUMENTS

### 基本使用
1. 分析現有 API 端點
2. 生成標準化文檔結構
3. 添加使用範例和說明
4. 驗證文檔完整性

## 跨平台相容性
此技能設計為跨平台相容，可在任何支援 Agent Skills 的 AI 工具中使用。
```

### 程式碼審查助手範本
```yaml
---
name: code-reviewer
description: 智能程式碼審查助手，提供品質分析和改善建議
---

# 程式碼審查助手

## 審查範圍
分析程式碼：$ARGUMENTS

### 檢查項目
- **程式碼品質**: 可讀性、可維護性、效能
- **安全性**: 常見漏洞、安全最佳實踐
- **最佳實踐**: 設計模式、架構原則
- **測試覆蓋**: 測試完整性和品質

### 支援語言
- JavaScript/TypeScript
- Python  
- Go
- Java
- C#
- Rust

## 審查流程
1. 靜態程式碼分析
2. 架構和設計評估
3. 安全性檢查
4. 效能分析
5. 提供改善建議

## 輸出格式
- 結構化審查報告
- 優先級分類的問題列表
- 具體的修復建議
- 最佳實踐參考連結
```

---

## 🎯 平台特定範本

### Claude Code 進階範本

#### 子代理研究助手
```yaml
---
name: research-assistant
description: 深度程式碼庫研究和分析助手
context: fork
agent: Explore
---

# 研究助手

在隔離的 Explore 代理中執行深度研究：$ARGUMENTS

## 研究能力
- 大型程式碼庫分析
- 架構模式識別
- 依賴關係追蹤
- 最佳實踐發現

## 執行環境
- **隔離執行**: 在子代理中運行，不影響主對話
- **唯讀模式**: 安全分析，不修改檔案
- **深度探索**: 使用 Glob 和 Grep 進行全面搜索

## 回傳格式
研究結果會以結構化摘要形式返回主對話。

注意: 此技能僅在 Claude Code 中可用，使用了子代理功能。
```

#### 自動格式化器 (帶鉤子)
```yaml
---
name: auto-formatter  
description: 檔案編輯後自動執行程式碼格式化
allowed-tools: Bash
hooks:
  PostToolUse:
    - matcher: "Edit|Write"
      hooks:
        - type: command
          command: "scripts/format-code.sh"
---

# 自動格式化器

## 支援的格式化工具
- **JavaScript/TypeScript**: Prettier
- **Go**: gofmt + goimports
- **Python**: black + isort
- **Rust**: rustfmt
- **Java**: google-java-format

## 自動觸發
每次使用 Edit 或 Write 工具修改檔案後，會自動執行對應的格式化工具。

## 手動格式化
格式化特定檔案：$ARGUMENTS

```bash
# 格式化單一檔案
scripts/format-code.sh src/main.js

# 格式化整個目錄
scripts/format-code.sh src/
```

注意: 此技能使用 Claude Code 的鉤子功能，在其他平台中將作為普通格式化技能運行。
```

### GitHub Copilot 最佳化範本

#### Git 工作流程助手
```yaml
---
name: git-workflow-helper
description: GitHub Copilot 最佳化的 Git 工作流程助手，專注於程式碼協作
---

# Git 工作流程助手

專為 GitHub Copilot 和程式碼協作最佳化的 Git 助手。

## 核心功能
處理 Git 操作：$ARGUMENTS

### Pull Request 管理
- 分析 PR 變更範圍
- 生成描述性 PR 標題和說明
- 建議審查者和標籤
- 檢查合併衝突

### Commit 最佳實踐
- 生成符合 Conventional Commits 的訊息
- 分析變更影響範圍
- 建議適當的 commit 類型
- 驗證 commit 訊息格式

### 分支策略
- 建議分支命名規範
- 管理 feature/bugfix/hotfix 分支
- 自動化 rebase 和 merge 策略
- 清理過期分支

## GitHub 整合
- 讀取 GitHub Issues 內容
- 連結 commit 到相關 issues
- 生成 release notes
- 管理 GitHub Labels 和 Milestones

## 最佳實踐指導
遵循業界標準的 Git 工作流程，特別適合團隊協作環境。
```

#### 程式碼生成助手
```yaml
---
name: code-generator
description: GitHub Copilot 輔助的智能程式碼生成器
---

# 程式碼生成助手

與 GitHub Copilot 協同工作的程式碼生成助手。

## 生成任務
生成程式碼：$ARGUMENTS

### 支援的生成類型
- **API 端點**: REST/GraphQL API 實作
- **資料模型**: 類別、介面、結構體定義  
- **測試程式碼**: 單元測試、整合測試
- **配置檔案**: Docker、CI/CD、套件管理
- **文檔**: README、API 文檔、註解

### 語言框架支援
- **Frontend**: React, Vue, Angular, Svelte
- **Backend**: Express, FastAPI, Spring Boot, Gin
- **Mobile**: React Native, Flutter
- **DevOps**: Kubernetes, Docker, Terraform

## 生成策略
1. **上下文分析**: 分析專案結構和現有程式碼
2. **模式識別**: 識別專案的編碼風格和架構模式
3. **最佳實踐**: 應用業界標準和最佳實踐
4. **測試覆蓋**: 為生成的程式碼提供測試建議

## Copilot 協作
- 提供結構化的 Copilot 提示
- 利用 Copilot 的程式碼補全能力
- 整合 Copilot 的重構建議
- 結合 Copilot Chat 進行程式碼解釋
```

---

## 🔄 平台移植範本

### 通用化範本 (從 Claude Code 移植)
```yaml
---
name: universal-analyzer
description: 跨平台程式碼分析器，移除平台特定功能以確保通用性
# 注意: 原始版本包含 Claude Code 特有的 context: fork 功能
# 此版本已移除以確保跨平台相容性
---

# 通用程式碼分析器

跨平台相容的程式碼分析器。

## 分析功能
分析目標：$ARGUMENTS

### 靜態分析
- 語法檢查和風格驗證
- 複雜度分析
- 重複程式碼檢測
- 依賴關係分析

### 品質指標
- 可讀性評分
- 可維護性評估  
- 效能風險識別
- 安全性檢查

## 支援語言
- JavaScript/TypeScript
- Python
- Java
- Go
- C#

## 平台相容性
此技能已針對跨平台使用進行最佳化：
- 移除了 Claude Code 特有的子代理功能
- 使用標準的檔案操作而非進階工具
- 確保在所有支援 Agent Skills 的平台中可用

原始 Claude Code 版本的進階功能可透過平台特定版本取得。
```

### GitHub Copilot 移植範本
```yaml
---
name: copilot-compatible-formatter
description: 從 Claude Code 移植到 GitHub Copilot 的程式碼格式化器
# 原始版本使用 hooks 功能，此版本改為手動觸發模式
---

# Copilot 相容格式化器

適用於 GitHub Copilot 環境的程式碼格式化器。

## 格式化功能
格式化目標：$ARGUMENTS

### 支援工具
- **Prettier**: JavaScript/TypeScript/CSS/HTML
- **Black**: Python 程式碼格式化
- **gofmt**: Go 程式碼格式化  
- **rustfmt**: Rust 程式碼格式化

### 使用方式
```bash
# 格式化當前檔案
format current-file

# 格式化指定檔案
format src/main.js

# 格式化整個專案
format all
```

## 平台差異說明
- **Claude Code 版本**: 使用鉤子自動觸發格式化
- **GitHub Copilot 版本**: 手動觸發，整合到 Copilot Chat 中
- **通用版本**: 提供格式化指導和最佳實踐

## 整合建議
在 GitHub Copilot Chat 中可以說：
"使用 copilot-compatible-formatter 格式化這個 JavaScript 檔案"
```

---

## 📋 範本選擇指南

### 1. 跨平台優先
```yaml
# ✅ 推薦: 最大相容性
name: universal-helper
description: 跨平台通用助手

# ❌ 避免: 平台特定功能
context: fork  # Claude Code 專用
hooks: ...     # Claude Code 專用
```

### 2. 功能降級策略
```yaml
# 進階版本 (Claude Code)
name: advanced-analyzer
context: fork
agent: Explore

# 標準版本 (跨平台)  
name: standard-analyzer
# 移除 context 和 agent 配置
```

### 3. 平台特定最佳化
```yaml
# GitHub Copilot 版本
name: copilot-git-helper
description: 針對 GitHub Copilot Chat 最佳化的 Git 助手

# Claude Code 版本
name: claude-git-helper  
description: 使用 Claude Code 進階功能的 Git 助手
context: fork
```

### 4. 描述指導原則
```yaml
# ✅ 清楚說明平台支援
description: 跨平台程式碼分析器，支援 Claude Code、GitHub Copilot、VS Code

# ✅ 說明功能限制
description: 基礎版本不包含進階分析功能，完整版本請使用 Claude Code

# ❌ 模糊不清
description: 程式碼分析工具
```

---

## 🔧 範本客製化指南

### 變數替換
```yaml
${SKILL_NAME}        → 實際技能名稱
${SKILL_DESCRIPTION} → 技能功能描述  
${SKILL_TITLE}       → 顯示標題
${SKILL_CONTENT}     → 主要內容
${TARGET_PLATFORM}   → 目標平台名稱
${SUPPORTED_TOOLS}   → 支援的工具列表
```

### 平台標記
```yaml
# 平台相容性標記
## 支援平台
- ✅ Claude Code (完整功能)
- ✅ GitHub Copilot (基礎功能)  
- ✅ VS Code Insiders
- ❌ Codex CLI (不支援進階功能)
```

### 版本管理
```yaml
# 建議的版本命名
skill-name           # 通用版本
skill-name-claude    # Claude Code 增強版
skill-name-copilot   # GitHub Copilot 最佳化版
skill-name-lite      # 精簡相容版
```

這些範本確保你可以建立在多個 AI 平台上都能正常運作的技能，同時為特定平台提供最佳化版本。