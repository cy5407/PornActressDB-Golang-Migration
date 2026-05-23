// Integration tests for the db-tool binary.
//
// Spawns the actual compiled binary via `CARGO_BIN_EXE_db-tool` (provided by
// Cargo for binary crates) and exercises end-to-end flows: db-init,
// db-import-json, db-compare-json, db-stats. Unit tests cover individual
// functions; this file covers the CLI plumbing and round-trip behaviour
// against a small in-memory fixture.

use std::path::Path;
use std::process::Command;

const FIXTURE: &str = r#"{
    "videos": {
        "ABC-001": {
            "code": "ABC-001",
            "title": "Title One",
            "studio": "Studio A",
            "release_date": "2025-01-01",
            "actresses": ["Alice", "Bob"]
        },
        "ABC-002": {
            "code": "ABC-002",
            "title": "Title Two",
            "studio": "Studio B",
            "actresses": ["Carol"]
        },
        "ABC-003": {
            "code": "ABC-003",
            "title": "Title Three",
            "studio": "Studio A",
            "actresses": []
        }
    }
}"#;

fn db_tool() -> Command {
    Command::new(env!("CARGO_BIN_EXE_db-tool"))
}

fn run(cmd: &mut Command) -> std::process::Output {
    let out = cmd.output().expect("spawn db-tool");
    if !out.status.success() {
        panic!(
            "db-tool failed (exit {:?}):\n--- stdout ---\n{}\n--- stderr ---\n{}",
            out.status.code(),
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr),
        );
    }
    out
}

fn write_fixture(dir: &Path, body: &str) -> std::path::PathBuf {
    let json_path = dir.join("data.json");
    std::fs::write(&json_path, body).expect("write fixture");
    json_path
}

#[test]
fn end_to_end_init_import_compare_succeeds() {
    let temp = tempfile::tempdir().expect("tempdir");
    let json_path = write_fixture(temp.path(), FIXTURE);
    let sqlite_path = temp.path().join("shadow.sqlite");

    run(db_tool().args([
        "db-init",
        "--sqlite",
        sqlite_path.to_str().unwrap(),
        "--replace",
    ]));

    let import_out = run(db_tool().args([
        "db-import-json",
        "--json",
        json_path.to_str().unwrap(),
        "--sqlite",
        sqlite_path.to_str().unwrap(),
        "--replace",
    ]));
    let import_stdout = String::from_utf8(import_out.stdout).unwrap();
    assert!(
        import_stdout.contains("\"videos\": 3"),
        "expected 3 videos, got: {import_stdout}"
    );
    assert!(
        import_stdout.contains("\"actresses\": 3"),
        "expected 3 actress links (Alice + Bob + Carol), got: {import_stdout}"
    );

    let compare_out = run(db_tool().args([
        "db-compare-json",
        "--json",
        json_path.to_str().unwrap(),
        "--sqlite",
        sqlite_path.to_str().unwrap(),
    ]));
    let compare_stdout = String::from_utf8(compare_out.stdout).unwrap();
    assert!(
        compare_stdout.contains("\"success\": true"),
        "expected compare success, got: {compare_stdout}"
    );

    let stats_out = run(db_tool().args(["db-stats", "--sqlite", sqlite_path.to_str().unwrap()]));
    let stats_stdout = String::from_utf8(stats_out.stdout).unwrap();
    assert!(stats_stdout.contains("\"schema_version\": 2"));
    assert!(stats_stdout.contains("\"video_count\": 3"));
    assert!(stats_stdout.contains("\"actress_link_count\": 3"));
    assert!(stats_stdout.contains("\"distinct_studio_count\": 2"));
}

#[test]
fn compare_detects_field_mismatch_after_sqlite_mutation() {
    let temp = tempfile::tempdir().expect("tempdir");
    let json_path = write_fixture(temp.path(), FIXTURE);
    let sqlite_path = temp.path().join("shadow.sqlite");

    run(db_tool().args([
        "db-import-json",
        "--json",
        json_path.to_str().unwrap(),
        "--sqlite",
        sqlite_path.to_str().unwrap(),
        "--replace",
    ]));

    // Mutate SQLite directly so JSON and SQLite drift.
    let conn = rusqlite::Connection::open(&sqlite_path).expect("open sqlite");
    conn.execute(
        "UPDATE videos SET release_date = '2099-12-31' WHERE code = 'ABC-001'",
        [],
    )
    .expect("mutate row");
    drop(conn);

    let out = db_tool()
        .args([
            "db-compare-json",
            "--json",
            json_path.to_str().unwrap(),
            "--sqlite",
            sqlite_path.to_str().unwrap(),
        ])
        .output()
        .expect("spawn compare");
    let stdout = String::from_utf8(out.stdout).unwrap();
    assert!(
        !out.status.success(),
        "compare should exit non-zero on mismatch"
    );
    assert!(
        stdout.contains("\"success\": false"),
        "report should mark success=false: {stdout}"
    );
    assert!(
        stdout.contains("\"field\": \"release_date\""),
        "report should call out release_date drift: {stdout}"
    );
    assert!(stdout.contains("\"code\": \"ABC-001\""));
}

#[test]
fn db_import_rejects_v1_schema_without_replace() {
    let temp = tempfile::tempdir().expect("tempdir");
    let json_path = write_fixture(temp.path(), FIXTURE);
    let sqlite_path = temp.path().join("shadow.sqlite");

    // Manually construct a v1-marked SQLite that the new tool must refuse.
    let conn = rusqlite::Connection::open(&sqlite_path).expect("open sqlite");
    conn.pragma_update(None, "user_version", 1)
        .expect("set v1 user_version");
    drop(conn);

    let out = db_tool()
        .args([
            "db-import-json",
            "--json",
            json_path.to_str().unwrap(),
            "--sqlite",
            sqlite_path.to_str().unwrap(),
        ])
        .output()
        .expect("spawn import");
    let stderr = String::from_utf8(out.stderr).unwrap();
    assert!(
        !out.status.success(),
        "import on v1 DB without --replace must fail"
    );
    assert!(
        stderr.contains("schema v1"),
        "stderr should explain v1 detection: {stderr}"
    );
}

#[test]
fn db_import_json_emits_deprecation_warning_to_stderr() {
    let temp = tempfile::tempdir().expect("tempdir");
    let json_path = write_fixture(temp.path(), FIXTURE);
    let sqlite_path = temp.path().join("shadow.sqlite");

    let out = run(db_tool().args([
        "db-import-json",
        "--json",
        json_path.to_str().unwrap(),
        "--sqlite",
        sqlite_path.to_str().unwrap(),
        "--replace",
    ]));
    let stderr = String::from_utf8(out.stderr).unwrap();
    assert!(
        stderr.contains("deprecated"),
        "stderr should mark db-import-json deprecated, got: {stderr}"
    );
}

#[test]
fn db_verify_succeeds_on_fresh_v3_database() {
    let temp = tempfile::tempdir().expect("tempdir");
    let sqlite_path = temp.path().join("runtime.sqlite");
    // Stand up a v3 SQLite directly via the embedded schema so this test
    // does not depend on the Go side being built.
    {
        let conn = rusqlite::Connection::open(&sqlite_path).expect("open");
        conn.execute_batch(include_str!("../../pkg/database/sqlite_schema.sql"))
            .expect("apply v3 schema");
        conn.pragma_update(None, "user_version", 3)
            .expect("stamp v3");
    }

    let out = run(db_tool().args(["db-verify", "--sqlite", sqlite_path.to_str().unwrap()]));
    let stdout = String::from_utf8(out.stdout).unwrap();
    assert!(stdout.contains("\"success\": true"));
    assert!(stdout.contains("\"schema_version\": 3"));
    assert!(stdout.contains("\"integrity_check\": \"ok\""));
}

#[test]
fn db_verify_fails_when_required_table_missing() {
    let temp = tempfile::tempdir().expect("tempdir");
    let sqlite_path = temp.path().join("partial.sqlite");
    {
        let conn = rusqlite::Connection::open(&sqlite_path).expect("open");
        conn.execute_batch(include_str!("../../pkg/database/sqlite_schema.sql"))
            .expect("apply schema");
        conn.pragma_update(None, "user_version", 3)
            .expect("stamp v3");
        conn.execute("DROP TABLE video_actress_links", [])
            .expect("drop");
    }

    let out = db_tool()
        .args(["db-verify", "--sqlite", sqlite_path.to_str().unwrap()])
        .output()
        .expect("spawn verify");
    assert!(
        !out.status.success(),
        "db-verify should exit non-zero when a required table is missing"
    );
    let stdout = String::from_utf8(out.stdout).unwrap();
    assert!(stdout.contains("\"success\": false"));
    assert!(stdout.contains("video_actress_links"));
}

#[test]
fn db_migrate_v3_to_v3_reports_noop() {
    let temp = tempfile::tempdir().expect("tempdir");
    let sqlite_path = temp.path().join("runtime.sqlite");
    {
        let conn = rusqlite::Connection::open(&sqlite_path).expect("open");
        conn.execute_batch(include_str!("../../pkg/database/sqlite_schema.sql"))
            .expect("apply schema");
        conn.pragma_update(None, "user_version", 3)
            .expect("stamp v3");
    }

    let out = run(db_tool().args(["db-migrate", "--sqlite", sqlite_path.to_str().unwrap()]));
    let stdout = String::from_utf8(out.stdout).unwrap();
    assert!(stdout.contains("\"success\": true"));
    assert!(stdout.contains("\"noop\": true"));
    assert!(stdout.contains("\"from_version\": 3"));
    assert!(stdout.contains("\"to_version\": 3"));
}

#[test]
fn db_migrate_unsupported_future_target_fails() {
    let temp = tempfile::tempdir().expect("tempdir");
    let sqlite_path = temp.path().join("runtime.sqlite");
    {
        let conn = rusqlite::Connection::open(&sqlite_path).expect("open");
        conn.execute_batch(include_str!("../../pkg/database/sqlite_schema.sql"))
            .expect("apply schema");
        conn.pragma_update(None, "user_version", 3)
            .expect("stamp v3");
    }

    let out = db_tool()
        .args([
            "db-migrate",
            "--sqlite",
            sqlite_path.to_str().unwrap(),
            "--target",
            "4",
        ])
        .output()
        .expect("spawn migrate");
    assert!(!out.status.success());
    let stdout = String::from_utf8(out.stdout).unwrap();
    assert!(stdout.contains("\"success\": false"));
    assert!(stdout.contains("beyond the highest known schema"));
}

#[test]
fn embedded_v3_schema_matches_canonical_go_package_file() {
    // Guards against forking the Rust embed away from the Go-side canonical
    // source. The test below is the production guarantee that Go and Rust
    // read the same bytes — the unit-test counterpart inside src/v3_schema.rs
    // covers the same property in a different harness.
    let canonical = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("pkg")
        .join("database")
        .join("sqlite_schema.sql");
    let on_disk = std::fs::read_to_string(&canonical).expect("read canonical schema");
    let embedded: &str = include_str!("../../pkg/database/sqlite_schema.sql");
    assert_eq!(embedded, on_disk);
}

#[test]
fn ordinal_preserved_through_round_trip() {
    let fixture = r#"{
        "videos": {
            "ORD-001": {
                "code": "ORD-001",
                "title": "Multi-cast",
                "studio": "S",
                "actresses": ["Zara", "Alice", "Mia"]
            }
        }
    }"#;
    let temp = tempfile::tempdir().expect("tempdir");
    let json_path = write_fixture(temp.path(), fixture);
    let sqlite_path = temp.path().join("shadow.sqlite");

    run(db_tool().args([
        "db-import-json",
        "--json",
        json_path.to_str().unwrap(),
        "--sqlite",
        sqlite_path.to_str().unwrap(),
        "--replace",
    ]));

    // The view joins actresses in ordinal order; if we'd alphabetised
    // them we'd see Alice first instead of Zara.
    let conn = rusqlite::Connection::open(&sqlite_path).expect("open sqlite");
    let actresses: String = conn
        .query_row(
            "SELECT actresses FROM videos_with_actresses WHERE code = 'ORD-001'",
            [],
            |row| row.get(0),
        )
        .expect("read view");
    assert_eq!(actresses, "Zara, Alice, Mia");
}
