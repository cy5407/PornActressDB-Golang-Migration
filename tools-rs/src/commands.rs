use crate::json_db::{load_json_rows, now_utc_rfc3339, InvalidRecord, VideoRow};
use crate::sqlite_db;
use anyhow::{bail, Context, Result};
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Instant;

type StringFieldAccessor = fn(&VideoRow) -> &str;

const COMPARED_STRING_FIELDS: &[(&str, StringFieldAccessor)] = &[
    ("title", |row| &row.title),
    ("studio", |row| &row.studio),
    ("release_date", |row| &row.release_date),
    ("url", |row| &row.url),
    ("search_status", |row| &row.search_status),
    ("search_method", |row| &row.search_method),
    ("last_search_date", |row| &row.last_search_date),
    ("created_at", |row| &row.created_at),
    ("updated_at", |row| &row.updated_at),
    ("original_filename", |row| &row.original_filename),
    ("file_path", |row| &row.file_path),
];

#[derive(Debug, Serialize)]
struct FieldMismatch {
    code: String,
    field: String,
    json: Value,
    sqlite: Value,
}

#[derive(Debug, Serialize)]
struct CompareReport {
    success: bool,
    source_consistent: bool,
    missing_in_sqlite: Vec<String>,
    extra_in_sqlite: Vec<String>,
    field_mismatches: Vec<FieldMismatch>,
    invalid_json_records: Vec<InvalidRecord>,
    duplicate_actresses: usize,
}

pub fn db_init(sqlite_path: &Path, replace: bool) -> Result<()> {
    let conn = sqlite_db::open_db(sqlite_path)?;
    sqlite_db::init_schema(&conn, replace)?;
    print_json(json!({
        "success": true,
        "sqlite": sqlite_path,
        "schema_version": sqlite_db::SCHEMA_VERSION,
    }))
}

pub fn db_import_json(
    json_path: &Path,
    sqlite_path: &Path,
    journal_path: Option<&Path>,
    replace: bool,
    allow_dirty_journal: bool,
) -> Result<()> {
    eprintln!(
        "warning: db-import-json is deprecated and operates on the legacy v2 shadow-DB schema. \
         The runtime database is now v3 SQLite owned by the Go side (classifier.exe db migrate-from-json). \
         This subcommand is kept for back-compat scripts and will not be removed without notice."
    );
    let timer = Instant::now();
    let started_at = now_utc_rfc3339();
    let source_consistent = ensure_clean_journal(json_path, journal_path, allow_dirty_journal)?;
    {
        let conn = sqlite_db::open_db(sqlite_path)?;
        sqlite_db::ensure_schema_compatible(&conn, replace)?;
    }
    let json_rows = load_json_rows(json_path)?;
    let actress_link_count = json_rows
        .rows
        .values()
        .map(|row| row.actress_items.len())
        .sum::<usize>();
    let metadata = sqlite_db::build_import_metadata(
        json_path,
        json_rows.rows.len(),
        actress_link_count,
        json_rows.invalid.len(),
        json_rows.duplicate_actresses,
        source_consistent,
        started_at,
    )?;
    let inserted_actresses =
        sqlite_db::import_rows(sqlite_path, &json_rows.rows, &metadata, replace)?;
    print_json(json!({
        "success": true,
        "videos": json_rows.rows.len(),
        "actresses": inserted_actresses,
        "invalid": json_rows.invalid.len(),
        "duplicate_actresses": json_rows.duplicate_actresses,
        "source_consistent": source_consistent,
        "elapsed_ms": timer.elapsed().as_millis(),
    }))
}

pub fn db_stats(sqlite_path: &Path) -> Result<()> {
    print_json(sqlite_db::stats(sqlite_path)?)
}

pub fn db_compare_json(
    json_path: &Path,
    sqlite_path: &Path,
    journal_path: Option<&Path>,
    allow_dirty_journal: bool,
    fail_on_mismatch: bool,
) -> Result<()> {
    let source_consistent = ensure_clean_journal(json_path, journal_path, allow_dirty_journal)?;
    let json_rows = load_json_rows(json_path)?;
    let sqlite_rows = sqlite_db::load_sqlite_rows(sqlite_path)?;
    let report = compare_rows(source_consistent, &json_rows, &sqlite_rows);
    print_json(serde_json::to_value(&report)?)?;
    if !report.success && fail_on_mismatch {
        std::process::exit(1);
    }
    Ok(())
}

pub fn db_benchmark(json_path: &Path, sqlite_path: &Path, iterations: usize) -> Result<()> {
    if iterations == 0 {
        bail!("iterations must be > 0");
    }

    let json_start = Instant::now();
    let mut json_rows = 0usize;
    for _ in 0..iterations {
        let rows = load_json_rows(json_path)?;
        json_rows = rows.rows.len();
        std::hint::black_box(json_rows);
    }
    let json_total_ms = json_start.elapsed().as_millis();

    let sqlite_cold_start = Instant::now();
    let mut sqlite_rows = 0usize;
    for _ in 0..iterations {
        let rows = sqlite_db::load_sqlite_rows(sqlite_path)?;
        sqlite_rows = rows.len();
        std::hint::black_box(sqlite_rows);
    }
    let sqlite_cold_total_ms = sqlite_cold_start.elapsed().as_millis();

    let conn = sqlite_db::open_db(sqlite_path)?;
    let sqlite_warm_start = Instant::now();
    for _ in 0..iterations {
        let rows = sqlite_db::load_rows_from_conn(&conn)?;
        sqlite_rows = rows.len();
        std::hint::black_box(sqlite_rows);
    }
    let sqlite_warm_total_ms = sqlite_warm_start.elapsed().as_millis();

    let sqlite_stats_start = Instant::now();
    for _ in 0..iterations {
        let stats = sqlite_db::stats_from_conn(&conn)?;
        std::hint::black_box(stats);
    }
    let sqlite_stats_total_ms = sqlite_stats_start.elapsed().as_millis();

    let open_start = Instant::now();
    for _ in 0..iterations {
        let conn = sqlite_db::open_db(sqlite_path)?;
        std::hint::black_box(&conn);
    }
    let sqlite_open_overhead_ms = open_start.elapsed().as_millis();

    print_json(json!({
        "success": true,
        "iterations": iterations,
        "json_rows": json_rows,
        "sqlite_rows": sqlite_rows,
        "json_total_ms": json_total_ms,
        "sqlite_cold_total_ms": sqlite_cold_total_ms,
        "sqlite_warm_total_ms": sqlite_warm_total_ms,
        "sqlite_stats_total_ms": sqlite_stats_total_ms,
        "sqlite_open_overhead_ms": sqlite_open_overhead_ms,
    }))
}

fn compare_rows(
    source_consistent: bool,
    json_rows: &crate::json_db::JsonRows,
    sqlite_rows: &BTreeMap<String, VideoRow>,
) -> CompareReport {
    let json_codes = json_rows.rows.keys().cloned().collect::<BTreeSet<_>>();
    let sqlite_codes = sqlite_rows.keys().cloned().collect::<BTreeSet<_>>();
    let missing_in_sqlite = json_codes
        .difference(&sqlite_codes)
        .cloned()
        .collect::<Vec<_>>();
    let extra_in_sqlite = sqlite_codes
        .difference(&json_codes)
        .cloned()
        .collect::<Vec<_>>();

    let mut field_mismatches = Vec::new();
    for code in json_codes.intersection(&sqlite_codes) {
        let json_row = &json_rows.rows[code];
        let sqlite_row = &sqlite_rows[code];
        for (field, accessor) in COMPARED_STRING_FIELDS {
            push_string_mismatch(
                &mut field_mismatches,
                code,
                field,
                accessor(json_row),
                accessor(sqlite_row),
            );
        }
        if json_row.actresses != sqlite_row.actresses {
            field_mismatches.push(FieldMismatch {
                code: code.clone(),
                field: "actresses".to_string(),
                json: json!(json_row.actresses),
                sqlite: json!(sqlite_row.actresses),
            });
        }
        let json_actress_items = sorted_actress_items(json_row);
        let sqlite_actress_items = sorted_actress_items(sqlite_row);
        if json_actress_items != sqlite_actress_items {
            field_mismatches.push(FieldMismatch {
                code: code.clone(),
                field: "actress_items".to_string(),
                json: json!(json_actress_items),
                sqlite: json!(sqlite_actress_items),
            });
        }
    }

    let success = missing_in_sqlite.is_empty()
        && extra_in_sqlite.is_empty()
        && field_mismatches.is_empty()
        && json_rows.invalid.is_empty();

    CompareReport {
        success,
        source_consistent,
        missing_in_sqlite,
        extra_in_sqlite,
        field_mismatches,
        invalid_json_records: json_rows.invalid.clone(),
        duplicate_actresses: json_rows.duplicate_actresses,
    }
}

fn sorted_actress_items(row: &VideoRow) -> Vec<crate::json_db::ActressItem> {
    let mut items = row.actress_items.clone();
    items.sort_by(|left, right| {
        left.name
            .cmp(&right.name)
            .then_with(|| left.ordinal.cmp(&right.ordinal))
    });
    items
}

fn push_string_mismatch(
    field_mismatches: &mut Vec<FieldMismatch>,
    code: &str,
    field: &str,
    json_value: &str,
    sqlite_value: &str,
) {
    if json_value != sqlite_value {
        field_mismatches.push(FieldMismatch {
            code: code.to_string(),
            field: field.to_string(),
            json: json!(json_value),
            sqlite: json!(sqlite_value),
        });
    }
}

fn ensure_clean_journal(
    json_path: &Path,
    journal_path: Option<&Path>,
    allow_dirty_journal: bool,
) -> Result<bool> {
    let path = journal_path
        .map(Path::to_path_buf)
        .or_else(|| inferred_journal_path(json_path));
    let Some(path) = path else {
        return Ok(true);
    };

    match fs::metadata(&path) {
        Ok(metadata) if metadata.len() > 0 => {
            if allow_dirty_journal {
                Ok(false)
            } else {
                bail!(
                    "journal is not clean: {}. Run classifier db compact first, or pass --allow-dirty-journal for diagnostics.",
                    path.display()
                );
            }
        }
        Ok(_) => Ok(true),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(true),
        Err(err) => Err(err).with_context(|| format!("read journal metadata: {}", path.display())),
    }
}

fn inferred_journal_path(json_path: &Path) -> Option<PathBuf> {
    if json_path.file_name().and_then(|name| name.to_str()) == Some("data.json") {
        Some(json_path.with_file_name("data.journal"))
    } else {
        None
    }
}

fn print_json(value: Value) -> Result<()> {
    println!("{}", serde_json::to_string_pretty(&value)?);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::json_db::{ActressItem, JsonRows};
    use rusqlite::Connection;

    fn row(code: &str, title: &str, studio: &str, actresses: Vec<&str>) -> VideoRow {
        VideoRow {
            code: code.to_string(),
            title: title.to_string(),
            studio: studio.to_string(),
            release_date: String::new(),
            url: String::new(),
            search_status: String::new(),
            search_method: String::new(),
            last_search_date: String::new(),
            created_at: String::new(),
            updated_at: String::new(),
            original_filename: String::new(),
            file_path: String::new(),
            actresses: actresses.iter().map(|v| v.to_string()).collect(),
            actress_items: actresses
                .iter()
                .enumerate()
                .map(|(ordinal, name)| ActressItem {
                    name: name.to_string(),
                    ordinal,
                })
                .collect(),
        }
    }

    fn set_string_field(row: &mut VideoRow, field: &str, value: &str) {
        match field {
            "title" => row.title = value.to_string(),
            "studio" => row.studio = value.to_string(),
            "release_date" => row.release_date = value.to_string(),
            "url" => row.url = value.to_string(),
            "search_status" => row.search_status = value.to_string(),
            "search_method" => row.search_method = value.to_string(),
            "last_search_date" => row.last_search_date = value.to_string(),
            "created_at" => row.created_at = value.to_string(),
            "updated_at" => row.updated_at = value.to_string(),
            "original_filename" => row.original_filename = value.to_string(),
            "file_path" => row.file_path = value.to_string(),
            other => panic!("unknown field: {other}"),
        }
    }

    #[test]
    fn duplicate_actresses_do_not_fail_compare() {
        let mut json_map = BTreeMap::new();
        json_map.insert("A".to_string(), row("A", "Title", "Studio", vec!["Alice"]));
        let json_rows = JsonRows {
            rows: json_map.clone(),
            invalid: Vec::new(),
            duplicate_actresses: 2,
        };
        let report = compare_rows(true, &json_rows, &json_map);
        assert!(report.success);
        assert_eq!(report.duplicate_actresses, 2);
    }

    #[test]
    fn compare_rows_reports_all_string_field_mismatches() {
        let mut json_map = BTreeMap::new();
        let mut sqlite_map = BTreeMap::new();

        for (field, _) in COMPARED_STRING_FIELDS {
            let code = format!("CODE-{field}");
            let mut json_row = row(&code, "Title", "Studio", Vec::new());
            let mut sqlite_row = json_row.clone();
            set_string_field(&mut json_row, field, "json-value");
            set_string_field(&mut sqlite_row, field, "sqlite-value");
            json_map.insert(code.clone(), json_row);
            sqlite_map.insert(code, sqlite_row);
        }

        let json_rows = JsonRows {
            rows: json_map,
            invalid: Vec::new(),
            duplicate_actresses: 0,
        };
        let report = compare_rows(true, &json_rows, &sqlite_map);
        assert!(!report.success);
        assert_eq!(report.field_mismatches.len(), COMPARED_STRING_FIELDS.len());

        let fields = report
            .field_mismatches
            .iter()
            .map(|mismatch| mismatch.field.as_str())
            .collect::<BTreeSet<_>>();
        let expected = COMPARED_STRING_FIELDS
            .iter()
            .map(|(field, _)| *field)
            .collect::<BTreeSet<_>>();
        assert_eq!(fields, expected);
    }

    #[test]
    fn compare_rows_succeeds_when_all_fields_match() {
        let mut json_map = BTreeMap::new();
        json_map.insert("A".to_string(), row("A", "Title", "Studio", vec!["Alice"]));
        let json_rows = JsonRows {
            rows: json_map.clone(),
            invalid: Vec::new(),
            duplicate_actresses: 0,
        };

        let report = compare_rows(true, &json_rows, &json_map);
        assert!(report.success);
        assert!(report.field_mismatches.is_empty());
    }

    #[test]
    fn compare_rows_reports_missing_and_extra_codes() {
        let mut json_map = BTreeMap::new();
        json_map.insert("ONLY-JSON".to_string(), row("ONLY-JSON", "T", "S", vec![]));
        json_map.insert("BOTH".to_string(), row("BOTH", "T", "S", vec![]));
        let json_rows = JsonRows {
            rows: json_map,
            invalid: Vec::new(),
            duplicate_actresses: 0,
        };

        let mut sqlite_map = BTreeMap::new();
        sqlite_map.insert("BOTH".to_string(), row("BOTH", "T", "S", vec![]));
        sqlite_map.insert(
            "ONLY-SQLITE".to_string(),
            row("ONLY-SQLITE", "T", "S", vec![]),
        );

        let report = compare_rows(true, &json_rows, &sqlite_map);
        assert!(!report.success);
        assert_eq!(report.missing_in_sqlite, vec!["ONLY-JSON".to_string()]);
        assert_eq!(report.extra_in_sqlite, vec!["ONLY-SQLITE".to_string()]);
    }

    #[test]
    fn compare_rows_marks_invalid_records_as_failure() {
        let json_rows = JsonRows {
            rows: BTreeMap::new(),
            invalid: vec![InvalidRecord {
                map_key: "X".to_string(),
                reason: "missing code".to_string(),
            }],
            duplicate_actresses: 0,
        };
        let report = compare_rows(true, &json_rows, &BTreeMap::new());
        assert!(!report.success, "invalid records should fail compare");
        assert_eq!(report.invalid_json_records.len(), 1);
    }

    #[test]
    fn compare_rows_reports_actress_item_ordinal_mismatch() {
        let json_row = row("A", "Title", "Studio", vec!["Alice"]);
        let mut sqlite_row = json_row.clone();
        sqlite_row.actress_items[0].ordinal = 9;

        let mut json_map = BTreeMap::new();
        json_map.insert("A".to_string(), json_row);
        let mut sqlite_map = BTreeMap::new();
        sqlite_map.insert("A".to_string(), sqlite_row);
        let json_rows = JsonRows {
            rows: json_map,
            invalid: Vec::new(),
            duplicate_actresses: 0,
        };

        let report = compare_rows(true, &json_rows, &sqlite_map);
        assert!(!report.success);
        assert!(report
            .field_mismatches
            .iter()
            .any(|mismatch| mismatch.field == "actress_items"));
    }

    #[test]
    fn db_import_json_rejects_v1_without_replace() {
        let dir = tempfile::tempdir().expect("tempdir");
        let json_path = dir.path().join("data.json");
        let sqlite_path = dir.path().join("shadow.sqlite");
        fs::write(
            &json_path,
            r#"{"videos":{"A":{"code":"A","title":"Title"}}}"#,
        )
        .expect("write json");

        let conn = Connection::open(&sqlite_path).expect("open db");
        conn.pragma_update(None, "user_version", 1).expect("set v1");
        drop(conn);

        let err = db_import_json(&json_path, &sqlite_path, None, false, true)
            .expect_err("v1 import without replace should fail");
        assert!(err.to_string().contains("schema v1"));
    }

    #[test]
    fn dirty_journal_fails_unless_allowed() {
        let dir = tempfile::tempdir().expect("tempdir");
        let json_path = dir.path().join("data.json");
        let journal_path = dir.path().join("data.journal");
        fs::write(&json_path, "{}").expect("write json");
        fs::write(&journal_path, "dirty").expect("write journal");

        assert!(ensure_clean_journal(&json_path, None, false).is_err());
        assert!(!ensure_clean_journal(&json_path, None, true).expect("allowed dirty"));
    }
}
