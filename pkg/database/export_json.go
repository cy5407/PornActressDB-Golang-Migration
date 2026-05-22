package database

import (
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"sort"
	"time"
)

// ExportOptions controls ExportToJSON.
type ExportOptions struct {
	// OutputPath: write the serialised JSON DB to this file. Empty
	// returns the in-memory DatabaseData without touching disk.
	OutputPath string
}

// ActressStatistic mirrors the JSON DB statistics.actress_statistics row.
type ActressStatistic struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	VideoCount int    `json:"video_count"`
}

// StudioStatistic mirrors the JSON DB statistics.studio_statistics row.
type StudioStatistic struct {
	Studio     string `json:"studio"`
	VideoCount int    `json:"video_count"`
}

// EnhancedActressStudioStatistic mirrors the JSON DB
// statistics.enhanced_actress_studio_statistics row.
type EnhancedActressStudioStatistic struct {
	ActressID   string `json:"actress_id"`
	ActressName string `json:"actress_name"`
	Studio      string `json:"studio"`
	VideoCount  int    `json:"video_count"`
}

// ExportToJSON rebuilds a DatabaseData structure from the SQLite store
// and (optionally) writes it to OutputPath. The reconstruction follows
// spec § 2.5 / § 4.2:
//
//   - actresses[].video_count is filled from the actress_video_counts view.
//   - statistics.{actress,studio,enhanced_actress_studio}_statistics are
//     computed at export time from the corresponding views.
//   - statistics.computed_at is the current UTC RFC3339 timestamp.
//   - data_hash is left as the empty string (reserved; see spec § 2.1).
//   - db_meta singletons supply schema_version / metadata / created_at;
//     updated_at is refreshed to the current UTC RFC3339 timestamp.
//
// Calling this on an SQLite store that has never run migrate-from-json
// returns a syntactically valid but empty JSON DB (no videos /
// actresses).
func (s *SQLiteStore) ExportToJSON(opts ExportOptions) (*DatabaseData, error) {
	if s == nil || s.db == nil {
		return nil, errors.New("sqlite store is not open")
	}

	now := time.Now().UTC().Format(time.RFC3339)

	root := NewDatabaseData()
	root.DataHash = "" // reserved per spec § 2.1
	root.UpdatedAt = now

	if err := loadDBMetaInto(s.db, root); err != nil {
		return nil, err
	}

	actresses, idToName, err := loadActressesFromSQLite(s.db)
	if err != nil {
		return nil, err
	}
	root.Actresses = actresses

	videos, perVideoOrdered, err := loadVideosAndOrderedLinks(s.db, idToName)
	if err != nil {
		return nil, err
	}
	// Stitch the per-video actresses[] name list onto each video.
	for code, names := range perVideoOrdered {
		if v, ok := videos[code]; ok {
			v.Actresses = names
		}
	}
	root.Videos = videos

	links, err := loadLinksFromSQLite(s.db)
	if err != nil {
		return nil, err
	}
	root.Links = links

	stats, err := buildStatistics(s.db, now)
	if err != nil {
		return nil, err
	}
	root.Statistics = stats

	if opts.OutputPath != "" {
		if err := writeJSONDatabaseRoot(opts.OutputPath, root); err != nil {
			return nil, err
		}
	}
	return root, nil
}

func writeJSONDatabaseRoot(path string, root *DatabaseData) error {
	raw, err := json.MarshalIndent(root, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal export: %w", err)
	}
	if err := os.WriteFile(path, raw, 0o600); err != nil {
		return fmt.Errorf("write export %q: %w", path, err)
	}
	return nil
}

func loadDBMetaInto(db *sql.DB, root *DatabaseData) error {
	rows, err := db.Query(`SELECT key, value FROM db_meta`)
	if err != nil {
		return fmt.Errorf("select db_meta: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var k, v string
		if err := rows.Scan(&k, &v); err != nil {
			return fmt.Errorf("scan db_meta: %w", err)
		}
		switch k {
		case "schema_version":
			if v != "" {
				root.SchemaVersion = v
			}
		case "description":
			if root.Metadata == nil {
				root.Metadata = &DatabaseMetadata{}
			}
			root.Metadata.Description = v
		case "encoding":
			if root.Metadata == nil {
				root.Metadata = &DatabaseMetadata{}
			}
			root.Metadata.Encoding = v
		case "created_at":
			if v != "" {
				root.CreatedAt = v
			}
		case "data_hash":
			// spec § 2.1: always empty in export — already initialised above.
		}
	}
	return rows.Err()
}

func loadActressesFromSQLite(db *sql.DB) (map[string]*ActressData, map[string]string, error) {
	aliases, err := loadAliasesGrouped(db)
	if err != nil {
		return nil, nil, err
	}

	rows, err := db.Query(`SELECT id, name, created_at, updated_at FROM actresses`)
	if err != nil {
		return nil, nil, fmt.Errorf("select actresses: %w", err)
	}
	defer rows.Close()

	out := map[string]*ActressData{}
	idToName := map[string]string{}
	for rows.Next() {
		a := ActressData{Aliases: []string{}}
		if err := rows.Scan(&a.ID, &a.Name, &a.CreatedAt, &a.UpdatedAt); err != nil {
			return nil, nil, fmt.Errorf("scan actress: %w", err)
		}
		if al, ok := aliases[a.ID]; ok {
			a.Aliases = al
		}
		out[a.ID] = &a
		idToName[a.ID] = a.Name
	}
	if err := rows.Err(); err != nil {
		return nil, nil, fmt.Errorf("iterate actresses: %w", err)
	}

	// Fill video_count from the canonical view.
	countRows, err := db.Query(`SELECT id, video_count FROM actress_video_counts`)
	if err != nil {
		return nil, nil, fmt.Errorf("select actress_video_counts: %w", err)
	}
	defer countRows.Close()
	for countRows.Next() {
		var id string
		var n int
		if err := countRows.Scan(&id, &n); err != nil {
			return nil, nil, fmt.Errorf("scan video_count: %w", err)
		}
		if a, ok := out[id]; ok {
			a.VideoCount = n
		}
	}
	return out, idToName, countRows.Err()
}

func loadAliasesGrouped(db *sql.DB) (map[string][]string, error) {
	rows, err := db.Query(`
		SELECT actress_id, alias FROM actress_aliases
		 ORDER BY actress_id, alias
	`)
	if err != nil {
		return nil, fmt.Errorf("select aliases: %w", err)
	}
	defer rows.Close()
	out := map[string][]string{}
	for rows.Next() {
		var id, alias string
		if err := rows.Scan(&id, &alias); err != nil {
			return nil, fmt.Errorf("scan alias: %w", err)
		}
		out[id] = append(out[id], alias)
	}
	return out, rows.Err()
}

func loadVideosAndOrderedLinks(db *sql.DB, idToName map[string]string) (map[string]*VideoData, map[string][]string, error) {
	rows, err := db.Query(`
		SELECT code, id, title, studio, studio_code, release_date, url,
		       search_status, search_method, last_search_date,
		       avwiki_actress_status, avwiki_last_search_date,
		       javdb_actress_status, javdb_last_search_date,
		       metadata_source, metadata_confidence,
		       created_at, updated_at, original_filename, file_path,
		       error, error_kind
		  FROM videos
	`)
	if err != nil {
		return nil, nil, fmt.Errorf("select videos: %w", err)
	}
	defer rows.Close()

	videos := map[string]*VideoData{}
	for rows.Next() {
		v := VideoData{Actresses: []string{}}
		if err := rows.Scan(
			&v.Code, &v.ID, &v.Title, &v.Studio, &v.StudioCode,
			&v.ReleaseDate, &v.URL,
			&v.SearchStatus, &v.SearchMethod, &v.LastSearchDate,
			&v.AVWikiActressStatus, &v.AVWikiLastSearchDate,
			&v.JAVDBActressStatus, &v.JAVDBLastSearchDate,
			&v.Metadata.Source, &v.Metadata.Confidence,
			&v.CreatedAt, &v.UpdatedAt, &v.OriginalFilename, &v.FilePath,
			&v.Error, &v.ErrorKind,
		); err != nil {
			return nil, nil, fmt.Errorf("scan video: %w", err)
		}
		videos[v.Code] = &v
	}
	if err := rows.Err(); err != nil {
		return nil, nil, fmt.Errorf("iterate videos: %w", err)
	}

	// Per-video name list reconstructed from video_actress_links by
	// ordinal. display_name (when non-empty) wins over actress.name —
	// it captures the original JSON-side spelling that migration chose
	// to preserve.
	linkRows, err := db.Query(`
		SELECT video_code, actress_id, ordinal, display_name
		  FROM video_actress_links
		 ORDER BY video_code, ordinal
	`)
	if err != nil {
		return nil, nil, fmt.Errorf("select video_actress_links for video.actresses: %w", err)
	}
	defer linkRows.Close()
	perVideo := map[string][]string{}
	for linkRows.Next() {
		var code, actressID, displayName string
		var ordinal int
		if err := linkRows.Scan(&code, &actressID, &ordinal, &displayName); err != nil {
			return nil, nil, fmt.Errorf("scan link for video.actresses: %w", err)
		}
		name := displayName
		if name == "" {
			name = idToName[actressID]
		}
		perVideo[code] = append(perVideo[code], name)
	}
	return videos, perVideo, linkRows.Err()
}

func loadLinksFromSQLite(db *sql.DB) ([]VideoActressLink, error) {
	rows, err := db.Query(`
		SELECT video_code, actress_id, role_type, timestamp
		  FROM video_actress_links
		 ORDER BY video_code, ordinal
	`)
	if err != nil {
		return nil, fmt.Errorf("select links: %w", err)
	}
	defer rows.Close()
	var out []VideoActressLink
	for rows.Next() {
		var l VideoActressLink
		if err := rows.Scan(&l.VideoCode, &l.ActressID, &l.RoleType, &l.Timestamp); err != nil {
			return nil, fmt.Errorf("scan link: %w", err)
		}
		out = append(out, l)
	}
	return out, rows.Err()
}

func buildStatistics(db *sql.DB, computedAt string) (map[string]any, error) {
	out := map[string]any{
		"computed_at": computedAt,
	}

	actressStats, err := queryActressStatistics(db)
	if err != nil {
		return nil, err
	}
	out["actress_statistics"] = actressStats

	studioStats, err := queryStudioStatistics(db)
	if err != nil {
		return nil, err
	}
	out["studio_statistics"] = studioStats

	enhanced, err := queryEnhancedActressStudioStatistics(db)
	if err != nil {
		return nil, err
	}
	out["enhanced_actress_studio_statistics"] = enhanced
	return out, nil
}

func queryActressStatistics(db *sql.DB) ([]ActressStatistic, error) {
	rows, err := db.Query(`
		SELECT id, name, video_count FROM actress_video_counts
		 ORDER BY id
	`)
	if err != nil {
		return nil, fmt.Errorf("select actress_video_counts: %w", err)
	}
	defer rows.Close()
	var out []ActressStatistic
	for rows.Next() {
		var a ActressStatistic
		if err := rows.Scan(&a.ID, &a.Name, &a.VideoCount); err != nil {
			return nil, fmt.Errorf("scan actress_statistic: %w", err)
		}
		out = append(out, a)
	}
	if out == nil {
		out = []ActressStatistic{}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	return out, rows.Err()
}

func queryStudioStatistics(db *sql.DB) ([]StudioStatistic, error) {
	rows, err := db.Query(`
		SELECT studio, video_count FROM studio_statistics
		 ORDER BY studio
	`)
	if err != nil {
		return nil, fmt.Errorf("select studio_statistics: %w", err)
	}
	defer rows.Close()
	var out []StudioStatistic
	for rows.Next() {
		var s StudioStatistic
		if err := rows.Scan(&s.Studio, &s.VideoCount); err != nil {
			return nil, fmt.Errorf("scan studio_statistic: %w", err)
		}
		out = append(out, s)
	}
	if out == nil {
		out = []StudioStatistic{}
	}
	return out, rows.Err()
}

func queryEnhancedActressStudioStatistics(db *sql.DB) ([]EnhancedActressStudioStatistic, error) {
	rows, err := db.Query(`
		SELECT actress_id, actress_name, studio, video_count
		  FROM enhanced_actress_studio_statistics
		 ORDER BY actress_id, studio
	`)
	if err != nil {
		return nil, fmt.Errorf("select enhanced_actress_studio_statistics: %w", err)
	}
	defer rows.Close()
	var out []EnhancedActressStudioStatistic
	for rows.Next() {
		var e EnhancedActressStudioStatistic
		if err := rows.Scan(&e.ActressID, &e.ActressName, &e.Studio, &e.VideoCount); err != nil {
			return nil, fmt.Errorf("scan enhanced_actress_studio_statistic: %w", err)
		}
		out = append(out, e)
	}
	if out == nil {
		out = []EnhancedActressStudioStatistic{}
	}
	return out, rows.Err()
}
