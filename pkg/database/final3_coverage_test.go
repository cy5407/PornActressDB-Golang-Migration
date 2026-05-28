package database

import (
	"testing"
)

// --- UpsertVideo / UpsertActress guard + partial-failure branches ------

func TestUpsertVideo_NilVideoErrors(t *testing.T) {
	store := runtimeTestStore(t)
	if err := store.UpsertVideo("X", nil); err == nil {
		t.Error("UpsertVideo(_, nil) returned nil error")
	}
}

func TestUpsertVideo_LinkRebuildFailsWhenLinksTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	// Keep videos; drop only links so upsertVideoRow succeeds but the
	// link rebuild's DELETE/INSERT fails.
	dropTable(t, store, "video_actress_links")
	v := &VideoData{Code: "STARS-707", Title: "x", Actresses: []string{"田中美奈実"}}
	if err := store.UpsertVideo("STARS-707", v); err == nil {
		t.Error("UpsertVideo with missing links table returned nil error")
	}
}

func TestUpsertActress_NilOrEmptyIDErrors(t *testing.T) {
	store := runtimeTestStore(t)
	if err := store.UpsertActress(nil); err == nil {
		t.Error("UpsertActress(nil) returned nil error")
	}
	if err := store.UpsertActress(&ActressData{ID: ""}); err == nil {
		t.Error("UpsertActress(empty id) returned nil error")
	}
}

func TestUpsertActress_AliasInsertFailsWhenAliasesTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "actress_aliases")
	a := &ActressData{ID: "new-a", Name: "New", Aliases: []string{"alias-x"}}
	if err := store.UpsertActress(a); err == nil {
		t.Error("UpsertActress with aliases + missing aliases table returned nil")
	}
}

func TestUpsertActress_HappyReplaceAliases(t *testing.T) {
	store := runtimeTestStore(t)
	// Upsert existing actress with a new alias set → covers the
	// delete-then-insert alias replacement happy path.
	a := &ActressData{ID: "tanaka-minami", Name: "田中美奈実", Aliases: []string{"new-alias-1", "new-alias-2"}}
	if err := store.UpsertActress(a); err != nil {
		t.Fatalf("UpsertActress: %v", err)
	}
	got, err := store.GetActress("tanaka-minami")
	if err != nil {
		t.Fatalf("GetActress: %v", err)
	}
	if len(got.Aliases) != 2 {
		t.Errorf("aliases = %v, want 2 replaced", got.Aliases)
	}
}

// --- rebuildLinksForVideoAutoCreate auto-create + skip branches --------

func TestAddVideo_AutoCreateAndDuplicateCollapse(t *testing.T) {
	store := runtimeTestStore(t)
	// Same display twice → duplicate collapses to one link; plus a blank
	// entry that is trimmed away.
	v := &Video{
		Code:      "DUP-1",
		Title:     "dup",
		Actresses: []string{"新女優X", "新女優X", "   "},
	}
	if err := store.AddVideo(v); err != nil {
		t.Fatalf("AddVideo: %v", err)
	}
	var linkCount int
	if err := store.db.QueryRow(
		`SELECT COUNT(*) FROM video_actress_links WHERE video_code='DUP-1'`,
	).Scan(&linkCount); err != nil {
		t.Fatalf("count links: %v", err)
	}
	if linkCount != 1 {
		t.Errorf("link count = %d, want 1 (duplicate collapsed, blank skipped)", linkCount)
	}
}

// --- mergeOneVideo / mergeLinksFromRoot SQL-error tails ----------------

func TestMergeFromFile_LinkOverrideFailsWhenLinksTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	// Drop links so mergeLinksFromRoot's applyLinkOverrides fails — but
	// keep videos/actresses so the merge reaches the link step.
	dropTable(t, store, "video_actress_links")
	src := writeJSONDB(t, mergeSourceRoot())
	if _, err := store.MergeFromFile(src, false); err == nil {
		t.Error("MergeFromFile with missing links table returned nil error")
	}
}

func TestMergeFromFile_VideoUpsertFailsWhenVideosTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "videos")
	src := writeJSONDB(t, &DatabaseData{
		SchemaVersion: SchemaVersion,
		Videos: map[string]*VideoData{
			"MV-1": {Code: "MV-1", Title: "m", UpdatedAt: "2026-07-01T00:00:00Z"},
		},
	})
	if _, err := store.MergeFromFile(src, false); err == nil {
		t.Error("MergeFromFile with missing videos table returned nil error")
	}
}

// --- prepareVideoForMerge legacy-id / empty-code branches --------------

func TestPrepareVideoForMerge_Branches(t *testing.T) {
	now := "2026-01-01T00:00:00Z"

	// nil video → not ok.
	if _, _, ok := prepareVideoForMerge("MAP", nil, now); ok {
		t.Error("nil video should return ok=false")
	}

	// Empty code everywhere → not ok.
	if _, _, ok := prepareVideoForMerge("   ", &VideoData{}, now); ok {
		t.Error("empty code should return ok=false")
	}

	// Code from video.GetCode() takes precedence over mapCode.
	code, prepared, ok := prepareVideoForMerge("MAP-IGNORED", &VideoData{Code: "REAL-1"}, now)
	if !ok || code != "REAL-1" || prepared.Code != "REAL-1" {
		t.Errorf("expected REAL-1, got code=%q ok=%v", code, ok)
	}

	// Empty Code but mapCode present → mapCode used.
	code2, _, ok2 := prepareVideoForMerge("FROM-MAP", &VideoData{}, now)
	if !ok2 || code2 != "FROM-MAP" {
		t.Errorf("expected FROM-MAP from mapCode, got %q ok=%v", code2, ok2)
	}
}

// --- ResyncFromJSON wipe error when a table is missing -----------------

func TestResyncFromJSON_WipeFailsWhenTableMissing(t *testing.T) {
	store := runtimeTestStore(t)
	// Drop a table that wipeImportTables tries to DELETE FROM → wipe errors.
	dropTable(t, store, "legacy_video_actress_links")
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.ResyncFromJSON(src, MigrationOptions{}); err == nil {
		t.Error("ResyncFromJSON with missing wipe table returned nil error")
	}
}
