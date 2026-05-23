// Shared SQLite v3 schema for the actress classifier runtime database.
//
// Canonical source lives at `pkg/database/sqlite_schema.sql` because Go's
// `//go:embed` cannot reference paths outside its package directory. Rust's
// `include_str!` happily resolves relative paths, so the Rust side embeds
// the same file from the Go package. The schema_consistency tests in
// `tests/integration_db_tool.rs` verify the include and the on-disk file
// agree, guarding against accidental drift if someone forks the schema.

use rusqlite::Connection;

/// Structural schema version recorded via PRAGMA user_version. Must match
/// `SQLiteSchemaVersion` in pkg/database/sqlite_store.go.
pub const V3_SCHEMA_VERSION: i32 = 3;

/// Embedded copy of the canonical v3 schema. Rebuilds when the source file
/// changes (rustc tracks files used by include_str! via dep-info).
#[allow(dead_code)]
pub const V3_SCHEMA_SQL: &str = include_str!("../../pkg/database/sqlite_schema.sql");

/// Tables that must exist in a healthy v3 database. Matches the runtime
/// surface in pkg/database/sqlite_schema.sql §§ 2.1–2.4.
pub const V3_REQUIRED_TABLES: &[&str] = &[
    "db_meta",
    "videos",
    "actresses",
    "actress_aliases",
    "video_actress_links",
];

/// Views that must exist in a healthy v3 database. Matches
/// pkg/database/sqlite_schema.sql § 2.5.
pub const V3_REQUIRED_VIEWS: &[&str] = &[
    "actress_video_counts",
    "studio_statistics",
    "enhanced_actress_studio_statistics",
];

/// Apply the embedded v3 schema to a fresh connection and stamp
/// PRAGMA user_version. Intended for tests and the migrate skeleton —
/// the runtime initialiser lives in Go.
#[allow(dead_code)]
pub fn apply_v3_schema(conn: &Connection) -> rusqlite::Result<()> {
    conn.execute_batch(V3_SCHEMA_SQL)?;
    conn.pragma_update(None, "user_version", V3_SCHEMA_VERSION)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn canonical_schema_path() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("pkg")
            .join("database")
            .join("sqlite_schema.sql")
    }

    #[test]
    fn embedded_schema_matches_canonical_file_on_disk() {
        let on_disk =
            std::fs::read_to_string(canonical_schema_path()).expect("read canonical schema file");
        assert_eq!(
            V3_SCHEMA_SQL, on_disk,
            "embedded V3_SCHEMA_SQL drifted from pkg/database/sqlite_schema.sql"
        );
    }

    #[test]
    fn embedded_schema_contains_expected_v3_markers() {
        for table in V3_REQUIRED_TABLES {
            let marker = format!("CREATE TABLE IF NOT EXISTS {table}");
            assert!(
                V3_SCHEMA_SQL.contains(&marker),
                "schema missing table marker {marker:?}"
            );
        }
        for view in V3_REQUIRED_VIEWS {
            let marker = format!("CREATE VIEW {view}");
            assert!(
                V3_SCHEMA_SQL.contains(&marker),
                "schema missing view marker {marker:?}"
            );
        }
    }
}
