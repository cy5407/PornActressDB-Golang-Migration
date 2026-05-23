// db-migrate: skeleton for forward migrations of the v3 SQLite runtime
// database. Slice C3 only ships the v3 → v3 no-op so the entry point
// exists and the JSON contract is fixed; higher target versions are
// surfaced as an unsupported-version error rather than speculative
// migration code.

use crate::v3_schema::V3_SCHEMA_VERSION;
use anyhow::{Context, Result};
use rusqlite::{Connection, OpenFlags};
use serde::Serialize;
use serde_json::json;
use std::path::Path;

#[derive(Debug, Serialize)]
pub struct MigrateReport {
    pub success: bool,
    pub sqlite: String,
    pub from_version: i32,
    pub to_version: i32,
    pub noop: bool,
    pub applied_steps: Vec<String>,
    pub message: String,
}

pub fn run(sqlite_path: &Path, target: i32) -> Result<()> {
    let report = migrate(sqlite_path, target)?;
    let success = report.success;
    println!("{}", serde_json::to_string_pretty(&json!(report))?);
    if !success {
        std::process::exit(1);
    }
    Ok(())
}

pub fn migrate(sqlite_path: &Path, target: i32) -> Result<MigrateReport> {
    let conn = Connection::open_with_flags(sqlite_path, OpenFlags::SQLITE_OPEN_READ_WRITE)
        .with_context(|| format!("open sqlite: {}", sqlite_path.display()))?;
    let from_version: i32 = conn.pragma_query_value(None, "user_version", |row| row.get(0))?;

    if target == from_version {
        return Ok(MigrateReport {
            success: true,
            sqlite: sqlite_path.display().to_string(),
            from_version,
            to_version: target,
            noop: true,
            applied_steps: Vec::new(),
            message: format!("already at user_version={target}; no migration needed"),
        });
    }

    if from_version == 0 {
        return Ok(MigrateReport {
            success: false,
            sqlite: sqlite_path.display().to_string(),
            from_version,
            to_version: target,
            noop: false,
            applied_steps: Vec::new(),
            message: String::from(
                "database has no schema (user_version=0); initialise via the Go runtime first",
            ),
        });
    }

    if target > V3_SCHEMA_VERSION {
        return Ok(MigrateReport {
            success: false,
            sqlite: sqlite_path.display().to_string(),
            from_version,
            to_version: target,
            noop: false,
            applied_steps: Vec::new(),
            message: format!(
                "target user_version={target} is beyond the highest known schema (v{V3_SCHEMA_VERSION}); db-tool needs to be updated before this migration is implemented"
            ),
        });
    }

    // The only currently-implemented migration is v3 → v3 (no-op above).
    // v2 → v3 and earlier paths are deliberately not implemented: the v3
    // runtime database is created by Go's InitSchema, not by upgrading a
    // legacy shadow-DB. Surfacing this loudly is the correct behaviour
    // rather than guessing a migration that hasn't been designed.
    Ok(MigrateReport {
        success: false,
        sqlite: sqlite_path.display().to_string(),
        from_version,
        to_version: target,
        noop: false,
        applied_steps: Vec::new(),
        message: format!(
            "migration from v{from_version} to v{target} is not implemented (db-tool only supports v{V3_SCHEMA_VERSION} → v{V3_SCHEMA_VERSION} no-op so far)"
        ),
    })
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
    fn migrate_v3_to_v3_is_noop() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("db.sqlite");
        fresh_v3_db(&path);

        let report = migrate(&path, V3_SCHEMA_VERSION).expect("migrate");
        assert!(report.success);
        assert!(report.noop);
        assert_eq!(report.from_version, V3_SCHEMA_VERSION);
        assert_eq!(report.to_version, V3_SCHEMA_VERSION);
        assert!(report.applied_steps.is_empty());
    }

    #[test]
    fn migrate_unsupported_future_target_fails_loudly() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("db.sqlite");
        fresh_v3_db(&path);

        let report = migrate(&path, V3_SCHEMA_VERSION + 1).expect("migrate");
        assert!(!report.success);
        assert!(report.message.contains("beyond the highest known schema"));
    }

    #[test]
    fn migrate_uninitialised_db_reports_missing_schema() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("empty.sqlite");
        Connection::open(&path).expect("open");

        let report = migrate(&path, V3_SCHEMA_VERSION).expect("migrate");
        assert!(!report.success);
        assert!(report.message.contains("user_version=0"));
    }

    #[test]
    fn migrate_missing_file_does_not_create_database() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("missing.sqlite");

        let err = migrate(&path, V3_SCHEMA_VERSION).expect_err("missing DB should fail open");
        assert!(
            err.to_string().contains("open sqlite"),
            "error should mention open failure: {err:#}"
        );
        assert!(
            !path.exists(),
            "db-migrate must not create missing SQLite files"
        );
    }

    #[test]
    fn migrate_v1_or_v2_legacy_db_is_unsupported() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("legacy.sqlite");
        let conn = Connection::open(&path).expect("open");
        conn.pragma_update(None, "user_version", 2).expect("set v2");
        drop(conn);

        let report = migrate(&path, V3_SCHEMA_VERSION).expect("migrate");
        assert!(!report.success);
        assert!(
            report.message.contains("not implemented"),
            "report message should explain the gap: {}",
            report.message
        );
    }
}
