# db-sync.ps1 — Shadow SQLite 同步腳本
# 用法: scripts\db-sync.ps1 [-Benchmark] [-SkipCompact]
#
# 執行順序: compact → db-init → db-import-json → db-compare-json
# compare 失敗則中止，不繼續跑 benchmark

param(
    [switch]$Benchmark,
    [switch]$SkipCompact
)

$ErrorActionPreference = "Stop"

$CLASSIFIER  = "classifier.exe"
$DB_TOOL     = "tools-rs\target\release\db-tool.exe"
$JSON_PATH   = "data\json_db\data.json"
$SQLITE_PATH = "data\shadow.sqlite"

if (-not (Test-Path $CLASSIFIER)) {
    Write-Error "找不到 $CLASSIFIER，請先執行: go build -o classifier.exe .\cmd\scanner"
    exit 1
}
if (-not (Test-Path $DB_TOOL)) {
    Write-Error "找不到 $DB_TOOL，請先執行: cd tools-rs; cargo build --release"
    exit 1
}
if (-not (Test-Path $JSON_PATH)) {
    Write-Error "找不到 $JSON_PATH，請先執行 compact 或確認 data.json 存在"
    exit 1
}

if (-not $SkipCompact) {
    Write-Host "[1/4] compact journal..." -ForegroundColor Cyan
    & $CLASSIFIER db compact
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "[1/4] compact 略過 (-SkipCompact)" -ForegroundColor DarkGray
}

Write-Host "[2/4] db-init..." -ForegroundColor Cyan
& $DB_TOOL db-init --sqlite $SQLITE_PATH --replace
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[3/4] db-import-json..." -ForegroundColor Cyan
& $DB_TOOL db-import-json --json $JSON_PATH --sqlite $SQLITE_PATH --replace
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[4/4] db-compare-json..." -ForegroundColor Cyan
& $DB_TOOL db-compare-json --json $JSON_PATH --sqlite $SQLITE_PATH
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n✗ compare 失敗，shadow DB 可能不完整" -ForegroundColor Red
    exit $LASTEXITCODE
}

if ($Benchmark) {
    Write-Host "[+]  db-benchmark..." -ForegroundColor Cyan
    & $DB_TOOL db-benchmark --json $JSON_PATH --sqlite $SQLITE_PATH
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "`n✓ shadow DB 同步完成" -ForegroundColor Green
