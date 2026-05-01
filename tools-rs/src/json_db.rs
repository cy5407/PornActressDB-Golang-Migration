use anyhow::{bail, Context, Result};
use serde::Serialize;
use serde_json::Value;
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;
use std::time::SystemTime;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ActressItem {
    pub name: String,
    pub ordinal: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct VideoRow {
    pub code: String,
    pub title: String,
    pub studio: String,
    pub release_date: String,
    pub url: String,
    pub search_status: String,
    pub search_method: String,
    pub last_search_date: String,
    pub created_at: String,
    pub updated_at: String,
    pub original_filename: String,
    pub file_path: String,
    pub actresses: Vec<String>,
    pub actress_items: Vec<ActressItem>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct InvalidRecord {
    pub map_key: String,
    pub reason: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct JsonRows {
    pub rows: BTreeMap<String, VideoRow>,
    pub invalid: Vec<InvalidRecord>,
    pub duplicate_actresses: usize,
}

pub fn load_json_rows(path: &Path) -> Result<JsonRows> {
    let source = fs::read_to_string(path)
        .with_context(|| format!("read JSON DB source: {}", path.display()))?;
    let root: Value = serde_json::from_str(&source)
        .with_context(|| format!("parse JSON DB source: {}", path.display()))?;
    let Some(root_obj) = root.as_object() else {
        bail!("JSON DB root must be an object");
    };

    let videos = root_obj
        .get("videos")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();

    let mut rows = BTreeMap::new();
    let mut invalid = Vec::new();
    let mut duplicate_actresses = 0;

    for (map_key, value) in videos {
        match video_from_value(&map_key, &value) {
            Ok((row, duplicates)) => {
                duplicate_actresses += duplicates;
                rows.insert(row.code.clone(), row);
            }
            Err(reason) => invalid.push(InvalidRecord {
                map_key,
                reason: reason.to_string(),
            }),
        }
    }

    Ok(JsonRows {
        rows,
        invalid,
        duplicate_actresses,
    })
}

fn video_from_value(
    map_key: &str,
    value: &Value,
) -> std::result::Result<(VideoRow, usize), String> {
    if !value.is_object() {
        return Err("video record must be an object".to_string());
    }

    let code = string_field(value, "code")
        .or_else(|| string_field(value, "id"))
        .ok_or_else(|| "video record missing code/id".to_string())?;

    if code.is_empty() {
        return Err("video record missing code/id".to_string());
    }

    let (actresses, actress_items, duplicate_count) = parse_actresses(value);

    let row = VideoRow {
        code,
        title: string_field(value, "title").unwrap_or_default(),
        studio: string_field(value, "studio").unwrap_or_default(),
        release_date: string_field(value, "release_date").unwrap_or_default(),
        url: string_field(value, "url").unwrap_or_default(),
        search_status: string_field(value, "search_status").unwrap_or_default(),
        search_method: string_field(value, "search_method").unwrap_or_default(),
        last_search_date: string_field(value, "last_search_date").unwrap_or_default(),
        created_at: string_field(value, "created_at").unwrap_or_default(),
        updated_at: string_field(value, "updated_at").unwrap_or_default(),
        original_filename: string_field(value, "original_filename").unwrap_or_default(),
        file_path: string_field(value, "file_path").unwrap_or_default(),
        actresses,
        actress_items,
    };

    let trimmed_key = map_key.trim();
    if !trimmed_key.is_empty() && trimmed_key != row.code {
        return Err(format!(
            "map key \"{}\" does not match record code \"{}\"",
            trimmed_key, row.code
        ));
    }
    Ok((row, duplicate_count))
}

fn string_field(value: &Value, key: &str) -> Option<String> {
    let text = value.get(key)?.as_str()?.trim().to_string();
    if text.is_empty() {
        None
    } else {
        Some(text)
    }
}

fn parse_actresses(value: &Value) -> (Vec<String>, Vec<ActressItem>, usize) {
    let Some(items) = value.get("actresses").and_then(Value::as_array) else {
        return (Vec::new(), Vec::new(), 0);
    };

    let mut seen = Vec::new();
    let mut actress_items = Vec::new();
    let mut duplicate_count = 0;

    for (ordinal, item) in items.iter().enumerate() {
        let Some(name) = item.as_str().map(str::trim).filter(|s| !s.is_empty()) else {
            continue;
        };
        let name = name.to_string();
        if !seen.contains(&name) {
            seen.push(name.clone());
            actress_items.push(ActressItem { name, ordinal });
        } else {
            duplicate_count += 1;
        }
    }

    let actresses = actress_items.iter().map(|item| item.name.clone()).collect();
    (actresses, actress_items, duplicate_count)
}

pub fn system_time_rfc3339(value: Option<SystemTime>) -> String {
    value
        .map(time::OffsetDateTime::from)
        .and_then(|t| {
            t.format(&time::format_description::well_known::Rfc3339)
                .ok()
        })
        .unwrap_or_default()
}

pub fn now_utc_rfc3339() -> String {
    time::OffsetDateTime::now_utc()
        .format(&time::format_description::well_known::Rfc3339)
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn load_json_rows_uses_id_fallback_and_tracks_duplicate_actresses() {
        let dir = tempfile::tempdir().expect("tempdir");
        let json_path = dir.path().join("data.json");
        let mut file = fs::File::create(&json_path).expect("create json");
        write!(
            file,
            r#"{{
                "videos": {{
                    "A": {{
                        "id": "A",
                        "title": "  Title  ",
                        "studio": "Studio",
                        "actresses": ["Alice", "Alice", " Bob ", ""]
                    }},
                    "B": {{"title": "missing code"}}
                }}
            }}"#
        )
        .expect("write json");

        let rows = load_json_rows(&json_path).expect("load rows");
        assert_eq!(rows.rows.len(), 1);
        assert_eq!(rows.invalid.len(), 1);
        assert_eq!(rows.duplicate_actresses, 1);

        let row = rows.rows.get("A").expect("row A");
        assert_eq!(row.title, "Title");
        assert_eq!(row.actresses, vec!["Alice".to_string(), "Bob".to_string()]);
        assert_eq!(
            row.actress_items,
            vec![
                ActressItem {
                    name: "Alice".to_string(),
                    ordinal: 0,
                },
                ActressItem {
                    name: "Bob".to_string(),
                    ordinal: 2,
                },
            ]
        );
    }

    #[test]
    fn load_json_rows_handles_empty_videos_object() {
        let dir = tempfile::tempdir().expect("tempdir");
        let json_path = dir.path().join("data.json");
        fs::write(&json_path, r#"{"videos": {}}"#).expect("write json");

        let rows = load_json_rows(&json_path).expect("load rows");
        assert_eq!(rows.rows.len(), 0);
        assert_eq!(rows.invalid.len(), 0);
        assert_eq!(rows.duplicate_actresses, 0);
    }

    #[test]
    fn load_json_rows_handles_missing_videos_key() {
        let dir = tempfile::tempdir().expect("tempdir");
        let json_path = dir.path().join("data.json");
        fs::write(&json_path, r#"{"meta": {"version": 1}}"#).expect("write json");

        let rows = load_json_rows(&json_path).expect("load rows");
        assert_eq!(rows.rows.len(), 0);
    }

    #[test]
    fn load_json_rows_rejects_non_object_root() {
        let dir = tempfile::tempdir().expect("tempdir");
        let json_path = dir.path().join("data.json");
        fs::write(&json_path, r#"["not", "an", "object"]"#).expect("write json");

        let err = load_json_rows(&json_path).expect_err("array root should fail");
        assert!(err.to_string().contains("must be an object"));
    }

    #[test]
    fn parse_actresses_skips_non_array_field() {
        use serde_json::json;
        let value = json!({
            "code": "A",
            "actresses": "not-an-array"
        });
        let (actresses, items, dupes) = parse_actresses(&value);
        assert!(actresses.is_empty());
        assert!(items.is_empty());
        assert_eq!(dupes, 0);
    }

    #[test]
    fn load_json_rows_marks_mismatched_map_key_as_invalid() {
        let dir = tempfile::tempdir().expect("tempdir");
        let json_path = dir.path().join("data.json");
        let mut file = fs::File::create(&json_path).expect("create json");
        write!(
            file,
            r#"{{
                "videos": {{
                    "WRONG-KEY": {{
                        "code": "RIGHT-CODE",
                        "title": "Title"
                    }}
                }}
            }}"#
        )
        .expect("write json");

        let rows = load_json_rows(&json_path).expect("load rows");
        assert_eq!(rows.rows.len(), 0, "row should be rejected, not inserted");
        assert_eq!(rows.invalid.len(), 1);

        let invalid = &rows.invalid[0];
        assert_eq!(invalid.map_key, "WRONG-KEY");
        assert!(
            invalid.reason.contains("WRONG-KEY"),
            "reason should mention map key: {}",
            invalid.reason
        );
        assert!(
            invalid.reason.contains("RIGHT-CODE"),
            "reason should mention record code: {}",
            invalid.reason
        );
    }
}
