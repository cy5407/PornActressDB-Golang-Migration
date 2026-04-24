# ============================================================
# Actress Classifier build script (Windows PowerShell)
# Builds classifier.exe, actress-classifier.exe, and a portable bundle.
# ============================================================
# Usage:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned  (first run only)
#   .\setup.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$PortableDir = Join-Path $RepoRoot "dist\portable"
$ZipPath = Join-Path $RepoRoot "dist\PornActressDB-windows-portable.zip"

function Write-Step($n, $msg) {
    Write-Host ""
    Write-Host "=== [$n] $msg ===" -ForegroundColor Cyan
}

# [1/4] Go version check
Write-Step "1/4" "Check Go version"
try {
    $goVer = go version
    Write-Host $goVer
} catch {
    Write-Host "ERROR: go was not found. Install Go 1.24+ and add it to PATH." -ForegroundColor Red
    Write-Host "Download: https://go.dev/dl/"
    exit 1
}

# [2/4] Build classifier.exe
Write-Step "2/4" "Build classifier.exe in repo root"
Set-Location $RepoRoot
go mod download
go build -o "$RepoRoot\classifier.exe" .\cmd\scanner
Write-Host "classifier.exe build completed" -ForegroundColor Green

# [3/4] Build actress-classifier.exe
Write-Step "3/4" "Build actress-classifier.exe in repo root"

try {
    node --version | Out-Null
} catch {
    Write-Host "ERROR: node was not found. Install Node.js 18+." -ForegroundColor Red
    exit 1
}

try {
    wails version | Out-Null
} catch {
    Write-Host "ERROR: wails was not found. Run: go install github.com/wailsapp/wails/v2/cmd/wails@latest" -ForegroundColor Red
    exit 1
}

Set-Location "$RepoRoot\wails-app"
go mod download
wails build
Set-Location $RepoRoot

$WailsOutput = "$RepoRoot\wails-app\build\bin\actress-classifier.exe"
if (Test-Path $WailsOutput) {
    Copy-Item $WailsOutput "$RepoRoot\actress-classifier.exe" -Force
    Write-Host "actress-classifier.exe build completed" -ForegroundColor Green
} else {
    Write-Host "ERROR: Wails build completed but output was not found: $WailsOutput" -ForegroundColor Red
    exit 1
}

# [4/4] Assemble portable bundle
Write-Step "4/4" "Assemble portable bundle -> dist\\portable"

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
    "Start-ActressClassifier.bat",
    "Setup-SearchRuntime.ps1",
    "README.md",
    "LICENSE"
)

foreach ($file in $bundleFiles) {
    Copy-Item (Join-Path $RepoRoot $file) $PortableDir -Force
}

Copy-Item (Join-Path $RepoRoot "src") (Join-Path $PortableDir "src") -Recurse -Force
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $PortableDir "*") -DestinationPath $ZipPath -Force
Write-Host "portable bundle written to $PortableDir" -ForegroundColor Green
Write-Host "portable zip written to $ZipPath" -ForegroundColor Green

# Done
Write-Host ""
Write-Host "============================================" -ForegroundColor Yellow
Write-Host "Build completed!" -ForegroundColor Green
Write-Host ""
Write-Host "  classifier.exe          Go CLI"
Write-Host "  actress-classifier.exe  Wails GUI"
Write-Host "  dist\portable\          portable bundle directory"
Write-Host ""
Write-Host "Start GUI:"
Write-Host "  .\Start-ActressClassifier.bat"
Write-Host ""
Write-Host "The first launch creates .venv and installs search dependencies."
Write-Host ""
Write-Host "For external users, distribute dist\PornActressDB-windows-portable.zip."
Write-Host "============================================" -ForegroundColor Yellow
