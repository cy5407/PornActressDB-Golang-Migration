#!/usr/bin/env bash
# ============================================================
# 女優分類系統 - 本地開發環境設定腳本
# Task 3: 補充測試環境配置
#
# 用途：自動安裝 Go + Python 並建置 Go CLI
# 執行方式：bash scripts/setup-dev-env.sh
# ============================================================

set -euo pipefail

# 顏色輸出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()    { echo -e "${GREEN}✅ $1${NC}"; }
log_warn()    { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error()   { echo -e "${RED}❌ $1${NC}"; }
log_section() { echo -e "\n${YELLOW}=== $1 ===${NC}"; }

# ─── 1. 檢查作業系統 ───
log_section "檢查作業系統"
OS="$(uname -s)"
case "${OS}" in
    Linux*)     PLATFORM="Linux" ;;
    Darwin*)    PLATFORM="macOS" ;;
    MINGW*|MSYS*|CYGWIN*)  PLATFORM="Windows" ;;
    *)          PLATFORM="Unknown:${OS}" ;;
esac
log_info "偵測到: ${PLATFORM}"

# ─── 2. 檢查 Go 安裝 ───
log_section "Go 環境檢查"
REQUIRED_GO_VERSION="1.24.5"

if command -v go &> /dev/null; then
    CURRENT_GO=$(go version | awk '{print $3}' | sed 's/go//')
    log_info "Go 已安裝: ${CURRENT_GO}"

    # 比較版本（簡易檢查）
    if [[ "$(printf '%s\n' "$REQUIRED_GO_VERSION" "$CURRENT_GO" | sort -V | head -n1)" == "$REQUIRED_GO_VERSION" ]]; then
        log_info "Go 版本符合需求（>= ${REQUIRED_GO_VERSION}）"
    else
        log_warn "Go 版本可能過低（需要 >= ${REQUIRED_GO_VERSION}，目前 ${CURRENT_GO}）"
        log_warn "請至 https://go.dev/dl/ 下載最新版本"
    fi
else
    log_error "Go 未安裝！"
    echo ""
    echo "安裝方式："
    if [[ "${PLATFORM}" == "macOS" ]]; then
        echo "  brew install go"
        echo "  或至 https://go.dev/dl/ 下載 .pkg 安裝"
    elif [[ "${PLATFORM}" == "Linux" ]]; then
        echo "  sudo snap install go --classic"
        echo "  或至 https://go.dev/dl/ 下載 .tar.gz 安裝"
        echo "  安裝後執行："
        echo "    tar -C /usr/local -xzf go${REQUIRED_GO_VERSION}.linux-amd64.tar.gz"
        echo "    export PATH=\$PATH:/usr/local/go/bin"
    elif [[ "${PLATFORM}" == "Windows" ]]; then
        echo "  至 https://go.dev/dl/ 下載 .msi 安裝程式"
        echo "  或使用 winget: winget install GoLang.Go"
    fi
    exit 1
fi

# ─── 3. 檢查 Python 安裝 ───
log_section "Python 環境檢查"
REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=11

if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    log_info "Python 已安裝: ${PYTHON_VERSION}"

    if [[ $PYTHON_MAJOR -ge $REQUIRED_PYTHON_MAJOR && $PYTHON_MINOR -ge $REQUIRED_PYTHON_MINOR ]]; then
        log_info "Python 版本符合需求（>= 3.11）"
    else
        log_error "Python 版本不符（需要 >= 3.11，目前 ${PYTHON_VERSION}）"
        exit 1
    fi
elif command -v python &> /dev/null; then
    log_warn "找到 python，但建議使用 python3"
    python --version
else
    log_error "Python 未安裝！請至 https://python.org/downloads/ 下載 Python 3.11+"
    exit 1
fi

# ─── 4. 安裝 Go 模組相依 ───
log_section "安裝 Go 模組"
go mod download
log_info "Go 模組下載完成"

# ─── 5. 建置 Go CLI ───
log_section "建置 classifier CLI"

if [[ "${PLATFORM}" == "Windows" ]]; then
    EXE_NAME="classifier.exe"
else
    EXE_NAME="classifier"
fi

go build -o "${EXE_NAME}" ./cmd/scanner/main.go
log_info "${EXE_NAME} 建置成功"

# 設定執行權限（非 Windows）
if [[ "${PLATFORM}" != "Windows" ]]; then
    chmod +x "${EXE_NAME}"
    log_info "執行權限已設定"
fi

# 驗證 CLI 可用
if ./"${EXE_NAME}" help &> /dev/null; then
    log_info "CLI 驗證成功"
else
    log_warn "CLI help 返回非零（可能正常）"
fi

# ─── 6. 安裝 Python 相依套件 ───
log_section "安裝 Python 相依套件"
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
log_info "Python 相依套件安裝完成"

# ─── 7. 執行基本測試驗證 ───
log_section "執行測試驗證"

echo ""
echo "正在執行 Go 單元測試..."
if go test ./pkg/... -v -race 2>&1 | tail -5; then
    log_info "Go 測試通過"
else
    log_warn "Go 測試有失敗項目，請檢查輸出"
fi

echo ""
echo "正在驗證 Python 環境..."
if python3 -c "import sys; sys.path.insert(0, '.'); from src.services.go_bridge import GoBridge; b = GoBridge(); print(f'Go Bridge 可用: {b.is_available}')"; then
    log_info "Python 環境驗證成功"
else
    log_warn "Python 環境驗證失敗，請檢查錯誤訊息"
fi

# ─── 完成 ───
log_section "設定完成"
echo ""
echo "開發環境設定完成！"
echo ""
echo "常用指令："
echo "  執行應用程式:    ./actress-classifier"
echo "  執行 Go 測試:   go test ./pkg/... -v"
echo "  執行 Python 測試: python3 -m pytest tests/ -v"
echo "  執行所有測試:    go test ./pkg/... && python3 -m pytest tests/ -v"
echo "  CLI 掃描範例:   ./${EXE_NAME} scan -dir './data' -workers 4"
echo ""
