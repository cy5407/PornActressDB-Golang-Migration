---
name: testing-validation
description: 測試與驗證指引 - 用於執行 Python pytest、Go 測試、整合測試、GUI 測試和修復測試失敗
argument-hint: "[test-type]"
---

# 測試與驗證 Skill

## 何時使用此 Skill

當需要：
1. **執行測試**（Python pytest、Go test）
2. **修復測試失敗**（分析錯誤、修正程式碼）
3. **新增測試**（單元測試、整合測試）
4. **驗證修改**（確保無副作用）
5. **CI/CD 設定**（GitHub Actions）

## 測試策略

### Python 測試（pytest）

```bash
# 執行所有測試
python -m pytest tests/ -v

# 執行特定測試檔案
python -m pytest tests/test_incremental_db.py -v

# 執行特定測試函式
python -m pytest tests/test_incremental_db.py::test_add_video -v

# 顯示詳細輸出
python -m pytest tests/ -v -s

# 只執行失敗的測試
python -m pytest --lf

# 停在第一個失敗
python -m pytest -x
```

### Go 測試

```bash
# 執行所有測試
go test ./... -v

# 執行特定套件
go test ./pkg/extractor -v

# 執行特定測試
go test ./pkg/extractor -run TestExtractCode -v

# 顯示覆蓋率
go test ./... -cover

# 產生覆蓋率報告
go test ./... -coverprofile=coverage.out
go tool cover -html=coverage.out
```

## 常見測試失敗處理

### Python Import Error

**症狀**:
```
ModuleNotFoundError: No module named 'models'
```

**解決**:
```python
# 在測試檔案開頭加入
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
```

### Go 測試找不到檔案

**症狀**:
```
open testdata/test.mp4: no such file or directory
```

**解決**:
```bash
# 建立 testdata 目錄
mkdir pkg/extractor/testdata
# 建立測試檔案
echo "" > pkg/extractor/testdata/test.mp4
```

## 測試檢查清單

開發前：
- [ ] 執行現有測試確認基準 (`pytest tests/`)
- [ ] 執行 Go 測試確認基準 (`go test ./...`)

開發後：
- [ ] 新增測試覆蓋新功能
- [ ] 執行所有測試確認無副作用
- [ ] 檢查測試覆蓋率

## 相關檔案

- `tests/` - Python 測試目錄
- `pkg/*/\*_test.go` - Go 單元測試
- `pytest.ini` - pytest 設定
