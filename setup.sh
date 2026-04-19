#!/usr/bin/env bash
# ============================================================
# 女優分類系統 — 建置腳本（Linux / macOS）
# 建置 classifier 到專案根目錄（Wails GUI 僅支援 Windows）
# ============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== [1/1] 建置 classifier → 專案根目錄 ==="
if ! command -v go &>/dev/null; then
  echo "❌ 找不到 go，請先安裝 Go 1.24+"
  exit 1
fi
go version
cd "$REPO_ROOT"
go mod download
go build -o "$REPO_ROOT/classifier" ./cmd/scanner
echo "✅ classifier 建置完成"

echo ""
echo "============================================"
echo "✅ 建置完成！"
echo ""
echo "  classifier    Go CLI"
echo ""
echo "注意：Wails GUI 僅支援 Windows 建置。"
echo "Python 搜尋功能需另外安裝：pip install -r requirements.txt"
echo "============================================"
