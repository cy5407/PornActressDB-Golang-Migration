package database

import (
	"testing"
)

// corruptIndexDB + SaveIndex JSON-side failure tests moved to
// pkg/database/jsonfixture/final6_coverage_test.go.

// --- loadVideosAndOrderedLinks link-query SQL-error tail ---------------

func TestLoadVideosAndOrderedLinks_LinkQueryErrorWhenLinksTableMissing(t *testing.T) {
	store := exportTestStore(t)
	dropTable(t, store, "video_actress_links")
	if _, _, err := loadVideosAndOrderedLinks(store.db, map[string]string{}); err == nil {
		t.Error("loadVideosAndOrderedLinks with missing links table returned nil error")
	}
}

func TestExportToJSON_LinkLoaderErrorPropagates(t *testing.T) {
	store := exportTestStore(t)
	dropTable(t, store, "video_actress_links")
	if _, err := store.ExportToJSON(ExportOptions{}); err == nil {
		t.Error("ExportToJSON with missing links table returned nil error")
	}
}

// --- mergeLinksFromRoot empty-links short-circuit (no tx) --------------

func TestMergeFromFile_EmptyLinksNoTransaction(t *testing.T) {
	store := runtimeTestStore(t)
	// Source with a video but NO links → mergeLinksFromRoot returns early
	// without opening a transaction.
	src := writeJSONDB(t, &DatabaseData{
		SchemaVersion: SchemaVersion,
		Videos: map[string]*VideoData{
			"NL-1": {Code: "NL-1", Title: "nolink", UpdatedAt: "2026-07-01T00:00:00Z"},
		},
	})
	stats, err := store.MergeFromFile(src, false)
	if err != nil {
		t.Fatalf("MergeFromFile: %v", err)
	}
	if stats.LinksAdded != 0 {
		t.Errorf("LinksAdded = %d, want 0", stats.LinksAdded)
	}
}
