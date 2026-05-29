package database

import (
	"testing"
)

// verifyStoreFromMinimal migrates minimalRoot into a fresh store so we
// can then VerifySync against deliberately-divergent JSON.
func verifyStoreFromMinimal(t *testing.T) *SQLiteStore {
	t.Helper()
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("seed migrate: %v", err)
	}
	return store
}

func diffsByReason(diffs []VerifyDiff, kind, reason string) int {
	n := 0
	for _, d := range diffs {
		if d.Kind == kind && d.Reason == reason {
			n++
		}
	}
	return n
}

func TestVerifySync_DetectsVideoFieldDiffAndMissingSides(t *testing.T) {
	store := verifyStoreFromMinimal(t)

	// Build a JSON that diverges from the migrated SQLite:
	//  - STARS-707 has a different title (field_diff)
	//  - SSIS-001 is absent in JSON (missing_in_json from SQLite side)
	//  - GHOST-999 exists only in JSON (missing_in_sqlite)
	divergent := minimalRoot()
	divergent.Videos["STARS-707"].Title = "DIFFERENT TITLE"
	delete(divergent.Videos, "SSIS-001")
	divergent.Videos["GHOST-999"] = &VideoData{
		Code: "GHOST-999", Title: "ghost", Studio: "X",
		Actresses: []string{"田中美奈実"}, UpdatedAt: "2026-05-22T12:00:00Z",
	}
	divergent.Links = append(divergent.Links, VideoActressLink{
		VideoCode: "GHOST-999", ActressID: "tanaka-minami", RoleType: "主演",
	})

	src := writeJSONDB(t, divergent)
	report, err := store.VerifySync(src)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	if report.Consistent {
		t.Fatal("expected inconsistent report")
	}
	if diffsByReason(report.Diffs, "video", "field_diff") == 0 {
		t.Error("expected a video field_diff for STARS-707 title")
	}
	if diffsByReason(report.Diffs, "video", "missing_in_json") == 0 {
		t.Error("expected missing_in_json for SSIS-001")
	}
	if diffsByReason(report.Diffs, "video", "missing_in_sqlite") == 0 {
		t.Error("expected missing_in_sqlite for GHOST-999")
	}
}

func TestVerifySync_DetectsActressFieldAndAliasDiffs(t *testing.T) {
	store := verifyStoreFromMinimal(t)

	divergent := minimalRoot()
	// Rename an actress (field_diff on name) + add an alias not in SQLite.
	divergent.Actresses["tanaka-minami"].Name = "RENAMED"
	divergent.Actresses["tanaka-minami"].Aliases = []string{"新別名"}
	// Add an actress only in JSON (missing_in_sqlite).
	divergent.Actresses["json-only"] = &ActressData{ID: "json-only", Name: "JSON Only"}

	src := writeJSONDB(t, divergent)
	report, err := store.VerifySync(src)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	if report.Consistent {
		t.Fatal("expected inconsistent report")
	}
	if diffsByReason(report.Diffs, "actress", "field_diff") == 0 {
		t.Error("expected actress field_diff on name")
	}
	if diffsByReason(report.Diffs, "actress", "missing_in_sqlite") == 0 {
		t.Error("expected actress missing_in_sqlite for json-only")
	}
	// Alias divergence: JSON has 新別名 not in SQLite; SQLite has 田中みなみ
	// not in this JSON.
	aliasDiffs := 0
	for _, d := range report.Diffs {
		if d.Kind == "actress_alias" {
			aliasDiffs++
		}
	}
	if aliasDiffs == 0 {
		t.Error("expected actress_alias diffs")
	}
}

func TestVerifySync_DetectsLinkRoleAndMissingDiffs(t *testing.T) {
	store := verifyStoreFromMinimal(t)

	divergent := minimalRoot()
	// Change a link's role_type → link field_diff.
	for i := range divergent.Links {
		if divergent.Links[i].VideoCode == "STARS-707" {
			divergent.Links[i].RoleType = "協演"
		}
	}
	// Add a JSON link referencing a real video+actress but absent from
	// SQLite's link table (missing_in_sqlite for links). Use MIDV-567 +
	// an actress id that exists but isn't currently linked to it.
	divergent.Links = append(divergent.Links, VideoActressLink{
		VideoCode: "STARS-707", ActressID: "suzuki-hanako", RoleType: "主演",
	})

	src := writeJSONDB(t, divergent)
	report, err := store.VerifySync(src)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	if report.Consistent {
		t.Fatal("expected inconsistent report")
	}
	linkDiffs := 0
	for _, d := range report.Diffs {
		if d.Kind == "link" {
			linkDiffs++
		}
	}
	if linkDiffs == 0 {
		t.Error("expected link diffs")
	}
}

func TestVerifySync_DetectsDBMetaDiff(t *testing.T) {
	store := verifyStoreFromMinimal(t)

	divergent := minimalRoot()
	divergent.SchemaVersion = "9.9.9"               // field_diff vs stored
	divergent.Metadata.Description = "changed-desc" // field_diff
	divergent.CreatedAt = "1990-01-01T00:00:00Z"    // field_diff

	src := writeJSONDB(t, divergent)
	report, err := store.VerifySync(src)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	dbMetaDiffs := 0
	for _, d := range report.Diffs {
		if d.Kind == "db_meta" {
			dbMetaDiffs++
		}
	}
	if dbMetaDiffs == 0 {
		t.Error("expected db_meta diffs for schema_version / description / created_at")
	}
}

func TestVerifySync_DetectsLegacyLinkDiffs(t *testing.T) {
	store := verifyStoreFromMinimal(t)

	// minimalRoot has 4 links; drop one + change another so the legacy
	// link snapshot comparison emits missing/field diffs.
	divergent := minimalRoot()
	divergent.Links = divergent.Links[:2] // fewer than SQLite has (missing_in_json side)
	divergent.Links[0].RoleType = "協演"    // field_diff on ordinal 0

	src := writeJSONDB(t, divergent)
	report, err := store.VerifySync(src)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	legacyDiffs := 0
	for _, d := range report.Diffs {
		if d.Kind == "legacy_link" {
			legacyDiffs++
		}
	}
	if legacyDiffs == 0 {
		t.Error("expected legacy_link diffs")
	}
}

// --- jsonHasVideoActress / jsonHasDerivedAutoActress direct coverage ---

func TestJSONHasVideoActress_AliasAndAutoPaths(t *testing.T) {
	root := &DatabaseData{
		Videos: map[string]*VideoData{
			"V1": {Code: "V1", Actresses: []string{"田中みなみ"}}, // alias spelling
		},
		Actresses: map[string]*ActressData{
			"a1": {ID: "a1", Name: "田中美奈実", Aliases: []string{"田中みなみ"}},
		},
	}
	// Alias match path.
	if !jsonHasVideoActress(root, "V1", "a1") {
		t.Error("expected alias match to return true")
	}
	// Missing video.
	if jsonHasVideoActress(root, "NOPE", "a1") {
		t.Error("missing video should return false")
	}
	// Missing actress id, non-auto.
	if jsonHasVideoActress(root, "V1", "unknown") {
		t.Error("unknown non-auto actress should return false")
	}

	// Auto-actress path: video references a display whose StableActressID
	// matches the queried auto_ id.
	display := "自動女優"
	autoID := StableActressID(display)
	rootAuto := &DatabaseData{
		Videos: map[string]*VideoData{
			"V2": {Code: "V2", Actresses: []string{display}},
		},
		Actresses: map[string]*ActressData{},
	}
	if !jsonHasVideoActress(rootAuto, "V2", autoID) {
		t.Error("expected auto-actress id match to return true")
	}
}

func TestJSONHasDerivedAutoActress_MatchAndReject(t *testing.T) {
	display := "派生女優"
	autoID := StableActressID(display)
	root := &DatabaseData{
		Videos: map[string]*VideoData{
			"V1": {Code: "V1", Actresses: []string{display}},
		},
	}
	if !jsonHasDerivedAutoActress(root, autoID, display) {
		t.Error("expected derived auto-actress to match")
	}
	// Non-auto prefix id → false immediately.
	if jsonHasDerivedAutoActress(root, "regular-id", display) {
		t.Error("non-auto id should return false")
	}
	// Auto id but no matching display.
	if jsonHasDerivedAutoActress(root, StableActressID("someone"), "someone-else") {
		t.Error("auto id without matching display should return false")
	}
}
