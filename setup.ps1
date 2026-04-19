# ============================================================
# 女優分類系統 — 安裝依賴腳本（Windows PowerShell）
# ============================================================
# 使用方式：在 repo 根目錄以系統管理員或一般使用者身份執行
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned  (首次需執行)
#   .\setup.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot

function Write-Step($n, $msg) {
    Write-Host ""
    Write-Host "=== [$n] $msg ===" -ForegroundColor Cyan
}

# ── [1/4] Python ────────────────────────────────────────────
Write-Step "1/4" "檢查 Python 版本"
try {
    $pyVer = python --version
    Write-Host $pyVer
} catch {
    Write-Host "❌ 找不到 python，請先安裝 Python 3.10+ 並加入 PATH" -ForegroundColor Red
    exit 1
}

Write-Step "2/4" "安裝 Python 相依套件"
Set-Location $RepoRoot
if (-not (Test-Path "venv")) {
    Write-Host "建立虛擬環境 venv\ ..."
    python -m venv venv
}
& .\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Write-Host "✅ Python 相依安裝完成" -ForegroundColor Green

# ── [2/4] Go ────────────────────────────────────────────────
Write-Step "3/4" "安裝 Go 相依 & 建置 classifier.exe"
try {
    $goVer = go version
    Write-Host $goVer
} catch {
    Write-Host "❌ 找不到 go，請先安裝 Go 1.24+ 並加入 PATH" -ForegroundColor Red
    Write-Host "   下載：https://go.dev/dl/"
    exit 1
}

Set-Location $RepoRoot
go mod download

Set-Location "$RepoRoot\wails-app"
go mod download

Set-Location $RepoRoot
go build -o classifier.exe .\cmd\scanner
Write-Host "✅ Go 相依 & classifier.exe 建置完成" -ForegroundColor Green

# ── [3/4] Node / Frontend ───────────────────────────────────
Write-Step "4/4" "安裝 Frontend Node 相依"
try {
    $nodeVer = node --version
    Write-Host "Node $nodeVer"
} catch {
    Write-Host "❌ 找不到 node，請先安裝 Node.js 18+" -ForegroundColor Red
    exit 1
}

Set-Location "$RepoRoot\wails-app\frontend"
npm install
Set-Location $RepoRoot
Write-Host "✅ Frontend 相依安裝完成" -ForegroundColor Green

# ── 完成 ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================" -ForegroundColor Yellow
Write-Host "✅ 所有依賴安裝完成！" -ForegroundColor Green
Write-Host ""
Write-Host "啟動方式："
Write-Host "  .\venv\Scripts\Activate.ps1"
Write-Host "  python run.py"
Write-Host ""
Write-Host "建置 Wails GUI："
Write-Host "  Set-Location wails-app"
Write-Host "  wails build"
Write-Host "============================================" -ForegroundColor Yellow
