# db-query.ps1 — Shadow SQLite 查詢腳本
# 用法:
#   scripts\db-query.ps1 tables
#   scripts\db-query.ps1 stats
#   scripts\db-query.ps1 search -Text ABF -Limit 20
#   scripts\db-query.ps1 code -Text ABF-056
#   scripts\db-query.ps1 actress -Text 女優名
#   scripts\db-query.ps1 studio -Text PRESTIGE
#   scripts\db-query.ps1 long-actresses -MinLength 10 -Limit 50
#   scripts\db-query.ps1 long-actresses -MinLength 10 -All
#   scripts\db-query.ps1 hash-actresses -All
#   scripts\db-query.ps1 long-title-fragments -All
#   scripts\db-query.ps1 sql -Sql "SELECT code, studio, actresses FROM videos_with_actresses LIMIT 10"
#
# 介面與舊 Bun 版本相同；內部委派給 db-tool query <mode>，不再需要 Bun。

param(
    [Parameter(Position = 0)]
    [ValidateSet("search", "code", "actress", "studio", "long-actresses", "hash-actresses", "long-title-fragments", "tables", "stats", "sql", "recent")]
    [string]$Mode = "search",

    [string]$Text = "",
    [string]$Sql = "",
    [int]$Limit = 20,
    [int]$MinLength = 10,
    [switch]$All,
    [string]$SqlitePath = ""
)

$ErrorActionPreference = "Stop"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT = Resolve-Path (Join-Path $SCRIPT_DIR "..")

if ([string]::IsNullOrWhiteSpace($SqlitePath)) {
    $SqlitePath = Join-Path $REPO_ROOT "data\shadow.sqlite"
}

if (-not (Test-Path $SqlitePath)) {
    Write-Error "找不到 SQLite：$SqlitePath。請先執行 scripts\db-sync.ps1 建立 data\shadow.sqlite"
    exit 1
}

$DB_TOOL = Join-Path $REPO_ROOT "tools-rs\target\release\db-tool.exe"
if (-not (Test-Path $DB_TOOL)) {
    Write-Error "找不到 $DB_TOOL，請先執行: cargo build --release --manifest-path tools-rs\Cargo.toml"
    exit 1
}

if ($Limit -lt 1) { $Limit = 1 }
if ($Limit -gt 500) { $Limit = 500 }
if ($MinLength -lt 1) { $MinLength = 1 }

$cmdArgs = @("query", $Mode, "--sqlite", (Resolve-Path $SqlitePath).Path)

switch ($Mode) {
    "tables" { }
    "stats" { }
    "recent" {
        $cmdArgs += @("--limit", [string]$Limit)
    }
    "code" {
        if (-not $Text) { Write-Error "code 模式需要 -Text，例如：scripts\db-query.ps1 code -Text ABF-056"; exit 1 }
        $cmdArgs += @("--text", $Text)
    }
    "actress" {
        if (-not $Text) { Write-Error "actress 模式需要 -Text"; exit 1 }
        $cmdArgs += @("--text", $Text, "--limit", [string]$Limit)
    }
    "studio" {
        if (-not $Text) { Write-Error "studio 模式需要 -Text"; exit 1 }
        $cmdArgs += @("--text", $Text, "--limit", [string]$Limit)
    }
    "search" {
        if (-not $Text) { Write-Error "search 模式需要 -Text，例如：scripts\db-query.ps1 search -Text ABF"; exit 1 }
        $cmdArgs += @("--text", $Text, "--limit", [string]$Limit)
    }
    "long-actresses" {
        $cmdArgs += @("--min-length", [string]$MinLength, "--limit", [string]$Limit)
        if ($All) { $cmdArgs += "--all" }
    }
    "hash-actresses" {
        $cmdArgs += @("--limit", [string]$Limit)
        if ($All) { $cmdArgs += "--all" }
    }
    "long-title-fragments" {
        $cmdArgs += @("--min-length", [string]$MinLength, "--limit", [string]$Limit)
        if ($All) { $cmdArgs += "--all" }
    }
    "sql" {
        if (-not $Sql) { Write-Error "sql 模式需要 -Sql"; exit 1 }
        $cmdArgs += @("--query", $Sql)
    }
}

& $DB_TOOL @cmdArgs
exit $LASTEXITCODE
