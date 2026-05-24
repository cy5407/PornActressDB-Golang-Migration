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
3. **版本管理**（同步 README、AGENTS.md、發布文件）
4. **驗證發布流程**（build、test、workflow 對齊）

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

### 3. 更新發布文件

依實際變更更新下列文件，而不是假設固定改單一版本號：
- `README.md`
- `AGENTS.md`
- `docs/` 內相關發布或操作文件

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

本 repo 目前沒有固定維護 `CHANGELOG.md`。發布相關記錄以：
- git commit / tag
- `README.md`
- `AGENTS.md`
- `docs/` 內專案文件

為主。

若未來新增正式版本文件，再把流程補回此 Skill，不要先假設檔案存在。

## 相關檔案

- `actress-classifier.exe` - Wails GUI 主程式
- `cmd/scanner/main.go` - Go CLI 入口
- `setup.ps1` - 端到端建置入口
- `README.md` - 使用說明
- `AGENTS.md` - 開發與建置規範
- `.github/workflows/` - CI 驗證流程
