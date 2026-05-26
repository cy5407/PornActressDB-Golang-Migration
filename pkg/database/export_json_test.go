package database

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"testing"
)

func TestExportToJSON_ReturnsValidStructureForEmptyStore(t *testing.T) {
	store := migrateTestStore(t)

	root, err := store.ExportToJSON(ExportOptions{})
	if err != nil {
		t.Fatalf("ExportToJSON: %v", err)
	}
	if root == nil {
		t.Fatal("export = nil")
		return
	}
	if root.SchemaVersion != SchemaVersion {
		t.Errorf("SchemaVersion = %q, want %q", root.SchemaVersion, SchemaVersion)
	}
	if root.DataHash != "" {
		t.Errorf("DataHash = %q, want empty (reserved)", root.DataHash)
	}
	if len(root.Videos) != 0 {
		t.Errorf("Videos = %d entries, want 0", len(root.Videos))
	}
	if len(root.Actresses) != 0 {
		t.Errorf("Actresses = %d entries, want 0", len(root.Actresses))
	}
}

func TestExportToJSON_AfterMigrate_PopulatesAllSections(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	root, err := store.ExportToJSON(ExportOptions{})
	if err != nil {
		t.Fatalf("ExportToJSON: %v", err)
	}

	if len(root.Videos) != 3 {
		t.Errorf("Videos = %d, want 3", len(root.Videos))
	}
	if len(root.Actresses) != 3 {
		t.Errorf("Actresses = %d, want 3", len(root.Actresses))
	}
	if len(root.Links) != 4 {
		t.Errorf("Links = %d, want 4", len(root.Links))
	}

	// statistics block must have the three expected sub-keys.
	for _, key := range []string{"actress_statistics", "studio_statistics", "enhanced_actress_studio_statistics", "computed_at"} {
		if _, ok := root.Statistics[key]; !ok {
			t.Errorf("statistics missing key %q: %+v", key, root.Statistics)
		}
	}

	// actresses[].video_count comes from the view, not from JSON input.
	tanaka := root.Actresses["tanaka-minami"]
	if tanaka == nil {
		t.Fatal("tanaka-minami missing")
		return
	}
	if tanaka.VideoCount != 2 {
		t.Errorf("tanaka-minami video_count = %d, want 2 (appears in STARS-707 + SSIS-001)", tanaka.VideoCount)
	}
}

func TestExportToJSON_StatisticsView(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	root, err := store.ExportToJSON(ExportOptions{})
	if err != nil {
		t.Fatalf("ExportToJSON: %v", err)
	}

	// studio_statistics must list each studio with the right count.
	studioStatsRaw, ok := root.Statistics["studio_statistics"].([]StudioStatistic)
	if !ok {
		t.Fatalf("studio_statistics shape = %T, want []StudioStatistic", root.Statistics["studio_statistics"])
	}
	gotByStudio := map[string]int{}
	for _, s := range studioStatsRaw {
		gotByStudio[s.Studio] = s.VideoCount
	}
	if gotByStudio["S1"] != 2 {
		t.Errorf("S1 count = %d, want 2", gotByStudio["S1"])
	}
	if gotByStudio["MOODYZ"] != 1 {
		t.Errorf("MOODYZ count = %d, want 1", gotByStudio["MOODYZ"])
	}

	// enhanced_actress_studio_statistics has one row per (actress, studio).
	enhanced, ok := root.Statistics["enhanced_actress_studio_statistics"].([]EnhancedActressStudioStatistic)
	if !ok {
		t.Fatalf("enhanced shape = %T", root.Statistics["enhanced_actress_studio_statistics"])
	}
	// tanaka-minami appears in S1 twice (STARS-707, SSIS-001) → expect 1 row, count=2.
	var tanakaS1 *EnhancedActressStudioStatistic
	for i := range enhanced {
		if enhanced[i].ActressID == "tanaka-minami" && enhanced[i].Studio == "S1" {
			tanakaS1 = &enhanced[i]
		}
	}
	if tanakaS1 == nil {
		t.Fatalf("missing (tanaka-minami, S1) enhanced row: %+v", enhanced)
		return
	}
	if tanakaS1.VideoCount != 2 {
		t.Errorf("(tanaka, S1).video_count = %d, want 2", tanakaS1.VideoCount)
	}
}

func TestExportToJSON_PreservesVideoActressOrder(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	root, err := store.ExportToJSON(ExportOptions{})
	if err != nil {
		t.Fatalf("ExportToJSON: %v", err)
	}
	v := root.Videos["MIDV-567"]
	if v == nil {
		t.Fatal("MIDV-567 missing")
		return
	}
	want := []string{"佐藤亞美", "鈴木花子"}
	if !equalStringSlices(v.Actresses, want) {
		t.Errorf("MIDV-567.actresses = %v, want %v", v.Actresses, want)
	}
}

func TestExportToJSON_WritesFile(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	out := filepath.Join(t.TempDir(), "exported.json")
	root, err := store.ExportToJSON(ExportOptions{OutputPath: out})
	if err != nil {
		t.Fatalf("ExportToJSON: %v", err)
	}
	raw, err := os.ReadFile(out)
	if err != nil {
		t.Fatalf("read output: %v", err)
	}
	var roundTripped DatabaseData
	if err := json.Unmarshal(raw, &roundTripped); err != nil {
		t.Fatalf("unmarshal output: %v", err)
	}
	if len(roundTripped.Videos) != len(root.Videos) {
		t.Errorf("disk videos = %d, in-mem = %d", len(roundTripped.Videos), len(root.Videos))
	}
}

func TestExportToJSON_RoundTripSemanticEquivalence(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	out := filepath.Join(t.TempDir(), "roundtrip.json")
	if _, err := store.ExportToJSON(ExportOptions{OutputPath: out}); err != nil {
		t.Fatalf("export: %v", err)
	}

	// Re-import the exported JSON into a fresh store and verify.
	store2 := migrateTestStore(t)
	if _, err := store2.MigrateFromJSON(out, MigrationOptions{}); err != nil {
		t.Fatalf("re-migrate from export: %v", err)
	}
	report, err := store2.VerifySync(out)
	if err != nil {
		t.Fatalf("verify roundtrip: %v", err)
	}
	if !report.Consistent {
		t.Errorf("roundtrip verify failed: %+v", report.Diffs)
	}
}

func TestExportToJSON_DBMetaFlowsBackThroughExport(t *testing.T) {
	store := migrateTestStore(t)
	root := minimalRoot()
	root.SchemaVersion = "1.0.0"
	root.Metadata = &DatabaseMetadata{Description: "custom desc", Encoding: "UTF-8"}
	root.CreatedAt = "2025-06-01T00:00:00Z"
	src := writeJSONDB(t, root)
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	exported, err := store.ExportToJSON(ExportOptions{})
	if err != nil {
		t.Fatalf("export: %v", err)
	}
	if exported.SchemaVersion != "1.0.0" {
		t.Errorf("SchemaVersion = %q, want 1.0.0", exported.SchemaVersion)
	}
	if exported.Metadata == nil || exported.Metadata.Description != "custom desc" {
		t.Errorf("Metadata.Description = %v, want %q", exported.Metadata, "custom desc")
	}
	if exported.CreatedAt != "2025-06-01T00:00:00Z" {
		t.Errorf("CreatedAt = %q, want 2025-06-01T00:00:00Z", exported.CreatedAt)
	}
}

func TestExportToJSON_ActressIdsAreSorted(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	root, err := store.ExportToJSON(ExportOptions{})
	if err != nil {
		t.Fatalf("export: %v", err)
	}
	stats := root.Statistics["actress_statistics"].([]ActressStatistic)
	ids := make([]string, len(stats))
	for i, s := range stats {
		ids[i] = s.ID
	}
	if !sort.StringsAreSorted(ids) {
		t.Errorf("actress_statistics IDs not sorted: %v", ids)
	}
}
