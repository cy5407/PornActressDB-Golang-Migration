# Go Scanner MVP - Quick Start

## 已完成

✅ **Phase 1: Pure Logic Port**
- `pkg/extractor/extractor.go` - 核心番號提取邏輯（從 Python 移植）
- `pkg/extractor/extractor_test.go` - 完整單元測試（14 個測試案例全通過）

✅ **Phase 2: High Performance Scanner**
- `cmd/scanner/main.go` - CLI 掃描器（支援並發處理）
- 編譯產出：`classifier.exe`

✅ **Phase 3: Python Integration**
- `tools/integration/go_integration.py` - Python 呼叫 Go 的整合範例

## 測試結果

```bash
# 單元測試
go test ./pkg/extractor -v
# PASS: TestExtractCode (14 cases)
# PASS: TestShouldSkip (6 cases)
# PASS: TestNormalizeCode (4 cases)

# CLI 掃描測試
.\classifier.exe -dir "C:\Users\cy540\Downloads\test_videos"
# 成功識別: STARS-707, SSIS-999, IPX-123
# 正確過濾: FC2-PPV-123456 (跳過)

# Python 整合測試
python tools/integration/go_integration.py "C:\Users\cy540\Downloads\test_videos"
# 成功透過 subprocess 呼叫 Go 並解析 JSON
```

## 效能

- **單執行緒**: ~20ms (3 個檔案)
- **並發處理**: 支援 `-workers` 參數調整（預設 10）

## 使用方式

### 直接使用 Go CLI
```powershell
# 基本掃描
.\classifier.exe -dir "D:\Videos"

# 調整並發數
.\classifier.exe -dir "D:\Videos" -workers 20

# 輸出為 JSON（可用 Python 解析）
.\classifier.exe -dir "D:\Videos" | python -m json.tool
```

### Python 整合範例
```python
from tools.integration.go_integration import scan_directory_go

results = scan_directory_go("D:\\Videos", workers=20)
for item in results:
    print(f"{item['code']}: {item['path']}")
```

## 下一步

### 選項 A：繼續擴充 Go 功能
- 加入檔案移動功能
- 整合 `studios.json` 做片商分類
- 加入進度條顯示

### 選項 B：整合到現有 Python GUI
1. 修改 `src/services/classifier_core.py`
2. 把 `os.walk` 改成呼叫 `go_integration.scan_directory_go()`
3. 其他邏輯（搜尋、分類、移動）維持 Python

### 選項 C：效能測試
- 準備大量測試檔案（1000+ 個）
- 比較 Python vs Go 掃描速度
- 決定是否值得繼續投資 Go 開發

## 檔案結構
```
PornActressDB-Golang-Migration/
├── pkg/
│   └── extractor/
│       ├── extractor.go          # 核心提取器
│       └── extractor_test.go     # 單元測試
├── cmd/
│   └── scanner/
│       └── main.go               # CLI 工具
├── tools/
│   └── integration/
│       └── go_integration.py     # Python 整合
├── classifier.exe                # 編譯產出
└── go.mod
```
