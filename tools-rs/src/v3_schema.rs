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
    "legacy_video_actress_links",
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

/// Normalised, order-stable text description of everything in
/// `sqlite_master` that carries DDL. Two databases with the same fingerprint
/// have the same schema shape — columns, indexes, views, triggers and the
/// constraints spelled out in their CREATE statements.
///
/// `db-verify` only asserts that the required tables *exist*; it says nothing
/// about their shape. This fills that gap so a database reached by migration
/// can be compared against one built fresh from the canonical schema.
///
/// Rows with a NULL `sql` are skipped. Those are the `sqlite_autoindex_*`
/// entries SQLite synthesises for UNIQUE / composite PRIMARY KEY constraints
/// (this schema produces six of them). They carry no DDL of their own, and
/// dropping the constraint that creates one necessarily rewrites the owning
/// table's CREATE statement, which the fingerprint does capture.
///
/// The result is plain text rather than a hash: there is no SHA-256 crate in
/// this binary's dependency set, and a failing assertion that prints the two
/// schemas is far more useful than one that prints two hex strings.
///
/// Known limits, so a future reader does not mistake them for flakiness:
///
/// * **Does not cover `PRAGMA user_version`.** A database with the right shape
///   but the wrong stamped version fingerprints identically. Callers that care
///   must compare it separately (`fresh_and_migrated_schemas_converge` does).
/// * **`ALTER TABLE ... RENAME` rewrites stored DDL.** SQLite re-quotes the
///   affected identifiers, so `videos` becomes `"videos"` in the table, its
///   indexes and any view referencing it. A v4 migration written with the
///   official 12-step rename-and-rebuild recipe will therefore trip this
///   comparison on quoting alone, with no semantic difference. That is the
///   most likely first real failure here — treat it as a signal to teach
///   `normalise_ddl` to strip identifier quotes, not as a broken test.
/// * **Whitespace normalisation reaches inside string literals.** `DEFAULT ' '`
///   and `DEFAULT '   '` fingerprint the same. The canonical schema currently
///   has no literal containing runs of whitespace, so this is latent rather
///   than active.
#[allow(dead_code)]
pub fn schema_fingerprint(conn: &Connection) -> rusqlite::Result<String> {
    // `name NOT LIKE 'sqlite_%'` drops both the autoindex rows and anything
    // SQLite adds on its own later -- notably `sqlite_stat1`, which `ANALYZE`
    // creates. Without it, a migration that ends in ANALYZE would diverge from
    // a fresh database over a statistics table nobody is trying to compare.
    let mut statement = conn.prepare(
        "SELECT type, name, sql FROM sqlite_master \
         WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type, name",
    )?;
    let rows = statement.query_map([], |row| {
        let kind: String = row.get(0)?;
        let name: String = row.get(1)?;
        let sql: String = row.get(2)?;
        Ok(format!("{kind}\t{name}\t{}", normalise_ddl(&sql)))
    })?;

    let mut entries = Vec::new();
    for entry in rows {
        entries.push(entry?);
    }
    Ok(entries.join("\n"))
}

/// Collapse every run of whitespace to a single space and trim. SQLite stores
/// the CREATE statement verbatim, so reformatting the canonical .sql file
/// would otherwise read as a schema change.
#[allow(dead_code)]
fn normalise_ddl(sql: &str) -> String {
    sql.split_whitespace().collect::<Vec<_>>().join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::migrate::migrate;
    use std::path::PathBuf;

    fn fresh_db(path: &std::path::Path) -> Connection {
        let conn = Connection::open(path).expect("open sqlite");
        apply_v3_schema(&conn).expect("apply v3 schema");
        conn
    }

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

    // --- schema equivalence safety net (slice SCHEMA-CONV-1) ---------------

    /// T1. A database reached through `migrate` must end up with the same
    /// schema as one built fresh from the canonical file. Today `migrate`
    /// to the current version is a no-op, so this passes trivially — the
    /// assertion that keeps it honest over time is T2 below.
    #[test]
    fn fresh_and_migrated_schemas_converge() {
        let dir = tempfile::tempdir().expect("tempdir");

        let fresh_path = dir.path().join("fresh.sqlite");
        let fresh_fingerprint =
            schema_fingerprint(&fresh_db(&fresh_path)).expect("fingerprint fresh db");

        let migrated_path = dir.path().join("migrated.sqlite");
        drop(fresh_db(&migrated_path));
        let report =
            migrate(&migrated_path, V3_SCHEMA_VERSION).expect("migrate to current version");
        // `migrate` reports most failures as Ok(success: false) rather than
        // Err, so unwrapping the Result alone would let a failed migration
        // through and then compare two untouched databases.
        assert!(
            report.success && report.noop,
            "migrate to the current version should have succeeded as a no-op: {report:?}"
        );

        let migrated_conn = Connection::open(&migrated_path).expect("reopen migrated db");
        let migrated_fingerprint =
            schema_fingerprint(&migrated_conn).expect("fingerprint migrated db");

        assert_eq!(
            fresh_fingerprint, migrated_fingerprint,
            "a migrated database drifted from a freshly created one"
        );

        // The fingerprint deliberately ignores user_version, so compare it
        // here: a migration that produces the right shape but forgets to stamp
        // the version leaves a database every later version check misreads.
        let fresh_conn = Connection::open(&fresh_path).expect("reopen fresh db");
        let fresh_version: i32 = fresh_conn
            .pragma_query_value(None, "user_version", |row| row.get(0))
            .expect("read fresh user_version");
        let migrated_version: i32 = migrated_conn
            .pragma_query_value(None, "user_version", |row| row.get(0))
            .expect("read migrated user_version");
        assert_eq!(
            fresh_version, migrated_version,
            "migrated database carries a different user_version than a fresh one"
        );
    }

    /// T2. The tripwire that gives T1 its value.
    ///
    /// T1 only compares v3-fresh against v3-migrated. The moment the schema
    /// version rises, that comparison stops covering the new migration and
    /// would sit there green forever — worse than no test, because it reads
    /// as an equivalence guarantee that no longer holds. Rather than rely on
    /// someone remembering, bumping the version breaks this assertion.
    #[test]
    fn equivalence_test_must_be_extended_when_schema_version_rises() {
        assert_eq!(
            V3_SCHEMA_VERSION, 3,
            "schema version rose above 3, but fresh_and_migrated_schemas_converge still only \
             compares v3-fresh against a v3 no-op migrate, so it has ZERO detection power for \
             the new version. Extend that test to cover fresh(vN) vs migrate(v(N-1) -> vN) \
             BEFORE changing this number. Leaving both as-is ships a green test that proves \
             nothing."
        );
    }

    /// T3. Guards the fingerprint against column-level drift.
    #[test]
    fn fingerprint_detects_column_change() {
        let dir = tempfile::tempdir().expect("tempdir");
        let conn = fresh_db(&dir.path().join("t3.sqlite"));
        let baseline = schema_fingerprint(&conn).expect("baseline fingerprint");
        conn.execute_batch("ALTER TABLE videos ADD COLUMN probe_col TEXT")
            .expect("add probe column");
        let mutated = schema_fingerprint(&conn).expect("mutated fingerprint");
        assert_ne!(baseline, mutated, "fingerprint ignored an added column");
    }

    /// T4. Guards the fingerprint against index-level drift.
    #[test]
    fn fingerprint_detects_index_change() {
        let dir = tempfile::tempdir().expect("tempdir");
        let conn = fresh_db(&dir.path().join("t4.sqlite"));
        let baseline = schema_fingerprint(&conn).expect("baseline fingerprint");
        conn.execute_batch("CREATE INDEX probe_idx ON videos(title)")
            .expect("add probe index");
        let mutated = schema_fingerprint(&conn).expect("mutated fingerprint");
        assert_ne!(baseline, mutated, "fingerprint ignored an added index");
    }

    /// T5. Guards the fingerprint against view-level drift.
    #[test]
    fn fingerprint_detects_view_change() {
        let dir = tempfile::tempdir().expect("tempdir");
        let conn = fresh_db(&dir.path().join("t5.sqlite"));
        let baseline = schema_fingerprint(&conn).expect("baseline fingerprint");
        conn.execute_batch("CREATE VIEW probe_view AS SELECT 1 AS probe")
            .expect("add probe view");
        let mutated = schema_fingerprint(&conn).expect("mutated fingerprint");
        assert_ne!(baseline, mutated, "fingerprint ignored an added view");
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
