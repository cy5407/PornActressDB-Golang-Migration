package database

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

// --- ActressCleaner.ApplyToDatabase error branches ---------------------

func TestApplyToDatabase_NilDBErrors(t *testing.T) {
	c := NewActressCleaner()
	if _, err := c.ApplyToDatabase(nil, false); err == nil {
		t.Error("ApplyToDatabase(nil) returned nil error")
	}
}

func TestApplyToDatabase_GetAllVideosErrorPropagates(t *testing.T) {
	store := exportTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "videos")
	c := NewActressCleaner()
	if _, err := c.ApplyToDatabase(store, false); err == nil {
		t.Error("ApplyToDatabase with broken GetAllVideos returned nil error")
	}
}

func TestApplyToDatabase_WriteUpdateErrorPropagates(t *testing.T) {
	// Seed a store with a video whose actresses[] contains a blocked name
	// so CleanActresses produces a change, then break the write path.
	store := migrateTestStore(t)
	src := writeJSONDB(t, &DatabaseData{
		SchemaVersion: SchemaVersion,
		Videos: map[string]*VideoData{
			"CLEAN-1": {Code: "CLEAN-1", Title: "t", Studio: "S",
				Actresses: []string{"正常名字", "デビュー"}, UpdatedAt: "2026-01-01T00:00:00Z"},
		},
		Actresses: map[string]*ActressData{
			"n1": {ID: "n1", Name: "正常名字"},
		},
		Links: []VideoActressLink{
			{VideoCode: "CLEAN-1", ActressID: "n1", RoleType: "主演"},
		},
	}, )
	if _, err := store.MigrateFromJSON(src, MigrationOptions{AutoCreateMissingActresses: true}); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	// Break the write path: drop links so UpdateVideo's rebuild fails.
	dropTable(t, store, "video_actress_links")
	c := NewActressCleaner()
	if _, err := c.ApplyToDatabase(store, true); err == nil {
		t.Error("ApplyToDatabase write with broken UpdateVideo returned nil error")
	}
}

// --- appendIfClean / appendReplacementIfClean remaining branches -------

func TestCleanActresses_ReplacementBlockedNameDropped(t *testing.T) {
	c := NewActressCleaner()
	// "石川澪とラブラブでハメまくる" → replaces with "石川澪". Then feed a
	// blocked name as a standalone to exercise appendIfClean's
	// shouldRemove branch, plus an empty replacement (skipped).
	cleaned, removed := c.CleanActresses([]string{
		"石川澪とラブラブでハメまくる", // → replacement 石川澪
		"デビュー",               // blocked → removed via shouldRemove
		"   ",                  // blank → skipped
		"石川澪",                // dup of replacement → appendIfClean seen branch
	})
	has := false
	for _, n := range cleaned {
		if n == "石川澪" {
			has = true
		}
		if n == "デビュー" {
			t.Error("blocked デビュー should not survive")
		}
	}
	if !has {
		t.Errorf("cleaned = %v, want to contain 石川澪", cleaned)
	}
	if len(removed) == 0 {
		t.Error("expected removals")
	}
}

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

// --- migrate insert SQL-error tails via dropped tables -----------------

func TestMigrateActresses_SQLErrorWhenActressesTableMissing(t *testing.T) {
	store := migrateTestStore(t)
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "actress_aliases")
	dropTable(t, store, "actresses")
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err == nil {
		t.Error("MigrateFromJSON with missing actresses table returned nil")
	}
}

func TestMigrateActresses_SQLErrorWhenAliasesTableMissing(t *testing.T) {
	store := migrateTestStore(t)
	dropTable(t, store, "actress_aliases")
	src := writeJSONDB(t, minimalRoot())
	// minimalRoot has an actress with an alias → alias insert hits the
	// missing table.
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err == nil {
		t.Error("MigrateFromJSON with missing aliases table returned nil")
	}
}

// --- verifyActresses / verifyDBMeta SQL-error tails --------------------

func TestVerifyActresses_SQLErrorWhenActressesTableMissing(t *testing.T) {
	store := verifyStoreFromMinimal(t)
	src := writeJSONDB(t, minimalRoot())
	dropTable(t, store, "video_actress_links")
	dropTable(t, store, "actress_aliases")
	dropTable(t, store, "actresses")
	if _, err := store.VerifySync(src); err == nil {
		t.Error("VerifySync with missing actresses table returned nil")
	}
}

func TestVerifyDBMeta_SQLErrorWhenTableMissing(t *testing.T) {
	store := verifyStoreFromMinimal(t)
	src := writeJSONDB(t, minimalRoot())
	dropTable(t, store, "db_meta")
	if _, err := store.VerifySync(src); err == nil {
		t.Error("VerifySync with missing db_meta returned nil")
	}
}
