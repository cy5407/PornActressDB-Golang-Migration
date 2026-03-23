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

### 架構設計

```
┌─────────────────┐
│  Python GUI     │
│  (main_gui.py)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      subprocess      ┌──────────────────┐
│   GoBridge      │ ──────────────────▶  │  classifier.exe  │
│ (go_bridge.py)  │ ◀────────────────── │  (Go CLI)        │
└─────────────────┘      JSON I/O        └──────────────────┘
         │                                        │
         │                                        ▼
         │                                ┌──────────────────┐
         │                                │  pkg/extractor/  │
         │                                │  pkg/mover/      │
         │                                │  pkg/database/   │
         └────────────────────────────────│  pkg/studio/     │
                 共用資料檔案                └──────────────────┘
                 (data/json_db/data.json)
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

檔案：`cmd/scanner/main.go`
```go
import (
    "your-project/pkg/validator"
)

func handleValidate(args []string) {
    if len(args) < 1 {
        fmt.Fprintln(os.Stderr, "Usage: classifier validate <file>")
        os.Exit(1)
    }

    result, err := validator.ValidateFile(args[0])
    if err != nil {
        fmt.Fprintf(os.Stderr, "Error: %v\n", err)
        os.Exit(1)
    }

    // 輸出 JSON
    enc := json.NewEncoder(os.Stdout)
    enc.Encode(result)
}

func main() {
    if len(os.Args) < 2 {
        printUsage()
        os.Exit(1)
    }

    command := os.Args[1]
    switch command {
    case "validate":
        handleValidate(os.Args[2:])
    // ... 其他命令
    }
}
```

#### Step 4: 重新編譯

```bash
# 從專案根目錄
go build -o classifier.exe ./cmd/scanner

# 測試命令
classifier.exe validate "test.mp4"
```

#### Step 5: 整合到 Python

檔案：`src/services/go_bridge.py`
```python
class GoBridge:
    def validate_file(self, file_path: str) -> Dict[str, Any]:
        """驗證檔案"""
        result = self._run_go_command([
            "validate",
            file_path
        ])
        return json.loads(result.stdout)
```

#### Step 6: 測試 Python 整合

```python
from services.go_bridge import GoBridge

bridge = GoBridge()
result = bridge.validate_file("test.mp4")
print(f"Valid: {result['valid']}")
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

檔案：`src/models/go_types.py`（建議建立）
```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ScanResult:
    path: str
    code: str
    size: int

@dataclass
class ScanResponse:
    files: List[ScanResult]
    total: int
    duration_ms: int

@dataclass
class MoveItem:
    source: str
    destination: str
    success: bool
    error: Optional[str] = None
```

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
- `src/services/go_bridge.py` - Python 橋接層
- `cmd/scanner/main.go` - Go CLI 主程式
- `pkg/extractor/extractor.go` - 番號提取器
- `pkg/mover/mover.go` - 檔案移動器

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
