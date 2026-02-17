# Skill Generator 使用範例

## 基本使用範例

### 範例 1：建立簡單的參考技能

#### 指令
```bash
/skill-generator create project-conventions reference "專案程式碼規範和最佳實踐"
```

#### 生成結果
```
project-conventions/
├── SKILL.md
├── examples/
│   └── usage-guide.md
└── templates/
    └── code-examples.md
```

#### 生成的 SKILL.md
```yaml
---
name: project-conventions
description: 專案程式碼規範和最佳實踐
user-invocable: false
---

# 專案程式碼規範

當撰寫程式碼時，請遵循以下規範：

## 命名規範
- 變數使用 camelCase
- 常數使用 UPPER_SNAKE_CASE
- 檔案名稱使用 kebab-case

## 程式碼結構  
- 每個函數不超過 50 行
- 適當添加註解
- 保持程式碼簡潔易讀

詳細規範請參考 [templates/code-examples.md](templates/code-examples.md)。
```

---

### 範例 2：建立任務執行技能

#### 指令  
```bash
/skill-generator create deploy-app task "自動化部署應用程式到生產環境" --disable-auto-invoke --tools="Bash"
```

#### 生成結果
```
deploy-app/
├── SKILL.md
├── examples/
│   └── deployment-scenarios.md
├── templates/
│   └── deployment-scripts.md
└── scripts/
    └── deploy-validator.sh
```

#### 生成的 SKILL.md
```yaml
---
name: deploy-app
description: 自動化部署應用程式到生產環境
disable-model-invocation: true
allowed-tools: Bash
argument-hint: [environment] [version]
---

# 應用程式部署

部署應用程式到指定環境：$ARGUMENTS

## 部署步驟

1. 檢查環境狀態
2. 建置應用程式
3. 執行部署腳本
4. 驗證部署結果

## 使用方式

```bash
/deploy-app production v1.2.3
/deploy-app staging latest
```

完整的部署指南請參考 [examples/deployment-scenarios.md](examples/deployment-scenarios.md)。
```

---

### 範例 3：建立分析型技能

#### 指令
```bash
/skill-generator create code-analyzer analyzer "智能程式碼分析和品質檢查" --context=default --tools="Read,Grep,Bash"
```

#### 生成結果  
```
code-analyzer/
├── SKILL.md
├── examples/
│   └── analysis-examples.md
├── templates/
│   └── analysis-templates.md
└── scripts/
    └── quality-check.sh
```

#### 生成的 SKILL.md
```yaml
---
name: code-analyzer
description: 智能程式碼分析和品質檢查
allowed-tools: Read, Grep, Bash
argument-hint: [analysis-type] [target-files]
---

# 程式碼分析器

執行程式碼品質分析：$ARGUMENTS

## 分析類型

### 靜態分析
- 語法檢查
- 程式碼風格檢查
- 潛在問題識別

### 複雜度分析
- 函數複雜度
- 模組耦合度
- 可維護性指標

### 安全性分析
- 漏洞掃描
- 依賴安全檢查
- 程式碼安全最佳實踐

## 使用範例

```bash
/code-analyzer security src/
/code-analyzer complexity app.js
/code-analyzer style ./components/
```

詳細的分析方法請參考 [examples/analysis-examples.md](examples/analysis-examples.md)。
```

---

### 範例 4：建立混合型技能

#### 指令
```bash
/skill-generator create api-helper hybrid "API 開發最佳實踐和管理工具" --tools="Read,Write,Bash"
```

#### 生成結果
```
api-helper/
├── SKILL.md
├── examples/
│   └── api-examples.md
├── templates/
│   └── api-templates.md
└── scripts/
    └── api-validator.sh
```

#### 生成的 SKILL.md  
```yaml
---
name: api-helper
description: API 開發最佳實踐和管理工具
allowed-tools: Read, Write, Bash
argument-hint: [action] [api-endpoint]
---

# API 開發助手

## API 設計原則

### RESTful 設計
- 使用適當的 HTTP 方法
- 資源導向的 URL 設計
- 一致的回應格式

### 錯誤處理
- 標準化的錯誤碼
- 清楚的錯誤訊息
- 適當的 HTTP 狀態碼

## API 操作

執行 API 相關操作：$ARGUMENTS

### 可用操作
- `validate` - 驗證 API 設計
- `test` - 測試 API 端點
- `document` - 生成 API 文檔
- `deploy` - 部署 API 服務

## 使用範例

```bash
/api-helper validate /api/users
/api-helper test POST /api/auth/login
/api-helper document ./api-spec.yaml
```

API 開發指南請參考 [templates/api-templates.md](templates/api-templates.md)。
```

---

## 進階使用範例

### 範例 5：使用子代理的技能

#### 指令
```bash
/skill-generator create research-assistant analyzer "深度程式碼研究和分析" --context=fork --agent=Explore
```

#### 生成的關鍵配置
```yaml
---
name: research-assistant
description: 深度程式碼研究和分析
context: fork
agent: Explore
---

# 研究助手

在隔離環境中執行深度研究：$ARGUMENTS

本技能在 Explore 代理中執行，具有以下特點：
- 唯讀操作，安全可靠
- 專門針對程式碼探索最佳化
- 結果以摘要形式返回

## 研究範圍
1. 程式碼架構分析
2. 依賴關係探索
3. 模式識別
4. 最佳實踐建議
```

---

### 範例 6：帶鉤子的技能

#### 指令
```bash
/skill-generator create auto-formatter task "自動程式碼格式化" --hooks --tools="Bash"
```

#### 生成的鉤子配置
```yaml
---
name: auto-formatter
description: 自動程式碼格式化
disable-model-invocation: true
allowed-tools: Bash
hooks:
  PostToolUse:
    - matcher: "Edit|Write"
      hooks:
        - type: command
          command: "scripts/format-code.sh"
---
```

#### 自動生成的格式化腳本
```bash
# scripts/format-code.sh
#!/bin/bash

# 從 JSON 輸入中提取檔案路徑
file_path=$(jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null)

if [ -z "$file_path" ]; then
    exit 0
fi

# 根據檔案副檔名選擇格式化工具
case "$file_path" in
    *.js|*.ts|*.jsx|*.tsx)
        if command -v prettier >/dev/null; then
            prettier --write "$file_path"
        fi
        ;;
    *.go)
        if command -v gofmt >/dev/null; then
            gofmt -w "$file_path"
        fi
        ;;
    *.py)
        if command -v black >/dev/null; then
            black "$file_path"
        fi
        ;;
esac
```

---

## 互動式建立範例

### 啟動互動式模式
```bash
/skill-generator interactive
```

### 互動流程
```
🛠️ Claude Skills Generator - 互動模式

1. 技能名稱 (小寫，使用連字號): code-reviewer
2. 技能類型:
   [1] Reference (背景知識)
   [2] Task (執行任務) 
   [3] Hybrid (混合型)
   [4] Analyzer (分析型)
   [5] Generator (生成型)
   
   選擇: 2

3. 技能描述: 自動程式碼審查和建議

4. 是否防止自動觸發? [y/N]: y

5. 允許的工具 (逗號分隔): Read,Grep,Bash

6. 是否需要子代理執行? [y/N]: n

7. 是否需要鉤子功能? [y/N]: n

8. 參數提示 (選填): [file-pattern] [review-type]

✅ 技能建立完成！
📁 位置: ./code-reviewer/
📄 查看: ./code-reviewer/SKILL.md
```

---

## 技能驗證範例

### 驗證現有技能
```bash
/skill-generator validate ./my-skill
```

### 驗證結果範例
```
🔍 驗證技能: ./my-skill

✅ SKILL.md 檔案存在
✅ YAML 前置資料格式正確
✅ 技能名稱符合命名規範
✅ 描述完整且清楚
❌ 缺少範例檔案
⚠️  工具權限過於寬泛

📊 總體評分: 8/10

🔧 建議改善:
1. 添加 examples/usage-guide.md
2. 考慮限制 allowed-tools 範圍
3. 增加更詳細的使用說明
```

### 自動修復
```bash
/skill-generator fix ./my-skill
```

### 修復結果
```
🔧 修復技能: ./my-skill

✅ 建立 examples/usage-guide.md
✅ 調整工具權限設定
✅ 增強技能描述
✅ 添加參數提示

📈 修復後評分: 10/10
```

---

## 技能更新範例

### 更新現有技能
```bash
/skill-generator update my-skill --add-tools="Write" --enable-hooks
```

### 批次處理範例
```bash
/skill-generator batch-update .claude/skills/ --format-check --add-examples
```

---

## 最佳實踐展示

### 1. 良好的技能結構
```
excellent-skill/
├── SKILL.md              # 簡潔的主要檔案
├── examples/
│   ├── basic-usage.md    # 基本使用方法  
│   ├── advanced.md       # 進階功能
│   └── troubleshooting.md # 疑難排解
├── templates/
│   ├── code-snippets.md  # 程式碼範本
│   └── config-files.md   # 配置檔案範本
└── scripts/
    ├── validate.sh       # 驗證腳本
    └── helper.py         # 輔助工具
```

### 2. 清楚的技能描述  
```yaml
# ❌ 不好的描述
description: 處理檔案

# ✅ 好的描述  
description: 自動分析程式碼檔案品質並提供改善建議
```

### 3. 適當的工具權限
```yaml
# ❌ 過於寬泛
allowed-tools: Read, Write, Edit, Bash, Grep, Glob

# ✅ 精確限制
allowed-tools: Read, Grep  # 只用於分析，不修改檔案
```

### 4. 有效的參數設計
```yaml
# ✅ 清楚的參數提示
argument-hint: [target-directory] [analysis-type]

# ✅ 在內容中使用參數
# 分析目標: $ARGUMENTS
# 會話ID: ${CLAUDE_SESSION_ID}
```

這些範例展示了如何使用 skill-generator 建立各種類型的高品質 Claude Skills。