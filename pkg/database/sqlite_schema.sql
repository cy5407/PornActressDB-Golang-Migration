-- SQLite schema for the actress classifier database.
-- Matches docs/superpowers/specs/2026-05-23-sqlite-migration-design.md § 2.
-- Structural version is recorded separately via PRAGMA user_version (set by
-- pkg/database/sqlite_store.go); the literal version constant lives in
-- SQLiteSchemaVersion.

-- 2.1 db_meta -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS db_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 2.2 videos ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS videos (
    code                     TEXT PRIMARY KEY,
    id                       TEXT NOT NULL DEFAULT '',
    title                    TEXT NOT NULL DEFAULT '',
    studio                   TEXT NOT NULL DEFAULT '',
    studio_code              TEXT NOT NULL DEFAULT '',
    release_date             TEXT NOT NULL DEFAULT '',
    url                      TEXT NOT NULL DEFAULT '',
    search_status            TEXT NOT NULL DEFAULT '',
    search_method            TEXT NOT NULL DEFAULT '',
    last_search_date         TEXT NOT NULL DEFAULT '',
    avwiki_actress_status    TEXT NOT NULL DEFAULT '',
    avwiki_last_search_date  TEXT NOT NULL DEFAULT '',
    javdb_actress_status     TEXT NOT NULL DEFAULT '',
    javdb_last_search_date   TEXT NOT NULL DEFAULT '',
    metadata_source          TEXT NOT NULL DEFAULT '',
    metadata_confidence      REAL NOT NULL DEFAULT 0,
    created_at               TEXT NOT NULL DEFAULT '',
    updated_at               TEXT NOT NULL DEFAULT '',
    original_filename        TEXT NOT NULL DEFAULT '',
    file_path                TEXT NOT NULL DEFAULT '',
    error                    TEXT NOT NULL DEFAULT '',
    error_kind               TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_videos_studio ON videos(studio);

-- 2.3 actresses + actress_aliases --------------------------------------------
CREATE TABLE IF NOT EXISTS actresses (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_actresses_name ON actresses(name);

CREATE TABLE IF NOT EXISTS actress_aliases (
    actress_id TEXT NOT NULL,
    alias      TEXT NOT NULL,
    PRIMARY KEY (actress_id, alias),
    FOREIGN KEY (actress_id) REFERENCES actresses(id) ON DELETE CASCADE
);

-- 2.4 video_actress_links ----------------------------------------------------
CREATE TABLE IF NOT EXISTS video_actress_links (
    video_code   TEXT NOT NULL,
    actress_id   TEXT NOT NULL,
    role_type    TEXT NOT NULL DEFAULT '主演',
    ordinal      INTEGER NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    timestamp    TEXT NOT NULL DEFAULT '',

    PRIMARY KEY (video_code, ordinal),
    UNIQUE (video_code, actress_id, role_type),
    FOREIGN KEY (video_code) REFERENCES videos(code)    ON DELETE CASCADE,
    FOREIGN KEY (actress_id) REFERENCES actresses(id)    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_links_actress ON video_actress_links(actress_id);

-- 2.5 statistics views (derived, never persisted) -----------------------------
DROP VIEW IF EXISTS actress_video_counts;
CREATE VIEW actress_video_counts AS
    SELECT a.id, a.name, COUNT(l.video_code) AS video_count
    FROM actresses a
    LEFT JOIN video_actress_links l ON l.actress_id = a.id
    GROUP BY a.id, a.name;

DROP VIEW IF EXISTS studio_statistics;
CREATE VIEW studio_statistics AS
    SELECT v.studio, COUNT(*) AS video_count
    FROM videos v
    WHERE v.studio <> ''
    GROUP BY v.studio;

DROP VIEW IF EXISTS enhanced_actress_studio_statistics;
CREATE VIEW enhanced_actress_studio_statistics AS
    SELECT a.id     AS actress_id,
           a.name   AS actress_name,
           v.studio AS studio,
           COUNT(*) AS video_count
    FROM actresses a
    JOIN video_actress_links l ON l.actress_id = a.id
    JOIN videos v               ON v.code = l.video_code
    WHERE v.studio <> ''
    GROUP BY a.id, a.name, v.studio;
