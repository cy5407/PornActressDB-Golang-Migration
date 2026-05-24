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
go build -o classifier.exe ./cmd/scanner

# 最佳化建置
go build -ldflags "-s -w" -o classifier.exe ./cmd/scanner
```

> 請建置 `./cmd/scanner` 套件，不要直接指定 `main.go`。

### 2. 執行測試

```bash
# Python 測試
python -m pytest tests/ -v

# Go 測試
go test ./... -v
```

### 3. 更新版本

依實際變更更新下列文件，而不是假設固定改單一版本號：
- `README.md`
- `AGENTS.md`
- `wails-app/wails.json`（若版本字串存在於此）

### 4. 打包檔案

正式發行請執行 `.\setup.ps1`，會產出：

```
dist/portable/
├── actress-classifier.exe   # Wails GUI（主程式）
├── classifier.exe           # Go CLI
├── Start-ActressClassifier.bat
├── Setup-SearchRuntime.ps1
├── studios.json / major_studios.json
├── src/                     # 爬蟲 Python 來源
└── requirements.txt
```

並壓縮為 `dist/PornActressDB-windows-portable.zip`。

## 版本管理

### 語義化版本 (SemVer)

```
v6.0.0
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

- `actress-classifier.exe` - Wails GUI 主程式
- `classifier.exe` - Go CLI
- `setup.ps1` - 端到端建置入口
- `CHANGELOG.md` - 變更日誌
- `README.md` - 使用說明
