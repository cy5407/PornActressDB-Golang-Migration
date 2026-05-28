package database

import (
	"testing"
)

// Drop ONLY the links table: insertVideoRow + insertActressRow succeed,
// then insertLinkRow fails → covers insertLinkRow's SQL-error tail
// (distinct from the videos/actresses table drops).
func TestMigrateFromJSON_InsertLinkErrorWhenLinksTableMissing(t *testing.T) {
	store := migrateTestStore(t)
	dropTable(t, store, "video_actress_links")
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err == nil {
		t.Error("MigrateFromJSON with missing links table returned nil error")
	}
}

// Drop ONLY the legacy snapshot table: the main migration succeeds up to
// saveLegacyRootLinks, which then fails → covers its SQL-error tail.
func TestMigrateFromJSON_SaveLegacyLinksErrorWhenTableMissing(t *testing.T) {
	store := migrateTestStore(t)
	dropTable(t, store, "legacy_video_actress_links")
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err == nil {
		t.Error("MigrateFromJSON with missing legacy table returned nil error")
	}
}

// upsertVideoRuntime auto-create path: a runtime AddVideo with an unknown
// actress drives rebuildLinksForVideoAutoCreate's INSERT OR IGNORE +
// link-insert happy branches end-to-end.
func TestAddVideo_AutoCreateActressPersistsEntity(t *testing.T) {
	store := runtimeTestStore(t)
	if err := store.AddVideo(&Video{Code: "AE-1", Title: "t", Actresses: []string{"全新女優Z"}}); err != nil {
		t.Fatalf("AddVideo: %v", err)
	}
	// The synth actress row must exist.
	id := StableActressID("全新女優Z")
	got, err := store.GetActress(id)
	if err != nil {
		t.Fatalf("GetActress(%s): %v", id, err)
	}
	if got.Name != "全新女優Z" {
		t.Errorf("synth actress name = %q, want 全新女優Z", got.Name)
	}
}

// rebuildLinksForVideoAutoCreate alias path: an UpdateVideo referencing an
// existing actress by alias resolves via lookupActressForLink's alias
// branch and stores the alias spelling as display_name.
func TestUpdateVideo_ResolvesActressByAliasPreservesDisplay(t *testing.T) {
	store := runtimeTestStore(t)
	// minimalRoot: tanaka-minami has alias 田中みなみ. Reference the alias.
	v := &Video{Code: "STARS-707", Title: "x", Actresses: []string{"田中みなみ"}}
	if err := store.UpdateVideo("STARS-707", v); err != nil {
		t.Fatalf("UpdateVideo: %v", err)
	}
	got, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	if len(got.Actresses) != 1 || got.Actresses[0] != "田中みなみ" {
		t.Errorf("actresses = %v, want [田中みなみ] (alias display preserved)", got.Actresses)
	}
}

// GetActressPrimaryStudio with a SQL error (links table dropped) returns
// "" (the function swallows the query error).
func TestGetActressPrimaryStudio_SQLErrorReturnsEmpty(t *testing.T) {
	store := runtimeTestStore(t)
	dropTable(t, store, "video_actress_links")
	if got := store.GetActressPrimaryStudio("田中美奈実"); got != "" {
		t.Errorf("GetActressPrimaryStudio on broken schema = %q, want empty", got)
	}
}
