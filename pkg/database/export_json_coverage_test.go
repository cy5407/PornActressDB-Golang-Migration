package database

import (
	"path/filepath"
	"testing"
)

// exportTestStore is a populated store for export coverage.
func exportTestStore(t *testing.T) *SQLiteStore {
	t.Helper()
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("setup migrate: %v", err)
	}
	return store
}

// --- ExportToJSON happy path + OutputPath ------------------------------

func TestExportToJSON_WritesFileWhenOutputPathSet(t *testing.T) {
	store := exportTestStore(t)
	out := filepath.Join(t.TempDir(), "export.json")
	root, err := store.ExportToJSON(ExportOptions{OutputPath: out})
	if err != nil {
		t.Fatalf("ExportToJSON: %v", err)
	}
	if len(root.Videos) != 3 {
		t.Errorf("exported videos = %d, want 3", len(root.Videos))
	}
	if len(root.Actresses) != 3 {
		t.Errorf("exported actresses = %d, want 3", len(root.Actresses))
	}
	// File must exist and re-import cleanly.
	store2 := migrateTestStore(t)
	rep, err := store2.MigrateFromJSON(out, MigrationOptions{})
	if err != nil {
		t.Fatalf("re-import exported file: %v", err)
	}
	if rep.VideosImported != 3 {
		t.Errorf("re-import videos = %d, want 3", rep.VideosImported)
	}
}

func TestExportToJSON_NoOutputPathReturnsRootOnly(t *testing.T) {
	store := exportTestStore(t)
	root, err := store.ExportToJSON(ExportOptions{})
	if err != nil {
		t.Fatalf("ExportToJSON: %v", err)
	}
	if root.Statistics == nil {
		t.Error("expected Statistics populated")
	}
}

func TestExportToJSON_ClosedStoreErrors(t *testing.T) {
	closed := &SQLiteStore{}
	if _, err := closed.ExportToJSON(ExportOptions{}); err == nil {
		t.Error("ExportToJSON on closed store returned nil")
	}
}

func TestExportToJSON_BadOutputPathErrors(t *testing.T) {
	store := exportTestStore(t)
	// Null byte → writeJSONDatabaseRoot's os.WriteFile fails.
	if _, err := store.ExportToJSON(ExportOptions{OutputPath: "bad\x00out.json"}); err == nil {
		t.Error("ExportToJSON with bad output path returned nil")
	}
}

// --- Direct loader error tails via dropped tables/views ----------------

func TestLoadDBMetaInto_SQLErrorWhenTableMissing(t *testing.T) {
	store := exportTestStore(t)
	dropTable(t, store, "db_meta")
	if err := loadDBMetaInto(store.db, NewDatabaseData()); err == nil {
		t.Error("loadDBMetaInto with missing db_meta returned nil")
	}
}

func TestLoadActressesFromSQLite_SQLErrorWhenTableMissing(t *testing.T) {
	store := exportTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "actress_aliases")
	dropTable(t, store, "actresses")
	if _, _, err := loadActressesFromSQLite(store.db); err == nil {
		t.Error("loadActressesFromSQLite with missing table returned nil")
	}
}

func TestLoadAliasesGrouped_SQLErrorWhenTableMissing(t *testing.T) {
	store := exportTestStore(t)
	dropTable(t, store, "actress_aliases")
	if _, err := loadAliasesGrouped(store.db); err == nil {
		t.Error("loadAliasesGrouped with missing table returned nil")
	}
}

func TestLoadVideosAndOrderedLinks_SQLErrorWhenTableMissing(t *testing.T) {
	store := exportTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "videos")
	if _, _, err := loadVideosAndOrderedLinks(store.db, map[string]string{}); err == nil {
		t.Error("loadVideosAndOrderedLinks with missing table returned nil")
	}
}

func TestLoadLinksFromSQLite_SQLErrorWhenTableMissing(t *testing.T) {
	store := exportTestStore(t)
	dropTable(t, store, "legacy_video_actress_links")
	if _, err := loadLinksFromSQLite(store.db); err == nil {
		t.Error("loadLinksFromSQLite with missing table returned nil")
	}
}

func TestBuildStatistics_SQLErrorWhenViewMissing(t *testing.T) {
	store := exportTestStore(t)
	if _, err := store.db.Exec("DROP VIEW studio_statistics"); err != nil {
		t.Fatalf("drop view: %v", err)
	}
	if _, err := buildStatistics(store.db, "2026-01-01T00:00:00Z"); err == nil {
		t.Error("buildStatistics with missing view returned nil")
	}
}

func TestExportToJSON_PropagatesLoaderErrors(t *testing.T) {
	// Drop actresses chain so ExportToJSON fails at loadActressesFromSQLite,
	// exercising the early-return after that loader.
	store := exportTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "actress_aliases")
	dropTable(t, store, "actresses")
	if _, err := store.ExportToJSON(ExportOptions{}); err == nil {
		t.Error("ExportToJSON with broken actresses schema returned nil")
	}
}

// --- ensureMetadata both branches --------------------------------------

func TestEnsureMetadata_AllocatesAndReuses(t *testing.T) {
	root := &DatabaseData{}
	m1 := ensureMetadata(root)
	if m1 == nil {
		t.Fatal("ensureMetadata returned nil")
	}
	m2 := ensureMetadata(root) // existing → reuse
	if m1 != m2 {
		t.Error("ensureMetadata allocated a second Metadata instead of reusing")
	}
}

func TestApplyDBMetaPair_AllKeys(t *testing.T) {
	root := NewDatabaseData()
	applyDBMetaPair(root, "schema_version", "1.0.0")
	applyDBMetaPair(root, "description", "desc")
	applyDBMetaPair(root, "encoding", "UTF-8")
	applyDBMetaPair(root, "created_at", "2026-01-01T00:00:00Z")
	applyDBMetaPair(root, "data_hash", "ignored")
	applyDBMetaPair(root, "unknown_key", "ignored")
	if root.SchemaVersion != "1.0.0" {
		t.Errorf("SchemaVersion = %q", root.SchemaVersion)
	}
	if root.Metadata == nil || root.Metadata.Description != "desc" {
		t.Error("description not applied")
	}
	if root.CreatedAt != "2026-01-01T00:00:00Z" {
		t.Errorf("CreatedAt = %q", root.CreatedAt)
	}
	// Empty values must be ignored (skip branches). Use a bare struct so
	// the fields start empty (NewDatabaseData pre-populates them).
	root2 := &DatabaseData{}
	applyDBMetaPair(root2, "schema_version", "")
	applyDBMetaPair(root2, "created_at", "")
	if root2.SchemaVersion != "" || root2.CreatedAt != "" {
		t.Error("empty values should be skipped")
	}
}

// --- ResyncFromJSON exercise (export round trip via resync) ------------

func TestResyncFromJSON_WipesAndRebuilds(t *testing.T) {
	store := exportTestStore(t)
	// Add an extra video not in the JSON source; resync should drop it.
	if err := store.AddVideo(&Video{Code: "EXTRA-1", Title: "transient"}); err != nil {
		t.Fatalf("AddVideo: %v", err)
	}
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.ResyncFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("ResyncFromJSON: %v", err)
	}
	if _, err := store.GetVideo("EXTRA-1"); err == nil {
		t.Error("EXTRA-1 should be gone after resync wipe")
	}
	n, _ := store.GetVideoCount()
	if n != 3 {
		t.Errorf("video count = %d after resync, want 3", n)
	}
}
