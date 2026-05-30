package jsonfixture

import (
	"testing"

	. "actress-classifier/pkg/database"
)

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
