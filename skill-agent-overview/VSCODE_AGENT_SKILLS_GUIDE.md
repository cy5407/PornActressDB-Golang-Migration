# VS Code Agent Skills 官方建置指南

> 📚 **官方文件來源**: https://code.visualstudio.com/docs/copilot/customization/agent-skills  
> 🌐 **Agent Skills 標準**: https://agentskills.io  
> 📅 **文件日期**: 2026-02-04  

---

## 📖 什麼是 Agent Skills？

**Agent Skills** 是包含指令、腳本和資源的資料夾，GitHub Copilot 可以在相關時載入以執行專業化任務。Agent Skills 是一個**開放標準**，可跨多個 AI 代理運作，包括：

- ✅ VS Code 中的 GitHub Copilot
- ✅ GitHub Copilot CLI
- ✅ GitHub Copilot Coding Agent

### 與 Custom Instructions 的差異

與主要定義編碼指南的[自訂指令](/docs/copilot/customization/custom-instructions)不同，Skills 能夠實現專業化能力和工作流程，可以包含腳本、範例和其他資源。您建立的 Skills 是可攜式的，可在任何支援 Skills 的代理中運作。

### Agent Skills 的主要優勢

1. ✅ **專業化 Copilot** - 為領域特定任務量身定制能力，無需重複上下文
2. ✅ **減少重複** - 建立一次，自動在所有對話中使用
3. ✅ **組合能力** - 結合多個 Skills 建構複雜工作流程
4. ✅ **高效載入** - 僅在需要時載入相關內容到上下文

---

## 🆚 Agent Skills vs Custom Instructions

雖然 Agent Skills 和 Custom Instructions 都有助於自訂 Copilot 的行為，但它們服務於不同目的：

| 特性 | Agent Skills | Custom Instructions |
|------|--------------|---------------------|
| **用途** | 教授專業化能力和工作流程 | 定義編碼標準和指南 |
| **可攜性** | 可跨 VS Code、Copilot CLI 和 Copilot Coding Agent 使用 | 僅限 VS Code 和 GitHub.com |
| **內容** | 指令、腳本、範例和資源 | 僅指令 |
| **範圍** | 任務特定，按需載入 | 始終應用（或透過 glob 模式） |
| **標準** | 開放標準 ([agentskills.io](https://agentskills.io)) | VS Code 特定 |

### 何時使用 Agent Skills

使用 Agent Skills 當您想要：

- ✅ 建立可跨不同 AI 工具運作的可重複使用能力
- ✅ 在指令旁包含腳本、範例或其他資源
- ✅ 與更廣泛的 AI 社群共享能力
- ✅ 定義專業化工作流程，如測試、除錯或部署流程

### 何時使用 Custom Instructions

使用 Custom Instructions 當您想要：

- ✅ 定義專案特定的編碼標準
- ✅ 設定語言或框架慣例
- ✅ 指定程式碼審查或提交訊息指南
- ✅ 使用 glob 模式根據檔案類型應用規則

---

## 🏗️ 建立 Skill

> 💡 **快速提示**: 在聊天輸入中輸入 `/skills` 快速開啟 **Configure Skills** 選單。

Skills 儲存在包含 `SKILL.md` 檔案的目錄中，該檔案定義 Skill 的行為。VS Code 支援兩種類型的 Skills：

| Skill 類型 | 位置 |
|-----------|------|
| **專案 Skills**（儲存在您的儲存庫中） | `.github/skills/`, `.claude/skills/`, `.agents/skills/` |
| **個人 Skills**（儲存在您的使用者設定檔中） | `~/.copilot/skills/`, `~/.claude/skills/`, `~/.agents/skills/` |

> 💡 **提示**: 您可以使用 `chat.agentSkillsLocations` 設定來配置 VS Code 搜尋 Skills 的其他位置。這對於跨專案共享 Skills 或將它們保存在中央位置很有用。

### 建立 Skill 的步驟

1. **建立目錄**  
   在工作區中建立 `.github/skills` 目錄。

2. **建立 Skill 子目錄**  
   為您的 Skill 建立一個子目錄。每個 Skill 應該有自己的目錄（例如 `.github/skills/webapp-testing`）。

3. **建立 SKILL.md 檔案**  
   在 Skill 目錄中建立一個具有以下結構的 `SKILL.md` 檔案：

   ```yaml
   ---
   name: skill-name
   description: Description of what the skill does and when to use it
   ---

   # Skill Instructions

   Your detailed instructions, guidelines, and examples go here...
   ```

4. **（可選）新增資源**  
   將腳本、範例或其他資源新增到您的 Skill 目錄。

   例如，用於測試 Web 應用程式的 Skill 可能包含：
   - `SKILL.md` - 執行測試的指令
   - `test-template.js` - 範本測試檔案
   - `examples/` - 範例測試場景

---

## 📝 SKILL.md 檔案格式

`SKILL.md` 檔案是一個帶有 YAML 前置資料的 Markdown 檔案，定義 Skill 的元資料和行為。

### YAML 前置資料欄位

| 欄位 | 必填 | 說明 |
|------|------|------|
| **`name`** | ✅ 是 | Skill 的唯一識別碼。必須是小寫，使用連字號代替空格（例如 `webapp-testing`）。必須與父目錄名稱匹配。最多 64 個字元。 |
| **`description`** | ✅ 是 | 描述 Skill 的功能**以及何時使用它**。要具體說明能力和使用案例，以幫助 Copilot 決定何時載入 Skill。最多 1024 個字元。 |
| **`argument-hint`** | ❌ 否 | 當 Skill 作為斜線命令呼叫時，在聊天輸入欄位中顯示的提示文字。幫助使用者了解要提供什麼額外資訊（例如 `[test file] [options]`）。 |
| **`user-invokable`** | ❌ 否 | 控制 Skill 是否作為斜線命令出現在聊天選單中。預設為 `true`。設定為 `false` 可從 `/` 選單中隱藏 Skill，同時仍允許代理自動載入它。 |
| **`disable-model-invocation`** | ❌ 否 | 控制代理是否可以根據相關性自動載入 Skill。預設為 `false`。設定為 `true` 需要僅透過 `/` 斜線命令手動呼叫。 |

### Skill 主體

Skill 主體包含 Copilot 在使用此 Skill 時應遵循的指令、指南和範例。撰寫清晰、具體的指令，描述：

- ✅ Skill 幫助完成什麼
- ✅ 何時使用 Skill
- ✅ 要遵循的分步驟程序
- ✅ 預期輸入和輸出的範例
- ✅ 對任何包含的腳本或資源的引用

您可以使用相對路徑引用 Skill 目錄中的檔案。例如，要引用 Skill 目錄中的腳本，使用 `[test script](./test-template.js)`。

---

## 📚 範例 Skills

以下範例展示了您可以建立的不同類型的 Skills。

### 範例 1：Web 應用程式測試 Skill

````yaml
---
name: webapp-testing
description: Guide for testing web applications using Playwright. Use this when asked to create or run browser-based tests.
---

# Web Application Testing with Playwright

This skill helps you create and run browser-based tests for web applications using Playwright.

## When to use this skill

Use this skill when you need to:
- Create new Playwright tests for web applications
- Debug failing browser tests
- Set up test infrastructure for a new project

## Creating tests

1. Review the [test template](./test-template.js) for the standard test structure
2. Identify the user flow to test
3. Create a new test file in the `tests/` directory
4. Use Playwright's locators to find elements (prefer role-based selectors)
5. Add assertions to verify expected behavior

## Running tests

To run tests locally:
```bash
npx playwright test
```

To debug tests:
```bash
npx playwright test --debug
```

## Best practices

- Use data-testid attributes for dynamic content
- Keep tests independent and atomic
- Use Page Object Model for complex pages
- Take screenshots on failure
````

### 範例 2：GitHub Actions 除錯 Skill

```yaml
---
name: github-actions-debugging
description: Guide for debugging failing GitHub Actions workflows. Use this when asked to debug failing GitHub Actions workflows.
---

# GitHub Actions Debugging

This skill helps you debug failing GitHub Actions workflows in pull requests.

## Process

1. Use the `list_workflow_runs` tool to look up recent workflow runs for the pull request and their status
2. Use the `summarize_job_log_failures` tool to get an AI summary of the logs for failed jobs
3. If you need more information, use the `get_job_logs` or `get_workflow_run_logs` tool to get the full failure logs
4. Try to reproduce the failure locally in your environment
5. Fix the failing build and verify the fix before committing changes

## Common issues

- **Missing environment variables**: Check that all required secrets are configured
- **Version mismatches**: Verify action versions and dependencies are compatible
- **Permission issues**: Ensure the workflow has the necessary permissions
- **Timeout issues**: Consider splitting long-running jobs or increasing timeout values
```

---

## 🔧 使用 Skills 作為斜線命令

Skills 在聊天中作為斜線命令可用，與[提示檔案](/docs/copilot/customization/prompt-files)一起。在聊天輸入欄位中輸入 `/` 以查看可用 Skills 和提示的列表，並選擇一個 Skill 來呼叫它。

您可以在斜線命令後新增額外的上下文。例如：
- `/webapp-testing for the login page`
- `/github-actions-debugging PR #42`

### 控制 Skill 存取方式

預設情況下，所有 Skills 都出現在 `/` 選單中。使用 `user-invokable` 和 `disable-model-invocation` 前置資料屬性來控制每個 Skill 的存取方式：

| 配置 | 斜線命令 | Copilot 自動載入 | 使用案例 |
|------|----------|-----------------|----------|
| **預設**（兩個屬性都省略） | ✅ 是 | ✅ 是 | 通用 Skills |
| **`user-invokable: false`** | ❌ 否 | ✅ 是 | 模型在相關時載入的背景知識 Skills |
| **`disable-model-invocation: true`** | ✅ 是 | ❌ 否 | 您只想按需執行的 Skills |
| **兩者都設定** | ❌ 否 | ❌ 否 | 已停用的 Skills |

---

## 🔄 Copilot 如何使用 Skills

Skills 使用**漸進式揭露**來高效載入僅在需要時的內容。這個三層載入系統確保您可以安裝許多 Skills 而不會消耗上下文：

### 第 1 層：Skill 發現

Copilot 始終透過從 YAML 前置資料讀取它們的 `name` 和 `description` 來知道哪些 Skills 可用。這個元資料是輕量級的，並幫助 Copilot 決定哪些 Skills 與您的請求相關。

### 第 2 層：指令載入

當您的請求與 Skill 的描述匹配時，Copilot 將 `SKILL.md` 檔案主體載入其上下文。只有在此時，詳細的指令才變得可用。您也可以透過在聊天中使用 `/` 斜線命令直接呼叫 Skill。

### 第 3 層：資源存取

Copilot 可以僅在需要時存取 Skill 目錄中的其他檔案（腳本、範例、文件）。這些資源在 Copilot 引用它們之前不會載入，保持您的上下文高效。

這種架構意味著 Skills 既可以根據您的提示自動啟動，也可以透過斜線命令手動呼叫。您可以安裝許多 Skills，Copilot 只載入每個任務相關的內容。

---

## 🌐 從社群使用共享 Skills

您可以使用其他人建立的 Skills 來增強 Copilot 的能力。

### 官方 Skills 儲存庫

- 📦 [github/awesome-copilot](https://github.com/github/awesome-copilot) - 包含不斷增長的社群集合：Skills、自訂代理、指令和提示
- 📦 [anthropics/skills](https://github.com/anthropics/skills) - 包含額外的參考 Skills

### 使用共享 Skill 的步驟

1. **瀏覽可用 Skills**  
   在儲存庫中瀏覽可用的 Skills

2. **複製 Skill 目錄**  
   將 Skill 目錄複製到您的 `.github/skills/` 資料夾

3. **審查和自訂**  
   審查並根據您的需求自訂 `SKILL.md` 檔案

4. **（可選）修改資源**  
   根據需要修改或新增資源

> ⚠️ **重要安全提示**: 在使用前始終審查共享 Skills，以確保它們符合您的要求和安全標準。VS Code 的[終端機工具](/docs/copilot/agents/agent-tools#_terminal-commands)提供腳本執行控制，包括具有可配置允許清單和對哪些程式碼執行的嚴格控制的[自動批准選項](/docs/copilot/agents/agent-tools#_automatically-approve-terminal-commands)。了解更多關於自動批准功能的[安全考量](/docs/copilot/security#_automated-approval)。

---

## 🔌 從擴充套件貢獻 Skills

擴充套件可以使用其 `package.json` 中的 `chatSkills` 貢獻點來貢獻 Skills。路徑必須指向包含 `SKILL.md` 檔案的目錄，遵循 [Agent Skills 規範](https://agentskills.io/specification)。

### 必要的資料夾結構

Skill 目錄必須遵循此結構：

```
extension-root/
└── skills/
    └── my-skill/           # 目錄名稱必須與 SKILL.md 中的 name 欄位匹配
        └── SKILL.md        # 必要
```

### 在 package.json 中註冊 Skill

在您的擴充套件的 `package.json` 中新增 `chatSkills` 貢獻點。`path` 屬性必須指向包含 `SKILL.md` 檔案的目錄：

```json
{
  "contributes": {
    "chatSkills": [
      {
        "path": "./skills/my-skill"
      }
    ]
  }
}
```

> ⚠️ **重要**: `SKILL.md` 前置資料中的 `name` 欄位必須與父目錄名稱匹配。例如，如果目錄是 `skills/my-skill/`，`name` 欄位必須是 `my-skill`。如果名稱不匹配，Skill 將不會載入。

### SKILL.md 範例

`SKILL.md` 檔案遵循與[專案和個人 Skills](#建立-skill) 相同的格式。例如：

```yaml
---
name: my-skill
description: Description of what the skill does and when to use it.
---

# My Skill

Detailed instructions for the skill...
```

---

## 🌍 Agent Skills 標準

Agent Skills 是一個開放標準，可實現跨不同 AI 代理的可攜性。您在 VS Code 中建立的 Skills 可與多個代理一起使用，包括：

- ✅ **VS Code 中的 GitHub Copilot** - 在聊天和代理模式下可用
- ✅ **GitHub Copilot CLI** - 在終端機中工作時可存取
- ✅ **GitHub Copilot Coding Agent** - 在自動編碼任務期間使用

了解更多關於 Agent Skills 標準的資訊：[agentskills.io](https://agentskills.io)

---

## 📊 Skills 配置速查表

### 前置資料屬性組合

| `user-invokable` | `disable-model-invocation` | 結果 |
|------------------|----------------------------|------|
| `true` (預設) | `false` (預設) | ✅ 斜線命令可用 + ✅ 自動載入 |
| `false` | `false` (預設) | ❌ 斜線命令隱藏 + ✅ 自動載入 |
| `true` (預設) | `true` | ✅ 斜線命令可用 + ❌ 僅手動呼叫 |
| `false` | `true` | ❌ 完全停用 |

### Skill 目錄結構範例

```
.github/skills/
├── webapp-testing/
│   ├── SKILL.md                 # 必要：主要指令檔案
│   ├── test-template.js         # 可選：範本腳本
│   └── examples/                # 可選：範例目錄
│       ├── login-test.js
│       └── checkout-test.js
│
├── api-testing/
│   ├── SKILL.md
│   ├── setup-guide.md
│   └── scripts/
│       └── mock-server.js
│
└── deployment/
    ├── SKILL.md
    ├── deploy.sh
    └── config/
        └── production.yaml
```

---

## 🎯 最佳實踐

### 1. 撰寫清晰的描述

```yaml
# ❌ 不好
description: Testing skill

# ✅ 好
description: Guide for testing web applications using Playwright. Use this when asked to create or run browser-based tests.
```

### 2. 包含何時使用 Skill

```markdown
## When to use this skill

Use this skill when you need to:
- Create new Playwright tests for web applications
- Debug failing browser tests
- Set up test infrastructure for a new project
```

### 3. 提供具體範例

```markdown
## Running tests

To run tests locally:
```bash
npx playwright test
```

To debug tests:
```bash
npx playwright test --debug
```
```

### 4. 引用相關資源

```markdown
Review the [test template](./test-template.js) for the standard test structure
```

### 5. 使用分步驟指令

```markdown
## Process

1. Use the `list_workflow_runs` tool to look up recent workflow runs
2. Use the `summarize_job_log_failures` tool to get an AI summary
3. If you need more information, use the `get_job_logs` tool
4. Try to reproduce the failure locally
5. Fix the failing build and verify the fix
```

---

## 🔗 相關資源

### VS Code 官方文件

- 📖 [自訂 AI 回應概述](/docs/copilot/customization/overview)
- 📝 [建立自訂指令](/docs/copilot/customization/custom-instructions)
- 📄 [建立可重複使用的提示檔案](/docs/copilot/customization/prompt-files)
- 🤖 [建立自訂代理](/docs/copilot/customization/custom-agents)

### Agent Skills 標準

- 🌐 [Agent Skills 規範](https://agentskills.io)
- 📦 [參考 Skills 儲存庫](https://github.com/anthropics/skills)
- 🌟 [Awesome Copilot](https://github.com/github/awesome-copilot)

---

## 💡 快速開始範本

### 基本 Skill 範本

```yaml
---
name: my-skill-name
description: Brief description of what this skill does and when to use it. Maximum 1024 characters.
---

# My Skill Name

## When to use this skill

Use this skill when you need to:
- [Use case 1]
- [Use case 2]
- [Use case 3]

## Instructions

### Step 1: [First step]
[Detailed instructions]

### Step 2: [Second step]
[Detailed instructions]

## Examples

[Concrete examples of using this skill]

## Best practices

- [Best practice 1]
- [Best practice 2]
- [Best practice 3]
```

### 帶腳本的 Skill 範本

```yaml
---
name: advanced-skill
description: Advanced skill with script support. Use when you need automated processing.
argument-hint: [input file] [options]
---

# Advanced Skill

## Setup

This skill includes a helper script. To use it:

1. Ensure dependencies are installed
2. Review the [configuration guide](./CONFIG.md)
3. Run the [processing script](./scripts/process.sh)

## Using the script

```bash
./scripts/process.sh --input data.json --output results.json
```

See [script documentation](./scripts/README.md) for all options.

## Troubleshooting

Common issues and solutions...
```

---

## 📋 檢查清單

建立新 Skill 時使用此檢查清單：

- [ ] 在適當位置建立 Skill 目錄（`.github/skills/` 或 `~/.copilot/skills/`）
- [ ] 目錄名稱與 `name` 欄位匹配
- [ ] `SKILL.md` 包含必填的 YAML 前置資料（`name` 和 `description`）
- [ ] `description` 包含功能和使用時機（最多 1024 字元）
- [ ] `name` 是小寫且使用連字號（最多 64 字元）
- [ ] Skill 主體包含清晰的指令和範例
- [ ] 如果包含腳本或資源，確保它們被正確引用
- [ ] 審查安全性（如果使用外部 Skills）
- [ ] 測試 Skill 是否被 Copilot 正確載入
- [ ] 測試斜線命令是否正常運作（如果 `user-invokable: true`）

---

**最後更新**: 2026-02-17  
**文件版本**: 1.0  
**基於**: VS Code 官方文件 (2026-02-04)
