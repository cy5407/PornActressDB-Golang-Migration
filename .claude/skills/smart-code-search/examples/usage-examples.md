# 智能程式碼搜尋 - 實用範例

## 🎯 實際使用場景

### 場景 1: 專案初探
**背景**: 接手一個新的 React 專案，需要快速了解結構

```bash
# 1. 查看專案整體結構
fd --type d --max-depth 3

# 2. 找到主要入口檔案
fd "index" --type f --max-depth 2

# 3. 分析 package.json 了解依賴
rg "\"(react|next|typescript)\"" package.json

# 4. 找到主要元件目錄
fd "component" --type d -i

# 5. 查看路由設定
rg "(route|router)" --type jsx --type tsx -C 2
```

**AI 分析結果**:
```
📁 專案結構分析：
├── src/components/     # React 元件
├── src/pages/         # 頁面檔案  
├── src/utils/         # 工具函數
├── public/            # 靜態資源
└── package.json       # 依賴管理

🔧 技術棧：React 18 + TypeScript + Next.js
📍 入口檔案：src/index.tsx
🛣️ 路由方式：Next.js 檔案路由
```

### 場景 2: API 整合分析
**背景**: 需要了解專案如何與後端 API 互動

```bash
# 1. 找到 API 相關檔案
fd -i "api|service|client"

# 2. 搜尋 API 呼叫方式
rg "(fetch|axios|request)" --type js --type ts -C 2

# 3. 找到 API 端點定義
rg "(\/api\/|http:|https:)" --type js --type ts

# 4. 分析錯誤處理
rg "\.catch|try.*catch" --type js --type ts -A 3

# 5. 查看 API 金鑰管理
rg "(API_KEY|REACT_APP_|process\.env)" --type js --type ts
```

**搜尋結果摘要**:
```
🌐 API 整合方式：
- HTTP 客戶端：axios 
- 基礎 URL：https://api.example.com
- 認證方式：Bearer Token
- 錯誤處理：集中式錯誤攔截器
- 環境變數：REACT_APP_API_URL
```

### 場景 3: 效能問題排查
**背景**: 網站載入速度慢，需要找出潛在效能問題

```bash
# 1. 查找大型第三方套件使用
rg "(import.*from.*['\"](?:lodash|moment|antd)" --type js --type ts

# 2. 找到可能的記憶體洩漏
rg "(setInterval|setTimeout)" --type js --type ts -A 2

# 3. 搜尋未最佳化的圖片載入
rg "(<img|\.jpg|\.png|\.gif)" --type jsx --type tsx

# 4. 檢查 console.log (除錯程式碼)
rg "console\.(log|error|warn)" --type js --type ts

# 5. 找到重複渲染問題
rg "(useEffect.*\[\]|componentDidMount)" --type jsx --type tsx -C 2
```

**效能分析報告**:
```
🐌 發現的效能問題：
1. 大型套件：lodash 完整匯入 (建議使用 tree-shaking)
2. 圖片最佳化：發現 20+ 未壓縮圖片  
3. 除錯程式碼：12 個 console.log 未移除
4. 記憶體洩漏：3 個 setInterval 未清理
```

### 場景 4: 安全性稽核
**背景**: 檢查專案中的潛在安全問題

```bash
# 1. 搜尋硬編碼的敏感資料
rg "(password|secret|key|token).*[=:].*['\"][^'\"]{8,}" -i

# 2. 檢查 SQL 注入風險
rg "(SELECT|INSERT|UPDATE|DELETE).*\+.*" --type js --type ts

# 3. 找到 XSS 風險點
rg "(innerHTML|dangerouslySetInnerHTML)" --type jsx --type tsx

# 4. 檢查不安全的 HTTP 請求
rg "http://" --type js --type ts

# 5. 找到檔案上傳功能
rg "(upload|multer|formData)" --type js --type ts -C 2
```

**安全性報告**:
```
🔒 安全性檢查結果：
✅ 無硬編碼密碼
⚠️ 發現 3 個 http:// 連結 (建議改用 https)
⚠️ 2 個 dangerouslySetInnerHTML 使用 (需檢查輸入清理)
✅ 檔案上傳有適當驗證
```

### 場景 5: 程式碼品質檢查
**背景**: 檢查程式碼風格和最佳實踐遵循情況

```bash
# 1. 檢查 TypeScript 型別使用
rg ": any|as any" --type ts --type tsx

# 2. 找到過長的函數 (超過 20 行)
rg "function.*\{" --type js --type ts -A 25 | grep -E "(function|const.*=.*\{)" -A 25

# 3. 搜尋魔法數字
rg "[^a-zA-Z_][0-9]{2,}[^a-zA-Z_]" --type js --type ts

# 4. 檢查註解覆蓋率
rg "^[[:space:]]*(//|/\*|\*)" --type js --type ts | wc -l

# 5. 找到重複程式碼
rg "function.*\(" --type js --type ts | sort | uniq -d
```

**品質報告**:
```
📊 程式碼品質分析：
- TypeScript：89% 型別化 (11% 使用 any)
- 函數長度：平均 15 行 (2 個超過 30 行)  
- 註解覆蓋：23% (建議提升至 40%+)
- 魔法數字：發現 8 個 (建議使用常數)
```

## 🎨 高級搜尋技巧

### 組合搜尋模式
```bash
# 找到所有 React Hooks 使用
rg "use(State|Effect|Context|Memo|Callback|Ref)" --type jsx --type tsx

# 搜尋特定模式的函數定義
rg "^(export\s+)?(const\s+|function\s+)\w+.*=.*\(" --type js --type ts

# 找到所有 CSS-in-JS 使用
rg "(styled\.|css`|emotion)" --type js --type jsx -C 1
```

### 條件搜尋
```bash
# 搜尋包含特定文字但排除測試檔案
rg "API_ENDPOINT" --type js --glob "!**/*test*" --glob "!**/*spec*"

# 在特定目錄中搜尋
rg "component" --type tsx --glob "src/components/**/*"

# 搜尋最近修改的檔案中的內容
fd --changed-within 7d --type f -e js -e ts -x rg "TODO" {}
```

### 結果處理
```bash
# 統計各種檔案類型數量
fd -e js -e ts -e jsx -e tsx | xargs wc -l | sort -rn

# 找到最大的檔案
fd -e js -e ts -e jsx -e tsx -x wc -c {} + | sort -rn | head -10

# 分析 import 依賴
rg "import.*from.*['\"](\w+)" --type js --type ts -o | sort | uniq -c | sort -rn
```

## 💡 AI 協作最佳實踐

### 漸進式搜尋策略
1. **廣泛搜尋**: 先找到相關檔案和目錄
2. **精確定位**: 使用具體關鍵詞搜尋
3. **上下文分析**: 查看程式碼前後脈絡
4. **關聯探索**: 找到相關的函數和模組

### 結果解釋範本
```
🔍 搜尋結果：[檔案數量] 個檔案，[匹配數量] 個匹配

📁 相關檔案：
- file1.js - [簡短描述]
- file2.ts - [簡短描述]

💡 關鍵發現：
- [重要發現 1]
- [重要發現 2]

🔗 相關程式碼：
[程式碼片段或位置]

📋 建議行動：
- [建議 1]
- [建議 2]
```

### 常見問題解決

**問題**: "找不到檔案"
**解決**:
```bash
# 檢查檔案是否存在
fd -u "filename"  # 包含隱藏檔案

# 檢查大小寫敏感
fd -i "filename"  # 忽略大小寫
```

**問題**: "搜尋結果太多"
**解決**:
```bash
# 限制搜尋範圍
rg "pattern" --max-count 20

# 使用更精確的模式
rg "\bexact_word\b" --type js
```

**問題**: "搜尋太慢"
**解決**:
```bash
# 限制搜尋深度
fd "pattern" --max-depth 5

# 排除大型目錄
rg "pattern" --glob "!node_modules" --glob "!dist"
```