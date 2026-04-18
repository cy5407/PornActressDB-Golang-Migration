# GitHub Copilot Agent 自動化設定指南

> **目標**：讓 Copilot Agent 像 Ralph 一樣自主完成開發任務

## ✅ 已完成的設定

### 1. **核心設定檔案**

| 檔案 | 用途 | 狀態 |
|------|------|------|
| [.github/copilot-instructions.md](.github/copilot-instructions.md) | Agent 行為準則與專案規範 | ✅ 已優化 |
| [.vscode/settings.json](.vscode/settings.json) | VS Code 整合設定 | ✅ 已更新 |
| [.github/COPILOT_TEMPLATES.md](.github/COPILOT_TEMPLATES.md) | 任務範本庫 | ✅ 已建立 |
| [.github/AGENT_LOG.md](.github/AGENT_LOG.md) | 任務執行記錄 | ✅ 已建立 |
| [.github/agent_verify.py](.github/agent_verify.py) | 自動驗證腳本 | ✅ 已建立 |

---

## 🚀 如何使用 Agent 模式

### 方法 1：VS Code Chat 面板

1. **開啟 Chat**：按 `Ctrl + Alt + I`（或點選左側 Chat 圖示）

2. **確認模式**：在對話框上方確認已選擇 **"Agent"** 模式（而非 "Chat"）

3. **使用任務範本**：
   - 打開 [.github/COPILOT_TEMPLATES.md](.github/COPILOT_TEMPLATES.md)
   - 複製適合的範本（例如「範本 1：新增功能」）
   - 貼到 Chat 中並調整需求

4. **觀察自動執行**：
   - Agent 會主動請求執行終端機指令
   - 點選 **"Allow"** 授權執行
   - Agent 會自動循環「修改 → 測試 → 修復」直到完成

### 方法 2：Inline Chat（快速修改）

1. **選取代碼**：在編輯器中選取要修改的程式碼
2. **開啟 Inline Chat**：按 `Ctrl + I`
3. **輸入指令**：
   ```
   重構此函式並執行測試驗證
   ```
4. **自動執行**：Agent 會在背景執行測試

---

## 📋 關鍵設定說明

### `.vscode/settings.json` 重點

```jsonc
{
  // 允許自動執行終端機指令（最重要的設定）
  "chat.tools.terminal.autoApprove": {
    "pytest": true,        // Python 測試
    "go test": true,       // Go 測試
    "go build": true,      // Go 編譯
    "python -m": true      // Python 模組指令
  },

  // 啟用 Agent 技能
  "chat.useAgentSkills": true,

  // 讀取自定義指令檔
  "github.copilot.chat.codeGeneration.useInstructionFiles": true
}
```

### `.github/copilot-instructions.md` 關鍵區塊

#### 1. **自主執行準則**（告訴 Agent 要循環執行）
```markdown
1. 理解需求 → 規劃步驟
2. 實作代碼 → 執行驗證
3. 若失敗 → 自動修復
4. 重複步驟 2-3 → 直到全部通過
```

#### 2. **終端機權限清單**（授權可執行的指令）
```bash
python -m pytest tests/ -v     # 單元測試
go test ./... -v               # Go 測試
go build -o classifier.exe     # 編譯 CLI
```

#### 3. **錯誤處理自動化**（遇錯自動修復）
```markdown
- Import Error → 執行 pip install
- Test Failure → 分析錯誤 → 修改代碼 → 重新測試
```

---

## 🎯 實戰範例

### 範例 1：請 Agent 修復測試失敗

**在 Chat 中輸入：**
```
目前有 8 個 Python 測試失敗（檔案：tests/test_json_statistics.py）

請自動修復這些錯誤：
1. 分析測試失敗原因
2. 修改相關程式碼
3. 執行 python -m pytest tests/test_json_statistics.py -v 驗證
4. 若仍失敗，重複步驟 2-3
5. 直到所有測試通過

無需詢問，直接開始修復。
```

**Agent 會自動執行：**
1. 讀取測試檔案
2. 執行測試查看錯誤
3. 分析錯誤訊息（例如：`missing 1 required positional argument: 'info'`）
4. 修改 `src/models/json_database.py`
5. 重新執行測試
6. 若失敗，重複步驟 4-5
7. 全部通過後回報結果

### 範例 2：新增功能並整合

**在 Chat 中輸入：**
```
請在 pkg/logger 新增日誌功能：
- 支援多等級（DEBUG/INFO/WARN/ERROR）
- 自動輪轉（每日新檔）
- 寫入 logs/ 目錄

完成後：
1. 撰寫單元測試（覆蓋率 >80%）
2. 執行 go test ./pkg/logger -v 確認通過
3. 更新 CLI (cmd/scanner/main.go) 整合日誌
4. 執行 go build 確認編譯成功

請自動執行所有步驟。
```

---

## 🔍 驗證設定是否生效

### 手動測試

1. **開啟 Chat**（`Ctrl + Alt + I`）

2. **輸入測試指令**：
   ```
   請執行 go test ./... -v 並回報結果
   ```

3. **觀察行為**：
   - ✅ **正確**：Agent 顯示「我將執行...」並請求授權
   - ❌ **錯誤**：Agent 只回覆「您可以執行...」（表示未進入 Agent 模式）

### 自動驗證

執行驗證腳本：
```powershell
python .github\agent_verify.py
```

**預期結果**：
```
📊 驗證結果總結
  Go 編譯....................... ✅ 通過
  Go 測試....................... ✅ 通過
  Python 語法................... ✅ 通過
  ...
```

---

## 🛠️ 進階設定（可選）

### 1. 設定終端機別名（加速測試）

編輯 PowerShell Profile：
```powershell
notepad $PROFILE
```

加入以下內容：
```powershell
# 快速測試
function Test-All {
    Write-Host "🧪 執行完整測試..." -ForegroundColor Cyan
    python .github\agent_verify.py
}
Set-Alias -Name ta -Value Test-All

# 快速建構
function Build-CLI {
    go build -o classifier.exe ./cmd/scanner
    Write-Host "✅ CLI 建構完成" -ForegroundColor Green
}
Set-Alias -Name bc -Value Build-CLI

# Agent 驗證
function Agent-Check {
    Write-Host "🤖 檢查 Agent 設定..." -ForegroundColor Magenta
    if (Test-Path ".github\copilot-instructions.md") {
        Write-Host "✅ Instructions 存在" -ForegroundColor Green
    } else {
        Write-Host "❌ Instructions 遺失" -ForegroundColor Red
    }
}
Set-Alias -Name ac -Value Agent-Check
```

使用：
- `ta` → 執行完整測試
- `bc` → 建構 CLI
- `ac` → 檢查 Agent 設定

### 2. 啟用 MCP 伺服器（未來擴充）

若要讓 Agent 存取更多工具（例如資料庫、API），可新增 MCP 伺服器：

在 `.vscode/settings.json` 加入：
```jsonc
{
  "github.copilot.chat.mcp.servers": [
    {
      "name": "local-database",
      "command": "python",
      "args": ["tools/mcp_server.py"]
    }
  ]
}
```

---

## 📊 效果對比

| 功能 | 傳統 Copilot Chat | Agent 模式 |
|------|------------------|-----------|
| 代碼建議 | ✅ 支援 | ✅ 支援 |
| 執行測試 | ❌ 需手動 | ✅ 自動執行 |
| 錯誤修復 | ❌ 只建議 | ✅ 自動循環修復 |
| 多步驟任務 | ❌ 需分次詢問 | ✅ 一次完成 |
| 終端機操作 | ❌ 不支援 | ✅ 自動請求授權 |

---

## 🚨 常見問題

### Q1：Agent 不會自動執行指令？

**檢查清單**：
1. Chat 面板上方是否顯示 **"Agent"** 模式（而非 "Chat"）？
2. `.vscode/settings.json` 是否有 `"chat.tools.terminal.autoApprove"`？
3. 是否有授權執行權限（首次會彈出確認視窗）？

### Q2：Agent 只回覆建議，不實際操作？

**解決方式**：在提示詞中加入明確指令：
- ✅ **正確**：「請執行 go test 並回報結果」
- ❌ **錯誤**：「我應該如何測試？」

### Q3：如何限制 Agent 的權限？

編輯 `.vscode/settings.json`：
```jsonc
{
  "chat.tools.terminal.autoApprove": {
    // 只允許測試指令，禁止刪除/修改系統檔案
    "pytest": true,
    "go test": true,
    "rm": false,      // 禁止刪除
    "del": false      // 禁止刪除
  }
}
```

---

## 📚 延伸閱讀

- [GitHub Copilot Agent 官方文件](https://docs.github.com/copilot/using-github-copilot/using-chat-features-in-your-ide#agent-mode)
- [VS Code Copilot Chat API](https://code.visualstudio.com/api/extension-guides/chat)
- [MCP Protocol 規範](https://modelcontextprotocol.io/)

---

## 🎉 下一步

1. **立即測試**：複製 [任務範本](.github/COPILOT_TEMPLATES.md) 到 Chat 中試用
2. **記錄結果**：在 [AGENT_LOG.md](.github/AGENT_LOG.md) 追蹤任務執行狀態
3. **持續優化**：根據實際使用經驗調整 `copilot-instructions.md`

---

**提示**：將此檔案加入書籤（`Ctrl + K Ctrl + B`），隨時查閱使用指南！
