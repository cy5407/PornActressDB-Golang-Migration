---
name: go-bridge-development
description: Python ↔ Go 橋接層開發指引 - 用於新增 Go CLI 功能、修改番號提取邏輯、整合 Go 加速到 Python GUI、處理 JSON 結構對齊和效能優化
argument-hint: "[feature-name]"
---

# Go Bridge 開發 Skill

## 何時使用此 Skill

當需要：
1. **新增 Go CLI 功能**（如新增掃描模式、移動策略）
2. **修改番號提取邏輯**（新增正則模式、調整優先級）
3. **整合 Go 功能到 Python GUI**（新增按鈕呼叫 Go 功能）
4. **處理 Python ↔ Go 資料傳遞問題**（JSON 結構不匹配）
5. **效能優化**（將 Python 慢速操作遷移到 Go）

## 核心概念

### 架構設計（Phase 2 重構後）

```
┌─────────────────┐
│  Python GUI     │
│  (main_gui.py)  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  GoBridge  (go_bridge.py)               │
│  ← 純 facade，只做 re-export            │
│    scan_directory / move_file / ...     │
└────────┬────────────────────────────────┘
         │ 委派（delegate）
         ▼
┌─────────────────────────────────────────┐
│  go_api/  （領域 API 層）               │
│  ├── scan.py      scan_directory()      │
│  ├── move.py      move_file()           │
│  │                batch_move()          │
│  │                rollback()            │
│  ├── db.py        db_get_video()        │
│  │                db_update_video() 等  │
│  └── identify.py  identify_studio()     │
└────────┬────────────────────────────────┘
         │ 使用
         ▼
┌─────────────────┐      subprocess      ┌──────────────────┐
│ GoCommandRunner │ ──────────────────▶  │  classifier.exe  │
│ (go_runner.py)  │ ◀────────────────── │  (Go CLI)        │
└─────────────────┘      JSON I/O        └──────────────────┘
                                                  │
                                                  ▼
                                         ┌─────────────────────┐
                                         │  pkg/app/           │ ← 服務層
                                         │  pkg/contracts/     │ ← CLI JSON DTO
                                         │  pkg/extractor/     │
                                         │  pkg/mover/         │ ← 拆分為 6 檔
                                         │  pkg/database/      │
                                         │  pkg/studio/        │
                                         └─────────────────────┘
                                                  │
                                         共用資料檔案
                                         (data/json_db/data.json)
```

#### Go 側套件結構

```
cmd/scanner/          # CLI 主程式（已拆分）
├── main.go           # 命令路由（scan/move/history/db/identify/cache）
├── db_cmd.go         # db 子命令
├── identify_cmd.go   # identify 子命令
└── cache_cmd.go      # cache 子命令

pkg/mover/            # 移動器（已拆分為 6 個專注檔案）
├── types.go          # 型別定義
├── file_move.go      # 單檔移動邏輯
├── dir_move.go       # 目錄移動邏輯
├── batch.go          # 批次移動（含 context cancel）
├── rollback.go       # 回滾邏輯
└── history.go        # 操作歷史

pkg/contracts/        # CLI JSON DTO（新增）
├── scan.go
├── move.go
└── history.go

pkg/app/              # 服務層（新增）
├── scan_service.go
├── move_service.go
└── history_service.go
```

### 關鍵原則

1. **Go 負責效能敏感操作**
   - 檔案掃描（10-20x 加速）
   - 批次移動（10x 加速）
   - 番號提取（20x 加速）
   - 片商識別（10x 加速）

2. **Python 負責業務邏輯與 GUI**
   - 使用者界面（Tkinter）
   - 網路爬蟲（BeautifulSoup）
   - 分類決策（女優配對）
   - 設定管理（config.ini）

3. **GoBridge 自動 Fallback**
   ```python
   if bridge.is_available:
       result = bridge.scan_directory(dir)  # Go 加速
   else:
       result = python_scanner.scan(dir)    # 降級到 Python
   ```

4. **命名對齊優先於局部美化**
   - GoBridge 的資料庫公開 helper 已形成 `db_` 前綴家族，例如 `db_get_video`、`db_update_video`
   - 片商識別已形成 `identify_studio` / `identify_studios_batch` 配對
   - 搜尋服務已形成 `batch_search`、`batch_cascade_search` 這類前綴批次家族
   - CLI 已穩定使用 `-dir`、`-src`、`-dst`、`-batch` 等旗標，新增介面時優先保留相容性

### 命名對齊規則

1. Python wrapper、Go 子命令、JSON 欄位要能一眼對照
2. 若 wrapper 直接綁定 `db` 子命令家族，可使用 `db_` 前綴，不要再混入 `database_` 同義寫法
3. 批次命名要延續既有家族，不要在同一功能面同時新增 `batch_xxx` 與 `xxx_batch`
4. 若資料格式同時保留 `code` 與 `id`，文件與新程式碼必須把 `code` 視為主業務名稱，`id` 視為相容或內部識別
5. 需要通用規範時，優先參考 `.claude/skills/naming-conventions/SKILL.md`

## 開發新功能的標準流程

### 流程 1: 新增 Go CLI 命令

**範例：新增「驗證檔案」功能**

#### Step 1: 實作 Go 核心邏輯

```bash
# 建立新套件
mkdir pkg\validator
```

檔案：`pkg/validator/validator.go`
```go
package validator

import (
    "fmt"
    "os"
    "path/filepath"
)

type ValidationResult struct {
    Path    string `json:"path"`
    Valid   bool   `json:"valid"`
    Error   string `json:"error,omitempty"`
}

func ValidateFile(path string) (*ValidationResult, error) {
    info, err := os.Stat(path)
    if err != nil {
        return &ValidationResult{
            Path:  path,
            Valid: false,
            Error: err.Error(),
        }, nil
    }

    // 驗證邏輯
    valid := info.Size() > 0 && !info.IsDir()
    
    return &ValidationResult{
        Path:  path,
        Valid: valid,
    }, nil
}
```

#### Step 2: 撰寫單元測試

檔案：`pkg/validator/validator_test.go`
```go
package validator

import (
    "testing"
)

func TestValidateFile(t *testing.T) {
    // 測試有效檔案
    result, err := ValidateFile("testdata/valid.mp4")
    if err != nil {
        t.Fatal(err)
    }
    if !result.Valid {
        t.Errorf("Expected valid file")
    }
}
```

執行測試：
```bash
go test ./pkg/validator -v
```

#### Step 3: 整合到 CLI

> **⚠️ 注意**：`cmd/scanner/main.go` 只負責命令路由。新命令依類型放到對應的 cmd 文件，或直接在 `main.go` 的 `switch` 中新增 case。

檔案：`cmd/scanner/main.go`（僅新增 switch case）
```go
switch command {
case "validate":
    validateCmd(os.Args[2:])  // 新增此行
case "scan":
    scanCmd(os.Args[2:])
// ... 其他既有命令
}
```

新建 `cmd/scanner/validate_cmd.go`（獨立成檔，保持 main.go 簡潔）：
```go
package main

import (
    "encoding/json"
    "fmt"
    "os"
    "actress-classifier/pkg/validator"
)

func validateCmd(args []string) {
    if len(args) < 1 {
        printError("缺少檔案路徑", "用法: classifier validate <file>")
        os.Exit(1)
    }

    result, err := validator.ValidateFile(args[0])
    if err != nil {
        fmt.Fprintf(os.Stderr, "Error: %v\n", err)
        os.Exit(1)
    }

    json.NewEncoder(os.Stdout).Encode(result)
}
```

#### Step 4: 重新編譯

```bash
# 從專案根目錄
go build -o classifier.exe ./cmd/scanner

# 測試命令
classifier.exe validate "test.mp4"
```

#### Step 5: 整合到 Python（Phase 2 正確做法）

> **⚠️ 重要**：Phase 2 後 `go_bridge.py` 是純 facade，**不應**在裡面加新方法的業務邏輯。
> 正確做法是在 `go_api/` 新增對應的領域函式，然後在 `go_bridge.py` re-export。

**Step 5a** - 在 `src/services/go_api/` 建立或擴充對應模組：

新建 `src/services/go_api/validate.py`：
```python
"""Go CLI 驗證 API。"""

from dataclasses import dataclass
from typing import Optional

try:
    from ..go_runner import GoCommandRunner
except ImportError:
    from services.go_runner import GoCommandRunner


@dataclass
class ValidationResult:
    """驗證結果。"""
    path: str
    valid: bool
    error: Optional[str] = None


def validate_file(
    file_path: str,
    *,
    runner: GoCommandRunner | None = None,
) -> ValidationResult:
    """驗證檔案是否有效。"""
    if runner is None:
        from ..go_bridge import get_bridge
        runner = get_bridge()._runner

    data = runner.run_json(["validate", file_path])
    return ValidationResult(
        path=data["path"],
        valid=data["valid"],
        error=data.get("error"),
    )
```

**Step 5b** - 在 `src/services/go_api/__init__.py` 匯出：
```python
from .validate import ValidationResult, validate_file
```

**Step 5c** - 在 `src/services/go_bridge.py` re-export（保持 facade 一致性）：
```python
# go_bridge.py 頂部新增
from . import go_api as api
validate_file = api.validate_file          # 新增這行
ValidationResult = api.ValidationResult   # 新增這行

# GoBridge 類別中新增轉發方法（可選，供習慣 OOP 寫法的呼叫端使用）
def validate_file(self, file_path: str) -> ValidationResult:
    """驗證檔案"""
    return api.validate_file(file_path, runner=self._runner)
```

#### Step 6: 測試 Python 整合

```python
# 直接呼叫領域 API（推薦）
from services.go_api.validate import validate_file
result = validate_file("test.mp4")
print(f"Valid: {result.valid}")

# 或透過 GoBridge facade
from services.go_bridge import GoBridge
bridge = GoBridge()
result = bridge.validate_file("test.mp4")
print(f"Valid: {result.valid}")
```

### 流程 2: 修改番號提取邏輯

**範例：新增支援 MGS 番號格式（259LUXU-1234）**

#### Step 1: 編輯提取器

檔案：`pkg/extractor/extractor.go`
```go
func ExtractCode(filename string) string {
    patterns := []string{
        `[A-Z]+-\d+`,           // 標準格式 (STARS-707)
        `FC2-PPV-\d+`,          // FC2 格式
        `\d+[A-Z]+-\d+`,        // 新增: MGS 格式 (259LUXU-1234)
    }

    for _, pattern := range patterns {
        re := regexp.MustCompile(pattern)
        if match := re.FindString(filename); match != "" {
            return strings.ToUpper(match)
        }
    }
    return ""
}
```

#### Step 2: 測試

檔案：`pkg/extractor/extractor_test.go`
```go
func TestExtractCodeMGS(t *testing.T) {
    tests := []struct {
        filename string
        want     string
    }{
        {"259LUXU-1234.mp4", "259LUXU-1234"},
        {"259luxu-1234.mp4", "259LUXU-1234"},
    }

    for _, tt := range tests {
        got := ExtractCode(tt.filename)
        if got != tt.want {
            t.Errorf("ExtractCode(%q) = %q; want %q", 
                tt.filename, got, tt.want)
        }
    }
}
```

#### Step 3: 重新編譯並測試

```bash
# 執行測試
go test ./pkg/extractor -v

# 重新編譯
go build -o classifier.exe ./cmd/scanner

# 驗證
classifier.exe scan -dir "測試目錄" | findstr "259LUXU"
```

**無需修改 Python 程式碼** - GoBridge 自動使用新版 CLI！

### 流程 3: 整合到 GUI

**範例：在 GUI 新增「驗證檔案」按鈕**

檔案：`src/ui/main_gui.py`
```python
def create_validate_button(self):
    """建立驗證按鈕"""
    btn = ttk.Button(
        self.button_frame,
        text="🔍 驗證檔案",
        command=self.validate_files,
        style='primary.TButton'
    )
    btn.pack(side='left', padx=5)

def validate_files(self):
    """驗證檔案（使用 Go 加速）"""
    bridge = get_bridge()
    
    if not bridge.is_available:
        messagebox.showwarning("警告", "Go CLI 不可用")
        return
    
    # 背景執行緒執行
    thread = threading.Thread(
        target=self._validate_worker,
        daemon=True
    )
    thread.start()

def _validate_worker(self):
    """驗證工作執行緒"""
    bridge = get_bridge()
    files = self.get_selected_files()
    
    for file in files:
        try:
            result = bridge.validate_file(file)
            # 回到主執行緒更新 UI
            self.root.after(0, lambda r=result: self.show_result(r))
        except Exception as e:
            logger.error(f"❌ 驗證失敗: {e}")
```

## JSON 結構規範

### Go 輸出格式

**掃描結果**:
```json
{
  "files": [
    {
      "path": "D:\\Videos\\STARS-707.mp4",
      "code": "STARS-707",
      "size": 1024000000
    }
  ],
  "total": 1,
  "duration_ms": 150
}
```

**移動結果**:
```json
{
  "operation_id": "abc123",
  "timestamp": "2025-12-22T10:30:00Z",
  "items": [
    {
      "source": "A.mp4",
      "destination": "dest/A.mp4",
      "success": true,
      "error": ""
    }
  ],
  "total": 1,
  "success": 1,
  "failed": 0
}
```

### Python 資料模型

> **Phase 2 後的正確位置**：dataclass 定義在各自的 `src/services/go_api/*.py` 模組中，不要建立 `src/models/go_types.py`。

```
src/services/go_api/
├── scan.py      → ScanResult
├── move.py      → MoveResult, BatchMoveResult, OperationLog
├── db.py        → （回傳 dict，直接對應 JSON schema）
└── identify.py  → （回傳 dict）
```

**現有資料模型範例**（已定義，直接使用）：
```python
# scan.py 中已定義
from services.go_api.scan import ScanResult
# ScanResult(path: str, code: str)

# move.py 中已定義
from services.go_api.move import MoveResult, BatchMoveResult, OperationLog
# MoveResult(source, destination, success, error, skipped, renamed)
# BatchMoveResult(operation_id, total_items, success_count, ...)
```

新增功能的資料模型應放在對應的 `go_api/` 模組中，並在 `go_api/__init__.py` 匯出。

## 常見問題與解決方法

### 問題 1: classifier.exe 找不到

**症狀**:
```
FileNotFoundError: [WinError 2] The system cannot find the file specified: 'classifier.exe'
```

**解決**:
```bash
# 確認編譯
go build -o classifier.exe ./cmd/scanner

# 確認位置（應在專案根目錄）
dir classifier.exe

# 測試
classifier.exe help
```

### 問題 2: JSON 解析失敗

**症狀**:
```python
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

**原因**: Go 輸出到 stderr 而非 stdout

**解決**:
```go
// ❌ 錯誤
fmt.Println("Error:", err)  // 預設輸出到 stdout

// ✅ 正確
fmt.Fprintln(os.Stderr, "Error:", err)  // 錯誤訊息到 stderr
json.NewEncoder(os.Stdout).Encode(result)  // JSON 到 stdout
```

### 問題 3: 路徑編碼問題（Windows）

**症狀**: 中文路徑在 Go 中顯示亂碼

**解決**:
```go
// Go 程式開頭
import (
    "syscall"
)

func init() {
    // Windows UTF-8 支援
    if runtime.GOOS == "windows" {
        syscall.LoadDLL("kernel32.dll").
            MustFindProc("SetConsoleOutputCP").
            Call(uintptr(65001))  // UTF-8
    }
}
```

## 效能基準

| 操作 | Python | Go | 提升倍數 |
|------|--------|----|---------|
| 掃描 1000 個檔案 | ~2.5s | ~0.15s | **16.7x** |
| 批次移動 100 個檔案 | ~3.0s | ~0.3s | **10x** |
| 番號提取 (正則) | ~100 μs | ~5 μs | **20x** |
| 片商識別 | ~1ms | ~0.1ms | **10x** |

## 範例程式碼

檔案位置：
- `src/services/go_bridge.py` - Python facade（137 行，pure re-export）
- `src/services/go_runner.py` - subprocess 執行器（GoCommandRunner）
- `src/services/go_api/scan.py` - 掃描領域 API
- `src/services/go_api/move.py` - 移動領域 API（含歷史/回滾）
- `src/services/go_api/db.py` - 資料庫領域 API
- `src/services/go_api/identify.py` - 片商識別領域 API
- `cmd/scanner/main.go` - Go CLI 命令路由
- `cmd/scanner/db_cmd.go` - db 子命令實作
- `cmd/scanner/identify_cmd.go` - identify 子命令實作
- `cmd/scanner/cache_cmd.go` - cache 子命令實作
- `pkg/extractor/extractor.go` - 番號提取器
- `pkg/mover/` - 檔案移動器（拆分為 types/file_move/dir_move/batch/rollback/history）
- `pkg/contracts/` - CLI JSON DTO 定義
- `pkg/app/` - Go 服務層

## 開發前檢查清單

使用此功能前，確認：
- [ ] 已安裝 Go 1.21+ (`go version`)
- [ ] 專案根目錄有 `classifier.exe`
- [ ] `GoBridge.is_available` 回傳 True
- [ ] Go 單元測試通過 (`go test ./pkg/... -v`)
- [ ] Python 整合測試通過

## 相關資源

- `GO_MIGRATION_TODO.md` - Go 遷移進度追蹤
- `CLAUDE.md` - 完整開發指南
- `pkg/` - Go 套件原始碼
- `src/services/go_bridge.py` - Python 橋接層實作
