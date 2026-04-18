---
name: smart-code-search  
description: 智能程式碼搜尋技能 - 使用 fd 和 rg 工具協助 AI 快速定位和分析程式碼檔案，提供精確的檔案搜尋、內容匹配和程式碼片段提取功能
version: "1.0"
platforms: ["Codex", "github-copilot", "vs-code", "copilot-cli", "codex-cli"]
allowed-tools: ["powershell", "view", "grep", "glob"]
user-invocable: true
auto-trigger: true
trigger-phrases: ["搜尋程式碼", "查找檔案", "找程式碼", "搜尋檔案", "code search", "find code", "locate file"]
context: default
---

# 🔍 智能程式碼搜尋技能

使用 **fd** (檔案搜尋) 和 **rg** (內容搜尋) 工具的高效程式碼定位技能，協助 AI 快速分析專案結構和找到相關程式碼。

## 🎯 核心功能

### 📁 檔案搜尋 (fd)
- **快速定位**: 根據檔案名稱模式快速找到檔案
- **類型篩選**: 按副檔名、目錄結構篩選
- **智能排除**: 自動排除 node_modules、.git 等無關目錄
- **模糊匹配**: 支援部分檔名匹配

### 📝 內容搜尋 (rg)  
- **程式碼片段**: 搜尋特定函數、類別、變數
- **正規表達式**: 支援複雜模式匹配
- **上下文顯示**: 顯示匹配行前後的程式碼
- **多檔案搜尋**: 跨檔案搜尋相關實作

### 🧠 AI 輔助
- **智能建議**: 根據搜尋結果提供程式碼分析
- **關聯發現**: 找到相關的檔案和函數
- **結構理解**: 協助理解專案架構

## 🛠️ 使用方式

### 自然語言觸發
```
"搜尋所有包含 API 的 JavaScript 檔案"
"找到處理錯誤的程式碼"  
"查找 user 相關的 TypeScript 檔案"
"搜尋 database 連線設定"
```

### 基本檔案搜尋
```bash
# 搜尋特定名稱的檔案
fd "config" --type f

# 搜尋特定副檔名
fd -e js -e ts

# 搜尋目錄
fd "components" --type d

# 排除特定目錄
fd "*.js" --exclude node_modules
```

### 內容搜尋範例
```bash
# 搜尋函數定義
rg "function\s+\w+" --type js

# 搜尋類別定義  
rg "class\s+\w+" --type typescript

# 搜尋變數使用
rg "const\s+API_KEY" -C 3

# 搜尋錯誤處理
rg "(try|catch|throw)" --type js -A 2 -B 2
```

## 📋 常用搜尋模式

### 1. 🔍 快速檔案定位
**場景**: 需要找到特定功能的檔案

```bash
# 找到所有 API 相關檔案
fd -i api

# 找到測試檔案
fd -e test.js -e spec.js

# 找到配置檔案
fd "config|setting" --type f
```

### 2. 📝 程式碼片段搜尋  
**場景**: 查找特定的函數或實作

```bash
# 搜尋所有 React 元件
rg "export\s+(default\s+)?function\s+\w+" --type tsx

# 搜尋 API 端點
rg "(app\.|router\.)(get|post|put|delete)" --type js

# 搜尋錯誤處理
rg "catch\s*\(" -A 5
```

### 3. 🏗️ 專案結構分析
**場景**: 理解專案架構和依賴關係

```bash
# 分析 import 結構
rg "import.*from" --type typescript -o

# 找到入口檔案
fd "index|main|app" --type f --max-depth 2

# 分析資料庫使用
rg "(sequelize|mongoose|prisma)" --type js
```

### 4. 🐛 問題診斷
**場景**: 快速定位錯誤和問題程式碼

```bash
# 搜尋 TODO 和 FIXME
rg "(TODO|FIXME|BUG)" -i

# 搜尋 console.log (除錯程式碼)
rg "console\.(log|error|warn)" --type js

# 搜尋已棄用的 API
rg "@deprecated|DEPRECATED" -i
```

## 🚀 智能工作流程

### 階段 1: 初步掃描
```bash
# 1. 了解專案結構
fd --type d --max-depth 2

# 2. 識別主要檔案類型
fd -e js -e ts -e py -e go | head -20

# 3. 找到配置和說明檔案  
fd "README|config|package" --type f
```

### 階段 2: 目標搜尋
```bash
# 根據需求搜尋特定內容
# 範例：查找使用者驗證相關程式碼

# 1. 找到相關檔案
fd -i "auth|user|login"

# 2. 搜尋相關函數
rg "(login|authenticate|authorize)" --type js -C 2

# 3. 分析實作
rg "passport|jwt|session" --type js
```

### 階段 3: 深度分析
```bash
# 分析找到的程式碼片段，提供：
# - 功能說明
# - 使用方式  
# - 相關檔案
# - 改善建議
```

## 📊 搜尋結果最佳化

### 提升搜尋精確度
```bash
# 使用更精確的模式
rg "\bfunction\s+(\w+)" --type js --only-matching

# 限制搜尋範圍
rg "API" --type js --glob "src/**/*"

# 排除測試檔案
rg "import" --type js --glob "!**/*test*" --glob "!**/*spec*"
```

### 結果格式化
```bash
# 顯示檔案名和行號
rg "error" --type js --with-filename --line-number

# 統計匹配數量
rg "TODO" --count-matches

# 只顯示檔案名
rg "component" --type tsx --files-with-matches
```

## 🎯 AI 協作模式

當 AI 使用此技能時的標準流程：

### 1. 🧠 需求理解
- 分析用戶查詢意圖
- 識別關鍵詞和搜尋目標
- 選擇適當的搜尋策略

### 2. 🔍 執行搜尋
- 使用 fd 定位相關檔案
- 使用 rg 搜尋程式碼內容
- 組合多個搜尋結果

### 3. 📝 結果分析
- 檢查找到的程式碼片段
- 理解程式碼功能和用途
- 識別相關的檔案和依賴

### 4. 💡 智能建議
- 提供程式碼說明
- 建議相關的檔案或函數
- 指出潛在的改善方向

## ⚡ 效率提升技巧

### 組合搜尋
```bash
# 先用 fd 找檔案，再用 rg 搜尋內容
fd -e js | xargs rg "function"

# 在特定檔案中搜尋
fd "component" --type f -x rg "props" {}
```

### 快速篩選
```bash
# 快速排除不需要的結果
rg "import" --type js | grep -v node_modules

# 只看特定目錄
fd --base-directory src -e tsx
```

### 結果快取
```bash
# 將常用搜尋結果儲存
fd -e js > js_files.txt
rg "function" --files-with-matches > functions.txt
```

## 🛡️ 安全和效能

### 搜尋限制
- 自動排除敏感目錄 (.git, node_modules, .env)
- 限制搜尋深度避免效能問題
- 檔案大小限制 (避免搜尋大型二進位檔案)

### 效能最佳化
- 使用適當的檔案類型篩選
- 優先搜尋常見的程式碼目錄
- 限制搜尋結果數量

## 📚 工具安裝

### Windows (推薦方式)
```powershell
# 使用 Chocolatey
choco install fd rg

# 或使用 Scoop
scoop install fd ripgrep

# 或手動下載
# fd: https://github.com/sharkdp/fd/releases
# rg: https://github.com/BurntSushi/ripgrep/releases
```

### 驗證安裝
```bash
fd --version
rg --version
```

## 🎨 範例使用場景

### 場景 1: 新專案探索
**用戶**: "這個專案的結構是什麼？"
**AI 搜尋**:
```bash
fd --type d --max-depth 2  # 查看目錄結構
fd "README|package|config" --type f  # 找說明檔案
rg "main|entry" package.json  # 找入口點
```

### 場景 2: 功能實作查找
**用戶**: "用戶登入是怎麼實作的？"
**AI 搜尋**:
```bash
fd -i "login|auth|user"  # 找相關檔案
rg "(login|authenticate)" --type js -C 3  # 找實作
rg "password|jwt|session" --type js  # 找認證方式
```

### 場景 3: 錯誤排查
**用戶**: "為什麼會出現這個錯誤？"
**AI 搜尋**:
```bash
rg "error_message_keyword" -i  # 搜尋錯誤訊息
rg "(try|catch|throw)" --type js -A 3  # 找錯誤處理
fd "test|spec" --type f -x rg "error_scenario" {}  # 找測試
```

---

## 💡 使用提示

1. **先檔案後內容**: 通常先用 fd 找到相關檔案，再用 rg 搜尋內容
2. **善用類型篩選**: 指定檔案類型可大幅提升搜尋精確度  
3. **組合關鍵詞**: 使用多個相關關鍵詞提升搜尋覆蓋度
4. **上下文很重要**: 使用 -A、-B、-C 參數查看程式碼上下文

**自動觸發**: 當您說「搜尋程式碼」、「查找檔案」、「找程式碼」等詞彙時，AI 會自動使用這個技能！