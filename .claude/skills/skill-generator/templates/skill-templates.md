# Claude Skills 範本庫

根據 Claude Code Skills 標準提供的完整技能範本集合。

## 1. Reference Content 技能範本

### 基礎參考範本
```yaml
---
name: ${SKILL_NAME}
description: ${SKILL_DESCRIPTION}
user-invocable: false
---

# ${SKILL_TITLE}

${SKILL_CONTENT}

## 相關資源

查看 [examples/](examples/) 獲取更多使用範例。
```

### API 文檔範本
```yaml
---
name: api-reference
description: 專案 API 端點文檔和使用指南
user-invocable: false
---

# API 參考文檔

## 端點列表

### 使用者管理
- `POST /api/users` - 建立新使用者
- `GET /api/users/{id}` - 取得使用者資訊
- `PUT /api/users/{id}` - 更新使用者資訊
- `DELETE /api/users/{id}` - 刪除使用者

## 認證方式
所有 API 請求需要包含 Bearer token：
```
Authorization: Bearer <your-token>
```

## 錯誤格式
```json
{
  "error": "error_code",
  "message": "Human readable error message",
  "details": {}
}
```

詳細的 API 規格請參考 [api-spec.md](api-spec.md)。
```

### 編碼規範範本
```yaml
---
name: coding-standards
description: 專案程式碼風格指南和最佳實踐
user-invocable: false
---

# 程式碼規範

## 命名規範
- 變數：使用 camelCase
- 常數：使用 UPPER_SNAKE_CASE  
- 函數：使用 camelCase
- 類別：使用 PascalCase

## 程式碼結構
- 每個檔案最多 300 行
- 每個函數最多 50 行
- 適當使用註解說明複雜邏輯

## 錯誤處理
- 總是處理可能的錯誤情況
- 使用明確的錯誤訊息
- 記錄重要的錯誤資訊

完整的風格指南請參考 [style-guide.md](style-guide.md)。
```

---

## 2. Task Content 技能範本

### 基礎任務範本
```yaml
---
name: ${SKILL_NAME}
description: ${SKILL_DESCRIPTION}
disable-model-invocation: true
allowed-tools: ${ALLOWED_TOOLS}
---

# ${SKILL_TITLE}

執行 ${TASK_NAME}：$ARGUMENTS

## 執行步驟

1. ${STEP_1}
2. ${STEP_2}  
3. ${STEP_3}
4. ${STEP_4}

## 驗證結果

執行完成後驗證：
- ${VALIDATION_1}
- ${VALIDATION_2}
```

### 部署技能範本
```yaml
---
name: deploy
description: 部署應用程式到指定環境
disable-model-invocation: true
allowed-tools: Bash
argument-hint: [environment] [version]
---

# 應用程式部署

部署應用程式到 $ARGUMENTS 環境。

## 部署流程

1. **環境檢查**
   ```bash
   # 檢查目標環境狀態
   kubectl get nodes
   docker ps
   ```

2. **建置應用程式**
   ```bash
   # 建置並標記映像
   docker build -t app:$VERSION .
   docker tag app:$VERSION registry/app:$VERSION
   ```

3. **推送到註冊表**
   ```bash
   # 推送映像
   docker push registry/app:$VERSION
   ```

4. **執行部署**
   ```bash
   # 部署到 Kubernetes
   kubectl apply -f k8s/
   kubectl set image deployment/app app=registry/app:$VERSION
   ```

5. **驗證部署**
   ```bash
   # 檢查部署狀態
   kubectl rollout status deployment/app
   kubectl get pods
   curl -f http://app-url/health
   ```

## 回滾程序

如果部署失敗：
```bash
kubectl rollout undo deployment/app
```

詳細的部署指南請參考 [deployment-guide.md](deployment-guide.md)。
```

### 測試執行範本
```yaml
---
name: run-tests
description: 執行專案測試套件
disable-model-invocation: true
allowed-tools: Bash
argument-hint: [test-type] [pattern]
---

# 測試執行器

執行測試：$ARGUMENTS

## 測試類型

### 單元測試
```bash
npm test
# 或
go test ./...
# 或  
pytest tests/unit/
```

### 整合測試
```bash
npm run test:integration
# 或
go test -tags=integration ./...
# 或
pytest tests/integration/
```

### 端對端測試
```bash
npm run test:e2e
# 或
pytest tests/e2e/
```

## 覆蓋率報告
```bash
# 生成覆蓋率報告
npm run test:coverage
open coverage/index.html
```

## 持續整合

本技能也會在 CI/CD 流水線中自動執行：
- Push 到 main 分支時執行所有測試
- Pull Request 時執行單元測試和整合測試
- 發布時執行完整測試套件

測試配置詳見 [testing-guide.md](testing-guide.md)。
```

---

## 3. Hybrid 技能範本

### 分析+執行範本
```yaml
---
name: performance-optimizer
description: 分析效能問題並提供最佳化建議
allowed-tools: Read, Grep, Bash
---

# 效能最佳化技能

## 效能分析原則

### 常見瓶頸
- 資料庫查詢過慢
- 記憶體洩漏
- 不必要的網路請求
- 未最佳化的演算法

### 分析工具
- 效能剖析器（Profiler）
- 記憶體分析器
- 網路監控工具
- 資料庫查詢分析

## 執行效能分析

分析 $ARGUMENTS 的效能問題：

1. **收集基準資料**
   ```bash
   # 記錄當前效能指標
   time ./app benchmark
   ```

2. **執行剖析**
   ```bash
   # 使用適當的剖析工具
   go tool pprof ./app
   # 或
   python -m cProfile app.py
   ```

3. **分析結果**
   - 識別最耗時的函數
   - 檢查記憶體使用模式
   - 分析 I/O 操作效率

4. **實施最佳化**
   - 最佳化演算法複雜度
   - 快取頻繁查詢的資料
   - 減少不必要的記憶體分配

5. **驗證改善**
   ```bash
   # 重新測試效能
   time ./app benchmark
   ```

詳細的最佳化策略請參考 [optimization-guide.md](optimization-guide.md)。
```

### 程式碼品質範本
```yaml
---
name: code-quality
description: 程式碼品質分析和改善建議
allowed-tools: Read, Grep, Bash
---

# 程式碼品質管理

## 品質標準

### 可讀性指標
- 函數長度 < 50 行
- 循環複雜度 < 10
- 適當的變數命名
- 充分的註解說明

### 可維護性指標
- 模組化設計
- 低耦合高內聚
- 遵循設計原則
- 適當的測試覆蓋率

## 執行品質檢查

分析 $ARGUMENTS 的程式碼品質：

1. **靜態分析**
   ```bash
   # JavaScript
   eslint src/
   
   # Python  
   pylint src/
   
   # Go
   golint ./...
   go vet ./...
   ```

2. **複雜度分析**
   ```bash
   # 使用 sonarqube 或類似工具
   sonar-scanner
   ```

3. **安全性掃描**
   ```bash
   # 使用安全性掃描工具
   npm audit
   safety check
   gosec ./...
   ```

4. **測試覆蓋率**
   ```bash
   # 檢查測試覆蓋率
   npm run test:coverage
   go test -cover ./...
   pytest --cov=src tests/
   ```

## 改善建議

基於分析結果提供：
- 重構建議
- 設計模式應用
- 效能最佳化機會
- 安全性改善

品質改善流程請參考 [quality-guide.md](quality-guide.md)。
```

---

## 4. 特殊功能範本

### 子代理執行範本
```yaml
---
name: research-assistant
description: 深度研究和分析助手
context: fork
agent: Explore
---

# 研究助手

在隔離環境中執行深度研究：$ARGUMENTS

## 研究方法

1. **資料收集**
   - 使用 Glob 尋找相關檔案
   - 使用 Grep 搜尋關鍵內容
   - 閱讀和分析文檔

2. **模式分析**
   - 識別程式碼模式
   - 分析架構設計
   - 找出潛在問題

3. **結論整理**
   - 提供結構化報告
   - 包含具體檔案參考
   - 給出可操作建議

## 研究範圍

此技能特別適用於：
- 大型程式碼庫分析
- 技術債務評估
- 架構決策支援
- 最佳實踐識別

研究結果將以摘要形式返回到主對話中。
```

### 動態上下文範本
```yaml
---
name: git-status-helper
description: Git 狀態分析和操作建議
allowed-tools: Bash
---

# Git 狀態助手

## 當前狀態
- 分支狀態：!`git branch --show-current`
- 工作區狀態：!`git status --porcelain`
- 最近提交：!`git log --oneline -5`
- 遠端同步：!`git fetch && git status`

## 建議操作

根據目前的 Git 狀態，建議執行 $ARGUMENTS 相關操作：

### 常見工作流程

1. **提交變更**
   ```bash
   git add .
   git commit -m "描述性提交訊息"
   ```

2. **同步遠端**
   ```bash
   git pull origin main
   git push origin feature-branch
   ```

3. **分支管理**
   ```bash
   git checkout -b new-feature
   git merge feature-branch
   ```

操作前會自動檢查工作區狀態以避免衝突。
```

### 鉤子整合範本
```yaml
---
name: auto-formatter
description: 自動格式化程式碼
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

根據檔案類型自動選擇格式化工具：

- **JavaScript/TypeScript**: Prettier
- **Go**: gofmt
- **Python**: black + isort
- **Java**: google-java-format
- **Rust**: rustfmt

## 自動觸發

每次編輯檔案後會自動執行對應的格式化工具。

## 手動格式化

手動格式化特定檔案或目錄：$ARGUMENTS

```bash
# 格式化整個專案
scripts/format-code.sh all

# 格式化特定檔案
scripts/format-code.sh src/main.js
```

格式化規則配置請參考 [format-config.md](format-config.md)。
```

---

## 使用指南

### 1. 選擇適合的範本
- **Reference**: 提供背景知識，不執行動作
- **Task**: 執行特定動作，有明確的輸入輸出
- **Hybrid**: 結合知識提供和動作執行
- **Special**: 使用進階功能（子代理、鉤子等）

### 2. 客製化範本
將 `${VARIABLE}` 替換為實際值：
- `${SKILL_NAME}`: 技能名稱
- `${SKILL_DESCRIPTION}`: 技能描述  
- `${ALLOWED_TOOLS}`: 允許的工具列表
- `${TASK_NAME}`: 任務名稱

### 3. 測試和驗證
- 使用 `/skill-generator validate` 檢查格式
- 測試技能在不同場景下的行為
- 確保文檔和範例的準確性