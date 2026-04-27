# db-query.ps1 — Shadow SQLite 查詢腳本
# 用法:
#   scripts\db-query.ps1 tables
#   scripts\db-query.ps1 stats
#   scripts\db-query.ps1 search -Text ABF -Limit 20
#   scripts\db-query.ps1 code -Text ABF-056
#   scripts\db-query.ps1 actress -Text 女優名
#   scripts\db-query.ps1 studio -Text PRESTIGE
#   scripts\db-query.ps1 long-actresses -MinLength 10 -Limit 50
#   scripts\db-query.ps1 sql -Sql "SELECT code, studio, actresses FROM videos_with_actresses LIMIT 10"

param(
    [Parameter(Position = 0)]
    [ValidateSet("search", "code", "actress", "studio", "long-actresses", "tables", "stats", "sql", "recent")]
    [string]$Mode = "search",

    [string]$Text = "",
    [string]$Sql = "",
    [int]$Limit = 20,
    [int]$MinLength = 10,
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

$bunCommand = Get-Command bun -ErrorAction SilentlyContinue
if ($bunCommand) {
    $BUN = $bunCommand.Source
} else {
    $BUN = Join-Path $HOME ".bun\bin\bun.exe"
}

if (-not (Test-Path $BUN)) {
    Write-Error "找不到 Bun。請先安裝 Bun，或重新開啟 terminal 讓 bun 進 PATH。"
    exit 1
}

if ($Limit -lt 1) {
    $Limit = 1
}
if ($Limit -gt 500) {
    $Limit = 500
}
if ($MinLength -lt 1) {
    $MinLength = 1
}

$env:DB_QUERY_MODE = $Mode
$env:DB_QUERY_TEXT = $Text
$env:DB_QUERY_SQL = $Sql
$env:DB_QUERY_LIMIT = [string]$Limit
$env:DB_QUERY_MIN_LENGTH = [string]$MinLength
$env:DB_QUERY_SQLITE_PATH = (Resolve-Path $SqlitePath).Path

$script = @'
import { Database } from "bun:sqlite";

const mode = process.env.DB_QUERY_MODE || "search";
const text = process.env.DB_QUERY_TEXT || "";
const rawSql = process.env.DB_QUERY_SQL || "";
const limit = Math.max(1, Math.min(Number(process.env.DB_QUERY_LIMIT || "20"), 500));
const minLength = Math.max(1, Number(process.env.DB_QUERY_MIN_LENGTH || "10"));
const sqlitePath = process.env.DB_QUERY_SQLITE_PATH;

const db = new Database(sqlitePath, { readonly: true });

function rows(sql, params = {}) {
  return db.query(sql).all(params);
}

function like(value) {
  return `%${value}%`;
}

function print(value) {
  if (Array.isArray(value)) {
    console.table(value);
  } else {
    console.log(JSON.stringify(value, null, 2));
  }
}

try {
  switch (mode) {
    case "tables":
      print(rows(`
        SELECT type, name
        FROM sqlite_master
        WHERE type IN ('table', 'view')
        ORDER BY type, name
      `));
      break;

    case "stats":
      print({
        videos: rows(`SELECT COUNT(*) AS count FROM videos`)[0].count,
        actress_links: rows(`SELECT COUNT(*) AS count FROM video_actresses`)[0].count,
        distinct_actresses: rows(`SELECT COUNT(DISTINCT actress_name) AS count FROM video_actresses`)[0].count,
        distinct_studios: rows(`SELECT COUNT(DISTINCT studio) AS count FROM videos WHERE studio != ''`)[0].count,
        empty_titles: rows(`SELECT COUNT(*) AS count FROM videos WHERE title = ''`)[0].count,
        last_import: rows(`
          SELECT id, started_at, finished_at, video_count, actress_link_count, source_consistent, source_path
          FROM import_runs
          ORDER BY id DESC
          LIMIT 1
        `)[0] || null,
      });
      break;

    case "recent":
      print(rows(`
        SELECT code, title, studio, actresses
        FROM videos_with_actresses
        ORDER BY updated_at DESC, code ASC
        LIMIT $limit
      `, { $limit: limit }));
      break;

    case "code":
      if (!text) throw new Error("code 模式需要 -Text，例如：scripts\\db-query.ps1 code -Text ABF-056");
      print(rows(`
        SELECT code, title, studio, actresses, search_status, search_method, updated_at
        FROM videos_with_actresses
        WHERE code = $code
        LIMIT 1
      `, { $code: text }));
      break;

    case "actress":
      if (!text) throw new Error("actress 模式需要 -Text");
      print(rows(`
        SELECT code, title, studio, actresses
        FROM videos_with_actresses
        WHERE code IN (
          SELECT video_code FROM video_actresses WHERE actress_name LIKE $text
        )
        ORDER BY code ASC
        LIMIT $limit
      `, { $text: like(text), $limit: limit }));
      break;

    case "studio":
      if (!text) throw new Error("studio 模式需要 -Text");
      print(rows(`
        SELECT code, title, studio, actresses
        FROM videos_with_actresses
        WHERE studio LIKE $text
        ORDER BY code ASC
        LIMIT $limit
      `, { $text: like(text), $limit: limit }));
      break;

    case "long-actresses":
      print(rows(`
        SELECT
          va.actress_name,
          length(va.actress_name) AS name_length,
          COUNT(*) AS video_count,
          GROUP_CONCAT(va.video_code, ', ') AS codes
        FROM video_actresses va
        WHERE length(va.actress_name) > $minLength
        GROUP BY va.actress_name
        ORDER BY name_length DESC, video_count DESC, va.actress_name ASC
        LIMIT $limit
      `, { $minLength: minLength, $limit: limit }));
      break;

    case "search":
      if (!text) throw new Error("search 模式需要 -Text，例如：scripts\\db-query.ps1 search -Text ABF");
      print(rows(`
        SELECT code, title, studio, actresses
        FROM videos_with_actresses
        WHERE code LIKE $text
           OR title LIKE $text
           OR studio LIKE $text
           OR actresses LIKE $text
        ORDER BY code ASC
        LIMIT $limit
      `, { $text: like(text), $limit: limit }));
      break;

    case "sql": {
      const normalized = rawSql.trim().toLowerCase();
      if (!normalized) throw new Error("sql 模式需要 -Sql");
      if (!/^(select|with|pragma)\b/.test(normalized)) {
        throw new Error("db-query.ps1 的 sql 模式只允許 SELECT / WITH / PRAGMA 查詢");
      }
      print(rows(rawSql));
      break;
    }

    default:
      throw new Error(`未知模式：${mode}`);
  }
} finally {
  db.close();
}
'@

& $BUN -e $script
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
