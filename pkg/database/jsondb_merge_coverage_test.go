package database

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

// --- MergeFromFile JSON-side error guards ------------------------------

func TestJSONMergeFromFile_EmptyPathErrors(t *testing.T) {
	db := loadedJSONDB(t)
	if _, err := db.MergeFromFile("   ", false); err == nil {
		t.Error("MergeFromFile empty path returned nil error")
	}
}

func TestJSONMergeFromFile_CorruptSourceErrors(t *testing.T) {
	db := loadedJSONDB(t)
	bad := filepath.Join(t.TempDir(), "corrupt.json")
	if err := os.WriteFile(bad, []byte("{not json"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := db.MergeFromFile(bad, false); err == nil {
		t.Error("MergeFromFile corrupt source returned nil error")
	}
}

func TestJSONMergeFromFile_NotLoadedErrors(t *testing.T) {
	db := NewJSONDatabase(t.TempDir()) // never loaded
	src := writeJSONDB(t, minimalRoot())
	if _, err := db.MergeFromFile(src, false); err == nil {
		t.Error("MergeFromFile on unloaded db returned nil error")
	}
}

// --- MergeFromFile link dedup + finalize -------------------------------

func TestJSONMergeFromFile_LinkDedupAndFinalize(t *testing.T) {
	dir := t.TempDir()
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load: %v", err)
	}

	// Source with two videos, an actress, and links — one of which will be
	// re-merged on a second pass to exercise the dedup skip branch.
	src := writeJSONDB(t, &DatabaseData{
		SchemaVersion: SchemaVersion,
		Videos: map[string]*VideoData{
			"ML-1": {Code: "ML-1", Title: "a", Studio: "S", UpdatedAt: "2026-07-01T00:00:00Z"},
		},
		Actresses: map[string]*ActressData{
			"ml-a": {ID: "ml-a", Name: "ML Actress"},
		},
		Links: []VideoActressLink{
			{VideoCode: "ML-1", ActressID: "ml-a", RoleType: "主演", Timestamp: "2026-07-01T00:00:00Z"},
		},
	})

	stats1, err := db.MergeFromFile(src, false)
	if err != nil {
		t.Fatalf("first merge: %v", err)
	}
	if stats1.LinksAdded != 1 {
		t.Errorf("first merge LinksAdded = %d, want 1", stats1.LinksAdded)
	}

	// Second merge of the same file: link already present → dedup skip.
	stats2, err := db.MergeFromFile(src, false)
	if err != nil {
		t.Fatalf("second merge: %v", err)
	}
	if stats2.LinksAdded != 0 {
		t.Errorf("second merge LinksAdded = %d, want 0 (deduped)", stats2.LinksAdded)
	}
}
