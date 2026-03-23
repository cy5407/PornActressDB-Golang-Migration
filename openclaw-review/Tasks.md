# Tasks.md - PornActressDB-Golang-Migration 修復清單

**Code Review 日期**: 2026-03-23  
**Review 完成度**: 100% (80/80 檔案)  
**整體評分**: 8.5/10  
**最後更新**: 2026-03-23 自動修復執行 (Task 1-10 全部完成)

---

## 🔴 高優先級任務 (3 個 - 關鍵缺陷)

### Task 1: 修復 MergeFromFile ID 清空問題
**檔案**: `pkg/database/jsondb.go`  
**位置**: 第 428 行  
**優先級**: 🔴 高 (資料遺失風險)  
**狀態**: ✅ 已完成 (2026-03-23)

**問題描述**:
```go
// 現有代碼
videoCopy.ID = ""  // 無條件清空舊版 ID 欄位
```

若來源資料庫仍使用 `id` 欄位而非 `code`，會導致資訊遺失。MergeFromFile 操作後，舊資料的 ID 被清空，無法追蹤原始識別符。

**根本原因**:
- 假設所有資料都已遷移到 `code` 欄位
- 未做向後相容檢查

**修復方案**:
1. 新增向後相容邏輯：僅在 `code` 欄位有效時才清空 `id`
2. 或保留 `id` 作為 fallback：`if videoCopy.Code == "" { videoCopy.Code = videoCopy.ID }`
3. 新增遷移日誌：記錄清空的 ID 用於調試

**建議實現**:
```go
// 修復後
if videoCopy.Code == "" && videoCopy.ID != "" {
    // Fallback to old ID if code not available
    videoCopy.Code = videoCopy.ID
}
// 只在確認 code 有效時才清空
if videoCopy.Code != "" {
    videoCopy.ID = ""
}
```

**測試用例**:
- [ ] 舊版資料庫 (有 id、無 code) 的 merge
- [ ] 新版資料庫 (有 code) 的 merge
- [ ] 混合資料庫 (部分有 id、部分有 code) 的 merge
- [ ] Merge 後驗證資料完整性

**預期工作量**: 2-3 小時 (含測試)

---

### Task 2: 完善 GoAcceleratedDB Fallback 邏輯
**檔案**: `src/models/go_accelerated_db.py`
**位置**: 第 116-124 行
**優先級**: 🔴 高 (容錯機制不完整)
**狀態**: ✅ 已完成 (2026-03-23)

**問題描述**:
```python
# 現有代碼
def db_get_video(self, code: str):
    result = self.go_bridge.db_get_video(code)
    if result is None:
        return None  # ❌ 無法區分「不存在」 vs 「執行失敗」
    return result
```

返回 None 時無法判斷是真的「資料不存在」還是「Go CLI 執行失敗」。當 Go 執行失敗時應 fallback 到 Python，目前卻直接回傳 None。

**根本原因**:
- `go_bridge.db_get_video()` 無區別地返回 None
- 無 exception 機制表示執行失敗

**修復方案**:
1. Go bridge 層區分兩種情況：
   - 返回資料 (成功找到) → 回傳資料
   - 資料不存在 (成功但無結果) → 回傳特殊值或 exception
   - 執行失敗 (CLI 錯誤) → raise exception

2. Python fallback 邏輯：
   ```python
   try:
       result = self.go_bridge.db_get_video(code)
       if result is GoBridgeError:  # Go CLI 執行失敗
           return self.python_db.get_video(code)  # fallback
       return result  # Go 成功 (可能是 None 或資料)
   except GoBridgeException:
       return self.python_db.get_video(code)  # fallback
   ```

**測試用例**:
- [ ] Go CLI 存在且成功：回傳結果
- [ ] Go CLI 成功但資料不存在：回傳 None (不 fallback)
- [ ] Go CLI 不存在或執行失敗：fallback 到 Python
- [ ] Go 部分請求失敗：fallback 那部分

**預期工作量**: 3-4 小時 (含測試與 CI 驗證)

---

### Task 3: 補充測試環境配置
**檔案**: `.github/workflows/` (CI/CD) 與 `Dockerfile`  
**優先級**: 🔴 高 (無法驗證邏輯正確性)
**狀態**: ✅ 已完成 (2026-03-23)

**問題描述**:
當前 Docker 環境缺少 Go 與 Python，導致無法執行自動化測試驗證整合功能。Go bridge 與 Python fallback 機制無法完整測試。

**根本原因**:
- Dockerfile 未安裝 Go 編譯器
- Docker 環境未安裝 Python 運行時
- CI/CD 無完整的測試步驟

**修復方案**:
1. 更新 Dockerfile：
   ```dockerfile
   # 安裝 Go 1.24.5
   FROM golang:1.24.5 as go-builder
   
   # 安裝 Python 3.11+
   FROM python:3.11 as python-base
   
   # 整合兩個環境
   FROM python:3.11
   COPY --from=go-builder /usr/local/go /usr/local/go
   ENV PATH=$PATH:/usr/local/go/bin
   ```

2. 補充 CI/CD 步驟：
   - [ ] Go 編譯測試 (`go test ./...`)
   - [ ] Python 單元測試 (`pytest tests/`)
   - [ ] 集成測試 (Go bridge + Python fallback)
   - [ ] 覆蓋率報告 (codecov)

3. 本地開發環境指南：
   - [ ] Go 1.24.5+ 安裝指南
   - [ ] Python 3.11+ 環境設置
   - [ ] 依賴安裝 (`go mod download`, `pip install -r requirements.txt`)

**測試用例**:
- [ ] Docker 構建成功
- [ ] Go 與 Python 都正確安裝
- [ ] 所有 Go 測試通過
- [ ] 所有 Python 測試通過
- [ ] Bridge 集成測試通過

**預期工作量**: 4-5 小時 (含 Docker 優化與 CI/CD 設置)

---

## 🟡 中優先級任務 (7 個 - 改進與穩定性)

### Task 4: 改進 Rollback Summary 提示
**檔案**: `pkg/mover/mover.go`  
**位置**: 第 171-185 行  
**優先級**: 🟡 中 (使用者體驗)
**狀態**: ✅ 已完成 (2026-03-23)

**問題描述**:
Rollback 操作完成，但若有部分檔案因衝突被跳過，Summary 未明確告知使用者「回滾不完整」。

**修復方案**:
```go
// 修復前
result.Summary = "Rollback completed"  // ❌ 沒有提示失敗項

// 修復後
if result.SkippedCount > 0 {
    result.Summary = fmt.Sprintf(
        "Rollback completed: %d succeeded, %d skipped due to conflicts",
        result.SuccessCount, result.SkippedCount,
    )
} else {
    result.Summary = fmt.Sprintf("Rollback completed: %d files", result.SuccessCount)
}
```

**測試用例**:
- [ ] 全部回滾成功：Summary 清楚顯示成功數
- [ ] 部分回滾失敗：Summary 明確提示失敗項數
- [ ] 日誌記錄失敗項的詳細原因

**預期工作量**: 1 小時

---

### Task 5: 隔離 TestField 測試欄位
**檔案**: `pkg/database/types.go`  
**位置**: 第 68 行  
**優先級**: 🟡 中 (代碼整潔)
**狀態**: ✅ 已完成 (2026-03-23)

**問題描述**:
`VideoData.TestField` 是測試專用欄位，不應在正式結構定義中。

**修復方案** (選擇其一):

1. **Build Tag 隔離** (推薦):
   ```go
   type VideoData struct {
       Code string
       Title string
       // ... 其他欄位
       
       // +build test 
       TestField string  // 僅在測試時編譯
   }
   ```

2. **Test Helper 隔離**:
   - 在 `types_test.go` 中定義 `VideoDataForTest struct`
   - 包含 TestField 和其他測試輔助欄位

3. **Test Struct 繼承**:
   ```go
   // types.go
   type VideoData struct { /* 正式欄位 */ }
   
   // types_test.go
   type VideoDataWithTest struct {
       *VideoData
       TestField string
   }
   ```

**建議**: 使用 Build Tag 最簡潔，或考慮完全移除 TestField。

**測試用例**:
- [ ] 生產構建不包含 TestField
- [ ] 測試構建包含 TestField
- [ ] 現有測試仍正常運作

**預期工作量**: 1-2 小時

---

### Task 6: 改進 loadMajorStudios 錯誤回報
**檔案**: `pkg/studio/identifier.go`  
**位置**: 第 51-68 行  
**優先級**: 🟡 中 (可調試性)
**狀態**: ✅ 已完成 (2026-03-23)

**問題描述**:
多路徑載入時，若規則檔案不存在，不會回報錯誤，難以 debug。

**修復方案**:
```go
// 修復前
func (si *StudioIdentifier) loadMajorStudios() {
    // 嘗試多個路徑，都失敗也沒有回報
}

// 修復後
func (si *StudioIdentifier) loadMajorStudios() error {
    var lastErr error
    for _, path := range rulesFilePaths {
        if err := si.tryLoadRules(path); err == nil {
            return nil  // 成功
        } else {
            lastErr = err
        }
    }
    // 如果明確指定路徑但失敗，回傳 error
    if si.rulesFile != "" {
        return fmt.Errorf("failed to load rules from %s: %w", si.rulesFile, lastErr)
    }
    // fallback：使用預設規則或空規則
    logger.Warnf("Failed to load rules, using defaults: %v", lastErr)
    return nil
}
```

**測試用例**:
- [ ] 指定路徑存在：正常載入
- [ ] 指定路徑不存在：回傳 error
- [ ] 自動尋找路徑失敗：使用預設規則，記錄 warning

**預期工作量**: 1-2 小時

---

### Task 7: 澄清 DeleteVideo Dirty Tracking 語義
**檔案**: `pkg/database/jsondb.go` (第 314-335 行) + 文件  
**優先級**: 🟡 中 (文件與語義清晰度)
**狀態**: ✅ 已完成 (2026-03-23)

**問題描述**:
`DeleteVideo` 後，code 被保留在 `dirtyVideos` 中，外部呼叫 `GetStats()` 無法區分「新增/修改」vs「刪除」。

**修復方案**:

1. **更新文件/註解**:
   ```go
   // dirtyVideos 包含所有待 compact 的操作 (ADD/UPDATE/DELETE)
   // 呼叫端應通過 journal 檔案判斷具體操作類型
   ```

2. **新增獨立追蹤** (可選):
   ```go
   type DBStats struct {
       DirtyVideos int  // 包含 ADD/UPDATE/DELETE
       DeletedVideos int // 僅 DELETE 操作
       // ...
   }
   ```

3. **公開查詢 API**:
   ```go
   func (db *Database) GetDeletedCodes() []string {
       // 從 journal 中篩選 DELETE 操作
   }
   ```

**測試用例**:
- [ ] 文件清楚說明 dirty tracking 語義
- [ ] 新增/修改/刪除 操作的 Stats 正確區分
- [ ] 外部調用端可通過文件理解 dirtyVideos 含義

**預期工作量**: 1-2 小時

---

### Task 8: 強化 generateUniqueName 防護
**檔案**: `pkg/mover/mover.go`  
**位置**: 第 286-303 行  
**優先級**: 🟡 中 (邊界條件保護)
**狀態**: ✅ 已完成 (2026-03-23)

**問題描述**:
若目錄下已存在 `file_1.mp4` ~ `file_10000.mp4`，generateUniqueName 會無限迴圈（已有 maxAttempts 保護，但邏輯仍可優化）。

**修復方案**:
```go
// 現有（已有保護）
if attempts > generateUniqueNameMaxAttempts {
    // 使用時間戳
    return fmt.Sprintf("%s_%.0f%s", base, float64(time.Now().UnixNano()), ext)
}

// 改進：更清楚的邏輯 + 日誌
func (m *Mover) generateUniqueName(dir, filename string) string {
    base := strings.TrimSuffix(filename, filepath.Ext(filename))
    ext := filepath.Ext(filename)
    
    for i := 1; i <= generateUniqueNameMaxAttempts; i++ {
        candidate := fmt.Sprintf("%s_%d%s", base, i, ext)
        if _, err := os.Stat(filepath.Join(dir, candidate)); err == os.ErrNotExist {
            return candidate
        }
    }
    
    // Fallback：時間戳保證唯一性
    timestamp := time.Now().Format("20060102150405")
    result := fmt.Sprintf("%s_%s%s", base, timestamp, ext)
    m.logger.Warnf("Max attempts reached for %s, using timestamp: %s", filename, result)
    return result
}
```

**測試用例**:
- [ ] 正常情況：生成 `file_1.mp4`
- [ ] 衝突情況：正確遞增
- [ ] 極限情況：超過 maxAttempts 後使用時間戳，記錄 warning
- [ ] 大量衝突測試：性能可接受

**預期工作量**: 1-2 小時

---

### Task 9: 檢查 Go Bridge 執行權限
**檔案**: `src/services/go_bridge.py`  
**位置**: 第 119-145 行  
**優先級**: 🟡 中 (跨平台相容性)
**狀態**: ✅ 已完成 (2026-03-23)

**問題描述**:
`_find_exe()` 未檢查 classifier.exe 是否有執行權限，Windows 上可能無問題，但 Linux/macOS 上須檢查 +x 權限。

**修復方案**:
```python
# 修復前
def _find_exe(self):
    # 只檢查檔案是否存在
    if os.path.exists(exe_path):
        return exe_path
    return None

# 修復後
def _find_exe(self):
    exe_path = ...
    if not os.path.exists(exe_path):
        return None
    
    # 檢查執行權限
    if not os.access(exe_path, os.X_OK):
        logger.warning(f"{exe_path} exists but not executable. Check permissions.")
        return None
    
    return exe_path
```

**Windows 兼容性**:
```python
import platform

def _find_exe(self):
    exe_path = ...
    if not os.path.exists(exe_path):
        return None
    
    # Windows 上 os.X_OK 可能無效，僅檢查存在性
    if platform.system() != "Windows":
        if not os.access(exe_path, os.X_OK):
            logger.warning(f"{exe_path} not executable")
            return None
    
    return exe_path
```

**測試用例**:
- [ ] Linux/macOS：有執行權限，正常返回
- [ ] Linux/macOS：無執行權限，返回 None 並記錄 warning
- [ ] Windows：忽略執行權限檢查，正常返回
- [ ] 檔案不存在：返回 None

**預期工作量**: 1 小時

---

### Task 10: 改進 OperationHistoryDialog 重試機制
**檔案**: `src/ui/operation_history_dialog.py`  
**優先級**: 🟡 中 (穩定性)
**狀態**: ✅ 已完成 (2026-03-23)

**問題描述**:
若 Go CLI 連接失敗，UI 僅顯示 messagebox，無重試機制。使用者無法恢復。

**修復方案**:
```python
# 修復前
if not self.file_mover.go_bridge:
    messagebox.showerror("Error", "Cannot connect to Go CLI")
    return

# 修復後
def _connect_with_retry(self, max_retries=3):
    for attempt in range(max_retries):
        try:
            if self.file_mover.go_bridge.is_available():
                return True
        except Exception as e:
            logger.warning(f"Connection attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(1)  # 等待 1 秒後重試
    
    # 全部重試失敗
    result = messagebox.askyesno(
        "Go CLI 連接失敗",
        "無法連接到 Go CLI。\n\n選項：\nYes - 重試\nNo - 使用 Python fallback",
    )
    return result

def show(self):
    if not self._connect_with_retry():
        logger.info("Using Python fallback for file operations")
        # fallback：使用 Python 版本或禁用此功能
        return
    
    # 連接成功，繼續正常流程
    ...
```

**測試用例**:
- [ ] Go CLI 可用：正常顯示對話框
- [ ] Go CLI 短暫不可用：重試成功
- [ ] Go CLI 持續不可用：彈出 Yes/No 對話，允許 fallback
- [ ] 使用者選 No：優雅降級到 Python fallback

**預期工作量**: 2-3 小時

---

## 📋 優化建議 (非緊急)

### 建議 1: 統一 Go/Python 錯誤處理策略
- Go：使用 `error` interface
- Python：使用 exception + 返回值
- 建議：在 bridge 層標準化錯誤結構

### 建議 2: 補充集成測試
- 目前大多是單元測試
- 缺少 Go↔Python 跨進程測試
- 建議：補充 `tests/test_go_python_integration.py`

### 建議 3: 效能基準測試
- 大量檔案場景 (10K+ 檔案)
- Go vs Python 性能對比
- 建議：新增 `benchmarks/` 目錄

---

## 📊 任務優先順序建議

### 即刻開始 (本周)
1. **Task 1**: MergeFromFile ID 清空 (資料遺失風險)
2. **Task 2**: GoAcceleratedDB fallback (容錯機制)
3. **Task 3**: 測試環境配置 (CI/CD 驗證)

### 接下來 (下周)
4. **Task 4**: Rollback Summary 提示
5. **Task 9**: Go Bridge 執行權限
6. **Task 10**: OperationHistoryDialog 重試

### 可併行執行
- **Task 5-8**: 這些任務相對獨立，可同時推進

---

## ✅ 完成檢查清單

### Code Review 元數據
- [x] Go 檔案全檢查 (14/14)
- [x] Python 檔案全檢查 (46/46)
- [x] 問題分類與優先級 (10 個任務)
- [x] 改進建議整理 (3 個建議)

### 修復前置條件
- [ ] 所有任務均已確認可執行
- [ ] 測試用例已列出
- [ ] 預期工作量已估算

### 修復驗收標準
- [ ] 所有高優先級任務完成
- [ ] CI/CD 全綠色
- [ ] 集成測試通過
- [ ] Code review 評分 ≥ 9.0/10

---

**文件生成時間**: 2026-03-23 22:00 Asia/Taipei
**基於 Review**: REVIEW_UPDATE_2026-03-23.md
**Review 完成度**: 100% (80/80 檔案)

---

## ✅ 自動修復完成摘要

**修復完成日期**: 2026-03-23
**執行批次**: 2 個排程批次（Task 1-3 + Task 4-10）
**全部 10 個任務均已完成**

### 本批次修復內容（Task 4-10）

| Task | 檔案 | 說明 |
|------|------|------|
| Task 4 | `pkg/mover/mover.go`、`mover_test.go` | Rollback Summary 改為 switch 語句，明確覆蓋全成功/衝突跳過/執行失敗三種情境；補充兩個測試用例 |
| Task 5 | `pkg/database/types.go`、`journal.go` | 從 VideoData 完整移除 TestField（production 程式碼不應含測試欄位） |
| Task 6 | `pkg/studio/identifier.go` | loadMajorStudios 回傳 warning 字串；檔案存在但解析失敗時明確回報；明確目錄找不到時記錄 warning |
| Task 7 | `pkg/database/jsondb.go`、`types.go` | 新增 deletedVideos 獨立追蹤；補充詳細 struct 文件；新增 GetDeletedCodes() API；Stats 加入 DeletedVideos 欄位 |
| Task 8 | `pkg/mover/mover.go` | generateUniqueName Fallback 改用 Format("20060102150405") 時間戳；加入 stderr warning log |
| Task 9 | `src/services/go_bridge.py` | _find_exe 在 Linux/macOS 檢查 os.X_OK 執行權限；新增 platform import |
| Task 10 | `src/ui/operation_history_dialog.py` | 新增 _connect_with_retry(max_retries=3)；失敗時顯示 Yes/No 對話詢問重試或關閉 |

### 後續建議
- Task 3 產生的 CI/CD 配置可進一步整合到實際部署流程
- 建議執行 `go test ./pkg/...` 與 `pytest tests/` 確認所有測試通過
