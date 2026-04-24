# ============================================================
# 女優分類系統 — 建置腳本（Windows PowerShell）
# 建置 classifier.exe、actress-classifier.exe，並輸出 portable bundle
# ============================================================
# 使用方式：
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned  (首次需執行)
#   .\setup.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$PortableDir = Join-Path $RepoRoot "dist\portable"

function Write-Step($n, $msg) {
    Write-Host ""
    Write-Host "=== [$n] $msg ===" -ForegroundColor Cyan
}

# ── [1/4] Go 版本檢查 ─────────────────────────────────────────
Write-Step "1/4" "檢查 Go 版本"
try {
    $goVer = go version
    Write-Host $goVer
} catch {
    Write-Host "❌ 找不到 go，請先安裝 Go 1.24+ 並加入 PATH" -ForegroundColor Red
    Write-Host "   下載：https://go.dev/dl/"
    exit 1
}

# ── [2/4] 建置 classifier.exe ────────────────────────────────
Write-Step "2/4" "建置 classifier.exe → 專案根目錄"
Set-Location $RepoRoot
go mod download
go build -o "$RepoRoot\classifier.exe" .\cmd\scanner
Write-Host "✅ classifier.exe 建置完成" -ForegroundColor Green

# ── [3/4] 建置 actress-classifier.exe ───────────────────────
Write-Step "3/4" "建置 actress-classifier.exe → 專案根目錄"

try {
    node --version | Out-Null
} catch {
    Write-Host "❌ 找不到 node，請先安裝 Node.js 18+" -ForegroundColor Red
    exit 1
}

try {
    wails version | Out-Null
} catch {
    Write-Host "❌ 找不到 wails，請執行：go install github.com/wailsapp/wails/v2/cmd/wails@latest" -ForegroundColor Red
    exit 1
}

Set-Location "$RepoRoot\wails-app"
go mod download
wails build
Set-Location $RepoRoot

$WailsOutput = "$RepoRoot\wails-app\build\bin\actress-classifier.exe"
if (Test-Path $WailsOutput) {
    Copy-Item $WailsOutput "$RepoRoot\actress-classifier.exe" -Force
    Write-Host "✅ actress-classifier.exe 建置完成" -ForegroundColor Green
} else {
    Write-Host "❌ Wails build 完成但找不到輸出：$WailsOutput" -ForegroundColor Red
    exit 1
}

# ── [4/4] 組合 portable bundle ───────────────────────────────
Write-Step "4/4" "組合 portable bundle → dist\\portable"

if (Test-Path $PortableDir) {
    Remove-Item -LiteralPath $PortableDir -Recurse -Force
}

New-Item -ItemType Directory -Path $PortableDir | Out-Null

$bundleFiles = @(
    "actress-classifier.exe",
    "classifier.exe",
    "major_studios.json",
    "studios.json",
    "requirements.txt",
    "config.ini.example",
    "README.md",
    "LICENSE"
)

foreach ($file in $bundleFiles) {
    Copy-Item (Join-Path $RepoRoot $file) $PortableDir -Force
}

Copy-Item (Join-Path $RepoRoot "src") (Join-Path $PortableDir "src") -Recurse -Force
Write-Host "✅ portable bundle 已輸出到 $PortableDir" -ForegroundColor Green

# ── 完成 ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================" -ForegroundColor Yellow
Write-Host "✅ 建置完成！" -ForegroundColor Green
Write-Host ""
Write-Host "  classifier.exe          Go CLI"
Write-Host "  actress-classifier.exe  Wails GUI"
Write-Host "  dist\portable\          可分發 portable bundle"
Write-Host ""
Write-Host "啟動 GUI："
Write-Host "  .\actress-classifier.exe"
Write-Host ""
Write-Host "Python 搜尋功能需另外安裝相依："
Write-Host "  pip install -r requirements.txt"
Write-Host ""
Write-Host "若要提供給其他人，請分發 dist\portable 內的完整目錄結構，不要只單獨複製 exe。"
Write-Host "============================================" -ForegroundColor Yellow
