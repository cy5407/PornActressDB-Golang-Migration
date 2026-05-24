use crate::v3_schema;
use anyhow::{bail, Context, Result};
use rusqlite::{params, Connection, Transaction};
use serde::{Deserialize, Serialize};
use sha1::{Digest, Sha1};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::Path;
use std::time::Instant;

const ROLE_MAIN: &str = "主演";
const AUTO_ACTRESS_ID_PREFIX: &str = "auto_";

#[derive(Clone, Copy, Debug, Default)]
pub struct ImportOptions {
    pub replace: bool,
    pub auto_create_missing_actresses: bool,
}

#[derive(Debug, Default, Serialize)]
pub struct ImportReport {
    pub success: bool,
    pub source_path: String,
    pub sqlite_path: String,
    pub videos_imported: usize,
    pub actresses_imported: usize,
    pub links_imported: usize,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub auto_created: Vec<AutoCreatedEntry>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub unresolved: Vec<UnresolvedEntry>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub duplicates: Vec<DuplicateEntry>,
    pub elapsed_ms: i64,
}

#[derive(Debug, Clone, Eq, PartialEq, Serialize)]
pub struct AutoCreatedEntry {
    pub name: String,
    pub actress_id: String,
    pub video_code: String,
}

#[derive(Debug, Clone, Eq, PartialEq, Serialize)]
pub struct UnresolvedEntry {
    pub video_code: String,
    pub display: String,
}

#[derive(Debug, Clone, Eq, PartialEq, Serialize)]
pub struct DuplicateEntry {
    pub video_code: String,
    pub actress_name: String,
    pub actress_id: String,
    pub ordinals: Vec<usize>,
}

#[derive(Debug, Default, Deserialize)]
struct DatabaseRoot {
    #[serde(default)]
    schema_version: String,
    #[serde(default)]
    metadata: Option<DatabaseMetadata>,
    #[serde(default)]
    created_at: String,
    #[serde(default)]
    updated_at: String,
    #[serde(default)]
    videos: BTreeMap<String, Option<VideoData>>,
    #[serde(default)]
    actresses: BTreeMap<String, Option<ActressData>>,
    #[serde(default)]
    links: Vec<VideoActressLink>,
}

#[derive(Debug, Default, Deserialize)]
struct DatabaseMetadata {
    #[serde(default)]
    description: String,
    #[serde(default)]
    encoding: String,
}

#[derive(Debug, Default, Deserialize)]
struct VideoMetadata {
    #[serde(default)]
    source: String,
    #[serde(default)]
    confidence: f64,
}

#[derive(Debug, Default, Deserialize)]
struct VideoData {
    #[serde(default)]
    id: String,
    #[serde(default)]
    title: String,
    #[serde(default)]
    studio: String,
    #[serde(default)]
    studio_code: String,
    #[serde(default)]
    release_date: String,
    #[serde(default)]
    url: String,
    #[serde(default)]
    actresses: Vec<String>,
    #[serde(default)]
    search_status: String,
    #[serde(default)]
    search_method: String,
    #[serde(default)]
    last_search_date: String,
    #[serde(default)]
    avwiki_actress_status: String,
    #[serde(default)]
    avwiki_last_search_date: String,
    #[serde(default)]
    javdb_actress_status: String,
    #[serde(default)]
    javdb_last_search_date: String,
    #[serde(default)]
    metadata: VideoMetadata,
    #[serde(default)]
    created_at: String,
    #[serde(default)]
    updated_at: String,
    #[serde(default)]
    original_filename: String,
    #[serde(default)]
    file_path: String,
    #[serde(default)]
    error: String,
    #[serde(default)]
    error_kind: String,
}

#[derive(Debug, Default, Deserialize)]
struct ActressData {
    #[serde(default)]
    name: String,
    #[serde(default)]
    aliases: Vec<String>,
    #[serde(default)]
    created_at: String,
    #[serde(default)]
    updated_at: String,
}

#[derive(Debug, Default, Deserialize)]
struct VideoActressLink {
    #[serde(default)]
    video_code: String,
    #[serde(default)]
    actress_id: String,
    #[serde(default)]
    role_type: String,
    #[serde(default)]
    timestamp: String,
}

pub fn run(json: &Path, sqlite: &Path, opts: ImportOptions) -> Result<()> {
    let report = import_runtime_json(json, sqlite, opts)?;
    println!("{}", serde_json::to_string_pretty(&report)?);
    if !report.success {
        bail!("runtime v3 import failed");
    }
    Ok(())
}

pub fn import_runtime_json(
    json_path: &Path,
    sqlite_path: &Path,
    opts: ImportOptions,
) -> Result<ImportReport> {
    let start = Instant::now();
    let mut report = ImportReport {
        source_path: json_path.display().to_string(),
        sqlite_path: sqlite_path.display().to_string(),
        ..ImportReport::default()
    };

    let root = read_database_root(json_path)?;
    let mut conn = open_runtime_db(sqlite_path)?;
    let tx = conn.transaction().context("begin transaction")?;

    if opts.replace {
        wipe_runtime_tables(&tx)?;
    }
    migrate_db_meta(&tx, &root)?;
    let (mut id_by_name, id_by_alias, mut id_to_name) = migrate_actresses(&tx, &root, &mut report)?;
    migrate_videos_and_links(
        &tx,
        &root,
        opts,
        &mut report,
        &mut id_by_name,
        &id_by_alias,
        &mut id_to_name,
    )?;

    sort_report_lists(&mut report);
    if !report.unresolved.is_empty() || !report.duplicates.is_empty() {
        report.elapsed_ms = start.elapsed().as_millis() as i64;
        return Ok(report);
    }

    apply_link_overrides(&tx, &root.links)?;
    save_legacy_root_links(&tx, &root.links)?;
    tx.commit().context("commit transaction")?;

    report.success = true;
    report.elapsed_ms = start.elapsed().as_millis() as i64;
    Ok(report)
}

pub fn stable_actress_id(name: &str) -> String {
    let mut hasher = Sha1::new();
    hasher.update(name.trim().as_bytes());
    let digest = hasher.finalize();
    let hex = hex_lower(&digest);
    format!("{AUTO_ACTRESS_ID_PREFIX}{}", &hex[..16])
}

fn hex_lower(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        out.push(HEX[(b >> 4) as usize] as char);
        out.push(HEX[(b & 0x0f) as usize] as char);
    }
    out
}

fn read_database_root(path: &Path) -> Result<DatabaseRoot> {
    let raw =
        std::fs::read(path).with_context(|| format!("read source JSON {}", path.display()))?;
    serde_json::from_slice(&raw).with_context(|| format!("parse source JSON {}", path.display()))
}

fn open_runtime_db(path: &Path) -> Result<Connection> {
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("create sqlite parent {}", parent.display()))?;
        }
    }

    let conn = Connection::open(path).with_context(|| format!("open sqlite {}", path.display()))?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .context("enable foreign_keys")?;
    let version: i32 = conn
        .pragma_query_value(None, "user_version", |row| row.get(0))
        .context("read user_version")?;
    if version != 0 && version != v3_schema::V3_SCHEMA_VERSION {
        bail!(
            "{} is schema v{}, not runtime v{}",
            path.display(),
            version,
            v3_schema::V3_SCHEMA_VERSION
        );
    }
    v3_schema::apply_v3_schema(&conn).context("apply v3 schema")?;
    Ok(conn)
}

fn wipe_runtime_tables(tx: &Transaction<'_>) -> Result<()> {
    for table in [
        "legacy_video_actress_links",
        "video_actress_links",
        "actress_aliases",
        "videos",
        "actresses",
    ] {
        tx.execute(&format!("DELETE FROM {table}"), [])
            .with_context(|| format!("wipe {table}"))?;
    }
    Ok(())
}

fn migrate_db_meta(tx: &Transaction<'_>, root: &DatabaseRoot) -> Result<()> {
    let mut pairs = BTreeMap::new();
    if !root.schema_version.is_empty() {
        pairs.insert("schema_version", root.schema_version.as_str());
    }
    if let Some(metadata) = &root.metadata {
        if !metadata.description.is_empty() {
            pairs.insert("description", metadata.description.as_str());
        }
        if !metadata.encoding.is_empty() {
            pairs.insert("encoding", metadata.encoding.as_str());
        }
    }
    if !root.created_at.is_empty() {
        pairs.insert("created_at", root.created_at.as_str());
    }
    if !root.updated_at.is_empty() {
        pairs.insert("updated_at", root.updated_at.as_str());
    }
    for (key, value) in pairs {
        tx.execute(
            r#"INSERT INTO db_meta(key, value) VALUES(?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value"#,
            params![key, value],
        )
        .with_context(|| format!("upsert db_meta {key}"))?;
    }
    Ok(())
}

fn migrate_actresses(
    tx: &Transaction<'_>,
    root: &DatabaseRoot,
    report: &mut ImportReport,
) -> Result<(
    HashMap<String, String>,
    HashMap<String, String>,
    HashMap<String, String>,
)> {
    let mut id_by_name = HashMap::new();
    let mut id_by_alias = HashMap::new();
    let mut id_to_name = HashMap::new();

    for (id, maybe_actress) in &root.actresses {
        let Some(actress) = maybe_actress else {
            continue;
        };
        insert_actress_row(
            tx,
            id,
            &actress.name,
            &actress.created_at,
            &actress.updated_at,
        )?;
        id_by_name.insert(actress.name.clone(), id.clone());
        id_to_name.insert(id.clone(), actress.name.clone());
        for alias in &actress.aliases {
            tx.execute(
                "INSERT INTO actress_aliases(actress_id, alias) VALUES(?, ?)",
                params![id, alias],
            )
            .with_context(|| format!("insert alias {alias} for actress {id}"))?;
            id_by_alias.insert(alias.clone(), id.clone());
        }
        report.actresses_imported += 1;
    }
    Ok((id_by_name, id_by_alias, id_to_name))
}

fn migrate_videos_and_links(
    tx: &Transaction<'_>,
    root: &DatabaseRoot,
    opts: ImportOptions,
    report: &mut ImportReport,
    id_by_name: &mut HashMap<String, String>,
    id_by_alias: &HashMap<String, String>,
    id_to_name: &mut HashMap<String, String>,
) -> Result<()> {
    for (code, maybe_video) in &root.videos {
        let Some(video) = maybe_video else {
            continue;
        };
        insert_video_row(tx, code, video)?;
        report.videos_imported += 1;
        migrate_video_actresses(
            tx,
            code,
            video,
            opts,
            report,
            id_by_name,
            id_by_alias,
            id_to_name,
        )?;
    }
    Ok(())
}

fn migrate_video_actresses(
    tx: &Transaction<'_>,
    code: &str,
    video: &VideoData,
    opts: ImportOptions,
    report: &mut ImportReport,
    id_by_name: &mut HashMap<String, String>,
    id_by_alias: &HashMap<String, String>,
    id_to_name: &mut HashMap<String, String>,
) -> Result<()> {
    let mut ordinals_by_actress: HashMap<String, Vec<usize>> = HashMap::new();

    for (ordinal, display) in video.actresses.iter().enumerate() {
        let actress_id = match resolve_actress_id(display, id_by_name, id_by_alias) {
            Some(id) => id,
            None if opts.auto_create_missing_actresses => auto_create_actress(
                tx,
                display,
                &video.updated_at,
                report,
                id_by_name,
                id_to_name,
                code,
            )?,
            None => {
                report.unresolved.push(UnresolvedEntry {
                    video_code: code.to_string(),
                    display: display.clone(),
                });
                continue;
            }
        };

        let ordinals = ordinals_by_actress.entry(actress_id.clone()).or_default();
        ordinals.push(ordinal);
        if ordinals.len() > 1 {
            continue;
        }

        let display_name = match id_to_name.get(&actress_id) {
            Some(name) if name != display => display.as_str(),
            _ => "",
        };
        insert_link_row(
            tx,
            code,
            &actress_id,
            ROLE_MAIN,
            ordinal,
            display_name,
            &video.updated_at,
        )?;
        report.links_imported += 1;
    }

    for (actress_id, mut ordinals) in ordinals_by_actress {
        if ordinals.len() <= 1 {
            continue;
        }
        ordinals.sort_unstable();
        report.duplicates.push(DuplicateEntry {
            video_code: code.to_string(),
            actress_name: id_to_name.get(&actress_id).cloned().unwrap_or_default(),
            actress_id,
            ordinals,
        });
    }
    Ok(())
}

fn resolve_actress_id(
    display: &str,
    id_by_name: &HashMap<String, String>,
    id_by_alias: &HashMap<String, String>,
) -> Option<String> {
    id_by_name
        .get(display)
        .or_else(|| id_by_alias.get(display))
        .cloned()
}

fn auto_create_actress(
    tx: &Transaction<'_>,
    display: &str,
    timestamp: &str,
    report: &mut ImportReport,
    id_by_name: &mut HashMap<String, String>,
    id_to_name: &mut HashMap<String, String>,
    video_code: &str,
) -> Result<String> {
    let id = stable_actress_id(display);
    if id_to_name.contains_key(&id) {
        id_by_name.insert(display.to_string(), id.clone());
        return Ok(id);
    }
    insert_actress_row(tx, &id, display, timestamp, timestamp)?;
    id_by_name.insert(display.to_string(), id.clone());
    id_to_name.insert(id.clone(), display.to_string());
    report.actresses_imported += 1;
    report.auto_created.push(AutoCreatedEntry {
        name: display.to_string(),
        actress_id: id.clone(),
        video_code: video_code.to_string(),
    });
    Ok(id)
}

fn insert_actress_row(
    tx: &Transaction<'_>,
    id: &str,
    name: &str,
    created_at: &str,
    updated_at: &str,
) -> Result<()> {
    tx.execute(
        "INSERT INTO actresses(id, name, created_at, updated_at) VALUES(?, ?, ?, ?)",
        params![id, name, created_at, updated_at],
    )
    .with_context(|| format!("insert actress {id}"))?;
    Ok(())
}

fn insert_video_row(tx: &Transaction<'_>, code: &str, video: &VideoData) -> Result<()> {
    tx.execute(
        r#"INSERT INTO videos(
            code, id, title, studio, studio_code, release_date, url,
            search_status, search_method, last_search_date,
            avwiki_actress_status, avwiki_last_search_date,
            javdb_actress_status, javdb_last_search_date,
            metadata_source, metadata_confidence,
            created_at, updated_at, original_filename, file_path,
            error, error_kind
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"#,
        params![
            code,
            video.id,
            video.title,
            video.studio,
            video.studio_code,
            video.release_date,
            video.url,
            video.search_status,
            video.search_method,
            video.last_search_date,
            video.avwiki_actress_status,
            video.avwiki_last_search_date,
            video.javdb_actress_status,
            video.javdb_last_search_date,
            video.metadata.source,
            video.metadata.confidence,
            video.created_at,
            video.updated_at,
            video.original_filename,
            video.file_path,
            video.error,
            video.error_kind,
        ],
    )
    .with_context(|| format!("insert video {code}"))?;
    Ok(())
}

fn insert_link_row(
    tx: &Transaction<'_>,
    video_code: &str,
    actress_id: &str,
    role_type: &str,
    ordinal: usize,
    display_name: &str,
    timestamp: &str,
) -> Result<()> {
    tx.execute(
        r#"INSERT INTO video_actress_links(
            video_code, actress_id, role_type, ordinal, display_name, timestamp
        ) VALUES(?, ?, ?, ?, ?, ?)"#,
        params![
            video_code,
            actress_id,
            role_type,
            ordinal,
            display_name,
            timestamp
        ],
    )
    .with_context(|| format!("insert link {video_code}<->{actress_id}"))?;
    Ok(())
}

/// Persist the JSON `root.links[]` list verbatim into
/// `legacy_video_actress_links`. Orphan entries with empty `video_code`
/// or `actress_id` round-trip through this table because the
/// FK-constrained `video_actress_links` cannot hold them.
fn save_legacy_root_links(tx: &Transaction<'_>, links: &[VideoActressLink]) -> Result<()> {
    if links.is_empty() {
        return Ok(());
    }
    let mut stmt = tx
        .prepare(
            r#"INSERT INTO legacy_video_actress_links(
                ordinal, video_code, actress_id, role_type, timestamp
            ) VALUES(?, ?, ?, ?, ?)"#,
        )
        .context("prepare legacy_video_actress_links insert")?;
    for (i, link) in links.iter().enumerate() {
        stmt.execute(params![
            i as i64,
            link.video_code,
            link.actress_id,
            link.role_type,
            link.timestamp,
        ])
        .with_context(|| format!("insert legacy_video_actress_links[{i}]"))?;
    }
    Ok(())
}

fn apply_link_overrides(tx: &Transaction<'_>, links: &[VideoActressLink]) -> Result<()> {
    for link in links {
        let role = if link.role_type.is_empty() {
            ROLE_MAIN
        } else {
            &link.role_type
        };
        tx.execute(
            r#"UPDATE video_actress_links
                  SET role_type = ?, timestamp = ?
                WHERE video_code = ? AND actress_id = ?"#,
            params![role, link.timestamp, link.video_code, link.actress_id],
        )
        .with_context(|| format!("override link {}<->{}", link.video_code, link.actress_id))?;
    }
    Ok(())
}

fn sort_report_lists(report: &mut ImportReport) {
    report.unresolved.sort_by(|a, b| {
        a.video_code
            .cmp(&b.video_code)
            .then_with(|| a.display.cmp(&b.display))
    });
    report.duplicates.sort_by(|a, b| {
        a.video_code
            .cmp(&b.video_code)
            .then_with(|| a.actress_id.cmp(&b.actress_id))
    });
    report.auto_created.sort_by(|a, b| {
        a.name
            .cmp(&b.name)
            .then_with(|| a.video_code.cmp(&b.video_code))
    });

    let mut seen = BTreeSet::new();
    report
        .auto_created
        .retain(|entry| seen.insert((entry.actress_id.clone(), entry.video_code.clone())));
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::Connection;

    fn write_json(dir: &Path, body: &str) -> std::path::PathBuf {
        let path = dir.join("data.json");
        std::fs::write(&path, body).expect("write json");
        path
    }

    #[test]
    fn stable_actress_id_matches_go_contract() {
        let padded = stable_actress_id("  田中美奈実 ");
        let trimmed = stable_actress_id("田中美奈実");
        assert_eq!(padded, trimmed);
        assert!(padded.starts_with("auto_"));
        assert_eq!(padded.len(), "auto_".len() + 16);

        let nfc = stable_actress_id("é");
        let nfd = stable_actress_id("e\u{301}");
        assert_ne!(nfc, nfd, "NFC/NFD variants must not be collapsed");
    }

    #[test]
    fn imports_full_runtime_shape_and_link_override() {
        let temp = tempfile::tempdir().expect("tempdir");
        let json_path = write_json(
            temp.path(),
            r#"{
                "schema_version": "1.0.0",
                "metadata": {"description": "desc", "encoding": "UTF-8"},
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-02T00:00:00Z",
                "videos": {
                    "ABC-001": {
                        "id": "legacy",
                        "title": "Title",
                        "studio": "S1",
                        "studio_code": "s1",
                        "release_date": "2026-01-03",
                        "url": "https://example.test",
                        "actresses": ["Alias A", "Name B"],
                        "search_status": "success",
                        "search_method": "manual",
                        "last_search_date": "2026-01-04T00:00:00Z",
                        "avwiki_actress_status": "found",
                        "avwiki_last_search_date": "2026-01-05T00:00:00Z",
                        "javdb_actress_status": "skipped",
                        "javdb_last_search_date": "2026-01-06T00:00:00Z",
                        "metadata": {"source": "fixture", "confidence": 0.9},
                        "created_at": "2026-01-07T00:00:00Z",
                        "updated_at": "2026-01-08T00:00:00Z",
                        "original_filename": "ABC-001.mp4",
                        "file_path": "D:/ABC-001.mp4",
                        "error": "",
                        "error_kind": ""
                    }
                },
                "actresses": {
                    "a1": {"name": "Name A", "aliases": ["Alias A"], "created_at": "ca", "updated_at": "ua"},
                    "b1": {"name": "Name B", "aliases": [], "created_at": "cb", "updated_at": "ub"}
                },
                "links": [
                    {"video_code": "ABC-001", "actress_id": "a1", "role_type": "配角", "timestamp": "override-ts"}
                ]
            }"#,
        );
        let sqlite_path = temp.path().join("runtime.sqlite");

        let report = import_runtime_json(
            &json_path,
            &sqlite_path,
            ImportOptions {
                replace: true,
                auto_create_missing_actresses: false,
            },
        )
        .expect("import");
        assert!(report.success);
        assert_eq!(report.videos_imported, 1);
        assert_eq!(report.actresses_imported, 2);
        assert_eq!(report.links_imported, 2);

        let conn = Connection::open(sqlite_path).expect("open");
        let meta: String = conn
            .query_row(
                "SELECT value FROM db_meta WHERE key = 'description'",
                [],
                |row| row.get(0),
            )
            .expect("meta");
        assert_eq!(meta, "desc");
        let link: (String, i64, String, String) = conn
            .query_row(
                r#"SELECT role_type, ordinal, display_name, timestamp
                   FROM video_actress_links
                   WHERE video_code = 'ABC-001' AND actress_id = 'a1'"#,
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .expect("link");
        assert_eq!(
            link,
            (
                "配角".to_string(),
                0,
                "Alias A".to_string(),
                "override-ts".to_string()
            )
        );
    }

    #[test]
    fn strict_unresolved_rolls_back_replace() {
        let temp = tempfile::tempdir().expect("tempdir");
        let sqlite_path = temp.path().join("runtime.sqlite");
        {
            let conn = Connection::open(&sqlite_path).expect("open");
            v3_schema::apply_v3_schema(&conn).expect("schema");
            conn.execute(
                "INSERT INTO videos(code, title) VALUES('KEEP-001', 'keep')",
                [],
            )
            .expect("seed");
        }
        let json_path = write_json(
            temp.path(),
            r#"{"videos":{"MISS-001":{"actresses":["Missing"]}},"actresses":{}}"#,
        );

        let report = import_runtime_json(
            &json_path,
            &sqlite_path,
            ImportOptions {
                replace: true,
                auto_create_missing_actresses: false,
            },
        )
        .expect("domain report");
        assert!(!report.success);
        assert_eq!(report.unresolved.len(), 1);

        let conn = Connection::open(sqlite_path).expect("open");
        let count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM videos WHERE code = 'KEEP-001'",
                [],
                |row| row.get(0),
            )
            .expect("count");
        assert_eq!(count, 1, "failed import must rollback replace wipe");
    }

    #[test]
    fn auto_create_missing_actress_uses_stable_id() {
        let temp = tempfile::tempdir().expect("tempdir");
        let json_path = write_json(
            temp.path(),
            r#"{"videos":{"AUTO-001":{"actresses":[" 未知女優 "],"updated_at":"ts"}}}"#,
        );
        let sqlite_path = temp.path().join("runtime.sqlite");

        let report = import_runtime_json(
            &json_path,
            &sqlite_path,
            ImportOptions {
                replace: true,
                auto_create_missing_actresses: true,
            },
        )
        .expect("import");
        assert!(report.success);
        assert_eq!(report.auto_created.len(), 1);
        assert_eq!(
            report.auto_created[0].actress_id,
            stable_actress_id("未知女優")
        );
    }

    #[test]
    fn orphan_root_link_persists_in_legacy_table() {
        let temp = tempfile::tempdir().expect("tempdir");
        let json_path = write_json(
            temp.path(),
            r#"{
                "videos": {
                    "ABC-001": {
                        "title": "Title",
                        "actresses": ["Name A"],
                        "updated_at": "2026-01-08T00:00:00Z"
                    }
                },
                "actresses": {
                    "a1": {"name": "Name A", "aliases": []}
                },
                "links": [
                    {"video_code": "ABC-001", "actress_id": "a1", "role_type": "主演", "timestamp": "ts1"},
                    {"video_code": "", "actress_id": "", "role_type": "", "timestamp": ""}
                ]
            }"#,
        );
        let sqlite_path = temp.path().join("runtime.sqlite");

        let report = import_runtime_json(
            &json_path,
            &sqlite_path,
            ImportOptions {
                replace: true,
                auto_create_missing_actresses: false,
            },
        )
        .expect("import");
        assert!(report.success, "import failed: {report:?}");

        let conn = Connection::open(&sqlite_path).expect("open sqlite");
        let legacy_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM legacy_video_actress_links", [], |row| {
                row.get(0)
            })
            .expect("count legacy");
        assert_eq!(legacy_count, 2, "expected 2 legacy rows (1 normal + 1 orphan)");

        let orphan_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM legacy_video_actress_links WHERE video_code = '' AND actress_id = ''",
                [],
                |row| row.get(0),
            )
            .expect("count orphan");
        assert_eq!(orphan_count, 1, "orphan link not preserved");

        let runtime_orphans: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM video_actress_links WHERE video_code = ''",
                [],
                |row| row.get(0),
            )
            .expect("count runtime orphan");
        assert_eq!(runtime_orphans, 0, "orphan leaked into FK-constrained table");
    }

    #[test]
    fn duplicate_actress_in_same_video_fails_loudly() {
        let temp = tempfile::tempdir().expect("tempdir");
        let json_path = write_json(
            temp.path(),
            r#"{
                "videos":{"DUP-001":{"actresses":["Name A","Alias A"]}},
                "actresses":{"a1":{"name":"Name A","aliases":["Alias A"]}}
            }"#,
        );
        let sqlite_path = temp.path().join("runtime.sqlite");

        let report = import_runtime_json(
            &json_path,
            &sqlite_path,
            ImportOptions {
                replace: true,
                auto_create_missing_actresses: false,
            },
        )
        .expect("domain report");
        assert!(!report.success);
        assert_eq!(report.duplicates.len(), 1);
        assert_eq!(report.duplicates[0].ordinals, vec![0, 1]);
    }
}
