# 🤖 Copilot Agent 自動化設定

> 讓 GitHub Copilot 像 Ralph 一樣自主完成開發任務

## 📁 設定檔案索引

| 檔案 | 用途 | 立即開啟 |
|------|------|---------|
| **[AGENT_SETUP_GUIDE.md](AGENT_SETUP_GUIDE.md)** | 📖 完整設定指南與使用說明 | ⭐ **必讀** |
| **[copilot-instructions.md](copilot-instructions.md)** | 🧠 Agent 行為準則與開發規範 | [開啟](copilot-instructions.md) |
| **[COPILOT_TEMPLATES.md](COPILOT_TEMPLATES.md)** | 📋 任務範本庫（快速複製使用） | [開啟](COPILOT_TEMPLATES.md) |
| **[AGENT_LOG.md](AGENT_LOG.md)** | 📝 任務執行記錄與統計 | [開啟](AGENT_LOG.md) |
| **[agent_verify.py](agent_verify.py)** | 🧪 自動化驗證腳本 | [執行](agent_verify.py) |
| **[powershell_aliases.ps1](powershell_aliases.ps1)** | ⚡ PowerShell 快捷指令 | [開啟](powershell_aliases.ps1) |

---

## ⚡ 快速開始（3 步驟）

### 1️⃣ 確認設定已生效

在終端機執行：
```powershell
python .github\agent_verify.py
```

**預期結果**：看到「✅ 通過」的測試項目

### 2️⃣ 載入 PowerShell 快捷指令（可選）

```powershell
# 開啟 Profile 編輯器
notepad $PROFILE

# 在檔案末尾加入：
. "C:\Users\cy540\OneDrive\桌面\PornActressDB-Golang-Migration\.github\powershell_aliases.ps1"

# 儲存後重新載入
. $PROFILE

# 測試是否成功
ah  # 應該顯示指令列表
```

### 3️⃣ 測試 Agent 模式

1. 在 VS Code 按 `Ctrl + Alt + I` 開啟 Chat
2. 確認上方模式為 **"Agent"**（而非 "Chat"）
3. 貼上以下測試提示詞：

```
請執行 go test ./... -v 並回報測試結果
```

**正確行為**：Agent 會顯示「我將執行...」並請求授權  
**錯誤行為**：Agent 只回覆「您可以執行...」→ 表示未進入 Agent 模式

---

## 🎯 核心功能

### ✅ 已啟用的自動化能力

- ✅ **自動執行測試**（Python pytest / Go test）
- ✅ **自動編譯檢查**（Go build）
- ✅ **錯誤循環修復**（失敗 → 分析 → 修改 → 重新測試）
- ✅ **多步驟任務**（新增功能 → 寫測試 → 整合 → 驗證）
- ✅ **終端機授權**（自動請求執行指令權限）

### 📋 使用範本（快速複製）

開啟 [COPILOT_TEMPLATES.md](COPILOT_TEMPLATES.md) 可找到：

- 範本 1：新增功能（含測試驗證）
- 範本 2：修復錯誤（自動循環）
- 範本 3：整合測試（Python + Go）
- 範本 4：效能優化（含基準測試）
- 範本 5：重構代碼（保證零破壞）

---

## 🛠️ PowerShell 快捷指令

載入 `powershell_aliases.ps1` 後可使用：

| 指令 | 功能 | 說明 |
|------|------|------|
| `ta` | Test-All | 執行完整自動驗證 |
| `tp` | Test-Python | 僅執行 Python 測試 |
| `tg` | Test-Go | 僅執行 Go 測試 |
| `bc` | Build-CLI | 建構 classifier.exe |
| `ba` | Build-All | 完整編譯檢查 |
| `ac` | Agent-Check | 檢查 Agent 設定檔案 |
| `ag` | Agent-Guide | 開啟設定指南 |
| `at` | Agent-Templates | 開啟任務範本 |
| `ps` | Project-Status | 顯示專案狀態 |
| `ah` | Show-AgentHelp | 顯示指令說明 |

---

## 📊 驗證結果示例

執行 `ta`（或 `python .github\agent_verify.py`）後：

```
============================================================
                   🤖 Copilot Agent 自動化驗證
============================================================

專案路徑: C:\Users\...\PornActressDB-Golang-Migration
開始時間: 2026-01-11 23:17:51

============================================================
                         🔷 Go 模組驗證
============================================================

▶ Go 編譯檢查
  指令: go build ./...
✅ 成功

▶ Go 單元測試
  指令: go test ./... -v -short
✅ 成功

============================================================
                       🐍 Python 模組驗證
============================================================

▶ Python 語法檢查
✅ 語法檢查通過

============================================================
                          📊 驗證結果總結
============================================================

  Go 編譯................................... ✅ 通過
  Go 測試................................... ✅ 通過
  Python 語法............................... ✅ 通過
  整合測試.................................. ✅ 通過

總計: 5/6 項通過
```

---

## 🔑 關鍵設定檔案

### `.github/copilot-instructions.md`（最重要）

定義 Agent 的行為準則：

```markdown
## 自主執行準則
1. 理解需求 → 規劃步驟
2. 實作代碼 → 執行驗證
3. 若失敗 → 自動修復
4. 重複步驟 2-3 → 直到全部通過

## 終端機權限
- python -m pytest tests/ -v
- go test ./... -v
- go build -o classifier.exe
```

### `.vscode/settings.json`

啟用自動執行權限：

```jsonc
{
  "chat.tools.terminal.autoApprove": {
    "pytest": true,
    "go test": true,
    "go build": true
  },
  "chat.useAgentSkills": true
}
```

---

## 🚨 常見問題

### ❓ Agent 不會自動執行指令？

**檢查清單**：
1. Chat 面板是否為 **"Agent"** 模式？
2. `.vscode/settings.json` 是否有 `chat.tools.terminal.autoApprove`？
3. 是否有授權執行權限（首次會彈出確認）？

### ❓ 如何記錄 Agent 執行歷史？

在 [AGENT_LOG.md](AGENT_LOG.md) 中手動記錄任務結果，格式：

```markdown
### [2026-01-11 14:30] 新增雜湊功能

**需求**：新增 SHA256 檔案雜湊計算

**執行步驟**：
1. ✅ 建立 pkg/hasher/hasher.go
2. ✅ 撰寫測試並通過

**最終狀態**：✅ 完成
```

---

## 📚 延伸閱讀

- [完整設定指南](AGENT_SETUP_GUIDE.md) - 詳細說明與範例
- [任務範本庫](COPILOT_TEMPLATES.md) - 可直接複製的提示詞
- [GitHub Copilot 官方文件](https://docs.github.com/copilot/)

---

## 🎉 立即體驗

1. **打開 VS Code Chat**（`Ctrl + Alt + I`）
2. **切換至 Agent 模式**
3. **複製範本**（從 [COPILOT_TEMPLATES.md](COPILOT_TEMPLATES.md)）
4. **觀察自動執行**

**範例提示詞**：
```
請幫我修復 tests/test_json_statistics.py 中的 8 個失敗測試。

要求：
1. 分析錯誤原因
2. 修改程式碼
3. 執行 python -m pytest tests/test_json_statistics.py -v 驗證
4. 若失敗，重複步驟 2-3 直到全部通過

請自動執行，無需詢問。
```

---

**提示**：按 `Ctrl + K Ctrl + B` 將此 README 加入書籤！
