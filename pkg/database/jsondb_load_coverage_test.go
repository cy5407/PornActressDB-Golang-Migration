package database

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// --- Load: nil-map initialisation from a minimal data.json -------------

func TestLoad_InitialisesNilMapsFromMinimalJSON(t *testing.T) {
	dir := t.TempDir()
	// Valid JSON that omits videos / actresses / statistics keys → Load
	// must allocate them rather than leave nil.
	if err := os.WriteFile(filepath.Join(dir, DataFileName),
		[]byte(`{"schema_version":"1.0.0"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load: %v", err)
	}
	// ListVideos / ListActresses must work (non-nil maps).
	if _, err := db.ListVideos(); err != nil {
		t.Errorf("ListVideos after minimal load: %v", err)
	}
	if _, err := db.ListActresses(); err != nil {
		t.Errorf("ListActresses after minimal load: %v", err)
	}
}

// --- loadIndex: corrupt index is tolerated -----------------------------

func TestLoad_ToleratesCorruptIndex(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, DataFileName),
		[]byte(`{"schema_version":"1.0.0","videos":{},"actresses":{}}`), 0o600); err != nil {
		t.Fatal(err)
	}
	// Corrupt index → loadIndex swallows the parse error.
	if err := os.WriteFile(filepath.Join(dir, IndexFileName),
		[]byte(`{not valid`), 0o600); err != nil {
		t.Fatal(err)
	}
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load with corrupt index should still succeed: %v", err)
	}
}

// --- loadIndex: populated index restores dirty keys + created_at -------

func TestLoad_RestoresDirtyKeysFromValidIndex(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, DataFileName),
		[]byte(`{"schema_version":"1.0.0","videos":{},"actresses":{}}`), 0o600); err != nil {
		t.Fatal(err)
	}
	idx := DirtyIndex{
		Videos:      []string{"V-1", "V-2"},
		Actresses:   []string{"A-1"},
		Links:       []string{"L-1"},
		JournalSize: 7,
		CreatedAt:   time.Now().UTC().Format(time.RFC3339),
	}
	raw, _ := json.MarshalIndent(idx, "", "  ")
	if err := os.WriteFile(filepath.Join(dir, IndexFileName), raw, 0o600); err != nil {
		t.Fatal(err)
	}
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load: %v", err)
	}
	db.mu.RLock()
	defer db.mu.RUnlock()
	if db.journalSize != 7 {
		t.Errorf("journalSize = %d, want 7 (restored from index)", db.journalSize)
	}
	if !db.dirtyVideos["V-1"] || !db.dirtyVideos["V-2"] {
		t.Error("dirty videos not restored from index")
	}
	if !db.dirtyActresses["A-1"] {
		t.Error("dirty actresses not restored from index")
	}
}

func TestLoad_IndexWithUnparseableCreatedAtFallsBackToNow(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, DataFileName),
		[]byte(`{"schema_version":"1.0.0","videos":{},"actresses":{}}`), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, IndexFileName),
		[]byte(`{"journal_size":0,"created_at":"not-a-timestamp"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load: %v", err)
	}
	db.mu.RLock()
	defer db.mu.RUnlock()
	if db.journalCreatedAt.IsZero() {
		t.Error("journalCreatedAt should fall back to now, got zero")
	}
}

// --- Load: data file exists but is unreadable (directory) --------------

func TestLoad_DataFileIsDirectoryErrors(t *testing.T) {
	dir := t.TempDir()
	// Make data.json a *directory* → os.Stat says exists, ReadFile fails.
	if err := os.MkdirAll(filepath.Join(dir, DataFileName), 0o750); err != nil {
		t.Fatal(err)
	}
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err == nil {
		t.Error("Load with data.json-as-directory returned nil error")
	}
}

// --- saveIndex round trip through CompactJournal-adjacent path ---------

func TestSaveIndex_PersistsDirtyState(t *testing.T) {
	db := loadedJSONDB(t)
	if err := db.AddVideo(&Video{Code: "DIRTY-1", Title: "d"}); err != nil {
		t.Fatalf("AddVideo: %v", err)
	}
	db.mu.Lock()
	err := db.saveIndex()
	db.mu.Unlock()
	if err != nil {
		t.Fatalf("saveIndex: %v", err)
	}
	// The index file should now exist and parse.
	raw, readErr := os.ReadFile(db.indexFile)
	if readErr != nil {
		t.Fatalf("read index: %v", readErr)
	}
	var idx DirtyIndex
	if err := json.Unmarshal(raw, &idx); err != nil {
		t.Fatalf("index not valid JSON: %v", err)
	}
}

func TestSaveIndex_BadIndexPathErrors(t *testing.T) {
	db := loadedJSONDB(t)
	db.mu.Lock()
	db.indexFile = "bad\x00index"
	err := db.saveIndex()
	db.mu.Unlock()
	if err == nil {
		t.Error("saveIndex with null-byte path returned nil error")
	}
}
