# 🚀 新專案 Copilot Agent 設定指南

> 5 分鐘完成設定，最大化自動化運行

## ⚡ 快速設定（3 個必要檔案）

### 📄 檔案 1：`.github/copilot-instructions.md`（最重要）

在專案根目錄建立此檔案：

```markdown
# Copilot Agent Instructions - [你的專案名稱]

## 🤖 自主執行準則
1. 理解需求 → 規劃步驟 → 實作代碼
2. 執行驗證 → 若失敗 → 自動修復
3. 重複步驟 2 直到全部通過

## 終端機權限
你被授權直接執行以下指令：

### 測試指令（根據專案類型選擇）
```bash
# Python
python -m pytest tests/ -v
python -m unittest discover

# JavaScript/TypeScript
npm test
npm run test:unit
jest

# Go
go test ./... -v

# Rust
cargo test

# Java
mvn test
gradle test

# .NET
dotnet test
```

### 建構指令
```bash
# Python
python -m py_compile src/**/*.py

# Node.js
npm run build
npm run lint

# Go
go build ./...

# Rust
cargo build

# .NET
dotnet build
```

## 錯誤處理自動化
1. **依賴錯誤** → 檢查並安裝相依套件
2. **測試失敗** → 分析錯誤 → 修改代碼 → 重新測試
3. **建構失敗** → 修正錯誤 → 確認編譯成功

## 開發規範
- 修改程式碼後立即執行測試
- 發現失敗時主動修復（不只報告）
- 新增功能時同步撰寫測試

## 絕對禁止
- ❌ 不得刪除測試檔案
- ❌ 不得提交未通過測試的程式碼

## Agent 使命
主動、持續、迭代地完成任務，自動驗證並修復問題。
```

---

### 📄 檔案 2：`.vscode/settings.json`

```jsonc
{
  // Copilot Agent 核心設定
  "github.copilot.chat.codeGeneration.useInstructionFiles": true,
  "chat.useAgentSkills": true,
  
  // 自動執行終端機指令（根據專案調整）
  "chat.tools.terminal.autoApprove": {
    // Python
    "pytest": true,
    "python -m": true,
    
    // JavaScript/TypeScript
    "npm test": true,
    "npm run": true,
    "jest": true,
    
    // Go
    "go test": true,
    "go build": true,
    
    // Rust
    "cargo test": true,
    "cargo build": true,
    
    // .NET
    "dotnet test": true,
    "dotnet build": true,
    
    // 品質工具
    "eslint": true,
    "pylint": true,
    "prettier": true
  },
  
  // 自動儲存
  "files.autoSave": "afterDelay",
  "files.autoSaveDelay": 3000,
  
  // 格式化（根據語言調整）
  "editor.formatOnSave": true
}
```

---

### 📄 檔案 3：`.github/AGENT_TEMPLATES.md`（任務範本）

```markdown
# Agent 任務範本

## 修復錯誤
\`\`\`
[檔案] 有測試失敗，請：
1. 執行測試查看錯誤
2. 分析原因並修改代碼
3. 重新測試
4. 若失敗，重複步驟 2-3
請自動執行。
\`\`\`

## 新增功能
\`\`\`
請新增 [功能描述]：
1. 實作功能
2. 撰寫測試
3. 執行測試確認通過
請自動執行。
\`\`\`

## 執行測試
\`\`\`
請執行測試並回報結果：
[測試指令]
若失敗，請自動修復。
\`\`\`
```

---

## 🎯 語言特定設定

### Python 專案

**額外設定**（加入 `.vscode/settings.json`）：
```jsonc
{
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests", "-v"],
  "[python]": {
    "editor.defaultFormatter": "ms-python.black-formatter",
    "editor.formatOnSave": true
  }
}
```

**copilot-instructions.md 加入**：
```markdown
## Python 規範
- 使用 pytest 進行測試
- 所有函式需要型別提示
- 遵循 PEP 8 風格
```

---

### JavaScript/TypeScript 專案

**額外設定**：
```jsonc
{
  "[javascript]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[typescript]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "eslint.validate": ["javascript", "typescript"]
}
```

**copilot-instructions.md 加入**：
```markdown
## JavaScript/TypeScript 規範
- 使用 Jest 進行測試
- 遵循 ESLint 規則
- 優先使用 TypeScript 型別定義
```

---

### Go 專案

**額外設定**：
```jsonc
{
  "go.testOnSave": false,
  "go.testFlags": ["-v"],
  "[go]": {
    "editor.defaultFormatter": "golang.go"
  }
}
```

**copilot-instructions.md 加入**：
```markdown
## Go 規範
- 所有錯誤必須檢查
- 使用 go fmt 格式化
- 測試覆蓋率 >80%
```

---

## ✅ 驗證設定

### 快速測試

1. **開啟 VS Code Chat**（`Ctrl + Alt + I`）
2. **確認模式為 "Agent"**
3. **貼上測試指令**：
   ```
   請執行專案的測試指令並回報結果
   ```

4. **觀察行為**：
   - ✅ Agent 請求執行授權 → 設定成功
   - ❌ Agent 只回覆建議 → 檢查設定

---

## 📋 設定檢查清單

- [ ] `.github/copilot-instructions.md` 已建立
- [ ] `.vscode/settings.json` 已設定
- [ ] `chat.tools.terminal.autoApprove` 包含測試指令
- [ ] `chat.useAgentSkills` 設為 true
- [ ] `.github/AGENT_TEMPLATES.md` 已建立（可選）
- [ ] 在 Chat 測試 Agent 模式

---

## 🎯 最大化自動化的關鍵

### 1. 明確的終端機權限

在 `copilot-instructions.md` 中列出所有可執行的指令：

```markdown
## 終端機權限
### 測試
- pytest tests/ -v
- npm test
- go test ./...

### 建構
- npm run build
- go build
- docker build
```

### 2. 自動核准設定

在 `.vscode/settings.json` 加入：

```jsonc
"chat.tools.terminal.autoApprove": {
  "pytest": true,
  "npm test": true,
  "go test": true
}
```

### 3. 使用強制性語言

在提示詞中使用：
- ✅ 「請執行...」「自動執行」「無需詢問」
- ❌ 「可以幫我...」「建議」「你覺得」

### 4. 定義自動修復規則

```markdown
## 錯誤處理
- Test Failure → 自動分析 → 修改 → 重新測試
- Import Error → 檢查依賴 → 安裝套件
- Build Error → 修正錯誤 → 確認編譯
```

---

## 🚀 進階技巧

### 自訂快捷指令（可選）

建立 `scripts/test.sh` 或 `.vscode/tasks.json`：

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Run All Tests",
      "type": "shell",
      "command": "pytest tests/ -v && npm test",
      "group": {
        "kind": "test",
        "isDefault": true
      }
    }
  ]
}
```

### 專案特定範本

在 `.github/AGENT_TEMPLATES.md` 建立專案專屬範本：

```markdown
## 我的 API 專案範本

### 新增 API 端點
\`\`\`
請新增 [端點名稱] API：
1. 在 routes/ 新增路由
2. 在 controllers/ 新增控制器
3. 撰寫單元測試
4. 執行 npm test 確認
5. 更新 API 文件
請自動執行。
\`\`\`
```

---

## 📝 完整範例

### 最小化 Python 專案設定

**`.github/copilot-instructions.md`**：
```markdown
# Agent Instructions - My Python Project

## 自主執行
1. 實作 → 測試 → 修復 → 重複

## 終端機權限
- python -m pytest tests/ -v
- python -m py_compile src/**/*.py

## 錯誤處理
- Test Failure → 修改代碼 → 重新測試

## 規範
- 修改後立即測試
- 主動修復失敗
```

**`.vscode/settings.json`**：
```jsonc
{
  "github.copilot.chat.codeGeneration.useInstructionFiles": true,
  "chat.useAgentSkills": true,
  "chat.tools.terminal.autoApprove": {
    "pytest": true,
    "python -m": true
  },
  "python.testing.pytestEnabled": true
}
```

**完成！** 現在可以在 Chat 中使用：
```
請執行 pytest tests/ -v 並修復所有失敗的測試
```

---

## 🎉 快速開始

1. 複製上方 3 個檔案到新專案
2. 根據專案類型調整測試指令
3. 開啟 VS Code Chat（`Ctrl + Alt + I`）
4. 切換至 "Agent" 模式
5. 開始使用自動化功能！

---

**提示**：可以從當前專案複製設定檔案：
```powershell
# 複製核心設定到新專案
Copy-Item .github\copilot-instructions.md [新專案路徑]\.github\
Copy-Item .vscode\settings.json [新專案路徑]\.vscode\
```
