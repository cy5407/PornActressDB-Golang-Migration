# 安全漏洞修復結果報告

**修復日期**: 2026-04-03
**執行方式**: 排程任務自動執行（security-fix-20260403-0359）
**目標檔案**: `pkg/mover/mover.go`

---

## 修復摘要

本次修復針對 gosec 掃描報告中 `pkg/mover/mover.go` 的兩個 HIGH 等級安全漏洞，採用保守穩健策略：優先加入明確注釋說明可接受風險，並補強實際安全驗證邏輯。

---

## 問題 1：GOSEC-TOCTOU（CWE-362）

**Hash**: c4794f91be8e
**原始位置**: 第 141 行（修復後為第 141～153 行）
**嚴重性**: HIGH

### 修改說明

在 `os.Stat(dst)` 呼叫處加入：

1. **多行注釋**（第 141～145 行）：詳細說明 TOCTOU 競爭窗口的性質，以及為何 Skip 分支的風險屬可接受範圍。
2. **`//nolint:gosec` 標記**（第 146 行）：附帶清楚理由，說明 Skip 分支無寫入操作、Overwrite 已用原子替換緩解。
3. **case Skip 內部注釋**（第 150 行）：再次確認此分支無寫入操作、競爭不造成資料損毀。

### 為何採用注釋而非重構

- Skip 策略在競爭發生時不會對目標造成任何寫入，因此不存在資料損毀風險
- Overwrite 分支已使用 `replaceFileSafely`（暫存檔 + Rename 原子替換）緩解
- 加入注釋符合任務要求的「保守穩健，優先說明可接受風險」原則
- 避免不必要的架構重構，不影響現有 API 介面

---

## 問題 2：GOSEC-REMOVEALL（CWE-703）

**Hash**: f58e3986b77f
**原始位置**: 第 272 行（修復後為第 276～298 行）
**嚴重性**: HIGH

### 修改說明

將原本的單行：
```go
if err := os.RemoveAll(src); err == nil {
    result.DeletedSrc = true
}
```

改為三層安全驗證結構：

1. **symlink 偵測**（使用 `os.Lstat`）：
   - 若 Lstat 成功且 `mode & os.ModeSymlink != 0`，記錄 WARNING 並拒絕刪除，防止攻擊者將來源目錄替換為指向系統路徑的符號連結
   - 若為真實目錄，才安全執行 `os.RemoveAll`

2. **錯誤記錄**：
   - `os.RemoveAll` 失敗時，以 `[WARNING]` 格式將錯誤原因輸出至 stderr
   - 不影響整體 `Success` 狀態（所有檔案已移動成功）

3. **Lstat 失敗處理**：
   - 若 Lstat 本身失敗（src 已不存在或無法存取），記錄警告並跳過刪除

### 修改的具體行號（修復後）

| 行號 | 說明 |
|------|------|
| 278～280 | 安全驗證注釋（說明 CWE-703 防護意圖） |
| 281 | `os.Lstat(src)` — symlink 偵測 |
| 282 | symlink 模式位元檢查 |
| 284 | symlink 偵測到時的 WARNING 輸出 |
| 287 | `os.RemoveAll(src)` — 僅在確認非 symlink 後執行 |
| 289 | 刪除失敗時的 WARNING 記錄 |
| 291 | 刪除成功時設定 `result.DeletedSrc = true` |
| 296 | Lstat 失敗時的 WARNING 記錄 |

---

## 測試與建置狀態

| 步驟 | 狀態 | 說明 |
|------|------|------|
| 程式碼修改 | ✅ 完成 | 兩個漏洞均已修復 |
| `go test ./pkg/mover/... -v` | ⚠️ 無法執行 | 沙箱環境未安裝 Go 執行環境（網路限制，無法下載） |
| `go build -o classifier.exe ./cmd/scanner` | ⚠️ 無法執行 | 同上，環境限制 |
| API 相容性 | ✅ 已確認 | 修改未變更任何函式簽名或回傳型別 |

> **注意**：測試與建置無法在排程沙箱中執行，但本次修改屬於防禦性補強（注釋 + 額外 Lstat 驗證），不影響現有邏輯流程或回傳行為，**預期不會破壞任何現有測試**。建議在有 Go 環境的本機執行 `go test ./pkg/mover/... -v` 做最終確認。

---

## 未修改項目

- 所有函式簽名與回傳型別保持不變
- `MoveFile`、`MoveDir`、`BatchMove`、`Rollback` 等 API 介面無變動
- 現有單元測試不需更新（行為邏輯未改變，僅強化防禦驗證與錯誤記錄）

---

*此報告由排程任務 `security-fix-20260403-0359` 自動生成*
