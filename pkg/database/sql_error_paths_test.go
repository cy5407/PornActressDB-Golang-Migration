package database

import (
	"testing"
)

// dropTable removes a table from a live store so that subsequent
// operations touching it hit their SQL-error tails. This exercises the
// real error-handling code against a genuinely broken schema (no mocks).
func dropTable(t *testing.T, store *SQLiteStore, table string) {
	t.Helper()
	if _, err := store.db.Exec("DROP TABLE " + table); err != nil {
		t.Fatalf("drop %s: %v", table, err)
	}
}

func TestUpsertVideo_SQLErrorWhenVideosTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	// Drop links first (FK child) then videos so the DROP succeeds.
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "videos")
	if err := store.UpsertVideo("X-1", &VideoData{Code: "X-1"}); err == nil {
		t.Error("UpsertVideo with missing videos table returned nil error")
	}
}

func TestUpsertActress_SQLErrorWhenActressesTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "actress_aliases")
	dropTable(t, store, "actresses")
	if err := store.UpsertActress(&ActressData{ID: "a-x", Name: "X"}); err == nil {
		t.Error("UpsertActress with missing actresses table returned nil error")
	}
}

func TestUpsertActress_SQLErrorWhenAliasesTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "actress_aliases")
	// Aliases present in input → the alias INSERT hits the missing table.
	err := store.UpsertActress(&ActressData{ID: "a-y", Name: "Y", Aliases: []string{"alias1"}})
	if err == nil {
		t.Error("UpsertActress with missing aliases table returned nil error")
	}
}

func TestDeleteVideo_SQLErrorWhenVideosTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "videos")
	if err := store.DeleteVideo("STARS-707"); err == nil {
		t.Error("DeleteVideo with missing videos table returned nil error")
	}
}

func TestDeleteActress_SQLErrorWhenActressesTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "actress_aliases")
	dropTable(t, store, "actresses")
	if err := store.DeleteActress("tanaka-minami"); err == nil {
		t.Error("DeleteActress with missing actresses table returned nil error")
	}
}

func TestAddVideo_SQLErrorWhenVideosTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "videos")
	if err := store.AddVideo(&Video{Code: "X-2", Title: "x"}); err == nil {
		t.Error("AddVideo with missing videos table returned nil error")
	}
}

func TestUpdateVideoFields_SQLErrorOnRebuild(t *testing.T) {
	store := runtimeTestStore(t)
	// Drop links so rebuildLinksForVideoAutoCreate's DELETE/INSERT errors
	// during the partial-field update of an existing video.
	dropTable(t, store, "video_actress_links")
	err := store.UpdateVideoFields("STARS-707", map[string]any{"title": "new"})
	if err == nil {
		t.Error("UpdateVideoFields with missing links table returned nil error")
	}
}

func TestGetActress_SQLErrorWhenAliasesTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "actress_aliases")
	// actresses row still present; alias query then fails.
	if _, err := store.GetActress("tanaka-minami"); err == nil {
		t.Error("GetActress with missing aliases table returned nil error")
	}
}

func TestGetVideoCount_SQLErrorWhenVideosTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "videos")
	if _, err := store.GetVideoCount(); err == nil {
		t.Error("GetVideoCount with missing videos table returned nil error")
	}
}

func TestGetStats_SQLErrorWhenActressesTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "actress_aliases")
	dropTable(t, store, "actresses")
	if _, err := store.GetStats(); err == nil {
		t.Error("GetStats with missing actresses table returned nil error")
	}
}

func TestGetActressStats_SQLErrorWhenViewMissing(t *testing.T) {
	store := runtimeTestStore(t)
	if _, err := store.db.Exec("DROP VIEW actress_video_counts"); err != nil {
		t.Fatalf("drop view: %v", err)
	}
	if _, err := store.GetActressStats(); err == nil {
		t.Error("GetActressStats with missing view returned nil error")
	}
}

func TestGetStudioStats_SQLErrorWhenVideosTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "videos")
	if _, err := store.GetStudioStats(); err == nil {
		t.Error("GetStudioStats with missing videos table returned nil error")
	}
}

func TestListVideos_SQLErrorWhenVideosTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "videos")
	if _, err := store.ListVideos(); err == nil {
		t.Error("ListVideos with missing videos table returned nil error")
	}
}

func TestListActresses_SQLErrorWhenActressesTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "actress_aliases")
	dropTable(t, store, "actresses")
	if _, err := store.ListActresses(); err == nil {
		t.Error("ListActresses with missing actresses table returned nil error")
	}
}

func TestGetAllVideos_SQLErrorWhenVideosTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "videos")
	if _, err := store.GetAllVideos(); err == nil {
		t.Error("GetAllVideos with missing videos table returned nil error")
	}
}

func TestMergeFromFile_SQLErrorWhenActressesTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "actress_aliases")
	dropTable(t, store, "actresses")
	src := writeJSONDB(t, mergeSourceRoot())
	if _, err := store.MergeFromFile(src, true); err == nil {
		t.Error("MergeFromFile with missing actresses table returned nil error")
	}
}

func TestMigrateFromJSON_SQLErrorWhenVideosTableMissing(t *testing.T) {
	store := migrateTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "videos")
	src := writeJSONDB(t, minimalRoot())
	report, err := store.MigrateFromJSON(src, MigrationOptions{})
	if err == nil {
		t.Errorf("MigrateFromJSON with missing videos table returned nil error; report=%+v", report)
	}
}

func TestVerifySync_SQLErrorWhenVideosTableMissing(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("seed migrate: %v", err)
	}
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "videos")
	if _, err := store.VerifySync(src); err == nil {
		t.Error("VerifySync with missing videos table returned nil error")
	}
}
