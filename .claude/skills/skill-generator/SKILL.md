---
name: skill-generator  
description: 跨平台 AI Agent 技能生成器 - 當用戶提到「建立技能」、「創建 skill」、「生成技能」或類似需求時自動啟用。基於 Anthropic Agent Skills 開放標準，自動建立符合多平台規範的技能。支援 Claude Code、GitHub Copilot、VS Code、Copilot CLI、Codex CLI 等平台
context: default
allowed-tools: ["create", "edit", "view", "powershell"]  
disable-model-invocation: false
user-invocable: true
auto-trigger: true
trigger-phrases: ["建立技能", "創建技能", "建立 skill", "創建 skill", "生成技能", "製作技能", "寫一個技能", "協助建立", "幫我建立", "想要一個技能"]
version: "2.0"
platforms: ["claude-code", "github-copilot", "vs-code", "copilot-cli", "codex-cli"]
---

# 跨平台 AI Agent 技能生成器 🌐

**Skill Generator v2.0** 是一個進階 meta-skill，基於 **Anthropic Agent Skills 開放標準**，專門建立可跨多個 AI 工具平台使用的技能。

## 🚀 多平台支援矩陣

| 平台 | 目錄位置 | 功能支援 | 相容性 |
|------|----------|----------|--------|
| **Claude Code** | `.claude/skills/` | 完整功能 (鉤子、子代理) | ✅ 100% |
| **GitHub Copilot Chat** | `.github/skills/` `.claude/skills/` | 基礎技能 | ✅ 基礎 |
| **VS Code Insiders** | `.claude/skills/` `.github/skills/` | 基礎技能 | ✅ 基礎 |
| **Copilot CLI** | `~/.copilot/skills/` | 基礎技能 | ✅ 基礎 |
| **Codex CLI** | `~/.codex/skills/` | 基礎技能 | ✅ 基礎 |
| **Gemini CLI** | 不支援 | - | ❌ 無 |

### 📊 功能相容性對比
- **基礎功能**: YAML 前置資料 + Markdown 內容 (所有平台支援)
- **進階功能**: 僅 Claude Code 支援的鉤子、子代理、動態上下文
- **智能轉換**: 自動移除進階功能以確保跨平台相容性

## 🎯 自然語言觸發

**Skill Generator v2.0** 支援自然語言觸發，無需使用 "/" 指令！

### 🗣️ 觸發方式
當您在對話中提到以下關鍵詞時，AI 會自動使用此技能：

**中文觸發詞**:
- 「建立技能」、「創建技能」、「生成技能」、「製作技能」
- 「建立 skill」、「創建 skill」、「寫一個技能」
- 「協助建立」、「幫我建立」、「想要一個技能」

**英文觸發詞**:
- "create skill", "generate skill", "build skill"
- "make a skill", "help me create", "need a skill"

### 💬 範例對話
```
用戶: "請建立一個技能，幫我用 fd 和 rg 搜尋程式碼"
AI: 🛠️ 偵測到技能建立需求，啟用 Skill Generator...

用戶: "我想要一個 API 文檔助手技能"  
AI: 📝 正在生成跨平台 API 文檔技能...

用戶: "協助建立 Git 工作流程技能"
AI: 🔧 開始建立 Git 工作流程管理技能...
```

## 🛠️ 使用方式 (兩種模式)

### 模式 1: 自然語言 (推薦 ⭐)
直接在對話中描述需求：
```
"幫我建立一個程式碼搜尋技能，使用 fd 和 rg 工具"
"創建一個多平台相容的 API 文檔助手"  
"我需要一個 Git 提交檢查技能"
```

### 模式 2: 傳統指令
```bash
/skill-generator create [skill-name] [skill-type] [description] [target-platform]
/skill-generator deploy [skill-name] [platforms...]
/skill-generator validate [skill-path] [platform-check]
```

### 平台特定部署
```bash
# 部署到 Claude Code
/skill-generator deploy my-skill claude-code

# 部署到 GitHub Copilot  
/skill-generator deploy my-skill github-copilot

# 部署到多平台
/skill-generator deploy my-skill claude-code,github-copilot,codex-cli

# 全平台部署
/skill-generator deploy my-skill all
```

### 快速建立範例
```bash
# Claude Code 專用技能
/skill-generator create code-analyzer analyzer "智能程式碼分析" claude-code

# GitHub Copilot 相容技能  
/skill-generator create git-helper task "Git 工作流程助手" github-copilot

# 跨平台通用技能
/skill-generator create api-docs reference "API 文檔助手" cross-platform
```

## 📋 平台特性對比

| 功能特性 | Claude Code | GitHub Copilot | Codex CLI | Agent Skills 標準 |
|----------|-------------|----------------|-----------|-------------------|
| 基礎 YAML + MD | ✅ | ✅ | ✅ | ✅ |
| 子代理執行 | ✅ | ❌ | ❌ | ❌ |
| 鉤子系統 | ✅ | ❌ | ❌ | ❌ |
| 動態上下文 | ✅ | ❌ | ❌ | ❌ |
| 工具權限控制 | ✅ | ✅ | ✅ | ✅ |
| 參數傳遞 | ✅ | ✅ | ✅ | ✅ |

## 🎨 技能範本類型

### 1. 跨平台相容範本 (推薦)
完全相容所有支援 Agent Skills 標準的平台：
```yaml
---
name: universal-skill
description: 通用技能描述
---

# 通用技能

適用於所有平台的基本技能結構。

## 使用方式
$ARGUMENTS

## 範例
- 範例 1
- 範例 2
```

### 2. Claude Code 增強範本
包含 Claude Code 特有功能：
```yaml
---
name: enhanced-skill  
description: Claude Code 增強技能
context: fork
agent: Explore
allowed-tools: Read, Grep
hooks:
  PostToolUse:
    - matcher: "Edit"
      hooks:
        - type: command
          command: "echo 'File edited'"
---

# Claude Code 增強技能

使用 Claude Code 特有的進階功能。
```

### 3. GitHub Copilot 最佳化範本
針對 Copilot 使用習慣最佳化：
```yaml
---
name: copilot-optimized
description: GitHub Copilot 最佳化技能，專注於程式碼生成和修復
---

# GitHub Copilot 技能

## 程式碼建議
當使用者請求 $ARGUMENTS 時：

1. 分析程式碼上下文
2. 提供最佳實踐建議  
3. 生成可執行的程式碼範例
4. 解釋實作原理

## GitHub 整合
- 支援 Pull Request 分析
- 程式碼審查建議
- Commit 訊息生成
```

## 🔧 生成器功能增強

### 多平台部署管理
```bash
# 檢查平台相容性
/skill-generator check-compatibility my-skill

# 轉換現有技能到其他平台
/skill-generator convert my-skill --from claude-code --to github-copilot

# 同步技能到多個位置
/skill-generator sync my-skill --platforms all
```

### 平台特定最佳化
```bash
# 為 Claude Code 添加進階功能
/skill-generator enhance my-skill --add-hooks --add-subagent

# 為 GitHub Copilot 最佳化
/skill-generator optimize my-skill --for github-copilot

# 移除平台特定功能以提升相容性
/skill-generator strip my-skill --make-universal
```

### 批次操作
```bash
# 批次部署專案中的所有技能
/skill-generator batch-deploy .claude/skills/ --to github-copilot

# 批次驗證多平台相容性
/skill-generator batch-validate .claude/skills/ --check-all-platforms
```

## 📁 智能目錄管理

### 自動目錄選擇
根據目標平台自動選擇適當的目錄：

```bash
# 自動偵測並部署到正確位置
/skill-generator auto-deploy my-skill

# 平台映射
claude-code      → .claude/skills/
github-copilot   → .github/skills/ (專案) 或 ~/.copilot/skills/ (全域)
codex-cli        → ~/.codex/skills/
vs-code          → .claude/skills/ 或 .github/skills/
```

### 目錄結構標準化
```
# 專案級技能
project/
├── .claude/skills/          # Claude Code
├── .github/skills/          # GitHub Copilot (專案級)
└── skills/                  # 通用備份

# 全域技能  
~/.claude/skills/            # Claude Code 全域
~/.copilot/skills/           # GitHub Copilot CLI
~/.codex/skills/             # Codex CLI
```

## 🎯 平台特定功能

### Claude Code 專屬功能
```bash
# 建立子代理技能
/skill-generator create research-agent analyzer "深度研究" claude-code --subagent

# 添加鉤子功能
/skill-generator create auto-formatter task "自動格式化" claude-code --hooks

# 動態上下文技能
/skill-generator create git-status helper "Git 狀態" claude-code --dynamic-context
```

### GitHub Copilot 整合
```bash
# Copilot Chat 最佳化
/skill-generator create chat-helper reference "聊天助手" github-copilot

# Copilot CLI 工具
/skill-generator create cli-wrapper task "CLI 包裝器" github-copilot --cli-mode
```

### 跨平台移植
```bash
# 從 Claude Code 移植到 Copilot
/skill-generator port claude-skill --from claude-code --to github-copilot

# 創建通用版本
/skill-generator universalize advanced-skill --strip-features
```

## 📊 相容性報告

### 生成相容性分析
```bash
/skill-generator analyze-compatibility ./skills/

# 範例輸出
┌─────────────────┬─────────────┬──────────────┬───────────┬──────────┐
│ 技能名稱        │ Claude Code │ GitHub Copilot │ Codex CLI │ 相容評分 │
├─────────────────┼─────────────┼──────────────┼───────────┼──────────┤
│ universal-helper│     ✅      │      ✅       │    ✅     │   100%   │
│ enhanced-analyzer│     ✅      │      ⚠️       │    ❌     │    33%   │
│ basic-formatter │     ✅      │      ✅       │    ✅     │   100%   │
└─────────────────┴─────────────┴──────────────┴───────────┴──────────┘

建議: enhanced-analyzer 包含 Claude Code 特有功能，需要移除進階特性以提升相容性
```

## 🔍 最佳實踐指南

### 1. 跨平台設計原則
- 使用最小公約數功能集
- 避免平台特有的進階功能
- 提供清楚的功能降級方案
- 維護平台特定的增強版本

### 2. 技能命名規範
```bash
# 好的命名
code-formatter          # 清楚、簡潔
api-documentation-helper # 描述性
git-workflow-assistant   # 明確用途

# 避免的命名  
my-awesome-skill        # 不描述性
helper                  # 太通用
code_formatter          # 使用底線
```

### 3. 描述撰寫最佳實踐
```yaml
# ✅ 好的描述
description: 自動分析 JavaScript 程式碼品質並提供 ESLint 規則建議，支援 React 和 Node.js 專案

# ❌ 不好的描述
description: 程式碼助手
```

## 📚 支援資源

### 更新的支援檔案
- **[templates/multi-platform-templates.md](templates/multi-platform-templates.md)**: 多平台範本庫
- **[examples/cross-platform-examples.md](examples/cross-platform-examples.md)**: 跨平台使用範例  
- **[scripts/platform-deploy.sh](scripts/platform-deploy.sh)**: 多平台部署腳本
- **[compatibility-guide.md](compatibility-guide.md)**: 平台相容性指南

### 官方資源連結
- [Agent Skills 標準](https://agentskills.io)
- [Anthropic 官方技能庫](https://github.com/anthropics/skills/)
- [Claude Code 技能文檔](https://code.claude.com/docs/zh-TW/skills)

---

**使用提示**: 
1. 優先建立跨平台相容的技能以最大化可用性
2. 使用 `/skill-generator check-compatibility` 確保平台相容性  
3. 根據需要為特定平台創建增強版本
4. 定期同步技能到所有目標平台

**新功能**: 現在支援 Claude Code、GitHub Copilot、VS Code Insiders、Codex CLI 等多種 AI 工具，一次建立，多平台使用！

## 📋 建立新技能流程

### 快速建立
```bash
/skill-generator create my-skill task "部署應用程式到生產環境"
```

### 完整建立流程
```bash
/skill-generator create react-helper analyzer "React 專案程式碼分析和最佳化建議" --context=fork --tools="Read,Edit,Bash"
```

### 互動式建立
```bash
/skill-generator interactive
```

## 🎨 技能範本類型

### 1. Reference Content 範本
適用於提供背景知識的技能：
```yaml
---
name: coding-standards  
description: 專案程式碼風格和最佳實踐指南
user-invocable: false  # 只供 Claude 自動載入
---

# 程式碼標準指南

當撰寫程式碼時：
- 使用一致的命名規範
- 遵循專案既有的架構模式
- 包含適當的錯誤處理
```

### 2. Task Content 範本  
適用於特定動作執行的技能：
```yaml
---
name: deploy-app
description: 部署應用程式到指定環境
disable-model-invocation: true  # 防止自動觸發
context: fork
allowed-tools: Bash
---

# 應用程式部署流程

部署 $ARGUMENTS 到指定環境：

1. 檢查部署前提條件
2. 執行建置流程
3. 執行部署
4. 驗證部署結果
```

### 3. Hybrid 範本
結合參考和任務功能：
```yaml
---
name: api-manager
description: API 開發最佳實踐和部署管理
allowed-tools: Read, Write, Bash
---

# API 管理技能

## API 設計原則
- RESTful 命名規範
- 一致的錯誤格式
- 適當的 HTTP 狀態碼

## 部署 API
執行 API 部署：$ARGUMENTS
```

## 🔧 生成的技能結構

執行 skill-generator 後會建立以下結構：
```
my-skill/
├── SKILL.md              # 主要技能檔案（必需）
├── examples/             # 使用範例
│   └── usage-guide.md    
├── templates/            # 程式碼範本
│   └── code-templates.md
└── scripts/              # 輔助腳本
    └── validate.sh
```

## 📝 自動生成內容

### SKILL.md 內容架構
1. **YAML 前置資料**：技能元資料和配置
2. **技能描述**：功能說明和使用場景  
3. **使用方式**：命令語法和參數說明
4. **範例展示**：實際使用案例
5. **支援檔案**：相關資源連結

### 範例檔案內容
- **usage-guide.md**：詳細使用說明和案例
- **code-templates.md**：可重用的程式碼範本
- **validate.sh**：技能驗證腳本

## 🎯 進階功能

### 動態字串替換
自動設定適當的替換變數：
```markdown
處理使用者請求：$ARGUMENTS
會話ID：${CLAUDE_SESSION_ID}
專案路徑：${PROJECT_DIR}
```

### 鉤子整合
為需要的技能自動添加鉤子配置：
```yaml
hooks:
  PostToolUse:
    - matcher: "Edit|Write"
      hooks:
        - type: command
          command: "prettier --write $file_path"
```

### 子代理支援
為複雜任務設定子代理執行：
```yaml
context: fork
agent: Explore  # 或自訂代理
```

## 📋 建立範例

### 範例 1：建立程式碼分析技能
```bash
/skill-generator create code-analyzer analyzer "智能程式碼分析和品質檢查"
```

**生成結果**：
- ✅ 建立 `code-analyzer/` 目錄
- ✅ 生成符合規範的 `SKILL.md`  
- ✅ 包含程式碼分析相關的範例和範本
- ✅ 設定適當的工具權限（Read, Grep, Bash）

### 範例 2：建立部署技能
```bash
/skill-generator create auto-deploy task "自動化應用程式部署流程" --disable-auto-invoke --tools="Bash"
```

**生成結果**：
- ✅ 設定 `disable-model-invocation: true`
- ✅ 限制工具使用為 Bash
- ✅ 包含部署腳本範本
- ✅ 生成安全檢查清單

### 範例 3：建立參考文檔技能
```bash  
/skill-generator create project-conventions reference "專案編碼規範和最佳實踐" --user-invocable=false
```

**生成結果**：
- ✅ 設定為背景知識型技能
- ✅ 不顯示在 `/` 選單中
- ✅ 包含編碼規範範本
- ✅ 自動載入到相關上下文

## 🔍 技能驗證功能

### 驗證現有技能
```bash
/skill-generator validate ./path/to/skill
```

**檢查項目**：
- ✅ SKILL.md 檔案存在且格式正確
- ✅ YAML 前置資料完整性
- ✅ 技能名稱符合命名規範
- ✅ 描述和文檔品質
- ✅ 支援檔案一致性

### 自動修復建議
```bash
/skill-generator fix ./path/to/skill
```

## 📚 支援檔案

### [templates/skill-templates.md](templates/skill-templates.md)
包含各種技能類型的完整範本，可直接複製使用。

### [examples/generated-examples.md](examples/generated-examples.md)  
展示使用 skill-generator 建立的實際技能範例。

### [scripts/skill-validator.sh](scripts/skill-validator.sh)
技能格式驗證和品質檢查腳本。

## 🎨 最佳實踐建議

### 1. 命名規範
- 使用小寫字母和連字號
- 名稱要具描述性但簡潔
- 避免過於通用的名稱

### 2. 描述撰寫
- 清楚說明技能功能和使用時機
- 包含具體的使用場景
- 避免模糊或過於技術性的描述

### 3. 工具權限設定
- 只授予必要的工具權限
- 對於高風險操作使用 `disable-model-invocation: true`
- 考慮使用子代理進行隔離執行

### 4. 支援檔案組織
- 保持 SKILL.md 簡潔，詳細內容放在支援檔案
- 使用清楚的檔案命名
- 從主檔案適當連結到支援檔案

---

## 💡 智能檢測實作

### 🧠 觸發詞檢測機制
當 AI 在對話中檢測到以下模式時，會自動啟用技能生成流程：

**檢測模式**:
```regex
(建立|創建|生成|製作|寫.*技能|skill|協助.*建立|幫.*建立|想要.*技能|需要.*技能)
```

**上下文分析**:
- 檢測是否提及特定工具名稱 (fd, rg, grep, etc.)
- 分析功能需求 (搜尋、分析、部署、格式化等)  
- 判斷目標平台 (如果有提及)

### 🎯 自動流程
1. **需求解析**: 分析用戶描述，提取技能需求
2. **類型推定**: 根據功能判斷技能類型 (task/reference/analyzer/hybrid)
3. **平台選擇**: 預設建立跨平台相容版本
4. **範本選取**: 選擇最適合的範本
5. **智能生成**: 自動填充內容和配置
6. **驗證部署**: 檢查格式並部署到指定位置

### 📋 範例自動處理

**輸入**: "請建立一個技能，幫我用 fd 和 rg 搜尋程式碼"

**AI 自動處理**:
```yaml
# 自動檢測結果
detected_intent: create_skill
skill_type: task  # 基於 "搜尋" 動作
tools_mentioned: ["fd", "rg"]
target_function: "程式碼搜尋"
platform: cross-platform  # 預設

# 自動生成配置
skill_name: code-search-tool
description: 使用 fd 和 rg 工具進行智能程式碼搜尋和定位
allowed_tools: ["powershell", "view", "grep", "glob"]
```

**輸入**: "我想要一個 Git 工作流程助手技能"

**AI 自動處理**:
```yaml
detected_intent: create_skill  
skill_type: hybrid  # Git 包含參考和任務
tools_mentioned: ["git"]
target_function: "Git 工作流程管理"
platform: cross-platform

skill_name: git-workflow-assistant
description: Git 工作流程管理和最佳實踐指導
allowed_tools: ["powershell", "view", "edit"]
```

## 🤖 自動生成演示

使用自然語言時的完整流程：

### 階段 1: 需求理解
```
用戶: "協助建立程式碼質量檢查技能"
AI: 🔍 正在分析需求...
   - 檢測到: 建立技能請求
   - 功能: 程式碼質量檢查  
   - 類型: analyzer (分析類)
   - 工具: 程式碼分析相關
```

### 階段 2: 智能設計  
```
AI: 📝 正在設計技能架構...
   - 技能名稱: code-quality-checker
   - 支援語言: JavaScript, Python, Go, Java
   - 檢查項目: 語法、風格、複雜度、安全性
   - 跨平台相容: ✅
```

### 階段 3: 自動實作
```
AI: ⚙️ 正在生成技能檔案...
   ✅ SKILL.md (主要技能檔案)
   ✅ examples/usage-examples.md  
   ✅ templates/check-templates.md
   ✅ 跨平台部署配置
```

### 階段 4: 驗證部署
```
AI: 🚀 正在驗證和部署...
   ✅ YAML 格式驗證通過
   ✅ Agent Skills 標準合規
   ✅ 跨平台相容性檢查通過
   ✅ 部署到 .claude/skills/code-quality-checker/
```

---

**重要**: 這個智能檢測系統讓您可以用自然語言快速建立技能，無需記憶複雜的指令語法！
