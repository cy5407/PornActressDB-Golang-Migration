package jsonfixture

import (
	"context"
	"testing"

	. "actress-classifier/pkg/database"
)

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
