package database

import (
	"testing"
)

// rootWithOrphanLink returns a JSON DB matching minimalRoot() but with
// an extra orphan link entry whose video_code is empty — the kind of
// legacy/orphan link that the FK-constrained video_actress_links table
// cannot hold. The orphan must still round-trip through SQLite via
// legacy_video_actress_links.
func rootWithOrphanLink() *DatabaseData {
	root := minimalRoot()
	root.Links = append(root.Links, VideoActressLink{
		VideoCode: "",
		ActressID: "",
		RoleType:  "",
		Timestamp: "",
	})
	return root
}

func TestMigrateFromJSON_PreservesOrphanRootLinkInLegacyTable(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, rootWithOrphanLink())

	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("MigrateFromJSON: %v", err)
	}

	// Orphan row must be present in the legacy snapshot table.
	var orphanCount int
	if err := store.db.QueryRow(
		`SELECT COUNT(*) FROM legacy_video_actress_links WHERE video_code='' AND actress_id=''`,
	).Scan(&orphanCount); err != nil {
		t.Fatalf("count orphan legacy rows: %v", err)
	}
	if orphanCount != 1 {
		t.Errorf("orphan legacy row count = %d, want 1", orphanCount)
	}

	// All 5 root.links entries must be in the legacy table, ordered by
	// the original array index.
	var legacyCount int
	if err := store.db.QueryRow(
		`SELECT COUNT(*) FROM legacy_video_actress_links`,
	).Scan(&legacyCount); err != nil {
		t.Fatalf("count legacy rows: %v", err)
	}
	if legacyCount != 5 {
		t.Errorf("legacy row count = %d, want 5 (4 normal + 1 orphan)", legacyCount)
	}

	// Orphan must NOT leak into the FK-constrained runtime table.
	var runtimeOrphan int
	if err := store.db.QueryRow(
		`SELECT COUNT(*) FROM video_actress_links WHERE video_code=''`,
	).Scan(&runtimeOrphan); err != nil {
		t.Fatalf("count runtime orphan: %v", err)
	}
	if runtimeOrphan != 0 {
		t.Errorf("runtime video_actress_links has %d orphans, want 0", runtimeOrphan)
	}
}

func TestExportToJSON_RoundTripsOrphanRootLinkAtOriginalOrdinal(t *testing.T) {
	store := migrateTestStore(t)
	root := rootWithOrphanLink()
	src := writeJSONDB(t, root)
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	exported, err := store.ExportToJSON(ExportOptions{})
	if err != nil {
		t.Fatalf("ExportToJSON: %v", err)
	}

	if len(exported.Links) != len(root.Links) {
		t.Fatalf("Links len = %d, want %d", len(exported.Links), len(root.Links))
	}
	last := exported.Links[len(exported.Links)-1]
	if last.VideoCode != "" || last.ActressID != "" {
		t.Errorf("last link = %+v, want orphan (empty video_code/actress_id)", last)
	}
}

func TestVerifySync_AcceptsOrphanRootLink(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, rootWithOrphanLink())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	report, err := store.VerifySync(src)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	if !report.Consistent {
		t.Errorf("Consistent = false with orphan link, diffs = %+v", report.Diffs)
	}
}

func TestVerifySync_DetectsLegacyLinkTampering(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, rootWithOrphanLink())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	// Tamper with the orphan row's role_type — verify must flag it.
	if _, err := store.db.Exec(
		`UPDATE legacy_video_actress_links SET role_type='客串'
		   WHERE video_code='' AND actress_id=''`,
	); err != nil {
		t.Fatalf("tamper legacy row: %v", err)
	}

	report, err := store.VerifySync(src)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	if report.Consistent {
		t.Errorf("Consistent = true after tampering, want false")
	}
	found := false
	for _, d := range report.Diffs {
		if d.Kind == "legacy_link" && d.Field == "role_type" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected legacy_link role_type diff, got %+v", report.Diffs)
	}
}

func TestResyncFromJSON_WipesLegacyRootLinksTable(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, rootWithOrphanLink())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("initial migrate: %v", err)
	}

	// Resync against a root that has NO orphan link; the legacy table
	// must be rebuilt to match the new JSON, not append on top.
	root := minimalRoot() // 4 links, no orphan
	src2 := writeJSONDB(t, root)
	if _, err := store.ResyncFromJSON(src2, MigrationOptions{}); err != nil {
		t.Fatalf("resync: %v", err)
	}

	var legacyCount int
	if err := store.db.QueryRow(
		`SELECT COUNT(*) FROM legacy_video_actress_links`,
	).Scan(&legacyCount); err != nil {
		t.Fatalf("count legacy: %v", err)
	}
	if legacyCount != 4 {
		t.Errorf("legacy row count after resync = %d, want 4", legacyCount)
	}

	var orphanCount int
	if err := store.db.QueryRow(
		`SELECT COUNT(*) FROM legacy_video_actress_links WHERE video_code=''`,
	).Scan(&orphanCount); err != nil {
		t.Fatalf("count orphan post-resync: %v", err)
	}
	if orphanCount != 0 {
		t.Errorf("orphan rows remain after resync: %d", orphanCount)
	}
}
