package database

import (
	"testing"
)

// TestUpdateVideoFields_ExercisesEveryHandler drives every key in
// videoFieldUpdateHandlers so each handler closure is executed.
func TestUpdateVideoFields_ExercisesEveryHandler(t *testing.T) {
	store := runtimeTestStore(t)

	updates := map[string]any{
		"id":                      "vid-id",
		"code":                    "STARS-707",
		"created_at":              "2020-01-01T00:00:00Z",
		"title":                   "new title",
		"studio":                  "NEWSTUDIO",
		"studio_code":             "NS",
		"release_date":            "2026-01-02",
		"url":                     "http://example.com",
		"search_status":           "done",
		"search_method":           "manual",
		"last_search_date":        "2026-01-03",
		"avwiki_actress_status":   "found",
		"avwiki_last_search_date": "2026-01-04",
		"javdb_actress_status":    "found",
		"javdb_last_search_date":  "2026-01-05",
		"original_filename":       "orig.mp4",
		"file_path":               "/data/orig.mp4",
		"error":                   "none",
		"error_kind":              "",
		"actresses":               []any{"田中美奈実", "佐藤亞美"},
		"metadata": map[string]any{
			"source":     "avwiki",
			"confidence": 0.95,
		},
		"updated_at": "2026-06-06T00:00:00Z",
	}
	if err := store.UpdateVideoFields("STARS-707", updates); err != nil {
		t.Fatalf("UpdateVideoFields: %v", err)
	}

	got, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	if got.ID != "vid-id" {
		t.Errorf("ID = %q, want vid-id", got.ID)
	}
	if got.Title != "new title" {
		t.Errorf("Title = %q, want new title", got.Title)
	}
	if got.Studio != "NEWSTUDIO" {
		t.Errorf("Studio = %q, want NEWSTUDIO", got.Studio)
	}
	if got.Metadata.Source != "avwiki" || got.Metadata.Confidence != 0.95 {
		t.Errorf("Metadata = %+v, want avwiki/0.95", got.Metadata)
	}
	if got.UpdatedAt != "2026-06-06T00:00:00Z" {
		t.Errorf("UpdatedAt = %q, want explicit value", got.UpdatedAt)
	}
}

// JSON-side BatchUpdate happy path covering applyBatchUpdateRecords +
// appendBatchUpdateJournalEntries with multiple records.
func TestJSONBatchUpdate_MultipleRecordsTracked(t *testing.T) {
	db := loadedJSONDB(t)
	updates := map[string]*Video{
		"BR-1": {Code: "BR-1", Title: "1", Studio: "S"},
		"BR-2": {Code: "BR-2", Title: "2", Studio: "S"},
		"BR-3": {Code: "BR-3", Title: "3", Studio: "S"},
	}
	if err := db.BatchUpdate(updates); err != nil {
		t.Fatalf("BatchUpdate: %v", err)
	}
	for code := range updates {
		if _, err := db.GetVideo(code); err != nil {
			t.Errorf("GetVideo(%s): %v", code, err)
		}
	}
}
