package database

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"sort"
	"testing"
)

// migrateTestStore opens a fresh SQLite store in t.TempDir and applies
// the schema. The returned store is closed at test teardown.
func migrateTestStore(t *testing.T) *SQLiteStore {
	t.Helper()
	path := filepath.Join(t.TempDir(), "migrate.sqlite")
	store, err := OpenSQLiteStore(path)
	if err != nil {
		t.Fatalf("OpenSQLiteStore: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })
	if err := store.InitSchema(); err != nil {
		t.Fatalf("InitSchema: %v", err)
	}
	return store
}

// writeJSONDB writes the given DatabaseData (marshalled) to a file in
// t.TempDir and returns its path.
func writeJSONDB(t *testing.T, root *DatabaseData) string {
	t.Helper()
	raw, err := json.MarshalIndent(root, "", "  ")
	if err != nil {
		t.Fatalf("marshal root: %v", err)
	}
	path := filepath.Join(t.TempDir(), "source.json")
	if err := os.WriteFile(path, raw, 0o600); err != nil {
		t.Fatalf("write source: %v", err)
	}
	return path
}

// minimalRoot is a happy-path JSON DB shaped like the CI fixture: 3
// videos, 3 actresses, 4 links, with one actress referenced from two
// distinct videos.
func minimalRoot() *DatabaseData {
	return &DatabaseData{
		SchemaVersion: SchemaVersion,
		Metadata:      &DatabaseMetadata{Description: "test", Encoding: "UTF-8"},
		CreatedAt:     "2026-05-23T00:00:00Z",
		UpdatedAt:     "2026-05-23T00:00:00Z",
		Videos: map[string]*VideoData{
			"STARS-707": {
				Code: "STARS-707", Title: "A", Studio: "S1",
				Actresses: []string{"田中美奈実"},
				UpdatedAt: "2026-05-22T12:00:00Z",
			},
			"MIDV-567": {
				Code: "MIDV-567", Title: "B", Studio: "MOODYZ",
				Actresses: []string{"佐藤亞美", "鈴木花子"},
				UpdatedAt: "2026-05-22T12:30:00Z",
			},
			"SSIS-001": {
				Code: "SSIS-001", Title: "C", Studio: "S1",
				Actresses: []string{"田中美奈実"},
				UpdatedAt: "2026-05-22T13:00:00Z",
			},
		},
		Actresses: map[string]*ActressData{
			"tanaka-minami": {ID: "tanaka-minami", Name: "田中美奈実", Aliases: []string{"田中みなみ"}},
			"sato-ami":      {ID: "sato-ami", Name: "佐藤亞美"},
			"suzuki-hanako": {ID: "suzuki-hanako", Name: "鈴木花子"},
		},
		Links: []VideoActressLink{
			{VideoCode: "STARS-707", ActressID: "tanaka-minami", RoleType: "主演", Timestamp: "2026-05-22T12:00:00Z"},
			{VideoCode: "MIDV-567", ActressID: "sato-ami", RoleType: "主演", Timestamp: "2026-05-22T12:30:00Z"},
			{VideoCode: "MIDV-567", ActressID: "suzuki-hanako", RoleType: "主演", Timestamp: "2026-05-22T12:30:00Z"},
			{VideoCode: "SSIS-001", ActressID: "tanaka-minami", RoleType: "主演", Timestamp: "2026-05-22T13:00:00Z"},
		},
	}
}

func TestMigrateFromJSON_HappyPath(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())

	report, err := store.MigrateFromJSON(src, MigrationOptions{})
	if err != nil {
		t.Fatalf("MigrateFromJSON: %v\nreport=%+v", err, report)
	}
	if !report.Success {
		t.Errorf("report.Success = false, want true")
	}
	if report.VideosImported != 3 {
		t.Errorf("VideosImported = %d, want 3", report.VideosImported)
	}
	if report.ActressesImported != 3 {
		t.Errorf("ActressesImported = %d, want 3", report.ActressesImported)
	}
	if report.LinksImported != 4 {
		t.Errorf("LinksImported = %d, want 4", report.LinksImported)
	}
	if len(report.Unresolved) != 0 {
		t.Errorf("Unresolved = %+v, want empty", report.Unresolved)
	}
	if len(report.Duplicates) != 0 {
		t.Errorf("Duplicates = %+v, want empty", report.Duplicates)
	}
	if len(report.AutoCreated) != 0 {
		t.Errorf("AutoCreated = %+v, want empty", report.AutoCreated)
	}

	var videoCount int
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM videos`).Scan(&videoCount); err != nil {
		t.Fatalf("count videos: %v", err)
	}
	if videoCount != 3 {
		t.Errorf("videos rows = %d, want 3", videoCount)
	}

	var linkCount int
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM video_actress_links`).Scan(&linkCount); err != nil {
		t.Fatalf("count links: %v", err)
	}
	if linkCount != 4 {
		t.Errorf("link rows = %d, want 4", linkCount)
	}

	var aliasCount int
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM actress_aliases`).Scan(&aliasCount); err != nil {
		t.Fatalf("count aliases: %v", err)
	}
	if aliasCount != 1 {
		t.Errorf("alias rows = %d, want 1", aliasCount)
	}
}

func TestMigrateFromJSON_PreservesOrdinal(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("MigrateFromJSON: %v", err)
	}

	rows, err := store.db.Query(
		`SELECT actress_id, ordinal FROM video_actress_links
		  WHERE video_code='MIDV-567' ORDER BY ordinal`,
	)
	if err != nil {
		t.Fatalf("query MIDV-567 links: %v", err)
	}
	defer rows.Close()
	var ids []string
	for rows.Next() {
		var id string
		var ord int
		if err := rows.Scan(&id, &ord); err != nil {
			t.Fatalf("scan: %v", err)
		}
		ids = append(ids, id)
	}
	if want := []string{"sato-ami", "suzuki-hanako"}; !equalStringSlices(ids, want) {
		t.Errorf("MIDV-567 actress order = %v, want %v", ids, want)
	}
}

func TestMigrateFromJSON_StrictModeFailsOnUnresolved(t *testing.T) {
	root := minimalRoot()
	// Reference an actress that does not exist in actresses{} and is not
	// listed as an alias of anyone.
	root.Videos["STARS-707"].Actresses = []string{"田中美奈実", "未知女優"}
	src := writeJSONDB(t, root)
	store := migrateTestStore(t)

	report, err := store.MigrateFromJSON(src, MigrationOptions{})
	if !errors.Is(err, ErrMigrationUnresolved) {
		t.Fatalf("err = %v, want ErrMigrationUnresolved", err)
	}
	if report.Success {
		t.Errorf("report.Success = true on failure")
	}
	if len(report.Unresolved) != 1 {
		t.Fatalf("Unresolved len = %d, want 1: %+v", len(report.Unresolved), report.Unresolved)
	}
	if report.Unresolved[0].VideoCode != "STARS-707" || report.Unresolved[0].Display != "未知女優" {
		t.Errorf("Unresolved[0] = %+v", report.Unresolved[0])
	}

	// Strict-mode failure must rollback the whole tx — DB should still be
	// empty.
	var videoCount int
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM videos`).Scan(&videoCount); err != nil {
		t.Fatalf("count videos: %v", err)
	}
	if videoCount != 0 {
		t.Errorf("videos rows = %d, want 0 (tx must rollback)", videoCount)
	}
}

func TestMigrateFromJSON_AutoCreateMissingActresses(t *testing.T) {
	root := minimalRoot()
	root.Videos["STARS-707"].Actresses = []string{"田中美奈実", "未知女優"}
	src := writeJSONDB(t, root)
	store := migrateTestStore(t)

	report, err := store.MigrateFromJSON(src, MigrationOptions{AutoCreateMissingActresses: true})
	if err != nil {
		t.Fatalf("MigrateFromJSON (auto): %v\nreport=%+v", err, report)
	}
	if !report.Success {
		t.Errorf("report.Success = false")
	}
	if len(report.AutoCreated) != 1 {
		t.Fatalf("AutoCreated len = %d, want 1: %+v", len(report.AutoCreated), report.AutoCreated)
	}
	got := report.AutoCreated[0]
	if got.Name != "未知女優" {
		t.Errorf("AutoCreated[0].Name = %q", got.Name)
	}
	if want := StableActressID("未知女優"); got.ActressID != want {
		t.Errorf("AutoCreated[0].ActressID = %q, want %q", got.ActressID, want)
	}
	if got.VideoCode != "STARS-707" {
		t.Errorf("AutoCreated[0].VideoCode = %q", got.VideoCode)
	}

	// 4 (original) + 1 (synthesised) = 4 actress rows; "未知女優" is brand
	// new so it adds 1; the original set already had 3.
	var actressCount int
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM actresses`).Scan(&actressCount); err != nil {
		t.Fatalf("count actresses: %v", err)
	}
	if actressCount != 4 {
		t.Errorf("actresses rows = %d, want 4", actressCount)
	}
}

func TestMigrateFromJSON_DuplicateActressInSameVideo(t *testing.T) {
	root := minimalRoot()
	// Same name appears twice within MIDV-567.
	root.Videos["MIDV-567"].Actresses = []string{"佐藤亞美", "鈴木花子", "佐藤亞美"}
	src := writeJSONDB(t, root)
	store := migrateTestStore(t)

	report, err := store.MigrateFromJSON(src, MigrationOptions{})
	if !errors.Is(err, ErrMigrationDuplicate) {
		t.Fatalf("err = %v, want ErrMigrationDuplicate", err)
	}
	if len(report.Duplicates) != 1 {
		t.Fatalf("Duplicates len = %d, want 1: %+v", len(report.Duplicates), report.Duplicates)
	}
	d := report.Duplicates[0]
	if d.VideoCode != "MIDV-567" || d.ActressID != "sato-ami" {
		t.Errorf("Duplicates[0] = %+v", d)
	}
	if want := []int{0, 2}; !equalIntSlices(d.Ordinals, want) {
		t.Errorf("Duplicates[0].Ordinals = %v, want %v", d.Ordinals, want)
	}

	var videoCount int
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM videos`).Scan(&videoCount); err != nil {
		t.Fatalf("count videos: %v", err)
	}
	if videoCount != 0 {
		t.Errorf("videos rows = %d, want 0 (tx must rollback)", videoCount)
	}
}

func TestMigrateFromJSON_LinksOverrideTimestamp(t *testing.T) {
	root := minimalRoot()
	// Override the STARS-707 link timestamp from the link list (which is
	// canonical per spec § 3.1 Pass 3).
	root.Links[0].Timestamp = "2030-01-01T00:00:00Z"
	root.Links[0].RoleType = "配角"
	src := writeJSONDB(t, root)
	store := migrateTestStore(t)

	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("MigrateFromJSON: %v", err)
	}

	var ts, role string
	if err := store.db.QueryRow(
		`SELECT timestamp, role_type FROM video_actress_links
		   WHERE video_code='STARS-707' AND actress_id='tanaka-minami'`,
	).Scan(&ts, &role); err != nil {
		t.Fatalf("query override: %v", err)
	}
	if ts != "2030-01-01T00:00:00Z" {
		t.Errorf("override timestamp = %q, want 2030-01-01T00:00:00Z", ts)
	}
	if role != "配角" {
		t.Errorf("override role_type = %q, want 配角", role)
	}
}

func TestMigrateFromJSON_AliasResolves(t *testing.T) {
	root := minimalRoot()
	// Reference an actress by her alias "田中みなみ" (which is set on
	// tanaka-minami in minimalRoot).
	root.Videos["STARS-707"].Actresses = []string{"田中みなみ"}
	src := writeJSONDB(t, root)
	store := migrateTestStore(t)

	report, err := store.MigrateFromJSON(src, MigrationOptions{})
	if err != nil {
		t.Fatalf("MigrateFromJSON: %v", err)
	}
	if len(report.Unresolved) != 0 {
		t.Errorf("Unresolved = %+v", report.Unresolved)
	}

	var actressID, displayName string
	if err := store.db.QueryRow(
		`SELECT actress_id, display_name FROM video_actress_links
		   WHERE video_code='STARS-707' AND ordinal=0`,
	).Scan(&actressID, &displayName); err != nil {
		t.Fatalf("query alias link: %v", err)
	}
	if actressID != "tanaka-minami" {
		t.Errorf("alias link actress_id = %q, want tanaka-minami", actressID)
	}
	if displayName != "田中みなみ" {
		t.Errorf("display_name = %q, want 田中みなみ (alias should be preserved)", displayName)
	}
}

func TestMigrateFromJSON_PopulatesDBMeta(t *testing.T) {
	root := minimalRoot()
	root.SchemaVersion = "1.0.0"
	root.Metadata = &DatabaseMetadata{Description: "from JSON", Encoding: "UTF-8"}
	root.CreatedAt = "2025-01-01T00:00:00Z"
	root.UpdatedAt = "2026-05-22T13:00:00Z"
	src := writeJSONDB(t, root)
	store := migrateTestStore(t)

	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("MigrateFromJSON: %v", err)
	}

	want := map[string]string{
		"schema_version": "1.0.0",
		"description":    "from JSON",
		"encoding":       "UTF-8",
		"created_at":     "2025-01-01T00:00:00Z",
		"updated_at":     "2026-05-22T13:00:00Z",
		"data_hash":      "", // never persisted from JSON input
	}
	for key, expected := range want {
		var got string
		if err := store.db.QueryRow(
			`SELECT value FROM db_meta WHERE key=?`, key,
		).Scan(&got); err != nil {
			t.Errorf("db_meta[%q]: %v", key, err)
			continue
		}
		if got != expected {
			t.Errorf("db_meta[%q] = %q, want %q", key, got, expected)
		}
	}
}

func TestMigrateFromJSON_FileNotFound(t *testing.T) {
	store := migrateTestStore(t)
	_, err := store.MigrateFromJSON("/no/such/file.json", MigrationOptions{})
	if err == nil {
		t.Error("MigrateFromJSON(/no/such/file) returned nil error")
	}
}

func TestStableActressID_FormatAndDeterministic(t *testing.T) {
	id := StableActressID("  田中美奈実 ")
	if id == StableActressID("田中美奈実") {
		// Good — TrimSpace makes these equal.
	} else {
		t.Errorf("StableActressID is not TrimSpace-equivalent: %q vs %q",
			StableActressID("  田中美奈実 "), StableActressID("田中美奈実"))
	}
	if len(id) != len(AutoActressIDPrefix)+16 {
		t.Errorf("StableActressID length = %d, want %d", len(id), len(AutoActressIDPrefix)+16)
	}
	// Must NOT collapse NFC/NFD variants — spec § 3.3.
	nfc := "é"     // é, single codepoint
	nfd := "é"    // e + combining acute
	if StableActressID(nfc) == StableActressID(nfd) {
		t.Error("StableActressID collapses NFC/NFD variants; spec § 3.3 forbids this")
	}
}

// --- helpers ---------------------------------------------------------------

func equalStringSlices(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func equalIntSlices(a, b []int) bool {
	if len(a) != len(b) {
		return false
	}
	aa := append([]int(nil), a...)
	bb := append([]int(nil), b...)
	sort.Ints(aa)
	sort.Ints(bb)
	for i := range aa {
		if aa[i] != bb[i] {
			return false
		}
	}
	return true
}
