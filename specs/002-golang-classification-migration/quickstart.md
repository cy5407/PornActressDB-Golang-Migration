# Quick Start Guide: Golang 分類功能開發

**Feature**: 002-golang-classification-migration  
**Date**: 2025-10-18  
**Target Audience**: 開發者、測試者

---

## 目錄

1. [環境設置](#環境設置)
2. [專案結構](#專案結構)
3. [開發流程](#開發流程)
4. [編譯與執行](#編譯與執行)
5. [測試](#測試)
6. [除錯技巧](#除錯技巧)
7. [常見問題](#常見問題)

---

## 環境設置

### 前置需求

| 工具 | 版本 | 用途 | 安裝連結 |
|------|------|------|---------|
| **Go** | 1.22+ | 主要開發語言 | [golang.org/dl](https://golang.org/dl/) |
| **Protocol Buffers** | 3.20+ | gRPC 介面定義 | [github.com/protocolbuffers/protobuf](https://github.com/protocolbuffers/protobuf/releases) |
| **Python** | 3.8+ | 整合層 | [python.org](https://www.python.org/downloads/) |
| **Git** | 2.30+ | 版本控制 | [git-scm.com](https://git-scm.com/downloads) |

### 安裝 Go

**Windows**:
```powershell
# 下載並安裝 Go from golang.org/dl
# 驗證安裝
go version
# 應輸出: go version go1.22.x ...
```

**Linux/macOS**:
```bash
# 使用套件管理器 (Ubuntu 範例)
sudo apt update
sudo apt install golang-1.22

# 或從官網下載
wget https://go.dev/dl/go1.22.0.linux-amd64.tar.gz
sudo tar -C /usr/local -xzf go1.22.0.linux-amd64.tar.gz

# 設置環境變數
export PATH=$PATH:/usr/local/go/bin
export GOPATH=$HOME/go
export PATH=$PATH:$GOPATH/bin

# 驗證
go version
```

### 安裝 Protocol Buffers 編譯器

**Windows**:
```powershell
# 使用 Chocolatey
choco install protoc

# 或手動下載
# https://github.com/protocolbuffers/protobuf/releases
# 解壓後將 protoc.exe 加入 PATH
```

**Linux**:
```bash
sudo apt install protobuf-compiler

# 驗證
protoc --version
# 應輸出: libprotoc 3.x.x
```

**macOS**:
```bash
brew install protobuf

# 驗證
protoc --version
```

### 安裝 Go 工具鏈

```bash
# Protocol Buffers Go 外掛
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest

# golangci-lint (程式碼檢查)
go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest

# gofumpt (格式化)
go install mvdan.cc/gofumpt@latest

# 驗證
protoc-gen-go --version
protoc-gen-go-grpc --version
golangci-lint --version
```

---

## 專案結構

### 初始化 Go 模組

```bash
cd /path/to/PornActressDB-Golang-Migration

# 建立 golang 目錄
mkdir -p golang
cd golang

# 初始化 Go 模組
go mod init github.com/cy5407/porn-actress-classifier

# 安裝核心依賴
go get google.golang.org/grpc@latest
go get google.golang.org/protobuf@latest
go get github.com/spf13/cobra@latest
go get go.uber.org/zap@latest
go get github.com/gofrs/flock@latest
go get github.com/hashicorp/golang-lru@latest

# 測試依賴
go get github.com/stretchr/testify@latest

# 整理依賴
go mod tidy
```

### 目錄結構

```
golang/
├── cmd/                        # 主程式入口
│   ├── classifier/             # CLI 工具
│   │   └── main.go
│   └── classifier-server/      # gRPC 伺服器
│       └── main.go
├── internal/                   # 私有程式碼 (不可匯出)
│   ├── scanner/                # 檔案掃描
│   │   ├── scanner.go
│   │   ├── code_extractor.go
│   │   └── scanner_test.go
│   ├── classifier/             # 分類邏輯
│   │   ├── actress_classifier.go
│   │   ├── studio_classifier.go
│   │   └── classifier_test.go
│   ├── database/               # JSON 資料庫
│   │   ├── json_db.go
│   │   ├── actress_repository.go
│   │   └── studio_repository.go
│   ├── fileops/                # 檔案操作
│   │   ├── mover.go
│   │   ├── conflict_resolver.go
│   │   └── fileops_test.go
│   ├── models/                 # 資料模型
│   │   ├── video.go
│   │   ├── actress.go
│   │   └── studio.go
│   └── grpc/                   # gRPC 實作
│       ├── server.go
│       ├── handlers.go
│       └── progress_stream.go
├── pkg/                        # 可匯出的公共程式碼
│   └── proto/                  # 生成的 Protocol Buffers 程式碼
│       ├── classifier.pb.go
│       └── classifier_grpc.pb.go
├── go.mod                      # Go 模組定義
├── go.sum                      # 依賴校驗和
├── Makefile                    # 建置腳本
└── README.md                   # 專案說明
```

---

## 開發流程

### Step 1: 生成 Protocol Buffers 程式碼

```bash
cd golang

# 從規格目錄複製 .proto 檔案
cp ../specs/002-golang-classification-migration/contracts/classifier.proto .

# 生成 Go 程式碼
protoc --go_out=. --go_opt=paths=source_relative \
       --go-grpc_out=. --go-grpc_opt=paths=source_relative \
       classifier.proto

# 移動生成的檔案到 pkg/proto/
mkdir -p pkg/proto
mv classifier.pb.go pkg/proto/
mv classifier_grpc.pb.go pkg/proto/
```

### Step 2: 建立 Makefile

建立 `golang/Makefile`:

```makefile
.PHONY: all build test lint clean proto

# 變數
BINARY_NAME_CLI=classifier
BINARY_NAME_SERVER=classifier-server
GO=go
GOFLAGS=-v
LDFLAGS=-ldflags "-s -w"

all: build

# 生成 Protocol Buffers 程式碼
proto:
	protoc --go_out=. --go_opt=paths=source_relative \
	       --go-grpc_out=. --go-grpc_opt=paths=source_relative \
	       classifier.proto
	mkdir -p pkg/proto
	mv classifier.pb.go pkg/proto/
	mv classifier_grpc.pb.go pkg/proto/

# 編譯
build:
	$(GO) build $(GOFLAGS) $(LDFLAGS) -o bin/$(BINARY_NAME_CLI) cmd/classifier/main.go
	$(GO) build $(GOFLAGS) $(LDFLAGS) -o bin/$(BINARY_NAME_SERVER) cmd/classifier-server/main.go

# 執行測試
test:
	$(GO) test -v -race -coverprofile=coverage.out ./...
	$(GO) tool cover -html=coverage.out -o coverage.html

# 程式碼檢查
lint:
	golangci-lint run ./...

# 格式化
fmt:
	gofumpt -l -w .

# 清理
clean:
	rm -rf bin/
	rm -f coverage.out coverage.html

# 安裝到系統
install:
	$(GO) install $(LDFLAGS) cmd/classifier/main.go
	$(GO) install $(LDFLAGS) cmd/classifier-server/main.go

# 跨平台編譯
build-all:
	GOOS=windows GOARCH=amd64 $(GO) build $(LDFLAGS) -o bin/$(BINARY_NAME_CLI).exe cmd/classifier/main.go
	GOOS=linux GOARCH=amd64 $(GO) build $(LDFLAGS) -o bin/$(BINARY_NAME_CLI)-linux cmd/classifier/main.go
	GOOS=darwin GOARCH=amd64 $(GO) build $(LDFLAGS) -o bin/$(BINARY_NAME_CLI)-macos cmd/classifier/main.go
```

### Step 3: 實作資料模型

建立 `golang/internal/models/video.go`:

```go
package models

import "time"

// VideoFile 代表一個影片檔案
type VideoFile struct {
    Path       string    `json:"path"`
    Name       string    `json:"name"`
    Size       int64     `json:"size"`
    Code       string    `json:"code"`
    Scanned    bool      `json:"scanned"`
    Error      string    `json:"error,omitempty"`
    CreatedAt  time.Time `json:"created_at"`
    ModifiedAt time.Time `json:"modified_at"`
}

// HasCode 檢查是否成功提取番號
func (v *VideoFile) HasCode() bool {
    return v.Code != ""
}
```

參考 `specs/002-golang-classification-migration/data-model.md` 完成其他模型。

### Step 4: 實作核心功能

**檔案掃描範例** (`internal/scanner/scanner.go`):

```go
package scanner

import (
    "os"
    "path/filepath"
    "github.com/cy5407/porn-actress-classifier/internal/models"
)

// Scanner 檔案掃描器
type Scanner struct {
    extensions map[string]bool
}

// NewScanner 建立掃描器
func NewScanner(extensions []string) *Scanner {
    extMap := make(map[string]bool)
    for _, ext := range extensions {
        extMap[ext] = true
    }
    return &Scanner{extensions: extMap}
}

// Scan 掃描資料夾
func (s *Scanner) Scan(folderPath string, recursive bool) ([]*models.VideoFile, error) {
    var files []*models.VideoFile
    
    walkFunc := func(path string, info os.FileInfo, err error) error {
        if err != nil {
            return err
        }
        
        if info.IsDir() {
            if !recursive && path != folderPath {
                return filepath.SkipDir
            }
            return nil
        }
        
        ext := filepath.Ext(path)
        if s.extensions[ext[1:]] { // 移除 "."
            videoFile := &models.VideoFile{
                Path:       path,
                Name:       info.Name(),
                Size:       info.Size(),
                ModifiedAt: info.ModTime(),
            }
            files = append(files, videoFile)
        }
        
        return nil
    }
    
    if err := filepath.Walk(folderPath, walkFunc); err != nil {
        return nil, err
    }
    
    return files, nil
}
```

---

## 編譯與執行

### 編譯

```bash
cd golang

# 編譯所有二進位檔案
make build

# 或單獨編譯
go build -o bin/classifier cmd/classifier/main.go
go build -o bin/classifier-server cmd/classifier-server/main.go
```

### 執行 CLI

```bash
# 掃描檔案
./bin/classifier scan --folder /path/to/videos --recursive

# 女優分類
./bin/classifier classify-actress --folder /path/to/videos

# 片商分類
./bin/classifier classify-studio --folder /path/to/actresses --threshold 0.7
```

### 執行 gRPC 伺服器

```bash
# 啟動伺服器
./bin/classifier-server --port 50051

# 在另一個終端測試
grpcurl -plaintext localhost:50051 classifier.ClassifierService/GetVersion
```

---

## 測試

### 執行所有測試

```bash
# 執行測試
make test

# 或使用 go test
go test -v ./...

# 查看覆蓋率
go test -cover ./...

# 生成覆蓋率報告
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out
```

### 編寫測試範例

`internal/scanner/scanner_test.go`:

```go
package scanner

import (
    "testing"
    "github.com/stretchr/testify/assert"
)

func TestScanner_Scan(t *testing.T) {
    scanner := NewScanner([]string{"mp4", "mkv"})
    
    files, err := scanner.Scan("testdata", false)
    
    assert.NoError(t, err)
    assert.NotEmpty(t, files)
    assert.Equal(t, "SONE-123.mp4", files[0].Name)
}
```

---

## 除錯技巧

### 使用 Delve 除錯器

```bash
# 安裝 Delve
go install github.com/go-delve/delve/cmd/dlv@latest

# 除錯 CLI
dlv debug cmd/classifier/main.go -- scan --folder /path/to/videos

# 設置中斷點
(dlv) break main.main
(dlv) continue
```

### 日誌除錯

```go
import "go.uber.org/zap"

logger, _ := zap.NewDevelopment()
defer logger.Sync()

logger.Info("開始掃描", zap.String("folder", folderPath))
logger.Debug("處理檔案", zap.String("file", fileName))
logger.Error("掃描失敗", zap.Error(err))
```

### 效能分析

```bash
# CPU profiling
go test -cpuprofile=cpu.prof -bench=.

# 記憶體 profiling
go test -memprofile=mem.prof -bench=.

# 分析結果
go tool pprof cpu.prof
go tool pprof mem.prof
```

---

## 常見問題

### Q1: 編譯錯誤 "cannot find module"

**A**: 執行 `go mod tidy` 更新依賴。

### Q2: gRPC 無法連線

**A**: 檢查防火牆設定，確認 port 50051 未被佔用。

### Q3: 測試失敗 "permission denied"

**A**: 確認測試資料夾權限，使用 `chmod` 調整。

### Q4: 跨平台編譯失敗

**A**: 設置正確的 GOOS 和 GOARCH 環境變數。

```bash
# Windows
set GOOS=windows
set GOARCH=amd64

# Linux/macOS
export GOOS=linux
export GOARCH=amd64
```

### Q5: Protocol Buffers 生成失敗

**A**: 確認 protoc 和外掛已正確安裝：

```bash
which protoc
which protoc-gen-go
which protoc-gen-go-grpc
```

---

## 下一步

1. ✅ 完成環境設置
2. ➡️ 閱讀 [data-model.md](./data-model.md) 了解資料結構
3. ➡️ 閱讀 [contracts/cli-interface.md](./contracts/cli-interface.md) 了解 CLI 規格
4. ➡️ 開始實作 Phase 1 功能（檔案掃描）
5. ➡️ 編寫單元測試達到 70% 覆蓋率

---

## 有用的資源

- [Effective Go](https://go.dev/doc/effective_go)
- [Go by Example](https://gobyexample.com/)
- [gRPC Go Tutorial](https://grpc.io/docs/languages/go/quickstart/)
- [Cobra CLI Framework](https://github.com/spf13/cobra)
- [Zap Logger](https://github.com/uber-go/zap)

---

**版本**: 1.0  
**更新日期**: 2025-10-18  
**狀態**: ✅ 已審核，可開始開發
