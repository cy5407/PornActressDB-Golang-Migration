package database

import (
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
	})
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
		"デビュー", // blocked → removed via shouldRemove
		"   ",  // blank → skipped
		"石川澪",  // dup of replacement → appendIfClean seen branch
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

// GetJournalEntryCount / GetJournalSize / LoadJournal JSON-side tests
// moved to pkg/database/jsonfixture/final2_coverage_test.go.

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
