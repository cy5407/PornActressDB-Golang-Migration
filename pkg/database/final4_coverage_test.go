package database

import (
	"testing"
)

// loadActressesFromSQLite's video_count query depends on the
// actress_video_counts view; dropping it exercises that error tail
// while the actresses table is still present.
func TestLoadActressesFromSQLite_VideoCountViewMissing(t *testing.T) {
	store := exportTestStore(t)
	if _, err := store.db.Exec("DROP VIEW actress_video_counts"); err != nil {
		t.Fatalf("drop view: %v", err)
	}
	if _, _, err := loadActressesFromSQLite(store.db); err == nil {
		t.Error("loadActressesFromSQLite with missing view returned nil error")
	}
}

// verifyVideos is the first verify step; dropping videos exercises its
// SQL-error tail (distinct from the actresses/db_meta ones).
func TestVerifyVideos_SQLErrorWhenVideosTableMissing(t *testing.T) {
	store := verifyStoreFromMinimal(t)
	src := writeJSONDB(t, minimalRoot())
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "videos")
	if _, err := store.VerifySync(src); err == nil {
		t.Error("VerifySync with missing videos table returned nil error")
	}
}

// verifyLinks SQL-error tail: drop links after seeding so the link
// select fails (videos/actresses still present).
func TestVerifyLinks_SQLErrorWhenLinksTableMissing(t *testing.T) {
	store := verifyStoreFromMinimal(t)
	src := writeJSONDB(t, minimalRoot())
	dropTable(t, store, "video_actress_links")
	if _, err := store.VerifySync(src); err == nil {
		t.Error("VerifySync with missing links table returned nil error")
	}
}

// verifyLegacyLinks SQL-error tail.
func TestVerifyLegacyLinks_SQLErrorWhenTableMissing(t *testing.T) {
	store := verifyStoreFromMinimal(t)
	src := writeJSONDB(t, minimalRoot())
	dropTable(t, store, "legacy_video_actress_links")
	if _, err := store.VerifySync(src); err == nil {
		t.Error("VerifySync with missing legacy table returned nil error")
	}
}

// loadLinksFromSQLite happy path returns the legacy snapshot rows.
func TestLoadLinksFromSQLite_ReturnsLegacyRows(t *testing.T) {
	store := exportTestStore(t)
	links, err := loadLinksFromSQLite(store.db)
	if err != nil {
		t.Fatalf("loadLinksFromSQLite: %v", err)
	}
	if len(links) != 4 {
		t.Errorf("legacy links = %d, want 4 (fixture)", len(links))
	}
}

// GetActressStats / GetStudioStats on an empty store cover the
// empty-result return shapes.
func TestStatsOnEmptyStore(t *testing.T) {
	store := migrateTestStore(t)
	as, err := store.GetActressStats()
	if err != nil {
		t.Fatalf("GetActressStats: %v", err)
	}
	if len(as) != 0 {
		t.Errorf("actress stats = %v, want empty", as)
	}
	ss, err := store.GetStudioStats()
	if err != nil {
		t.Fatalf("GetStudioStats: %v", err)
	}
	if len(ss) != 0 {
		t.Errorf("studio stats = %v, want empty", ss)
	}
}
