use crate::json_db::{now_utc_rfc3339, system_time_rfc3339, VideoRow};
use anyhow::{bail, Context, Result};
use rusqlite::{params, Connection, TransactionBehavior};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;
use std::time::SystemTime;

pub const SCHEMA_VERSION: i32 = 2;

#[derive(Debug, Clone)]
pub struct ImportMetadata {
    pub source_path: String,
    pub source_mtime: Option<SystemTime>,
    pub source_size_bytes: u64,
    pub video_count: usize,
    pub actress_link_count: usize,
    pub invalid_count: usize,
    pub duplicate_actresses: usize,
    pub source_consistent: bool,
    pub started_at: String,
    pub finished_at: String,
}

pub fn open_db(path: &Path) -> Result<Connection> {
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            fs::create_dir_all(parent)
                .with_context(|| format!("create sqlite parent dir: {}", parent.display()))?;
        }
    }
    let conn =
        Connection::open(path).with_context(|| format!("open sqlite: {}", path.display()))?;
    conn.execute_batch("PRAGMA foreign_keys = ON;")?;
    Ok(conn)
}

pub fn init_schema(conn: &Connection, replace: bool) -> Result<()> {
    ensure_schema_compatible(conn, replace)?;

    if replace {
        conn.execute_batch(
            "
            DROP VIEW IF EXISTS videos_with_actresses;
            DROP TABLE IF EXISTS video_actresses;
            DROP TABLE IF EXISTS videos;
            DROP TABLE IF EXISTS import_runs;
            ",
        )?;
    }

    conn.execute_batch(
        "
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS videos (
          code TEXT PRIMARY KEY NOT NULL,
          title TEXT NOT NULL DEFAULT '',
          studio TEXT NOT NULL DEFAULT '',
          release_date TEXT NOT NULL DEFAULT '',
          url TEXT NOT NULL DEFAULT '',
          search_status TEXT NOT NULL DEFAULT '',
          search_method TEXT NOT NULL DEFAULT '',
          last_search_date TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT '',
          updated_at TEXT NOT NULL DEFAULT '',
          original_filename TEXT NOT NULL DEFAULT '',
          file_path TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS video_actresses (
          video_code TEXT NOT NULL,
          actress_name TEXT NOT NULL,
          ordinal INTEGER NOT NULL,
          PRIMARY KEY (video_code, actress_name),
          FOREIGN KEY (video_code) REFERENCES videos(code) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_videos_studio ON videos(studio);
        CREATE INDEX IF NOT EXISTS idx_video_actresses_name ON video_actresses(actress_name);

        CREATE VIEW IF NOT EXISTS videos_with_actresses AS
        SELECT
          v.code,
          v.title,
          v.studio,
          COALESCE((
            SELECT group_concat(ordered.actress_name, ', ')
            FROM (
              SELECT va.actress_name
              FROM video_actresses va
              WHERE va.video_code = v.code
              ORDER BY va.ordinal, va.actress_name
            ) ordered
          ), '') AS actresses,
          v.release_date,
          v.url,
          v.search_status,
          v.search_method,
          v.last_search_date,
          v.created_at,
          v.updated_at,
          v.original_filename,
          v.file_path
        FROM videos v;

        CREATE TABLE IF NOT EXISTS import_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_path TEXT NOT NULL,
          source_mtime TEXT NOT NULL DEFAULT '',
          source_size_bytes INTEGER NOT NULL DEFAULT 0,
          video_count INTEGER NOT NULL DEFAULT 0,
          actress_link_count INTEGER NOT NULL DEFAULT 0,
          invalid_count INTEGER NOT NULL DEFAULT 0,
          duplicate_actresses INTEGER NOT NULL DEFAULT 0,
          source_consistent INTEGER NOT NULL DEFAULT 1,
          started_at TEXT NOT NULL,
          finished_at TEXT NOT NULL
        );
        ",
    )?;
    conn.pragma_update(None, "user_version", SCHEMA_VERSION)?;
    Ok(())
}

pub fn ensure_schema_compatible(conn: &Connection, replace: bool) -> Result<()> {
    let version = schema_version(conn)?;
    match version {
        0 | SCHEMA_VERSION => Ok(()),
        1 if replace => Ok(()),
        1 => bail!("shadow DB is schema v1, run with --replace to rebuild as v2 (or delete data\\shadow.sqlite)"),
        other => bail!("unknown shadow DB schema version: {other}. expected 0/1/2"),
    }
}

pub fn import_rows(
    sqlite_path: &Path,
    rows: &BTreeMap<String, VideoRow>,
    metadata: &ImportMetadata,
    replace: bool,
) -> Result<usize> {
    let mut conn = open_db(sqlite_path)?;
    init_schema(&conn, replace)?;
    let tx = conn.transaction_with_behavior(TransactionBehavior::Immediate)?;

    if replace {
        tx.execute("DELETE FROM video_actresses", [])?;
        tx.execute("DELETE FROM videos", [])?;
    }

    let mut actress_link_count = 0;
    for row in rows.values() {
        tx.execute(
            "
            INSERT OR REPLACE INTO videos (
                code, title, studio, release_date, url, search_status, search_method,
                last_search_date, created_at, updated_at, original_filename, file_path
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)
            ",
            params![
                row.code,
                row.title,
                row.studio,
                row.release_date,
                row.url,
                row.search_status,
                row.search_method,
                row.last_search_date,
                row.created_at,
                row.updated_at,
                row.original_filename,
                row.file_path,
            ],
        )?;
        tx.execute(
            "DELETE FROM video_actresses WHERE video_code = ?1",
            params![row.code],
        )?;
        for item in &row.actress_items {
            tx.execute(
                "
                INSERT INTO video_actresses (video_code, actress_name, ordinal)
                VALUES (?1, ?2, ?3)
                ",
                params![row.code, item.name, item.ordinal as i64],
            )?;
            actress_link_count += 1;
        }
    }

    tx.execute(
        "
        INSERT INTO import_runs (
            source_path, source_mtime, source_size_bytes, video_count, actress_link_count,
            invalid_count, duplicate_actresses, source_consistent, started_at, finished_at
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)
        ",
        params![
            metadata.source_path,
            system_time_rfc3339(metadata.source_mtime),
            metadata.source_size_bytes as i64,
            metadata.video_count as i64,
            metadata.actress_link_count as i64,
            metadata.invalid_count as i64,
            metadata.duplicate_actresses as i64,
            i64::from(metadata.source_consistent),
            metadata.started_at,
            metadata.finished_at,
        ],
    )?;

    tx.commit()?;
    Ok(actress_link_count)
}

pub fn load_sqlite_rows(sqlite_path: &Path) -> Result<BTreeMap<String, VideoRow>> {
    let conn = open_db(sqlite_path)?;
    load_rows_from_conn(&conn)
}

pub fn load_rows_from_conn(conn: &Connection) -> Result<BTreeMap<String, VideoRow>> {
    let actress_map = load_all_actresses(conn)?;
    let mut stmt = conn.prepare(
        "
        SELECT code, title, studio, release_date, url, search_status, search_method,
               last_search_date, created_at, updated_at, original_filename, file_path
        FROM videos
        ORDER BY code
        ",
    )?;
    let mut rows = BTreeMap::new();
    let iter = stmt.query_map([], |row| {
        let code: String = row.get(0)?;
        let actress_items = actress_map.get(&code).cloned().unwrap_or_default();
        let actresses = actress_items.iter().map(|item| item.name.clone()).collect();
        Ok(VideoRow {
            actresses,
            actress_items,
            code,
            title: row.get(1)?,
            studio: row.get(2)?,
            release_date: row.get(3)?,
            url: row.get(4)?,
            search_status: row.get(5)?,
            search_method: row.get(6)?,
            last_search_date: row.get(7)?,
            created_at: row.get(8)?,
            updated_at: row.get(9)?,
            original_filename: row.get(10)?,
            file_path: row.get(11)?,
        })
    })?;

    for row in iter {
        let row = row?;
        rows.insert(row.code.clone(), row);
    }
    Ok(rows)
}

fn load_all_actresses(
    conn: &Connection,
) -> Result<BTreeMap<String, Vec<crate::json_db::ActressItem>>> {
    let mut stmt = conn.prepare(
        "
        SELECT video_code, actress_name, ordinal
        FROM video_actresses
        ORDER BY video_code, ordinal, actress_name
        ",
    )?;
    let mut result: BTreeMap<String, Vec<crate::json_db::ActressItem>> = BTreeMap::new();
    let iter = stmt.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            crate::json_db::ActressItem {
                name: row.get::<_, String>(1)?,
                ordinal: row.get::<_, i64>(2)? as usize,
            },
        ))
    })?;
    for item in iter {
        let (video_code, actress) = item?;
        result.entry(video_code).or_default().push(actress);
    }
    Ok(result)
}

pub fn stats(sqlite_path: &Path) -> Result<Value> {
    let conn = open_db(sqlite_path)?;
    stats_from_conn(&conn)
}

pub fn stats_from_conn(conn: &Connection) -> Result<Value> {
    let video_count: i64 = conn.query_row("SELECT COUNT(*) FROM videos", [], |row| row.get(0))?;
    let actress_link_count: i64 =
        conn.query_row("SELECT COUNT(*) FROM video_actresses", [], |row| row.get(0))?;
    let distinct_studio_count: i64 = conn.query_row(
        "SELECT COUNT(DISTINCT studio) FROM videos WHERE studio <> ''",
        [],
        |row| row.get(0),
    )?;
    let empty_title_count: i64 =
        conn.query_row("SELECT COUNT(*) FROM videos WHERE title = ''", [], |row| {
            row.get(0)
        })?;

    let last_import = last_import_run(conn)?;
    Ok(json!({
        "success": true,
        "schema_version": schema_version(conn)?,
        "video_count": video_count,
        "actress_link_count": actress_link_count,
        "distinct_studio_count": distinct_studio_count,
        "empty_title_count": empty_title_count,
        "last_import": last_import,
    }))
}

fn schema_version(conn: &Connection) -> Result<i32> {
    Ok(conn.pragma_query_value(None, "user_version", |row| row.get(0))?)
}

fn last_import_run(conn: &Connection) -> Result<Value> {
    let mut stmt = conn.prepare(
        "
        SELECT id, source_path, source_mtime, source_size_bytes, video_count,
               actress_link_count, invalid_count, duplicate_actresses,
               source_consistent, started_at, finished_at
        FROM import_runs
        ORDER BY id DESC
        LIMIT 1
        ",
    )?;
    let mut rows = stmt.query([])?;
    if let Some(row) = rows.next()? {
        Ok(json!({
            "id": row.get::<_, i64>(0)?,
            "source_path": row.get::<_, String>(1)?,
            "source_mtime": row.get::<_, String>(2)?,
            "source_size_bytes": row.get::<_, i64>(3)?,
            "video_count": row.get::<_, i64>(4)?,
            "actress_link_count": row.get::<_, i64>(5)?,
            "invalid_count": row.get::<_, i64>(6)?,
            "duplicate_actresses": row.get::<_, i64>(7)?,
            "source_consistent": row.get::<_, i64>(8)? != 0,
            "started_at": row.get::<_, String>(9)?,
            "finished_at": row.get::<_, String>(10)?,
        }))
    } else {
        Ok(Value::Null)
    }
}

pub fn build_import_metadata(
    json_path: &Path,
    video_count: usize,
    actress_link_count: usize,
    invalid_count: usize,
    duplicate_actresses: usize,
    source_consistent: bool,
    started_at: String,
) -> Result<ImportMetadata> {
    let metadata = fs::metadata(json_path)
        .with_context(|| format!("read JSON DB metadata: {}", json_path.display()))?;
    Ok(ImportMetadata {
        source_path: json_path.display().to_string(),
        source_mtime: metadata.modified().ok(),
        source_size_bytes: metadata.len(),
        video_count,
        actress_link_count,
        invalid_count,
        duplicate_actresses,
        source_consistent,
        started_at,
        finished_at: now_utc_rfc3339(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::json_db::{ActressItem, VideoRow};

    #[test]
    fn import_and_load_rows_without_n_plus_one_shape() {
        let dir = tempfile::tempdir().expect("tempdir");
        let sqlite_path = dir.path().join("shadow.sqlite");
        let mut rows = BTreeMap::new();
        rows.insert(
            "A".to_string(),
            VideoRow {
                code: "A".to_string(),
                title: "Title".to_string(),
                studio: "Studio".to_string(),
                release_date: String::new(),
                url: String::new(),
                search_status: String::new(),
                search_method: String::new(),
                last_search_date: String::new(),
                created_at: String::new(),
                updated_at: String::new(),
                original_filename: String::new(),
                file_path: String::new(),
                actresses: vec!["Alice".to_string(), "Bob".to_string()],
                actress_items: vec![
                    ActressItem {
                        name: "Alice".to_string(),
                        ordinal: 0,
                    },
                    ActressItem {
                        name: "Bob".to_string(),
                        ordinal: 2,
                    },
                ],
            },
        );
        let metadata = ImportMetadata {
            source_path: "data.json".to_string(),
            source_mtime: None,
            source_size_bytes: 2,
            video_count: 1,
            actress_link_count: 2,
            invalid_count: 0,
            duplicate_actresses: 0,
            source_consistent: true,
            started_at: "start".to_string(),
            finished_at: "finish".to_string(),
        };

        import_rows(&sqlite_path, &rows, &metadata, true).expect("import rows");
        let loaded = load_sqlite_rows(&sqlite_path).expect("load sqlite rows");
        assert_eq!(
            loaded["A"].actresses,
            vec!["Alice".to_string(), "Bob".to_string()]
        );

        let stats = stats(&sqlite_path).expect("stats");
        assert_eq!(stats["video_count"], 1);
        assert_eq!(stats["actress_link_count"], 2);

        let conn = open_db(&sqlite_path).expect("open db");
        let summary: String = conn
            .query_row(
                "SELECT actresses FROM videos_with_actresses WHERE code = 'A'",
                [],
                |row| row.get(0),
            )
            .expect("summary view");
        assert_eq!(summary, "Alice, Bob");
    }

    #[test]
    fn init_schema_rejects_v1_without_replace() {
        let dir = tempfile::tempdir().expect("tempdir");
        let sqlite_path = dir.path().join("shadow.sqlite");
        let conn = open_db(&sqlite_path).expect("open db");
        conn.pragma_update(None, "user_version", 1).expect("set v1");

        let err = init_schema(&conn, false).expect_err("v1 without replace should fail");
        assert!(err.to_string().contains("schema v1"));
    }

    #[test]
    fn init_schema_rebuilds_v1_with_replace() {
        let dir = tempfile::tempdir().expect("tempdir");
        let sqlite_path = dir.path().join("shadow.sqlite");
        let conn = open_db(&sqlite_path).expect("open db");
        conn.pragma_update(None, "user_version", 1).expect("set v1");

        init_schema(&conn, true).expect("replace v1");
        let version = schema_version(&conn).expect("schema version");
        assert_eq!(version, SCHEMA_VERSION);
    }

    #[test]
    fn init_schema_rejects_unknown_version_even_with_replace() {
        let dir = tempfile::tempdir().expect("tempdir");
        let sqlite_path = dir.path().join("shadow.sqlite");
        let conn = open_db(&sqlite_path).expect("open db");
        conn.pragma_update(None, "user_version", 3).expect("set v3");

        let err = init_schema(&conn, true).expect_err("v3 should fail");
        assert!(err
            .to_string()
            .contains("unknown shadow DB schema version: 3"));
    }
}
