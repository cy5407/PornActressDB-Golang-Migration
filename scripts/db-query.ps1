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
$env:DB_QUERY_ALL = if ($All) { "1" } else { "0" }
$env:DB_QUERY_SQLITE_PATH = (Resolve-Path $SqlitePath).Path

$script = @'
import { Database } from "bun:sqlite";

const mode = process.env.DB_QUERY_MODE || "search";
const text = process.env.DB_QUERY_TEXT || "";
const rawSql = process.env.DB_QUERY_SQL || "";
const limit = Math.max(1, Math.min(Number(process.env.DB_QUERY_LIMIT || "20"), 500));
const minLength = Math.max(1, Number(process.env.DB_QUERY_MIN_LENGTH || "10"));
const showAll = process.env.DB_QUERY_ALL === "1";
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

function printRowsWithSummary(summary, query, params) {
  const total = rows(`
    SELECT COUNT(*) AS count
    FROM (${query})
  `, params)[0].count;
  const pagedQuery = showAll ? query : `${query} LIMIT $limit`;
  const resultRows = rows(pagedQuery, params);
  console.log(JSON.stringify({
    ...summary,
    total_matches: total,
    returned_rows: resultRows.length,
    limited: !showAll,
  }, null, 2));
  print(resultRows);
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
      printRowsWithSummary(
        { min_length_exclusive: minLength, category: "all_long_actress_fields" },
        `
        SELECT
          va.actress_name,
          length(va.actress_name) AS name_length,
          COUNT(*) AS video_count,
          GROUP_CONCAT(va.video_code, ', ') AS codes
        FROM video_actresses va
        WHERE length(va.actress_name) > $minLength
        GROUP BY va.actress_name
        ORDER BY name_length DESC, video_count DESC, va.actress_name ASC
        `,
        { $minLength: minLength, $limit: limit }
      );
      break;

    case "hash-actresses":
      printRowsWithSummary(
        { category: "hash_joined_cast_fields" },
        `
        SELECT
          va.actress_name,
          length(va.actress_name) AS name_length,
          COUNT(*) AS video_count,
          GROUP_CONCAT(va.video_code, ', ') AS codes
        FROM video_actresses va
        WHERE va.actress_name LIKE '%#%'
        GROUP BY va.actress_name
        ORDER BY name_length DESC, video_count DESC, va.actress_name ASC
        `,
        { $limit: limit }
      );
      break;

    case "long-title-fragments":
      printRowsWithSummary(
        { min_length_exclusive: minLength, category: "long_without_hash" },
        `
        SELECT
          va.actress_name,
          length(va.actress_name) AS name_length,
          COUNT(*) AS video_count,
          GROUP_CONCAT(va.video_code, ', ') AS codes,
          COALESCE((
            SELECT GROUP_CONCAT(candidate.actress_name, ', ')
            FROM (
              SELECT DISTINCT known.actress_name
              FROM video_actresses known
              WHERE known.actress_name != va.actress_name
                AND known.actress_name NOT LIKE '%#%'
                AND length(known.actress_name) BETWEEN 3 AND 10
                AND instr(va.actress_name, known.actress_name) > 0
              ORDER BY length(known.actress_name) DESC, known.actress_name ASC
            ) candidate
          ), '') AS known_name_hits
        FROM video_actresses va
        WHERE length(va.actress_name) > $minLength
          AND va.actress_name NOT LIKE '%#%'
        GROUP BY va.actress_name
        ORDER BY name_length DESC, video_count DESC, va.actress_name ASC
        `,
        { $minLength: minLength, $limit: limit }
      );
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
