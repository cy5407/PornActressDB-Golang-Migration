// db-verify: structural integrity check for a v3 SQLite runtime database.
//
// Reports PRAGMA integrity_check, user_version, and presence of every
// required table/view from pkg/database/sqlite_schema.sql. Exits 0 on a
// healthy v3 database, non-zero otherwise. Read-only — never mutates.

use crate::v3_schema::{V3_REQUIRED_TABLES, V3_REQUIRED_VIEWS, V3_SCHEMA_VERSION};
use anyhow::{Context, Result};
use rusqlite::{Connection, OpenFlags};
use serde::Serialize;
use serde_json::Value;
use std::path::Path;

#[derive(Debug, Serialize)]
pub struct VerifyReport {
    pub success: bool,
    pub sqlite: String,
    pub schema_version: i32,
    pub expected_schema_version: i32,
    pub integrity_check: String,
    pub missing_tables: Vec<String>,
    pub missing_views: Vec<String>,
    pub failure_reason: Option<String>,
}

pub fn run(sqlite_path: &Path) -> Result<()> {
    let report = verify(sqlite_path)?;
    println!("{}", serde_json::to_string_pretty(&report)?);
    if !report.success {
        std::process::exit(1);
    }
    Ok(())
}

pub fn verify(sqlite_path: &Path) -> Result<VerifyReport> {
    let conn = Connection::open_with_flags(sqlite_path, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .with_context(|| format!("open sqlite: {}", sqlite_path.display()))?;
    conn.execute_batch("PRAGMA foreign_keys = ON;")?;

    let schema_version: i32 = conn.pragma_query_value(None, "user_version", |row| row.get(0))?;
    let integrity_check = read_integrity_check(&conn)?;
    let missing_tables = missing_objects(&conn, "table", V3_REQUIRED_TABLES)?;
    let missing_views = missing_objects(&conn, "view", V3_REQUIRED_VIEWS)?;

    let mut failure_reasons = Vec::new();
    if schema_version != V3_SCHEMA_VERSION {
        failure_reasons.push(format!(
            "user_version is {schema_version}, want {V3_SCHEMA_VERSION}"
        ));
    }
    if integrity_check.to_ascii_lowercase() != "ok" {
        failure_reasons.push(format!("integrity_check returned {integrity_check:?}"));
    }
    if !missing_tables.is_empty() {
        failure_reasons.push(format!("missing tables: {}", missing_tables.join(", ")));
    }
    if !missing_views.is_empty() {
        failure_reasons.push(format!("missing views: {}", missing_views.join(", ")));
    }

    let success = failure_reasons.is_empty();
    let failure_reason = if success {
        None
    } else {
        Some(failure_reasons.join("; "))
    };

    Ok(VerifyReport {
        success,
        sqlite: sqlite_path.display().to_string(),
        schema_version,
        expected_schema_version: V3_SCHEMA_VERSION,
        integrity_check,
        missing_tables,
        missing_views,
        failure_reason,
    })
}

fn read_integrity_check(conn: &Connection) -> Result<String> {
    let mut stmt = conn.prepare("PRAGMA integrity_check")?;
    let mut rows = stmt.query([])?;
    let mut messages = Vec::new();
    while let Some(row) = rows.next()? {
        let v: Value = match row.get_ref(0)? {
            rusqlite::types::ValueRef::Text(t) => {
                Value::String(String::from_utf8_lossy(t).into_owned())
            }
            rusqlite::types::ValueRef::Null => Value::Null,
            other => Value::String(format!("{other:?}")),
        };
        match v {
            Value::String(s) => messages.push(s),
            Value::Null => messages.push(String::from("null")),
            other => messages.push(other.to_string()),
        }
    }
    if messages.is_empty() {
        Ok(String::from("no rows returned"))
    } else if messages.len() == 1 {
        Ok(messages.remove(0))
    } else {
        Ok(messages.join("; "))
    }
}

fn missing_objects(conn: &Connection, kind: &str, expected: &[&str]) -> Result<Vec<String>> {
    let mut stmt =
        conn.prepare("SELECT name FROM sqlite_master WHERE type = ?1 AND name = ?2 LIMIT 1")?;
    let mut missing = Vec::new();
    for name in expected {
        let mut rows = stmt.query(rusqlite::params![kind, *name])?;
        if rows.next()?.is_none() {
            missing.push((*name).to_string());
        }
    }
    Ok(missing)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::v3_schema::apply_v3_schema;

    fn fresh_v3_db(path: &Path) {
        let conn = Connection::open(path).expect("open");
        apply_v3_schema(&conn).expect("apply v3 schema");
    }

    #[test]
    fn verify_succeeds_on_fresh_v3_database() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("db.sqlite");
        fresh_v3_db(&path);

        let report = verify(&path).expect("verify");
        assert!(
            report.success,
            "expected success, got reason {:?}",
            report.failure_reason
        );
        assert_eq!(report.schema_version, V3_SCHEMA_VERSION);
        assert_eq!(report.integrity_check.to_ascii_lowercase(), "ok");
        assert!(report.missing_tables.is_empty());
        assert!(report.missing_views.is_empty());
    }

    #[test]
    fn verify_reports_wrong_user_version_on_uninitialised_db() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("empty.sqlite");
        // Create empty file with PRAGMA user_version = 0.
        Connection::open(&path).expect("open");

        let report = verify(&path).expect("verify");
        assert!(!report.success);
        let reason = report.failure_reason.expect("reason");
        assert!(
            reason.contains("user_version is 0"),
            "reason should mention version drift: {reason}"
        );
        // All v3 tables/views should be reported missing too.
        assert_eq!(report.missing_tables.len(), V3_REQUIRED_TABLES.len());
        assert_eq!(report.missing_views.len(), V3_REQUIRED_VIEWS.len());
    }

    #[test]
    fn verify_missing_file_does_not_create_database() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("missing.sqlite");

        let err = verify(&path).expect_err("missing DB should fail read-only open");
        assert!(
            err.to_string().contains("open sqlite"),
            "error should mention open failure: {err:#}"
        );
        assert!(
            !path.exists(),
            "db-verify must not create missing SQLite files"
        );
    }

    #[test]
    fn verify_flags_missing_required_table() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("partial.sqlite");
        fresh_v3_db(&path);

        // Drop one required table to simulate manual corruption / partial
        // schema. Use video_actress_links because it has no FK-dependent
        // children, sidestepping any SQLite version differences around
        // dropping FK parents.
        let conn = Connection::open(&path).expect("open");
        conn.execute("DROP TABLE video_actress_links", [])
            .expect("drop");
        drop(conn);

        let report = verify(&path).expect("verify");
        assert!(!report.success);
        assert!(report
            .missing_tables
            .iter()
            .any(|t| t == "video_actress_links"));
    }

    #[test]
    fn verify_flags_missing_required_view() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("partial.sqlite");
        fresh_v3_db(&path);

        let conn = Connection::open(&path).expect("open");
        conn.execute("DROP VIEW actress_video_counts", [])
            .expect("drop view");
        drop(conn);

        let report = verify(&path).expect("verify");
        assert!(!report.success);
        assert!(report
            .missing_views
            .iter()
            .any(|v| v == "actress_video_counts"));
    }
}
