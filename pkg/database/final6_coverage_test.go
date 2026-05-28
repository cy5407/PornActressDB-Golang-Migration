package database

import (
	"testing"
)

// corruptIndexDB returns a loaded JSONDatabase whose index path is
// unwritable, so saveIndex fails and the writers exercise their
// warn-on-saveIndex-failure branches (without failing the operation).
func corruptIndexDB(t *testing.T) *JSONDatabase {
	t.Helper()
	db := loadedJSONDB(t)
	if err := db.AddVideo(&Video{Code: "IDX-SEED", Title: "s"}); err != nil {
		t.Fatalf("seed: %v", err)
	}
	db.mu.Lock()
	db.indexFile = "bad\x00index"
	db.mu.Unlock()
	return db
}

func TestAddVideo_SaveIndexFailureWarnsButSucceeds(t *testing.T) {
	db := corruptIndexDB(t)
	if err := db.AddVideo(&Video{Code: "IDX-1", Title: "a"}); err != nil {
		t.Errorf("AddVideo returned %v, want nil (saveIndex failure only warns)", err)
	}
	if _, err := db.GetVideo("IDX-1"); err != nil {
		t.Errorf("IDX-1 should be present despite index warn: %v", err)
	}
}

func TestUpdateVideo_SaveIndexFailureWarnsButSucceeds(t *testing.T) {
	db := corruptIndexDB(t)
	if err := db.UpdateVideo("IDX-SEED", &Video{Code: "IDX-SEED", Title: "u"}); err != nil {
		t.Errorf("UpdateVideo returned %v, want nil", err)
	}
}

func TestDeleteVideo_SaveIndexFailureWarnsButSucceeds(t *testing.T) {
	db := corruptIndexDB(t)
	if err := db.DeleteVideo("IDX-SEED"); err != nil {
		t.Errorf("DeleteVideo returned %v, want nil", err)
	}
}

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
