// Read-only diagnostic queries against the shadow SQLite. Replaces the
// Bun-based scripts/db-query.ps1 implementation; PowerShell wrapper now
// just forwards to `db-tool query <mode>`.

use crate::sqlite_db;
use anyhow::{bail, Result};
use clap::Subcommand;
use rusqlite::params;
use serde_json::{json, Map, Value};
use std::path::{Path, PathBuf};

#[derive(Subcommand)]
pub enum QueryCmd {
    /// List tables and views.
    Tables {
        #[arg(long)]
        sqlite: PathBuf,
    },
    /// Aggregate counts and last import metadata.
    Stats {
        #[arg(long)]
        sqlite: PathBuf,
    },
    /// Most recently updated videos.
    Recent {
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long, default_value_t = 20)]
        limit: usize,
    },
    /// Look up a single video by exact code.
    Code {
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long)]
        text: String,
    },
    /// Find videos featuring an actress (LIKE match).
    Actress {
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long)]
        text: String,
        #[arg(long, default_value_t = 20)]
        limit: usize,
    },
    /// Find videos by studio (LIKE match).
    Studio {
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long)]
        text: String,
        #[arg(long, default_value_t = 20)]
        limit: usize,
    },
    /// Fuzzy search across code/title/studio/actresses.
    Search {
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long)]
        text: String,
        #[arg(long, default_value_t = 20)]
        limit: usize,
    },
    /// Actress fields whose name length exceeds --min-length.
    LongActresses {
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long, default_value_t = 10)]
        min_length: usize,
        #[arg(long, default_value_t = 20)]
        limit: usize,
        #[arg(long, default_value_t = false)]
        all: bool,
    },
    /// Actress fields containing '#' (hash-joined cast strings).
    HashActresses {
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long, default_value_t = 20)]
        limit: usize,
        #[arg(long, default_value_t = false)]
        all: bool,
    },
    /// Long actress fields without '#' that may be title contamination.
    LongTitleFragments {
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long, default_value_t = 10)]
        min_length: usize,
        #[arg(long, default_value_t = 20)]
        limit: usize,
        #[arg(long, default_value_t = false)]
        all: bool,
    },
    /// Run an arbitrary read-only SELECT/WITH/PRAGMA query.
    Sql {
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long)]
        query: String,
    },
}

pub fn run(cmd: QueryCmd) -> Result<()> {
    let value = match cmd {
        QueryCmd::Tables { sqlite } => tables(&sqlite)?,
        QueryCmd::Stats { sqlite } => stats(&sqlite)?,
        QueryCmd::Recent { sqlite, limit } => recent(&sqlite, limit)?,
        QueryCmd::Code { sqlite, text } => code(&sqlite, &text)?,
        QueryCmd::Actress {
            sqlite,
            text,
            limit,
        } => actress(&sqlite, &text, limit)?,
        QueryCmd::Studio {
            sqlite,
            text,
            limit,
        } => studio(&sqlite, &text, limit)?,
        QueryCmd::Search {
            sqlite,
            text,
            limit,
        } => search(&sqlite, &text, limit)?,
        QueryCmd::LongActresses {
            sqlite,
            min_length,
            limit,
            all,
        } => long_actresses(&sqlite, min_length, limit, all)?,
        QueryCmd::HashActresses { sqlite, limit, all } => hash_actresses(&sqlite, limit, all)?,
        QueryCmd::LongTitleFragments {
            sqlite,
            min_length,
            limit,
            all,
        } => long_title_fragments(&sqlite, min_length, limit, all)?,
        QueryCmd::Sql { sqlite, query } => sql(&sqlite, &query)?,
    };
    println!("{}", serde_json::to_string_pretty(&value)?);
    Ok(())
}

fn collect_rows(
    stmt: &mut rusqlite::Statement,
    params: impl rusqlite::Params,
) -> Result<Vec<Map<String, Value>>> {
    let col_names: Vec<String> = stmt.column_names().iter().map(|s| s.to_string()).collect();
    let mut rows = Vec::new();
    let mut iter = stmt.query(params)?;
    while let Some(row) = iter.next()? {
        let mut obj = Map::new();
        for (i, name) in col_names.iter().enumerate() {
            let v: rusqlite::types::Value = row.get(i)?;
            obj.insert(name.clone(), sqlite_value_to_json(v));
        }
        rows.push(obj);
    }
    Ok(rows)
}

fn sqlite_value_to_json(v: rusqlite::types::Value) -> Value {
    match v {
        rusqlite::types::Value::Null => Value::Null,
        rusqlite::types::Value::Integer(i) => json!(i),
        rusqlite::types::Value::Real(f) => serde_json::Number::from_f64(f)
            .map(Value::Number)
            .unwrap_or(Value::Null),
        rusqlite::types::Value::Text(s) => Value::String(s),
        rusqlite::types::Value::Blob(b) => Value::String(format!("<{} bytes>", b.len())),
    }
}

fn tables(path: &Path) -> Result<Value> {
    let conn = sqlite_db::open_db(path)?;
    let mut stmt = conn.prepare(
        "SELECT type, name FROM sqlite_master
         WHERE type IN ('table', 'view')
         ORDER BY type, name",
    )?;
    let rows = collect_rows(&mut stmt, [])?;
    Ok(json!({"mode": "tables", "rows": rows}))
}

fn stats(path: &Path) -> Result<Value> {
    let conn = sqlite_db::open_db(path)?;
    let base = sqlite_db::stats_from_conn(&conn)?;
    let distinct_actresses: i64 = conn.query_row(
        "SELECT COUNT(DISTINCT actress_name) FROM video_actresses",
        [],
        |row| row.get(0),
    )?;
    let mut merged = base;
    merged["distinct_actresses"] = json!(distinct_actresses);
    merged["mode"] = json!("stats");
    Ok(merged)
}

fn recent(path: &Path, limit: usize) -> Result<Value> {
    let conn = sqlite_db::open_db(path)?;
    let mut stmt = conn.prepare(
        "SELECT code, title, studio, actresses
         FROM videos_with_actresses
         ORDER BY updated_at DESC, code ASC
         LIMIT ?1",
    )?;
    let rows = collect_rows(&mut stmt, params![limit as i64])?;
    Ok(json!({"mode": "recent", "rows": rows}))
}

fn code(path: &Path, code_value: &str) -> Result<Value> {
    let conn = sqlite_db::open_db(path)?;
    let mut stmt = conn.prepare(
        "SELECT code, title, studio, actresses, search_status, search_method, updated_at
         FROM videos_with_actresses
         WHERE code = ?1
         LIMIT 1",
    )?;
    let rows = collect_rows(&mut stmt, params![code_value])?;
    Ok(json!({"mode": "code", "rows": rows}))
}

fn actress(path: &Path, text: &str, limit: usize) -> Result<Value> {
    let conn = sqlite_db::open_db(path)?;
    let pattern = format!("%{text}%");
    let mut stmt = conn.prepare(
        "SELECT code, title, studio, actresses
         FROM videos_with_actresses
         WHERE code IN (
             SELECT video_code FROM video_actresses WHERE actress_name LIKE ?1
         )
         ORDER BY code ASC
         LIMIT ?2",
    )?;
    let rows = collect_rows(&mut stmt, params![pattern, limit as i64])?;
    Ok(json!({"mode": "actress", "rows": rows}))
}

fn studio(path: &Path, text: &str, limit: usize) -> Result<Value> {
    let conn = sqlite_db::open_db(path)?;
    let pattern = format!("%{text}%");
    let mut stmt = conn.prepare(
        "SELECT code, title, studio, actresses
         FROM videos_with_actresses
         WHERE studio LIKE ?1
         ORDER BY code ASC
         LIMIT ?2",
    )?;
    let rows = collect_rows(&mut stmt, params![pattern, limit as i64])?;
    Ok(json!({"mode": "studio", "rows": rows}))
}

fn search(path: &Path, text: &str, limit: usize) -> Result<Value> {
    let conn = sqlite_db::open_db(path)?;
    let pattern = format!("%{text}%");
    let mut stmt = conn.prepare(
        "SELECT code, title, studio, actresses
         FROM videos_with_actresses
         WHERE code LIKE ?1
            OR title LIKE ?1
            OR studio LIKE ?1
            OR actresses LIKE ?1
         ORDER BY code ASC
         LIMIT ?2",
    )?;
    let rows = collect_rows(&mut stmt, params![pattern, limit as i64])?;
    Ok(json!({"mode": "search", "rows": rows}))
}

fn long_actresses(path: &Path, min_length: usize, limit: usize, all: bool) -> Result<Value> {
    let conn = sqlite_db::open_db(path)?;
    let base = "SELECT
            va.actress_name,
            length(va.actress_name) AS name_length,
            COUNT(*) AS video_count,
            GROUP_CONCAT(va.video_code, ', ') AS codes
        FROM video_actresses va
        WHERE length(va.actress_name) > ?1
        GROUP BY va.actress_name
        ORDER BY name_length DESC, video_count DESC, va.actress_name ASC";
    let total: i64 = conn.query_row(
        &format!("SELECT COUNT(*) FROM ({base}) inner_q"),
        params![min_length as i64],
        |row| row.get(0),
    )?;
    let limited = !all;
    let rows = if limited {
        let final_sql = format!("{base} LIMIT ?2");
        let mut stmt = conn.prepare(&final_sql)?;
        collect_rows(&mut stmt, params![min_length as i64, limit as i64])?
    } else {
        let mut stmt = conn.prepare(base)?;
        collect_rows(&mut stmt, params![min_length as i64])?
    };
    Ok(json!({
        "mode": "long-actresses",
        "summary": {
            "min_length_exclusive": min_length,
            "category": "all_long_actress_fields",
            "total_matches": total,
            "returned_rows": rows.len(),
            "limited": limited,
        },
        "rows": rows,
    }))
}

fn hash_actresses(path: &Path, limit: usize, all: bool) -> Result<Value> {
    let conn = sqlite_db::open_db(path)?;
    let base = "SELECT
            va.actress_name,
            length(va.actress_name) AS name_length,
            COUNT(*) AS video_count,
            GROUP_CONCAT(va.video_code, ', ') AS codes
        FROM video_actresses va
        WHERE va.actress_name LIKE '%#%'
        GROUP BY va.actress_name
        ORDER BY name_length DESC, video_count DESC, va.actress_name ASC";
    let total: i64 = conn.query_row(
        &format!("SELECT COUNT(*) FROM ({base}) inner_q"),
        [],
        |row| row.get(0),
    )?;
    let limited = !all;
    let rows = if limited {
        let final_sql = format!("{base} LIMIT ?1");
        let mut stmt = conn.prepare(&final_sql)?;
        collect_rows(&mut stmt, params![limit as i64])?
    } else {
        let mut stmt = conn.prepare(base)?;
        collect_rows(&mut stmt, [])?
    };
    Ok(json!({
        "mode": "hash-actresses",
        "summary": {
            "category": "hash_joined_cast_fields",
            "total_matches": total,
            "returned_rows": rows.len(),
            "limited": limited,
        },
        "rows": rows,
    }))
}

fn long_title_fragments(path: &Path, min_length: usize, limit: usize, all: bool) -> Result<Value> {
    let conn = sqlite_db::open_db(path)?;
    let base = "SELECT
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
        WHERE length(va.actress_name) > ?1
          AND va.actress_name NOT LIKE '%#%'
        GROUP BY va.actress_name
        ORDER BY name_length DESC, video_count DESC, va.actress_name ASC";
    let total: i64 = conn.query_row(
        &format!("SELECT COUNT(*) FROM ({base}) inner_q"),
        params![min_length as i64],
        |row| row.get(0),
    )?;
    let limited = !all;
    let rows = if limited {
        let final_sql = format!("{base} LIMIT ?2");
        let mut stmt = conn.prepare(&final_sql)?;
        collect_rows(&mut stmt, params![min_length as i64, limit as i64])?
    } else {
        let mut stmt = conn.prepare(base)?;
        collect_rows(&mut stmt, params![min_length as i64])?
    };
    Ok(json!({
        "mode": "long-title-fragments",
        "summary": {
            "min_length_exclusive": min_length,
            "category": "long_without_hash",
            "total_matches": total,
            "returned_rows": rows.len(),
            "limited": limited,
        },
        "rows": rows,
    }))
}

fn sql(path: &Path, query: &str) -> Result<Value> {
    validate_readonly_sql(query)?;
    let conn = sqlite_db::open_db(path)?;
    let mut stmt = conn.prepare(query)?;
    let rows = collect_rows(&mut stmt, [])?;
    Ok(json!({"mode": "sql", "rows": rows}))
}

fn validate_readonly_sql(sql: &str) -> Result<()> {
    let trimmed = sql.trim().to_lowercase();
    if !(trimmed.starts_with("select")
        || trimmed.starts_with("with")
        || trimmed.starts_with("pragma"))
    {
        bail!("sql query must start with SELECT / WITH / PRAGMA");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validate_readonly_sql_accepts_select() {
        assert!(validate_readonly_sql("SELECT * FROM videos").is_ok());
        assert!(validate_readonly_sql("  select 1  ").is_ok());
    }

    #[test]
    fn validate_readonly_sql_accepts_with() {
        assert!(validate_readonly_sql("WITH a AS (SELECT 1) SELECT * FROM a").is_ok());
    }

    #[test]
    fn validate_readonly_sql_accepts_pragma() {
        assert!(validate_readonly_sql("PRAGMA user_version").is_ok());
    }

    #[test]
    fn validate_readonly_sql_rejects_writes() {
        for bad in [
            "INSERT INTO videos VALUES (1)",
            "UPDATE videos SET title = 'x'",
            "DELETE FROM videos",
            "DROP TABLE videos",
            "CREATE TABLE x (a INT)",
            "ALTER TABLE videos ADD COLUMN x INT",
            "ATTACH DATABASE 'x' AS y",
            "",
            "; SELECT 1",
        ] {
            assert!(validate_readonly_sql(bad).is_err(), "should reject: {bad}");
        }
    }
}
