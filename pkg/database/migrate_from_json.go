package database

import (
	// SHA-1 is used here strictly for deterministic actress ID derivation
	// (StableActressID, spec § 3.3) — not for any cryptographic property.
	// Switching to SHA-256 would change every previously generated ID and
	// invalidate existing data; collision-resistance is irrelevant for an
	// internal 64-bit identifier.
	"crypto/sha1" //#nosec G505 -- deterministic ID derivation, not crypto
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

// AutoActressIDPrefix marks actress IDs synthesised by
// MigrateFromJSON's --auto-create-missing-actresses path. The full ID
// shape is "auto_<sha1(trim(name))[:16]>" (spec § 3.3).
const AutoActressIDPrefix = "auto_"

// MigrationOptions controls MigrateFromJSON behaviour.
type MigrationOptions struct {
	// AutoCreateMissingActresses, when true, synthesises actress entities
	// for video.actresses[] names that have no matching actresses{} entry.
	// Default false → strict mode: migration fails loudly and lists all
	// unresolved names in MigrationReport.Unresolved.
	AutoCreateMissingActresses bool
}

// MigrationUnresolvedEntry records a video.actresses[] name that has no
// matching actresses{} entity (and no alias match). Only populated in
// strict mode; auto-create mode promotes these into AutoCreated.
type MigrationUnresolvedEntry struct {
	VideoCode string `json:"video_code"`
	Display   string `json:"display"`
}

// MigrationDuplicateEntry records the same actress appearing multiple
// times within a single video.actresses[] list. Migration fails when any
// duplicate is detected — duplicates always violate the
// UNIQUE(video_code, actress_id, role_type) constraint and must be
// resolved upstream (e.g. via classifier.exe db clean-actresses).
type MigrationDuplicateEntry struct {
	VideoCode   string `json:"video_code"`
	ActressName string `json:"actress_name"`
	ActressID   string `json:"actress_id"`
	Ordinals    []int  `json:"ordinals"`
}

// MigrationAutoCreated records an actress entity synthesised by the
// --auto-create-missing-actresses flag.
type MigrationAutoCreated struct {
	Name      string `json:"name"`
	ActressID string `json:"actress_id"`
	VideoCode string `json:"video_code"` // first video that referenced it
}

// MigrationReport summarises a MigrateFromJSON run. It is always fully
// populated and JSON-serialisable, even on failure, so callers can render
// it to stdout/stderr verbatim.
type MigrationReport struct {
	Success           bool                       `json:"success"`
	SourcePath        string                     `json:"source_path"`
	SQLitePath        string                     `json:"sqlite_path"`
	VideosImported    int                        `json:"videos_imported"`
	ActressesImported int                        `json:"actresses_imported"`
	LinksImported     int                        `json:"links_imported"`
	AutoCreated       []MigrationAutoCreated     `json:"auto_created,omitempty"`
	Unresolved        []MigrationUnresolvedEntry `json:"unresolved,omitempty"`
	Duplicates        []MigrationDuplicateEntry  `json:"duplicates,omitempty"`
	ElapsedMs         int64                      `json:"elapsed_ms"`
}

// ErrMigrationUnresolved is returned by MigrateFromJSON in strict mode
// when any video.actresses[] name cannot be matched against an actress
// entity or alias. The accompanying report.Unresolved lists every entry.
var ErrMigrationUnresolved = errors.New("migrate-from-json: unresolved actress references")

// ErrMigrationDuplicate is returned by MigrateFromJSON when any video
// references the same actress more than once. The accompanying
// report.Duplicates lists every (video, actress, ordinals) triple.
var ErrMigrationDuplicate = errors.New("migrate-from-json: duplicate actress references")

// StableActressID returns the deterministic actress ID used by
// MigrateFromJSON's auto-create path. Format:
// "auto_<sha1(strings.TrimSpace(name))[:16]>" — spec § 3.3.
// Normalisation is strictly TrimSpace; no NFC, case-folding, or width
// folding, to avoid collapsing names the user considers distinct.
func StableActressID(name string) string {
	trimmed := strings.TrimSpace(name)
	sum := sha1.Sum([]byte(trimmed)) //#nosec G401 -- deterministic ID, not crypto
	return AutoActressIDPrefix + hex.EncodeToString(sum[:])[:16]
}

// MigrateFromJSON reads a JSON DB at sourcePath and bulk-imports it into
// the SQLite store. The store must be open and InitSchema'd. The whole
// operation runs in a single transaction: on any error the database is
// left untouched.
//
// Three passes execute in order (spec § 3.1):
//
//  1. db_meta + actresses + actress_aliases (from root.actresses{}).
//  2. videos + video_actress_links (from root.videos{}, deriving links
//     from each video.actresses[] name list).
//  3. JSON.links overrides timestamp / role_type when present.
//
// Strict mode is the default. Pass AutoCreateMissingActresses to
// synthesise missing actress entities instead of failing.
func (s *SQLiteStore) MigrateFromJSON(sourcePath string, opts MigrationOptions) (*MigrationReport, error) {
	return s.runImport(sourcePath, opts, false /* wipeFirst */)
}

// ResyncFromJSON force-rebuilds the SQLite store from a JSON DB. It is
// equivalent to MigrateFromJSON except every row in videos /
// video_actress_links / actresses / actress_aliases is deleted up front
// (inside the same transaction). db_meta keys are upserted, never
// deleted, so the singleton stays consistent with the JSON source.
//
// Use this when the SQLite store has drifted from the JSON source and a
// clean re-import is preferable to incremental diffing. Failure rolls
// back the wipe — the SQLite store is left in its prior state.
func (s *SQLiteStore) ResyncFromJSON(sourcePath string, opts MigrationOptions) (*MigrationReport, error) {
	return s.runImport(sourcePath, opts, true /* wipeFirst */)
}

func (s *SQLiteStore) runImport(sourcePath string, opts MigrationOptions, wipeFirst bool) (*MigrationReport, error) {
	start := time.Now()
	report := &MigrationReport{
		SourcePath: sourcePath,
		SQLitePath: s.path,
	}
	defer func() { report.ElapsedMs = time.Since(start).Milliseconds() }()

	if s == nil || s.db == nil {
		return report, errors.New("sqlite store is not open")
	}

	root, err := loadJSONDatabaseRoot(sourcePath)
	if err != nil {
		return report, err
	}

	tx, err := s.db.Begin()
	if err != nil {
		return report, fmt.Errorf("begin tx: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()

	if wipeFirst {
		if err := wipeImportTables(tx); err != nil {
			return report, err
		}
	}

	if err := migrateDBMeta(tx, root); err != nil {
		return report, err
	}

	idByName, idByAlias, actressNames, err := migrateActresses(tx, root, report)
	if err != nil {
		return report, err
	}

	if err := migrateVideosAndLinks(tx, root, opts, report, idByName, idByAlias, actressNames); err != nil {
		return report, err
	}

	sortReportLists(report)

	if len(report.Unresolved) > 0 {
		return report, fmt.Errorf("%w (%d entries)", ErrMigrationUnresolved, len(report.Unresolved))
	}
	if len(report.Duplicates) > 0 {
		return report, fmt.Errorf("%w (%d entries)", ErrMigrationDuplicate, len(report.Duplicates))
	}

	if err := applyLinkOverrides(tx, root.Links); err != nil {
		return report, err
	}

	if err := saveLegacyRootLinks(tx, root.Links); err != nil {
		return report, err
	}

	if err := tx.Commit(); err != nil {
		return report, fmt.Errorf("commit tx: %w", err)
	}
	committed = true
	report.Success = true
	return report, nil
}

// wipeImportTables removes every row from the data tables in
// dependency-safe order. db_meta is left alone; the seeded singleton
// values stay around to be upserted by migrateDBMeta.
// legacy_video_actress_links is the JSON-import snapshot table — wiped
// here so resync rebuilds it from the canonical JSON source.
func wipeImportTables(tx *sql.Tx) error {
	for _, table := range []string{
		"legacy_video_actress_links",
		"video_actress_links",
		"actress_aliases",
		"videos",
		"actresses",
	} {
		if _, err := tx.Exec(fmt.Sprintf("DELETE FROM %s", table)); err != nil {
			return fmt.Errorf("wipe %s: %w", table, err)
		}
	}
	return nil
}

func loadJSONDatabaseRoot(path string) (*DatabaseData, error) {
	// Path comes from operator-provided CLI flag (`db migrate-from-json -source`)
	// or store bootstrap; Clean strips any `..` traversal without altering
	// legitimate absolute or relative paths.
	cleaned := filepath.Clean(path)
	raw, err := os.ReadFile(cleaned) //#nosec G304 -- operator-supplied path, cleaned above
	if err != nil {
		return nil, fmt.Errorf("read source JSON %q: %w", path, err)
	}
	var root DatabaseData
	if err := json.Unmarshal(raw, &root); err != nil {
		return nil, fmt.Errorf("parse source JSON %q: %w", path, err)
	}
	return &root, nil
}

func migrateDBMeta(tx *sql.Tx, root *DatabaseData) error {
	if root == nil {
		return nil
	}
	pairs := map[string]string{}
	if root.SchemaVersion != "" {
		pairs["schema_version"] = root.SchemaVersion
	}
	if root.Metadata != nil {
		if root.Metadata.Description != "" {
			pairs["description"] = root.Metadata.Description
		}
		if root.Metadata.Encoding != "" {
			pairs["encoding"] = root.Metadata.Encoding
		}
	}
	if root.CreatedAt != "" {
		pairs["created_at"] = root.CreatedAt
	}
	if root.UpdatedAt != "" {
		pairs["updated_at"] = root.UpdatedAt
	}
	// data_hash is the reserved/export-time field per spec § 2.1 — never
	// persisted from JSON input.
	for key, value := range pairs {
		if _, err := tx.Exec(
			`INSERT INTO db_meta(key, value) VALUES(?, ?)
			 ON CONFLICT(key) DO UPDATE SET value=excluded.value`,
			key, value,
		); err != nil {
			return fmt.Errorf("upsert db_meta %q: %w", key, err)
		}
	}
	return nil
}

func migrateActresses(
	tx *sql.Tx,
	root *DatabaseData,
	report *MigrationReport,
) (idByName, idByAlias, idToName map[string]string, err error) {
	idByName = map[string]string{}
	idByAlias = map[string]string{}
	idToName = map[string]string{}

	if root == nil {
		return idByName, idByAlias, idToName, nil
	}

	for id, a := range root.Actresses {
		if a == nil {
			continue
		}
		if err := insertActressRow(tx, id, a.Name, a.CreatedAt, a.UpdatedAt); err != nil {
			return nil, nil, nil, err
		}
		idByName[a.Name] = id
		idToName[id] = a.Name
		for _, alias := range a.Aliases {
			if err := insertActressAliasRow(tx, id, alias); err != nil {
				return nil, nil, nil, err
			}
			idByAlias[alias] = id
		}
		report.ActressesImported++
	}
	return idByName, idByAlias, idToName, nil
}

func migrateVideosAndLinks(
	tx *sql.Tx,
	root *DatabaseData,
	opts MigrationOptions,
	report *MigrationReport,
	idByName, idByAlias, idToName map[string]string,
) error {
	if root == nil {
		return nil
	}

	for code, v := range root.Videos {
		if v == nil {
			continue
		}
		if err := insertVideoRow(tx, code, v); err != nil {
			return err
		}
		report.VideosImported++

		if err := migrateVideoActresses(
			tx, code, v, opts, report, idByName, idByAlias, idToName,
		); err != nil {
			return err
		}
	}
	return nil
}

func migrateVideoActresses(
	tx *sql.Tx,
	code string,
	v *VideoData,
	opts MigrationOptions,
	report *MigrationReport,
	idByName, idByAlias, idToName map[string]string,
) error {
	ordinalsByActress := map[string][]int{}

	for ordinal, display := range v.Actresses {
		actressID, found := resolveActressID(display, idByName, idByAlias)
		if !found {
			if !opts.AutoCreateMissingActresses {
				report.Unresolved = append(report.Unresolved, MigrationUnresolvedEntry{
					VideoCode: code,
					Display:   display,
				})
				continue
			}
			synthID, err := autoCreateActress(tx, display, v.UpdatedAt, report, idByName, idToName, code)
			if err != nil {
				return err
			}
			actressID = synthID
		}

		ordinalsByActress[actressID] = append(ordinalsByActress[actressID], ordinal)
		if len(ordinalsByActress[actressID]) > 1 {
			// Defer duplicate detection until we've seen all ordinals; the
			// first occurrence is already in the slice. The link row is
			// only inserted on the first occurrence.
			continue
		}

		displayName := ""
		if name, ok := idToName[actressID]; ok && name != display {
			displayName = display
		}

		if err := insertLinkRow(tx, code, actressID, RoleMain, ordinal, displayName, v.UpdatedAt); err != nil {
			return err
		}
		report.LinksImported++
	}

	for actressID, ordinals := range ordinalsByActress {
		if len(ordinals) <= 1 {
			continue
		}
		name := idToName[actressID]
		report.Duplicates = append(report.Duplicates, MigrationDuplicateEntry{
			VideoCode:   code,
			ActressName: name,
			ActressID:   actressID,
			Ordinals:    append([]int(nil), ordinals...),
		})
	}
	return nil
}

func autoCreateActress(
	tx *sql.Tx,
	display, ts string,
	report *MigrationReport,
	idByName, idToName map[string]string,
	videoCode string,
) (string, error) {
	id := StableActressID(display)
	if _, already := idToName[id]; already {
		idByName[display] = id
		return id, nil
	}
	if err := insertActressRow(tx, id, display, ts, ts); err != nil {
		return "", err
	}
	idByName[display] = id
	idToName[id] = display
	report.ActressesImported++
	report.AutoCreated = append(report.AutoCreated, MigrationAutoCreated{
		Name:      display,
		ActressID: id,
		VideoCode: videoCode,
	})
	return id, nil
}

func resolveActressID(
	display string,
	idByName, idByAlias map[string]string,
) (string, bool) {
	if id, ok := idByName[display]; ok {
		return id, true
	}
	if id, ok := idByAlias[display]; ok {
		return id, true
	}
	return "", false
}

func insertActressRow(tx *sql.Tx, id, name, createdAt, updatedAt string) error {
	if _, err := tx.Exec(
		`INSERT INTO actresses(id, name, created_at, updated_at) VALUES(?, ?, ?, ?)`,
		id, name, createdAt, updatedAt,
	); err != nil {
		return fmt.Errorf("insert actress %q: %w", id, err)
	}
	return nil
}

func insertActressAliasRow(tx *sql.Tx, actressID, alias string) error {
	if _, err := tx.Exec(
		`INSERT INTO actress_aliases(actress_id, alias) VALUES(?, ?)`,
		actressID, alias,
	); err != nil {
		return fmt.Errorf("insert alias %q for actress %q: %w", alias, actressID, err)
	}
	return nil
}

func insertVideoRow(tx *sql.Tx, code string, v *VideoData) error {
	if _, err := tx.Exec(
		`INSERT INTO videos(
			code, id, title, studio, studio_code, release_date, url,
			search_status, search_method, last_search_date,
			avwiki_actress_status, avwiki_last_search_date,
			javdb_actress_status, javdb_last_search_date,
			metadata_source, metadata_confidence,
			created_at, updated_at, original_filename, file_path,
			error, error_kind
		) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		code,
		v.ID,
		v.Title,
		v.Studio,
		v.StudioCode,
		v.ReleaseDate,
		v.URL,
		v.SearchStatus,
		v.SearchMethod,
		v.LastSearchDate,
		v.AVWikiActressStatus,
		v.AVWikiLastSearchDate,
		v.JAVDBActressStatus,
		v.JAVDBLastSearchDate,
		v.Metadata.Source,
		v.Metadata.Confidence,
		v.CreatedAt,
		v.UpdatedAt,
		v.OriginalFilename,
		v.FilePath,
		v.Error,
		v.ErrorKind,
	); err != nil {
		return fmt.Errorf("insert video %q: %w", code, err)
	}
	return nil
}

func insertLinkRow(tx *sql.Tx, videoCode, actressID, roleType string, ordinal int, displayName, timestamp string) error {
	if _, err := tx.Exec(
		`INSERT INTO video_actress_links(
			video_code, actress_id, role_type, ordinal, display_name, timestamp
		) VALUES(?, ?, ?, ?, ?, ?)`,
		videoCode, actressID, roleType, ordinal, displayName, timestamp,
	); err != nil {
		return fmt.Errorf("insert link %s↔%s: %w", videoCode, actressID, err)
	}
	return nil
}

// saveLegacyRootLinks writes the JSON `root.links[]` list verbatim to
// `legacy_video_actress_links` with the input array index as ordinal.
// Orphan entries (empty video_code or actress_id) are preserved here
// because the FK-constrained `video_actress_links` cannot hold them.
// On migrate the table is empty (fresh InitSchema seeds nothing);
// on resync wipeImportTables already deleted any prior rows.
func saveLegacyRootLinks(tx *sql.Tx, links []VideoActressLink) error {
	if len(links) == 0 {
		return nil
	}
	stmt, err := tx.Prepare(
		`INSERT INTO legacy_video_actress_links(
			ordinal, video_code, actress_id, role_type, timestamp
		) VALUES(?, ?, ?, ?, ?)`,
	)
	if err != nil {
		return fmt.Errorf("prepare legacy_video_actress_links insert: %w", err)
	}
	defer stmt.Close()
	for i, l := range links {
		if _, err := stmt.Exec(i, l.VideoCode, l.ActressID, l.RoleType, l.Timestamp); err != nil {
			return fmt.Errorf("insert legacy_video_actress_links[%d]: %w", i, err)
		}
	}
	return nil
}

func applyLinkOverrides(tx *sql.Tx, links []VideoActressLink) error {
	for _, l := range links {
		role := l.RoleType
		if role == "" {
			role = RoleMain
		}
		// JSON.links is canonical for role_type / timestamp on an existing
		// link row keyed by (video_code, actress_id). It does not introduce
		// new rows here — Pass 2 already built the link set from the
		// ordered video.actresses[] list, which is the source of ordinal.
		// If JSON.links references a (video, actress) that wasn't created
		// in Pass 2 we still want it represented; SQLite reports rows-
		// affected = 0 on a no-op UPDATE, which we use to detect that.
		res, err := tx.Exec(
			`UPDATE video_actress_links
			    SET role_type = ?, timestamp = ?
			  WHERE video_code = ? AND actress_id = ?`,
			role, l.Timestamp, l.VideoCode, l.ActressID,
		)
		if err != nil {
			return fmt.Errorf("override link %s↔%s: %w", l.VideoCode, l.ActressID, err)
		}
		n, err := res.RowsAffected()
		if err != nil {
			return fmt.Errorf("override link rows-affected %s↔%s: %w", l.VideoCode, l.ActressID, err)
		}
		if n == 0 {
			// JSON.links references a pair that isn't in Pass 2's output.
			// We can't fabricate an ordinal, so we skip silently here —
			// strict mode in Pass 2 already would have flagged any
			// unresolved name; if it didn't, the link is best-effort.
			continue
		}
	}
	return nil
}

func sortReportLists(report *MigrationReport) {
	sort.Slice(report.Unresolved, func(i, j int) bool {
		if report.Unresolved[i].VideoCode != report.Unresolved[j].VideoCode {
			return report.Unresolved[i].VideoCode < report.Unresolved[j].VideoCode
		}
		return report.Unresolved[i].Display < report.Unresolved[j].Display
	})
	sort.Slice(report.Duplicates, func(i, j int) bool {
		if report.Duplicates[i].VideoCode != report.Duplicates[j].VideoCode {
			return report.Duplicates[i].VideoCode < report.Duplicates[j].VideoCode
		}
		return report.Duplicates[i].ActressID < report.Duplicates[j].ActressID
	})
	sort.Slice(report.AutoCreated, func(i, j int) bool {
		if report.AutoCreated[i].Name != report.AutoCreated[j].Name {
			return report.AutoCreated[i].Name < report.AutoCreated[j].Name
		}
		return report.AutoCreated[i].VideoCode < report.AutoCreated[j].VideoCode
	})
	for i := range report.Duplicates {
		sort.Ints(report.Duplicates[i].Ordinals)
	}
}
