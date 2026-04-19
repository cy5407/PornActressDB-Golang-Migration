#!/usr/bin/env bash
# ============================================================
# 女優分類系統 — 安裝依賴腳本（Linux / macOS）
# ============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== [1/4] 檢查 Python 版本 ==="
python3 --version || { echo "❌ 找不到 python3，請先安裝 Python 3.10+"; exit 1; }

echo ""
echo "=== [2/4] 安裝 Python 相依套件 ==="
cd "$REPO_ROOT"
if [ ! -d "venv" ]; then
  echo "建立虛擬環境 venv/ ..."
  python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Python 相依安裝完成"

echo ""
echo "=== [3/4] 安裝 Go 相依 & 建置 classifier ==="
if ! command -v go &>/dev/null; then
  echo "❌ 找不到 go，請先安裝 Go 1.24+；Linux 可執行："
  echo "   curl -OL https://go.dev/dl/go1.24.3.linux-amd64.tar.gz"
  echo "   sudo tar -C /usr/local -xzf go1.24.3.linux-amd64.tar.gz"
  echo "   export PATH=\$PATH:/usr/local/go/bin"
  exit 1
fi
go version
# 根 module 相依
go mod download
# Wails app 相依
cd "$REPO_ROOT/wails-app"
go mod download
cd "$REPO_ROOT"
# 建置 Go CLI
go build -o classifier ./cmd/scanner
echo "✅ Go 相依 & classifier 建置完成"

echo ""
echo "=== [4/4] 安裝 Frontend Node 相依 ==="
if ! command -v node &>/dev/null; then
  echo "❌ 找不到 node，請先安裝 Node.js 18+"; exit 1
fi
node --version
cd "$REPO_ROOT/wails-app/frontend"
npm install
cd "$REPO_ROOT"
echo "✅ Frontend 相依安裝完成"

echo ""
echo "============================================"
echo "✅ 所有依賴安裝完成！"
echo ""
echo "啟動方式（Linux/macOS 僅支援 Go CLI 模式）："
echo "  source venv/bin/activate"
echo "  python run.py"
echo ""
echo "若要建置 Wails GUI（需在 Windows 執行）："
echo "  cd wails-app && wails build"
echo "============================================"
