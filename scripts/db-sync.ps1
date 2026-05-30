# db-sync.ps1 — Shadow SQLite 同步腳本
#
# ⚠ 已退役：此腳本串接的是 v2 shadow 流程（db-init / db-import-json / db-compare-json，
# 寫入 data\shadow.sqlite），已非 runtime source of truth。runtime 為 v3 SQLite
# （data\db.sqlite）。請改用：
#   - classifier.exe db verify-sync / export-json / resync-from-json（v3 runtime）
#   - db-tool db-import-json-v3 / db-verify（v3 runtime）
# 本腳本僅供 legacy v2 shadow 診斷保留，不應再進入正式同步流程。
#
# 用法: scripts\db-sync.ps1 [-Benchmark] [-SkipCompact] [-Quiet]
#
# 執行順序: compact → db-init → db-import-json → db-compare-json
# compare 失敗則中止，不繼續跑 benchmark

param(
    [switch]$Benchmark,
    [switch]$SkipCompact,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT = Resolve-Path (Join-Path $SCRIPT_DIR "..")

$CLASSIFIER  = Join-Path $REPO_ROOT "classifier.exe"
$DB_TOOL     = Join-Path $REPO_ROOT "tools-rs\target\release\db-tool.exe"
$JSON_PATH   = Join-Path $REPO_ROOT "data\json_db\data.json"
$SQLITE_PATH = Join-Path $REPO_ROOT "data\shadow.sqlite"

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

Push-Location $REPO_ROOT
try {
    if (-not $SkipCompact) {
        if (-not $Quiet) { Write-Host "[1/4] compact journal..." -ForegroundColor Cyan }
        if ($Quiet) {
            $compactOutput = & $CLASSIFIER db compact 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Error ($compactOutput -join "`n")
                exit $LASTEXITCODE
            }
        } else {
            & $CLASSIFIER db compact
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
    } else {
        if (-not $Quiet) { Write-Host "[1/4] compact 略過 (-SkipCompact)" -ForegroundColor DarkGray }
    }

    if (-not $Quiet) { Write-Host "[2/4] db-init..." -ForegroundColor Cyan }
    & $DB_TOOL db-init --sqlite $SQLITE_PATH --replace
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    if (-not $Quiet) { Write-Host "[3/4] db-import-json..." -ForegroundColor Cyan }
    & $DB_TOOL db-import-json --json $JSON_PATH --sqlite $SQLITE_PATH --replace
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    if (-not $Quiet) { Write-Host "[4/4] db-compare-json..." -ForegroundColor Cyan }
    & $DB_TOOL db-compare-json --json $JSON_PATH --sqlite $SQLITE_PATH
    if ($LASTEXITCODE -ne 0) {
        if (-not $Quiet) { Write-Host "`n✗ compare 失敗，shadow DB 可能不完整" -ForegroundColor Red }
        exit $LASTEXITCODE
    }

    if ($Benchmark) {
        if (-not $Quiet) { Write-Host "[+]  db-benchmark..." -ForegroundColor Cyan }
        & $DB_TOOL db-benchmark --json $JSON_PATH --sqlite $SQLITE_PATH
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    if (-not $Quiet) { Write-Host "`n✓ shadow DB 同步完成" -ForegroundColor Green }
} finally {
    Pop-Location
}
