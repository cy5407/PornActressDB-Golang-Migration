# Copilot Agent 任務範本

> 複製以下範本到 Chat 中，讓 Agent 自動執行完整流程

## 🎯 範本 1：新增功能（含測試驗證）

```
請幫我實作以下功能，並**自動執行測試驗證**：

【功能需求】
- 在 `pkg/newmodule` 新增 XXX 功能
- 需要處理 YYY 情況
- 輸出格式為 JSON

【驗證要求】
- 撰寫單元測試（覆蓋率 >80%）
- 執行 `go test ./pkg/newmodule -v` 確認通過
- 更新 CLI (`cmd/scanner/main.go`) 並測試指令
- 整合至 Python (`src/services/go_bridge.py`)
- 執行 `python -m pytest tests/ -v` 確認無破壞

**請主動執行所有測試，若失敗請自動修復，直到全部通過。**
```

---

## 🔧 範本 2：修復錯誤（自動循環）

```
以下測試失敗，請**自動修復並重新測試**：

【錯誤資訊】
（貼上錯誤訊息或測試輸出）

【修復流程】
1. 分析錯誤原因
2. 修改相關程式碼
3. 執行 `python -m pytest tests/test_XXX.py -v` 驗證
4. 若仍失敗，重複步驟 2-3
5. 確認所有測試通過後回報

**無需詢問，直接執行修復循環。**
```

---

## 🚀 範本 3：整合測試（Python + Go）

```
請執行完整的整合測試流程：

1. **Go 模組測試**
   - `go test ./... -v`
   - 檢查是否有編譯錯誤

2. **Python 模組測試**
   - `python -m pytest tests/ -v`
   - 檢查橋接層 (`go_bridge.py`) 是否正常

3. **CLI 功能測試**
   - `go build -o classifier.exe ./cmd/scanner`
   - `./classifier.exe scan ./test_data`
   - 驗證 JSON 輸出格式

4. **整合測試**
   - `python test_go_db_bridge.py`

**若任何步驟失敗，請自動修復並重新執行。最終提供測試報告。**
```

---

## 📊 範本 4：效能優化（含基準測試）

```
請優化以下功能的效能：

【目標】
- 檔案掃描速度提升 2 倍
- 記憶體使用降低 30%

【步驟】
1. 執行基準測試：`go test -bench=. -benchmem ./pkg/extractor`
2. 記錄初始數據
3. 實作優化（並發處理、快取等）
4. 重新執行基準測試
5. 比較結果並確認測試通過

**請自動執行並提供優化前後對比。**
```

---

## 🛠️ 範本 5：重構代碼（保證零破壞）

```
請重構以下模組，並確保零破壞：

【重構目標】
- 檔案：`src/services/XXX.py`
- 目的：提升可讀性、減少重複代碼

【安全流程】
1. 執行重構前測試：`python -m pytest tests/ -v`
2. 記錄通過的測試數量
3. 執行重構
4. 重新執行測試
5. 確認測試數量不變且全通過
6. 若有失敗，回滾並重新調整

**請自動執行完整流程，確保無任何測試被破壞。**
```

---

## 💡 使用技巧

### 觸發 Agent 自主模式的關鍵字
在對話中使用以下詞語，Agent 會更主動：

- ✅ **「自動執行」**「主動測試」「循環修復」
- ✅ **「直到通過」**「無需詢問」**「完整驗證」**
- ✅ **「若失敗請修復」**「重複嘗試」**「自主完成」**

### 避免使用的被動詞語
- ❌ 「幫我看看」「建議」「可能需要」
- ❌ 「請告訴我」「你覺得」「應該如何」

---

## 📝 自訂範本

您可以根據需求調整範本，重點是明確告知 Agent：

1. **具體任務**（要做什麼）
2. **驗證步驟**（如何確認完成）
3. **自動化指令**（直接執行，不要只建議）
4. **錯誤處理**（失敗後如何修復）

---

## 🔗 快速啟動指令

將以下指令加入終端機別名，快速觸發測試：

```powershell
# 加入 PowerShell Profile ($PROFILE)
function Test-All {
    Write-Host "🧪 執行 Go 測試..." -ForegroundColor Cyan
    go test ./... -v
    Write-Host "🐍 執行 Python 測試..." -ForegroundColor Yellow
    python -m pytest tests/ -v
}
Set-Alias -Name ta -Value Test-All

function Build-CLI {
    Write-Host "🔨 建構 CLI..." -ForegroundColor Green
    go build -o classifier.exe ./cmd/scanner
    Write-Host "✅ 建構完成！" -ForegroundColor Green
}
Set-Alias -Name bc -Value Build-CLI
```

使用方式：
- 輸入 `ta` → 執行所有測試
- 輸入 `bc` → 建構 Go CLI

---

**提示**：將此檔案加入 VS Code 快速開啟清單：  
`Ctrl + P` → 輸入 `COPILOT_TEMPLATES.md` → 快速複製範本使用！
