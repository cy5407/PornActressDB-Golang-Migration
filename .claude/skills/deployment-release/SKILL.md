---
name: deployment-release
description: 部署與發布指引 - 用於建置 Go CLI、打包應用程式、版本管理、發布流程和更新文件
argument-hint: "[task]"
---

# 部署與發布 Skill

## 何時使用此 Skill

當需要：
1. **建置 Go CLI**（編譯 classifier.exe）
2. **打包應用程式**（包含所有相依檔案）
3. **版本管理**（更新版本號、CHANGELOG）
4. **發布新版本**（GitHub Release）

## 建置流程

### 1. 建置 Go CLI

```bash
# Windows
go build -o classifier.exe cmd/scanner/main.go

# 最佳化建置
go build -ldflags "-s -w" -o classifier.exe cmd/scanner/main.go
```

### 2. 執行測試

```bash
# Python 測試
python -m pytest tests/ -v

# Go 測試
go test ./... -v
```

### 3. 更新版本

編輯：`run.py`
```python
# 版本：v5.4.3 → v5.4.4
```

### 4. 打包檔案

```
發布檔案/
├── classifier.exe
├── run.py
├── requirements.txt
├── config.ini
├── README.md
├── src/
├── data/
└── logs/
```

## 版本管理

### 語義化版本 (SemVer)

```
v5.4.3
│ │ │
│ │ └─ 修補版本（Bug 修復）
│ └─── 次版本（新功能）
└───── 主版本（重大變更）
```

### CHANGELOG 格式

```markdown
## [5.4.4] - 2025-01-15

### 新增
- 新增 MGS 番號支援

### 修正
- 修復 Journal 損壞問題

### 變更
- 優化搜尋效能
```

## 相關檔案

- `run.py` - 主程式進入點（版本號）
- `CHANGELOG.md` - 變更日誌
- `README.md` - 使用說明
