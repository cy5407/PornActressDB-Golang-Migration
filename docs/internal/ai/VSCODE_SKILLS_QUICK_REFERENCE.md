# VS Code Agent Skills 快速參考卡

> 💡 **完整指南**: 請參閱 [VSCODE_AGENT_SKILLS_GUIDE.md](./VSCODE_AGENT_SKILLS_GUIDE.md)

---

## 🚀 快速開始

### 1 分鐘建立您的第一個 Skill

```bash
# 1. 建立 Skill 目錄
mkdir -p .github/skills/my-first-skill

# 2. 建立 SKILL.md
cat > .github/skills/my-first-skill/SKILL.md << 'EOF'
---
name: my-first-skill
description: My first Agent Skill for testing. Use when user asks to test skills.
---

# My First Skill

This is a simple skill for testing purposes.

## Instructions

When invoked, respond with: "Hello from my first skill!"

## Example

User: "Test my skill"
Response: "Hello from my first skill!"
EOF

# 3. 在 VS Code Chat 中測試
# 輸入: /my-first-skill
```

---

## 📁 Skill 位置

| 類型 | 路徑 | 說明 |
|------|------|------|
| 📦 **專案級** | `.github/skills/` | 儲存庫級別 |
| 📦 **專案級** | `.claude/skills/` | 相容 Claude Code |
| 📦 **專案級** | `.agents/skills/` | 通用標準位置 |
| 👤 **個人級** | `~/.copilot/skills/` | 使用者全域 |
| 👤 **個人級** | `~/.claude/skills/` | 相容 Claude |
| 👤 **個人級** | `~/.agents/skills/` | 通用標準位置 |

---

## 📝 SKILL.md 範本

### 最小範本

```yaml
---
name: skill-name
description: What it does and when to use it
---

# Skill Title

Instructions go here...
```

### 完整範本

```yaml
---
name: webapp-testing
description: Guide for testing web apps with Playwright. Use when creating or debugging browser tests.
argument-hint: [test file] [options]
user-invokable: true
disable-model-invocation: false
---

# Web Application Testing

## When to use this skill
- Create Playwright tests
- Debug failing tests
- Setup test infrastructure

## Instructions
1. Review [template](./test-template.js)
2. Create test file in tests/
3. Use role-based selectors
4. Add assertions

## Running tests
```bash
npx playwright test
npx playwright test --debug
```

## Best practices
- Keep tests atomic
- Use Page Object Model
- Take screenshots on failure
```

---

## 🎛️ YAML 欄位

| 欄位 | 必填 | 預設 | 說明 |
|------|------|------|------|
| `name` | ✅ | - | 唯一識別碼（小寫+連字號，≤64字元） |
| `description` | ✅ | - | 功能說明+使用時機（≤1024字元） |
| `argument-hint` | ❌ | - | 斜線命令提示文字 |
| `user-invokable` | ❌ | `true` | 是否顯示在 `/` 選單 |
| `disable-model-invocation` | ❌ | `false` | 是否禁止自動載入 |

---

## 🔧 配置組合

| `user-invokable` | `disable-model-invocation` | 斜線命令 | 自動載入 | 用途 |
|------------------|----------------------------|----------|----------|------|
| `true` (預設) | `false` (預設) | ✅ | ✅ | **通用 Skills** |
| `false` | `false` (預設) | ❌ | ✅ | **背景知識 Skills** |
| `true` (預設) | `true` | ✅ | ❌ | **僅手動呼叫 Skills** |
| `false` | `true` | ❌ | ❌ | **已停用 Skills** |

---

## 📂 目錄結構範例

```
.github/skills/
├── webapp-testing/
│   ├── SKILL.md                 # 必要
│   ├── test-template.js         # 可選：範本
│   └── examples/                # 可選：範例
│       └── login-test.js
│
├── api-testing/
│   ├── SKILL.md
│   ├── setup.md
│   └── scripts/
│       └── mock-server.js
│
└── deployment/
    ├── SKILL.md
    └── deploy.sh
```

---

## 🔄 三層漸進式載入

| 層級 | 載入時機 | Token 成本 | 內容 |
|------|----------|-----------|------|
| **1️⃣ 發現** | 啟動時 | ~100 tokens/skill | `name` + `description` |
| **2️⃣ 指令** | 觸發時 | <5k tokens | `SKILL.md` 主體 |
| **3️⃣ 資源** | 按需 | 實際上無限 | 腳本、範例、文件 |

---

## 💬 使用方式

### 斜線命令

```
/skill-name
/skill-name extra context here
/webapp-testing for login page
/github-actions-debugging PR #42
```

### 在 Chat 中輸入 `/` 查看所有可用 Skills

### 快速配置選單

```
在 Chat 輸入: /skills
```

---

## 🌐 共享與社群

### 官方儲存庫

- 🌟 [github/awesome-copilot](https://github.com/github/awesome-copilot) - 社群集合
- 📦 [anthropics/skills](https://github.com/anthropics/skills) - 參考 Skills

### 使用共享 Skill

```bash
# 1. 下載 Skill
git clone https://github.com/example/skill-repo
cd skill-repo

# 2. 複製到專案
cp -r skill-name ../my-project/.github/skills/

# 3. 審查內容
cat ../my-project/.github/skills/skill-name/SKILL.md

# 4. 測試
# 在 VS Code Chat 中: /skill-name
```

---

## ⚠️ 安全檢查清單

使用外部 Skills 前：

- [ ] 審查所有檔案內容（SKILL.md、腳本）
- [ ] 檢查異常網路呼叫
- [ ] 驗證檔案存取模式
- [ ] 確認工具呼叫合理性
- [ ] 檢查外部 URL 來源
- [ ] 測試於非生產環境

---

## 🎯 常見 Skill 範例

### 測試 Skill

```yaml
---
name: unit-testing
description: Guide for writing and running unit tests. Use when creating or debugging tests.
---

# Unit Testing Guide

## Framework detection
1. Check for Jest/Mocha/Vitest
2. Use appropriate test syntax

## Test structure
```javascript
describe('Component', () => {
  it('should do something', () => {
    expect(result).toBe(expected);
  });
});
```

## Commands
- Jest: `npm test`
- Mocha: `npm run test:mocha`
- Vitest: `npm run test:vitest`
```

### 除錯 Skill

```yaml
---
name: debugging-assistant
description: Step-by-step debugging workflow. Use when user needs help debugging code.
---

# Debugging Assistant

## Process
1. **Identify** - What's the error message?
2. **Locate** - Which file/line?
3. **Reproduce** - Can you reproduce it?
4. **Fix** - What's the solution?
5. **Verify** - Test the fix

## Tools
- Console logs: `console.log()`
- Debugger: Set breakpoints in VS Code
- Stack trace: Read from bottom to top
```

### 部署 Skill

```yaml
---
name: deployment-guide
description: Deployment checklist and commands. Use when deploying to production.
---

# Deployment Guide

## Pre-deployment checklist
- [ ] Tests passing
- [ ] Environment variables set
- [ ] Database migrations ready
- [ ] Rollback plan prepared

## Deploy commands
```bash
# Build
npm run build

# Deploy
npm run deploy:production

# Verify
curl https://api.example.com/health
```

## Rollback
```bash
npm run rollback:previous
```
```

---

## 🔌 VS Code 設定

### settings.json

```json
{
  // 啟用 Agent Skills
  "chat.useAgentSkills": true,
  
  // 自訂 Skill 位置（可選）
  "chat.agentSkillsLocations": [
    ".github/skills",
    ".claude/skills",
    "~/my-shared-skills"
  ],
  
  // 終端機自動批准（可選）
  "chat.tools.terminal.autoApprove": {
    "npm test": true,
    "npm run build": true
  }
}
```

---

## 📊 Skills vs Custom Instructions

| 何時使用 | Agent Skills | Custom Instructions |
|----------|--------------|---------------------|
| ✅ 專業化工作流程 | ✅ | ❌ |
| ✅ 包含腳本/資源 | ✅ | ❌ |
| ✅ 跨工具可攜性 | ✅ | ❌ |
| ✅ 編碼標準 | 可以 | ✅ |
| ✅ 全域應用 | 可以 | ✅ |
| ✅ 按檔案類型應用 | ❌ | ✅ |

---

## 🛠️ 除錯 Skills

### 檢查 Skill 是否載入

```bash
# 1. 在 Chat 輸入 /
# 2. 查看是否出現您的 Skill

# 3. 或檢查 Developer Tools
# Help > Toggle Developer Tools
# Console 中搜尋 "skill"
```

### 常見問題

| 問題 | 原因 | 解決方法 |
|------|------|---------|
| Skill 未出現在 `/` 選單 | `user-invokable: false` | 設為 `true` 或移除 |
| Skill 未自動載入 | `disable-model-invocation: true` | 設為 `false` 或移除 |
| 目錄名稱與 `name` 不符 | 不一致 | 確保完全匹配 |
| `SKILL.md` 找不到 | 位置錯誤 | 確認在 Skill 目錄根部 |

---

## 📚 延伸閱讀

- 📖 [完整指南](./VSCODE_AGENT_SKILLS_GUIDE.md)
- 🌐 [Agent Skills 標準](https://agentskills.io)
- 📦 [VS Code 官方文件](https://code.visualstudio.com/docs/copilot/customization/agent-skills)
- 🌟 [Awesome Copilot](https://github.com/github/awesome-copilot)

---

**最後更新**: 2026-02-17  
**快速參考版本**: 1.0
