package database

import (
	"context"
	"testing"
)

// --- ActressCleaner branch coverage ------------------------------------

func TestCleanActresses_DeduplicatesRepeatedNames(t *testing.T) {
	c := NewActressCleaner()
	cleaned, removed := c.CleanActresses([]string{"佐藤A", "佐藤A", "鈴木B"})
	// First 佐藤A kept, second is a dup → removed; 鈴木B kept.
	if len(cleaned) != 2 {
		t.Errorf("cleaned = %v, want 2 unique", cleaned)
	}
	foundDupRemoved := false
	for _, r := range removed {
		if r == "佐藤A" {
			foundDupRemoved = true
		}
	}
	if !foundDupRemoved {
		t.Errorf("removed = %v, want duplicate 佐藤A listed", removed)
	}
}

func TestCleanActresses_SkipsBlankNames(t *testing.T) {
	c := NewActressCleaner()
	cleaned, _ := c.CleanActresses([]string{"   ", "", "正常名字"})
	if len(cleaned) != 1 || cleaned[0] != "正常名字" {
		t.Errorf("cleaned = %v, want [正常名字]", cleaned)
	}
}

func TestCleanActresses_RemovesBlockedExactName(t *testing.T) {
	c := NewActressCleaner()
	cleaned, removed := c.CleanActresses([]string{"デビュー", "正常名字"})
	for _, n := range cleaned {
		if n == "デビュー" {
			t.Error("blocked name デビュー should not survive")
		}
	}
	if len(removed) == 0 {
		t.Error("expected デビュー in removed list")
	}
}

func TestCleanActresses_ReplaceExactExpandsAndDedups(t *testing.T) {
	c := NewActressCleaner()
	// "石川澪" present first, then the replace-exact phrase that maps to
	// "石川澪" → the replacement dedups against the already-seen name
	// (appendReplacementIfClean seen-branch).
	cleaned, removed := c.CleanActresses([]string{"石川澪", "石川澪とラブラブでハメまくる"})
	count := 0
	for _, n := range cleaned {
		if n == "石川澪" {
			count++
		}
	}
	if count != 1 {
		t.Errorf("石川澪 appears %d times, want 1 (replacement dedup)", count)
	}
	if len(removed) == 0 {
		t.Error("expected the replaced phrase in removed list")
	}
}

// --- SQLiteStore nil-receiver / closed-store guard sweep ---------------

func TestSQLiteStore_NilReceiverGuards(t *testing.T) {
	var s *SQLiteStore

	if s.DataDir() != "" {
		t.Error("nil DataDir should be empty")
	}
	if s.Path() != "" {
		t.Error("nil Path should be empty")
	}
	s.SetDataDir("x") // must not panic on nil receiver
	if s.GetActressPrimaryStudio("anyone") != "" {
		t.Error("nil GetActressPrimaryStudio should be empty")
	}

	if _, err := s.SchemaVersion(); err == nil {
		t.Error("nil SchemaVersion should error")
	}
}

func TestSQLiteStore_ClosedStoreGuardSweep(t *testing.T) {
	closed := &SQLiteStore{} // db == nil

	checks := []struct {
		name string
		run  func() error
	}{
		{"GetVideoCount", func() error { _, err := closed.GetVideoCount(); return err }},
		{"GetStats", func() error { _, err := closed.GetStats(); return err }},
		{"ListVideos", func() error { _, err := closed.ListVideos(); return err }},
		{"ListActresses", func() error { _, err := closed.ListActresses(); return err }},
		{"GetAllVideos", func() error { _, err := closed.GetAllVideos(); return err }},
		{"GetVideo", func() error { _, err := closed.GetVideo("x"); return err }},
		{"GetActress", func() error { _, err := closed.GetActress("x"); return err }},
		{"GetActressStats", func() error { _, err := closed.GetActressStats(); return err }},
		{"GetStudioStats", func() error { _, err := closed.GetStudioStats(); return err }},
		{"UpsertVideo", func() error { return closed.UpsertVideo("x", &VideoData{}) }},
		{"UpsertActress", func() error { return closed.UpsertActress(&ActressData{ID: "x"}) }},
		{"DeleteVideo", func() error { return closed.DeleteVideo("x") }},
		{"DeleteActress", func() error { return closed.DeleteActress("x") }},
		{"AddVideo", func() error { return closed.AddVideo(&Video{Code: "x"}) }},
		{"UpdateVideo", func() error { return closed.UpdateVideo("x", &Video{}) }},
		{"UpdateVideoFields", func() error { return closed.UpdateVideoFields("x", nil) }},
		{"BackupCreate", func() error { _, err := closed.BackupCreate(); return err }},
		{"BackupRestore", func() error { return closed.BackupRestore("x.sqlite") }},
		{"VerifySync", func() error { _, err := closed.VerifySync("x"); return err }},
		{"MergeFromFile", func() error { _, err := closed.MergeFromFile("x", false); return err }},
		{"SchemaVersion", func() error { _, err := closed.SchemaVersion(); return err }},
		{"InitSchema", func() error { return closed.InitSchema() }},
		{"isEmpty", func() error { _, err := closed.isEmpty(); return err }},
	}
	for _, c := range checks {
		t.Run(c.name, func(t *testing.T) {
			if err := c.run(); err == nil {
				t.Errorf("%s on closed store returned nil error", c.name)
			}
		})
	}
}

// --- DataDir / SetDataDir round trip on a live store -------------------

func TestSetDataDir_LiveStoreRoundTrip(t *testing.T) {
	store := migrateTestStore(t)
	store.SetDataDir(`C:\some\dir`)
	if store.DataDir() != `C:\some\dir` {
		t.Errorf("DataDir = %q, want round-tripped value", store.DataDir())
	}
}

// --- GetVideoCount / GetStats happy paths ------------------------------

func TestGetVideoCount_LivePopulatedStore(t *testing.T) {
	store := runtimeTestStore(t)
	n, err := store.GetVideoCount()
	if err != nil {
		t.Fatalf("GetVideoCount: %v", err)
	}
	if n != 3 {
		t.Errorf("GetVideoCount = %d, want 3 (fixture)", n)
	}
}

func TestGetStats_LivePopulatedStoreHasRetiredZeroKeys(t *testing.T) {
	store := runtimeTestStore(t)
	stats, err := store.GetStats()
	if err != nil {
		t.Fatalf("GetStats: %v", err)
	}
	if stats["video_count"].(int) != 3 {
		t.Errorf("video_count = %v, want 3", stats["video_count"])
	}
	// Retired journal counters must exist as zero/false per spec § 7.1.
	for _, k := range []string{"journal_size", "dirty_videos", "needs_compact", "sync_degraded_total"} {
		if _, ok := stats[k]; !ok {
			t.Errorf("stats missing retired key %q", k)
		}
	}
}

// --- VerifySync happy path against a freshly-migrated store ------------

func TestVerifySync_ConsistentAfterMigrate(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	report, err := store.VerifySync(src)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	if !report.Consistent {
		t.Errorf("expected consistent, got diffs: %+v", report.Diffs)
	}
}

func TestVerifySync_BadJSONPathErrors(t *testing.T) {
	store := migrateTestStore(t)
	if _, err := store.VerifySync("nonexistent.json"); err == nil {
		t.Error("VerifySync on missing JSON returned nil error")
	}
}

// --- JSONDatabase BatchUpdate + Save round trip ------------------------

func TestJSONDatabase_BatchUpdateThenReload(t *testing.T) {
	dir := t.TempDir()
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load: %v", err)
	}
	updates := map[string]*Video{
		"AAA-001": {Code: "AAA-001", Title: "one", Studio: "S"},
		"BBB-002": {Code: "BBB-002", Title: "two", Studio: "S"},
	}
	if err := db.BatchUpdate(updates); err != nil {
		t.Fatalf("BatchUpdate: %v", err)
	}

	// Reload from disk and confirm both videos persisted.
	db2 := NewJSONDatabase(dir)
	if err := db2.Load(context.Background()); err != nil {
		t.Fatalf("reload: %v", err)
	}
	for _, code := range []string{"AAA-001", "BBB-002"} {
		if _, err := db2.GetVideo(code); err != nil {
			t.Errorf("GetVideo(%s) after reload: %v", code, err)
		}
	}
}

func TestJSONDatabase_MergeActressRecordOverwriteAndSkip(t *testing.T) {
	dir := t.TempDir()
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load: %v", err)
	}
	// Seed one actress.
	if err := db.UpsertActress(&ActressData{ID: "a1", Name: "Original"}); err != nil {
		t.Fatalf("UpsertActress: %v", err)
	}

	stats := &MergeStats{}
	now := "2026-07-01T00:00:00Z"
	// Skip branch (overwrite=false on existing).
	db.mergeActressRecord("a1", &ActressData{ID: "a1", Name: "ShouldNotApply"}, false, now, stats)
	if stats.ActressesUpdated != 0 {
		t.Errorf("ActressesUpdated = %d, want 0 (skip)", stats.ActressesUpdated)
	}
	// Overwrite branch.
	db.mergeActressRecord("a1", &ActressData{ID: "a1", Name: "Updated"}, true, now, stats)
	if stats.ActressesUpdated != 1 {
		t.Errorf("ActressesUpdated = %d, want 1 (overwrite)", stats.ActressesUpdated)
	}
	// New-record branch.
	db.mergeActressRecord("a2", &ActressData{ID: "a2", Name: "Brand New"}, false, now, stats)
	if stats.ActressesAdded != 1 {
		t.Errorf("ActressesAdded = %d, want 1 (new)", stats.ActressesAdded)
	}
	// Nil + empty-id no-ops.
	db.mergeActressRecord("a3", nil, false, now, stats)
	db.mergeActressRecord("   ", &ActressData{Name: "x"}, false, now, stats)
}
