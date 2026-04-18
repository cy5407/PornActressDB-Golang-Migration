# 智能搜尋模式範本

## 🎯 常用檢索模式

### 檔案搜尋模式 (fd)

#### 基本檔案類型
```bash
# JavaScript/TypeScript 檔案
fd -e js -e ts -e jsx -e tsx

# 樣式檔案  
fd -e css -e scss -e less -e styled

# 配置檔案
fd "(config|setting|env)" --type f

# 文檔檔案
fd -e md -e txt -e doc

# 圖片檔案
fd -e jpg -e png -e svg -e gif
```

#### 專案結構檢索
```bash
# 元件目錄
fd "component|widget|ui" --type d

# 頁面/路由目錄
fd "page|route|view" --type d

# 工具/輔助目錄  
fd "util|helper|lib|tool" --type d

# 測試目錄
fd "test|spec|__test__|__spec__" --type d

# 建置/部署目錄
fd "build|dist|deploy|output" --type d
```

#### 特殊檔案搜尋
```bash
# 入口檔案
fd "^(index|main|app|entry)" --type f

# README 和說明檔案
fd "^(README|CHANGELOG|LICENSE)" --type f

# 環境設定
fd "^\.env|^config\." --type f

# 封裝管理檔案
fd "(package\.json|yarn\.lock|pnpm-lock)" --type f
```

### 內容搜尋模式 (rg)

#### 函數和方法檢索
```bash
# JavaScript 函數定義
rg "function\s+\w+\s*\(" --type js

# Arrow 函數
rg "(const|let|var)\s+\w+\s*=\s*\(" --type js

# TypeScript 型別定義
rg "(interface|type|enum)\s+\w+" --type ts

# 類別定義
rg "class\s+\w+(\s+extends)?" --type js --type ts

# React 元件
rg "(export\s+)?(default\s+)?function\s+[A-Z]\w*" --type jsx --type tsx
```

#### API 和網路相關
```bash
# HTTP 請求
rg "(fetch|axios|request)\s*\(" --type js --type ts

# API 端點
rg "(\/api\/|\/v\d+\/)" --type js --type ts

# 環境變數
rg "process\.env\.\w+" --type js --type ts

# 錯誤處理
rg "(catch|error|exception)" --type js --type ts -C 2

# 狀態管理
rg "(useState|useReducer|setState)" --type jsx --type tsx
```

#### 資料庫和存儲
```bash
# SQL 查詢
rg "(SELECT|INSERT|UPDATE|DELETE)" --type js --type ts

# MongoDB 查詢
rg "(find|findOne|insert|update|remove)" --type js

# Redis 操作
rg "(set|get|del|expire|incr)" --type js

# 本地存儲
rg "(localStorage|sessionStorage|cookie)" --type js
```

#### 安全性檢查模式
```bash
# 敏感資料
rg "(password|secret|token|key)\s*[=:]\s*['\"][^'\"]{8,}" -i

# XSS 風險
rg "(innerHTML|dangerouslySetInnerHTML)" 

# CSRF 相關
rg "(csrf|xsrf)" -i

# 輸入驗證
rg "(validate|sanitize|escape)" --type js --type ts
```

## 🔧 進階搜尋技巧

### 組合搜尋
```bash
# 搜尋檔案後在其中查找內容
fd -e js | xargs rg "function"

# 在特定檔案中搜尋多個模式
fd "component" --type f -x rg "(props|state)" {}

# 搜尋並統計
rg "TODO" --count | sort -rn
```

### 條件篩選
```bash
# 排除測試檔案
rg "import" --glob "!**/*test*" --glob "!**/*spec*"

# 只搜尋 src 目錄
rg "function" --glob "src/**/*"

# 搜尋最近修改的檔案
fd --changed-within 7d -e js -x rg "pattern" {}
```

### 輸出格式化
```bash
# 顯示行號和檔案名
rg "pattern" --line-number --with-filename

# 只顯示匹配的部分
rg "function\s+(\w+)" --only-matching

# 統計模式
rg "pattern" --count-matches

# JSON 格式輸出
rg "pattern" --json
```

## 📊 專案分析範本

### React/Next.js 專案
```bash
# 1. 專案結構概覽
echo "📁 專案結構分析"
fd --type d --max-depth 2

# 2. 技術棧分析  
echo "🔧 技術棧檢查"
rg "(react|next|typescript)" package.json

# 3. 元件分析
echo "🎨 元件結構"
fd "component" --type d
rg "export.*function.*[A-Z]" --type jsx --type tsx

# 4. 路由分析
echo "🛣️ 路由檢查"
rg "(useRouter|Router|route)" --type js --type jsx

# 5. 狀態管理
echo "📦 狀態管理"
rg "(useState|useContext|redux|zustand)" --type js --type jsx
```

### Node.js API 專案
```bash
# 1. API 架構
echo "🌐 API 結構分析"
fd "(route|controller|middleware)" --type d

# 2. 端點檢查
echo "📡 API 端點"
rg "(app|router)\.(get|post|put|delete)" --type js

# 3. 資料庫連線
echo "💾 資料庫設定"
rg "(mongoose|sequelize|prisma|knex)" --type js

# 4. 中介軟體分析
echo "🔧 中介軟體"
rg "(middleware|use\()" --type js

# 5. 錯誤處理
echo "🚨 錯誤處理"
rg "(try.*catch|error.*handler)" --type js -C 2
```

### Python Django 專案
```bash
# 1. 應用結構
echo "🐍 Django 專案結構"
fd "models|views|urls" --type f

# 2. 模型分析
echo "📊 資料模型"
rg "class.*\(models\.Model\)" --type py

# 3. 視圖函數
echo "👁️ 視圖分析"
rg "def.*\(request" --type py

# 4. URL 路由
echo "🔗 URL 配置"
rg "path\(|url\(" --type py

# 5. 設定檔案
echo "⚙️ 專案設定"
rg "DATABASES|SECRET_KEY|DEBUG" --type py
```

## 🎨 自定義搜尋模式

### 建立專案特定別名
```bash
# 在 ~/.bash_profile 或 ~/.zshrc 中添加

# 快速檔案搜尋
alias fjs="fd -e js -e jsx -e ts -e tsx"
alias fcss="fd -e css -e scss -e sass -e less"
alias fimg="fd -e jpg -e png -e svg -e gif"

# 快速內容搜尋  
alias rjs="rg --type js --type jsx --type ts --type tsx"
alias rcss="rg --type css --type scss"
alias rmd="rg --type md"

# 專案特定搜尋
alias findc="fd component --type d"
alias findapi="rg 'api|endpoint' --type js"
alias findtest="fd test --type d"
```

### 搜尋腳本範本
```bash
#!/bin/bash
# project-analyzer.sh - 專案分析腳本

analyze_project() {
    echo "🔍 開始分析專案..."
    
    # 基本結構
    echo "📁 目錄結構："
    fd --type d --max-depth 3 | head -20
    
    # 檔案類型統計
    echo -e "\n📊 檔案類型統計："
    fd --type f | grep -oE '\.[^.]+$' | sort | uniq -c | sort -rn | head -10
    
    # 程式碼行數統計
    echo -e "\n📏 程式碼行數："
    fd -e js -e ts -e jsx -e tsx | xargs wc -l | tail -1
    
    # 依賴分析
    echo -e "\n📦 主要依賴："
    if [ -f "package.json" ]; then
        rg '"[^"]+":' package.json | head -10
    fi
    
    # 待辦事項
    echo -e "\n✅ 待辦事項："
    rg "(TODO|FIXME|BUG)" -i --count || echo "無待辦事項"
}

# 執行分析
analyze_project
```

## 🎯 搜尋策略指南

### 從廣泛到精確
```bash
# 第一步：廣泛搜尋
fd "user" --type f

# 第二步：縮小範圍  
fd "user" --type f --glob "src/**/*"

# 第三步：精確搜尋
rg "function.*user" --type js --glob "src/**/*"

# 第四步：上下文分析
rg "function.*user" --type js -C 3
```

### 問題導向搜尋
```bash
# 問題：找不到登入功能
# 策略：多關鍵詞搜尋
rg "(login|signin|auth)" --type js -i
fd "(login|auth)" --type d -i

# 問題：API 回應太慢
# 策略：找效能相關程式碼  
rg "(timeout|delay|sleep)" --type js
rg "(Promise|async|await)" --type js | grep -E "(all|race)"

# 問題：記憶體洩漏
# 策略：找事件監聽和定時器
rg "(addEventListener|setInterval|setTimeout)" --type js
rg "(removeEventListener|clearInterval|clearTimeout)" --type js
```

這些模式和範本可以大幅提升程式碼搜尋的效率和準確性！