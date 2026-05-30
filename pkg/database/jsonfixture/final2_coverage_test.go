package jsonfixture

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	. "actress-classifier/pkg/database"
)

// --- GetJournalEntryCount / GetJournalSize with a real journal ---------

func TestGetJournalEntryCountAndSize_WithEntries(t *testing.T) {
	db := loadedJSONDB(t)
	for i := 0; i < 3; i++ {
		if err := db.AddVideo(&Video{Code: "JC-" + string(rune('A'+i)), Title: "t"}); err != nil {
			t.Fatalf("AddVideo: %v", err)
		}
	}
	count, err := db.GetJournalEntryCount()
	if err != nil {
		t.Fatalf("GetJournalEntryCount: %v", err)
	}
	if count < 3 {
		t.Errorf("journal entry count = %d, want >= 3", count)
	}
	size, err := db.GetJournalSize()
	if err != nil {
		t.Fatalf("GetJournalSize: %v", err)
	}
	if size <= 0 {
		t.Errorf("journal size = %d, want > 0", size)
	}
}

func TestGetJournalEntryCount_NoJournalIsZero(t *testing.T) {
	db := loadedJSONDB(t)
	count, err := db.GetJournalEntryCount()
	if err != nil {
		t.Fatalf("GetJournalEntryCount: %v", err)
	}
	if count != 0 {
		t.Errorf("count = %d, want 0 (no journal yet)", count)
	}
}

// --- loadJournal: tolerates corrupt + legacy + empty lines -------------

func TestLoadJournal_SkipsCorruptAndEmptyLines(t *testing.T) {
	dir := t.TempDir()
	// Valid data.json + a journal with: empty line, corrupt line, and a
	// valid new-format ADD entry.
	if err := os.WriteFile(filepath.Join(dir, DataFileName),
		[]byte(`{"schema_version":"1.0.0","videos":{},"actresses":{}}`), 0o600); err != nil {
		t.Fatal(err)
	}
	journal := "\n" + // empty line
		"{not valid json}\n" + // corrupt → warn+skip
		`{"op":"ADD","type":"video","id":"JL-1","data":{"code":"JL-1","title":"from journal"},"ts":"2026-01-01T00:00:00Z"}` + "\n"
	if err := os.WriteFile(filepath.Join(dir, JournalFileName), []byte(journal), 0o600); err != nil {
		t.Fatal(err)
	}
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load: %v", err)
	}
	// The valid ADD entry should have been replayed.
	if _, err := db.GetVideo("JL-1"); err != nil {
		t.Errorf("journal ADD not replayed: %v", err)
	}
}
