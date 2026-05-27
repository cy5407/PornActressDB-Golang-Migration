package database

import (
	"database/sql"
	"fmt"
	"sort"
	"strings"
	"time"
)

// VerifyDiff describes a single point where JSON and SQLite disagree.
// JSONValue and SQLiteValue are rendered as strings for serialisation;
// the canonical form for both sides is the JSON-encoded representation
// of the underlying value.
type VerifyDiff struct {
	Kind        string `json:"kind"`   // "video" / "actress" / "actress_alias" / "link" / "db_meta"
	Key         string `json:"key"`    // identifier (code / id / link key / meta key)
	Field       string `json:"field"`  // empty when Reason != "field_diff"
	Reason      string `json:"reason"` // "missing_in_sqlite" / "missing_in_json" / "field_diff"
	JSONValue   string `json:"json_value,omitempty"`
	SQLiteValue string `json:"sqlite_value,omitempty"`
}

// VerifyReport summarises a VerifySync run. Consistent is true iff Diffs
// is empty. Counts are read from the SQLite side.
type VerifyReport struct {
	Consistent   bool         `json:"consistent"`
	VideoCount   int          `json:"video_count"`
	ActressCount int          `json:"actress_count"`
	LinkCount    int          `json:"link_count"`
	Diffs        []VerifyDiff `json:"diffs,omitempty"`
}

// VerifySync compares the contents of jsonPath (a JSON DB at rest)
// against the current SQLite store. It does not modify either side.
// Returns a populated report; the boolean .Consistent on the report is
// the canonical pass/fail signal. The error return is non-nil only for
// I/O / parse / SQL faults — disagreement is reported via .Diffs, not
// via err.
func (s *SQLiteStore) VerifySync(jsonPath string) (*VerifyReport, error) {
	if s == nil || s.db == nil {
		return nil, fmt.Errorf("sqlite store is not open")
	}
	root, err := loadJSONDatabaseRoot(jsonPath)
	if err != nil {
		return nil, err
	}
	report := &VerifyReport{}

	if err := verifyVideos(s.db, root, report); err != nil {
		return nil, err
	}
	if err := verifyActresses(s.db, root, report); err != nil {
		return nil, err
	}
	if err := verifyLinks(s.db, root, report); err != nil {
		return nil, err
	}
	if err := verifyLegacyLinks(s.db, root, report); err != nil {
		return nil, err
	}
	if err := verifyDBMeta(s.db, root, report); err != nil {
		return nil, err
	}

	sortDiffs(report.Diffs)
	report.Consistent = len(report.Diffs) == 0
	return report, nil
}

func verifyVideos(db *sql.DB, root *DatabaseData, report *VerifyReport) error {
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
		return fmt.Errorf("select videos: %w", err)
	}
	defer rows.Close()

	sqliteSide := map[string]VideoData{}
	for rows.Next() {
		var v VideoData
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
			return fmt.Errorf("scan video row: %w", err)
		}
		sqliteSide[v.Code] = v
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterate videos: %w", err)
	}
	report.VideoCount = len(sqliteSide)

	for code, jv := range root.Videos {
		sv, ok := sqliteSide[code]
		if !ok {
			report.Diffs = append(report.Diffs, VerifyDiff{
				Kind: "video", Key: code, Reason: "missing_in_sqlite",
			})
			continue
		}
		diffVideoFields(code, jv, &sv, report)
	}
	for code := range sqliteSide {
		if _, ok := root.Videos[code]; !ok {
			report.Diffs = append(report.Diffs, VerifyDiff{
				Kind: "video", Key: code, Reason: "missing_in_json",
			})
		}
	}
	return nil
}

func diffVideoFields(code string, jv *VideoData, sv *VideoData, report *VerifyReport) {
	checks := []struct {
		field   string
		jsonVal string
		sqliVal string
	}{
		{"title", jv.Title, sv.Title},
		{"studio", jv.Studio, sv.Studio},
		{"studio_code", jv.StudioCode, sv.StudioCode},
		{"release_date", jv.ReleaseDate, sv.ReleaseDate},
		{"url", jv.URL, sv.URL},
		{"search_status", jv.SearchStatus, sv.SearchStatus},
		{"search_method", jv.SearchMethod, sv.SearchMethod},
		{"avwiki_actress_status", jv.AVWikiActressStatus, sv.AVWikiActressStatus},
		{"javdb_actress_status", jv.JAVDBActressStatus, sv.JAVDBActressStatus},
		{"metadata_source", jv.Metadata.Source, sv.Metadata.Source},
		{"original_filename", jv.OriginalFilename, sv.OriginalFilename},
		{"file_path", jv.FilePath, sv.FilePath},
		{"error", jv.Error, sv.Error},
		{"error_kind", jv.ErrorKind, sv.ErrorKind},
		{"id", jv.ID, sv.ID},
	}
	for _, c := range checks {
		if c.jsonVal != c.sqliVal {
			report.Diffs = append(report.Diffs, VerifyDiff{
				Kind: "video", Key: code, Field: c.field, Reason: "field_diff",
				JSONValue: c.jsonVal, SQLiteValue: c.sqliVal,
			})
		}
	}
	if jv.Metadata.Confidence != sv.Metadata.Confidence {
		report.Diffs = append(report.Diffs, VerifyDiff{
			Kind: "video", Key: code, Field: "metadata_confidence",
			Reason:      "field_diff",
			JSONValue:   fmt.Sprintf("%g", jv.Metadata.Confidence),
			SQLiteValue: fmt.Sprintf("%g", sv.Metadata.Confidence),
		})
	}
	diffTimestampSecondTolerance(code, "video", "last_search_date", jv.LastSearchDate, sv.LastSearchDate, report)
	diffTimestampSecondTolerance(code, "video", "avwiki_last_search_date", jv.AVWikiLastSearchDate, sv.AVWikiLastSearchDate, report)
	diffTimestampSecondTolerance(code, "video", "javdb_last_search_date", jv.JAVDBLastSearchDate, sv.JAVDBLastSearchDate, report)
	diffTimestampSecondTolerance(code, "video", "created_at", jv.CreatedAt, sv.CreatedAt, report)
	diffTimestampSecondTolerance(code, "video", "updated_at", jv.UpdatedAt, sv.UpdatedAt, report)
}

func verifyActresses(db *sql.DB, root *DatabaseData, report *VerifyReport) error {
	sqliteSide, err := loadSQLiteActressRows(db)
	if err != nil {
		return err
	}
	report.ActressCount = len(sqliteSide)

	aliasesByID, err := loadActressAliasesByID(db)
	if err != nil {
		return err
	}

	for id, ja := range root.Actresses {
		if ja == nil {
			continue
		}
		sa, ok := sqliteSide[id]
		if !ok {
			report.Diffs = append(report.Diffs, VerifyDiff{
				Kind: "actress", Key: id, Reason: "missing_in_sqlite",
			})
			continue
		}
		diffActressEntity(id, ja, sa, aliasesByID[id], report)
	}
	for id, sa := range sqliteSide {
		if _, ok := root.Actresses[id]; ok {
			continue
		}
		if jsonHasDerivedAutoActress(root, id, sa.Name) {
			continue
		}
		report.Diffs = append(report.Diffs, VerifyDiff{
			Kind: "actress", Key: id, Reason: "missing_in_json",
		})
	}
	return nil
}

func jsonHasDerivedAutoActress(root *DatabaseData, actressID, sqliteName string) bool {
	if !strings.HasPrefix(actressID, AutoActressIDPrefix) {
		return false
	}
	for _, v := range root.Videos {
		if v == nil {
			continue
		}
		for _, display := range v.Actresses {
			if display == sqliteName && StableActressID(display) == actressID {
				return true
			}
		}
	}
	return false
}

func diffAliasSet(actressID string, jsonAliases, sqliteAliases []string, report *VerifyReport) {
	jsonSet := map[string]bool{}
	for _, a := range jsonAliases {
		jsonSet[a] = true
	}
	sqliteSet := map[string]bool{}
	for _, a := range sqliteAliases {
		sqliteSet[a] = true
	}
	for alias := range jsonSet {
		if !sqliteSet[alias] {
			report.Diffs = append(report.Diffs, VerifyDiff{
				Kind: "actress_alias", Key: actressID + "/" + alias, Reason: "missing_in_sqlite",
				JSONValue: alias,
			})
		}
	}
	for alias := range sqliteSet {
		if !jsonSet[alias] {
			report.Diffs = append(report.Diffs, VerifyDiff{
				Kind: "actress_alias", Key: actressID + "/" + alias, Reason: "missing_in_json",
				SQLiteValue: alias,
			})
		}
	}
}

func verifyLinks(db *sql.DB, root *DatabaseData, report *VerifyReport) error {
	sqliteSide, err := loadSQLiteVideoActressLinks(db)
	if err != nil {
		return err
	}
	report.LinkCount = len(sqliteSide)

	// JSON-side: a link conceptually exists if either (a) videos[].actresses
	// referenced it during Pass 2, or (b) root.links lists it. Both should
	// have already been written by MigrateFromJSON.
	// Orphan root.links entries (empty video_code) cannot live in the
	// FK-constrained video_actress_links table — they are tracked
	// separately by verifyLegacyLinks against legacy_video_actress_links.
	jsonSeen := map[string]bool{}
	for _, l := range root.Links {
		if l.VideoCode == "" {
			continue
		}
		key := l.VideoCode + "|" + l.ActressID
		jsonSeen[key] = true
		sv, ok := sqliteSide[key]
		if !ok {
			report.Diffs = append(report.Diffs, VerifyDiff{
				Kind: "link", Key: key, Reason: "missing_in_sqlite",
			})
			continue
		}
		diffJSONLinkAgainstSQLite(key, l, sv, report)
	}
	// videos[].actresses derived links: the verify side treats these as
	// implicit JSON-side links, indexed via the SQLite rows themselves.
	// We accept any extra SQLite row that has a JSON video → actress
	// reference even if root.links didn't enumerate it (because Pass 2
	// of migration created it). Therefore we only complain about
	// missing_in_json when the SQLite link has no corresponding video
	// reference at all.
	for key, sv := range sqliteSide {
		if jsonSeen[key] {
			continue
		}
		if !jsonHasVideoActress(root, sv.VideoCode, sv.ActressID) {
			report.Diffs = append(report.Diffs, VerifyDiff{
				Kind: "link", Key: key, Reason: "missing_in_json",
			})
		}
	}
	return nil
}

// verifyLegacyLinks compares root.links[] verbatim against the
// legacy_video_actress_links snapshot table. The table is the canonical
// store for the JSON `root.links[]` list (filled by MigrateFromJSON /
// ResyncFromJSON), so the two sides must match field-for-field, in the
// same order. Diffs are emitted with kind = "legacy_link" and a key
// shaped "ordinal:<n>".
func verifyLegacyLinks(db *sql.DB, root *DatabaseData, report *VerifyReport) error {
	rows, err := db.Query(`
		SELECT ordinal, video_code, actress_id, role_type, timestamp
		  FROM legacy_video_actress_links
		 ORDER BY ordinal
	`)
	if err != nil {
		return fmt.Errorf("select legacy_video_actress_links: %w", err)
	}
	defer rows.Close()

	type legacyRow struct {
		Ordinal   int
		VideoCode string
		ActressID string
		RoleType  string
		Timestamp string
	}
	var sqliteSide []legacyRow
	for rows.Next() {
		var l legacyRow
		if err := rows.Scan(&l.Ordinal, &l.VideoCode, &l.ActressID, &l.RoleType, &l.Timestamp); err != nil {
			return fmt.Errorf("scan legacy_video_actress_links: %w", err)
		}
		sqliteSide = append(sqliteSide, l)
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterate legacy_video_actress_links: %w", err)
	}

	n := len(root.Links)
	if m := len(sqliteSide); m > n {
		n = m
	}
	for i := 0; i < n; i++ {
		key := fmt.Sprintf("ordinal:%d", i)
		switch {
		case i >= len(sqliteSide):
			report.Diffs = append(report.Diffs, VerifyDiff{
				Kind: "legacy_link", Key: key, Reason: "missing_in_sqlite",
				JSONValue: root.Links[i].VideoCode + "|" + root.Links[i].ActressID,
			})
		case i >= len(root.Links):
			report.Diffs = append(report.Diffs, VerifyDiff{
				Kind: "legacy_link", Key: key, Reason: "missing_in_json",
				SQLiteValue: sqliteSide[i].VideoCode + "|" + sqliteSide[i].ActressID,
			})
		default:
			diffLegacyLinkRow(key, root.Links[i], sqliteSide[i].VideoCode,
				sqliteSide[i].ActressID, sqliteSide[i].RoleType, sqliteSide[i].Timestamp, report)
		}
	}
	return nil
}

func diffLegacyLinkRow(
	key string,
	jl VideoActressLink,
	svVideoCode, svActressID, svRole, svTimestamp string,
	report *VerifyReport,
) {
	for _, c := range []struct {
		field   string
		jsonVal string
		sqliVal string
	}{
		{"video_code", jl.VideoCode, svVideoCode},
		{"actress_id", jl.ActressID, svActressID},
		{"role_type", jl.RoleType, svRole},
	} {
		if c.jsonVal != c.sqliVal {
			report.Diffs = append(report.Diffs, VerifyDiff{
				Kind: "legacy_link", Key: key, Field: c.field, Reason: "field_diff",
				JSONValue: c.jsonVal, SQLiteValue: c.sqliVal,
			})
		}
	}
	diffTimestampSecondTolerance(key, "legacy_link", "timestamp", jl.Timestamp, svTimestamp, report)
}

func jsonHasVideoActress(root *DatabaseData, videoCode, actressID string) bool {
	v, ok := root.Videos[videoCode]
	if !ok || v == nil {
		return false
	}
	if a, ok := root.Actresses[actressID]; ok && a != nil && videoReferencesActress(v, a) {
		return true
	}
	// Auto-created actress: id == "auto_<sha1>"; match by id derived from
	// the displayed name.
	if strings.HasPrefix(actressID, AutoActressIDPrefix) {
		return videoReferencesAutoActressID(v, actressID)
	}
	return false
}

func verifyDBMeta(db *sql.DB, root *DatabaseData, report *VerifyReport) error {
	rows, err := db.Query(`SELECT key, value FROM db_meta`)
	if err != nil {
		return fmt.Errorf("select db_meta: %w", err)
	}
	defer rows.Close()
	sqliteSide := map[string]string{}
	for rows.Next() {
		var k, v string
		if err := rows.Scan(&k, &v); err != nil {
			return fmt.Errorf("scan db_meta: %w", err)
		}
		sqliteSide[k] = v
	}

	for key, want := range buildExpectedDBMeta(root) {
		got, ok := sqliteSide[key]
		if !ok {
			report.Diffs = append(report.Diffs, VerifyDiff{
				Kind: "db_meta", Key: key, Reason: "missing_in_sqlite", JSONValue: want,
			})
			continue
		}
		if got != want {
			report.Diffs = append(report.Diffs, VerifyDiff{
				Kind: "db_meta", Key: key, Field: "value", Reason: "field_diff",
				JSONValue: want, SQLiteValue: got,
			})
		}
	}
	return nil
}

func diffTimestampSecondTolerance(key, kind, field, jsonVal, sqliteVal string, report *VerifyReport) {
	if jsonVal == sqliteVal {
		return
	}
	if timestampsEqualWithinSecond(jsonVal, sqliteVal) {
		return
	}
	report.Diffs = append(report.Diffs, VerifyDiff{
		Kind: kind, Key: key, Field: field, Reason: "field_diff",
		JSONValue: jsonVal, SQLiteValue: sqliteVal,
	})
}

func timestampsEqualWithinSecond(a, b string) bool {
	if a == "" || b == "" {
		return false
	}
	ta, errA := parseAnyTimestamp(a)
	tb, errB := parseAnyTimestamp(b)
	if errA != nil || errB != nil {
		return false
	}
	diff := ta.Sub(tb)
	if diff < 0 {
		diff = -diff
	}
	return diff < time.Second
}

func parseAnyTimestamp(s string) (time.Time, error) {
	for _, layout := range []string{time.RFC3339Nano, time.RFC3339, ISODateTimeFormat, ISODateFormat} {
		if t, err := time.Parse(layout, s); err == nil {
			return t, nil
		}
	}
	return time.Time{}, fmt.Errorf("unparseable timestamp %q", s)
}

// verifyLinkRow is the file-local projection of a video_actress_links
// row used by verifyLinks + diffJSONLinkAgainstSQLite.
type verifyLinkRow struct {
	VideoCode string
	ActressID string
	RoleType  string
	Ordinal   int
	Display   string
	Timestamp string
}

func loadSQLiteVideoActressLinks(db *sql.DB) (map[string]verifyLinkRow, error) {
	rows, err := db.Query(`
		SELECT video_code, actress_id, role_type, ordinal, display_name, timestamp
		  FROM video_actress_links
	`)
	if err != nil {
		return nil, fmt.Errorf("select links: %w", err)
	}
	defer rows.Close()
	out := map[string]verifyLinkRow{}
	for rows.Next() {
		var l verifyLinkRow
		if err := rows.Scan(&l.VideoCode, &l.ActressID, &l.RoleType, &l.Ordinal, &l.Display, &l.Timestamp); err != nil {
			return nil, fmt.Errorf("scan link row: %w", err)
		}
		key := l.VideoCode + "|" + l.ActressID
		out[key] = l
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate links: %w", err)
	}
	return out, nil
}

// diffJSONLinkAgainstSQLite emits the per-link role_type + timestamp
// comparison. Empty JSON role_type defaults to RoleMain to match what
// MigrateFromJSON wrote (applyLinkOverrides has the same fallback).
func diffJSONLinkAgainstSQLite(key string, jl VideoActressLink, sv verifyLinkRow, report *VerifyReport) {
	role := jl.RoleType
	if role == "" {
		role = RoleMain
	}
	if sv.RoleType != role {
		report.Diffs = append(report.Diffs, VerifyDiff{
			Kind: "link", Key: key, Field: "role_type", Reason: "field_diff",
			JSONValue: role, SQLiteValue: sv.RoleType,
		})
	}
	diffTimestampSecondTolerance(key, "link", "timestamp", jl.Timestamp, sv.Timestamp, report)
}

// verifyActressRow is the file-local projection of an actresses row
// used by verifyActresses + diffActressEntity. Kept narrow (no
// aliases) so the loader stays single-query.
type verifyActressRow struct {
	ID        string
	Name      string
	CreatedAt string
	UpdatedAt string
}

func loadSQLiteActressRows(db *sql.DB) (map[string]verifyActressRow, error) {
	rows, err := db.Query(`SELECT id, name, created_at, updated_at FROM actresses`)
	if err != nil {
		return nil, fmt.Errorf("select actresses: %w", err)
	}
	defer rows.Close()
	out := map[string]verifyActressRow{}
	for rows.Next() {
		var a verifyActressRow
		if err := rows.Scan(&a.ID, &a.Name, &a.CreatedAt, &a.UpdatedAt); err != nil {
			return nil, fmt.Errorf("scan actress row: %w", err)
		}
		out[a.ID] = a
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate actresses: %w", err)
	}
	return out, nil
}

func loadActressAliasesByID(db *sql.DB) (map[string][]string, error) {
	rows, err := db.Query(`SELECT actress_id, alias FROM actress_aliases`)
	if err != nil {
		return nil, fmt.Errorf("select aliases: %w", err)
	}
	defer rows.Close()
	out := map[string][]string{}
	for rows.Next() {
		var id, alias string
		if err := rows.Scan(&id, &alias); err != nil {
			return nil, fmt.Errorf("scan alias row: %w", err)
		}
		out[id] = append(out[id], alias)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate aliases: %w", err)
	}
	return out, nil
}

// diffActressEntity emits VerifyDiffs for the per-entity comparison
// (name + created_at + updated_at + alias set). Called only when both
// sides have the actress id; missing-in-{sqlite,json} are handled by
// the caller.
func diffActressEntity(id string, ja *ActressData, sa verifyActressRow, sqliteAliases []string, report *VerifyReport) {
	if ja.Name != sa.Name {
		report.Diffs = append(report.Diffs, VerifyDiff{
			Kind: "actress", Key: id, Field: "name", Reason: "field_diff",
			JSONValue: ja.Name, SQLiteValue: sa.Name,
		})
	}
	diffTimestampSecondTolerance(id, "actress", "created_at", ja.CreatedAt, sa.CreatedAt, report)
	diffTimestampSecondTolerance(id, "actress", "updated_at", ja.UpdatedAt, sa.UpdatedAt, report)
	diffAliasSet(id, ja.Aliases, sqliteAliases, report)
}

// videoReferencesActress reports whether any of v.Actresses[] matches
// the canonical actress name or one of its registered aliases.
func videoReferencesActress(v *VideoData, a *ActressData) bool {
	for _, display := range v.Actresses {
		if display == a.Name {
			return true
		}
		for _, alias := range a.Aliases {
			if display == alias {
				return true
			}
		}
	}
	return false
}

// videoReferencesAutoActressID reports whether any of v.Actresses[]
// hashes (via StableActressID) to actressID. Used to confirm a SQLite
// row tagged "auto_<sha1>" still has a JSON-side display string that
// would have produced the same synth id under MigrateFromJSON's
// auto-create path.
func videoReferencesAutoActressID(v *VideoData, actressID string) bool {
	for _, display := range v.Actresses {
		if StableActressID(display) == actressID {
			return true
		}
	}
	return false
}

// buildExpectedDBMeta collects the db_meta keys that should round-trip
// between JSON and SQLite, omitting empty values so VerifySync does not
// flag rows the import path itself never wrote.
func buildExpectedDBMeta(root *DatabaseData) map[string]string {
	expected := map[string]string{}
	if root.SchemaVersion != "" {
		expected["schema_version"] = root.SchemaVersion
	}
	if root.Metadata != nil {
		if root.Metadata.Description != "" {
			expected["description"] = root.Metadata.Description
		}
		if root.Metadata.Encoding != "" {
			expected["encoding"] = root.Metadata.Encoding
		}
	}
	if root.CreatedAt != "" {
		expected["created_at"] = root.CreatedAt
	}
	return expected
}

func sortDiffs(d []VerifyDiff) {
	sort.Slice(d, func(i, j int) bool {
		if d[i].Kind != d[j].Kind {
			return d[i].Kind < d[j].Kind
		}
		if d[i].Key != d[j].Key {
			return d[i].Key < d[j].Key
		}
		if d[i].Field != d[j].Field {
			return d[i].Field < d[j].Field
		}
		return d[i].Reason < d[j].Reason
	})
}
