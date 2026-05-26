package database

import (
	"testing"
)

func TestResyncFromJSON_OnEmptyStoreBehavesLikeMigrate(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())

	report, err := store.ResyncFromJSON(src, MigrationOptions{})
	if err != nil {
		t.Fatalf("ResyncFromJSON: %v", err)
	}
	if !report.Success {
		t.Errorf("Success = false")
	}
	if report.VideosImported != 3 || report.ActressesImported != 3 || report.LinksImported != 4 {
		t.Errorf("counts = videos=%d actresses=%d links=%d, want 3/3/4",
			report.VideosImported, report.ActressesImported, report.LinksImported)
	}
}

func TestResyncFromJSON_ReplacesDriftedRows(t *testing.T) {
	store := migrateTestStore(t)
	original := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(original, MigrationOptions{}); err != nil {
		t.Fatalf("initial migrate: %v", err)
	}

	// Drift the SQLite store: tamper with a row that should be brought
	// back to canonical shape by resync.
	if _, err := store.db.Exec(
		`UPDATE videos SET title='drifted' WHERE code='STARS-707'`,
	); err != nil {
		t.Fatalf("drift videos: %v", err)
	}
	if _, err := store.db.Exec(
		`INSERT INTO videos(code, title) VALUES('GHOST-999', 'should be wiped')`,
	); err != nil {
		t.Fatalf("insert ghost: %v", err)
	}

	report, err := store.ResyncFromJSON(original, MigrationOptions{})
	if err != nil {
		t.Fatalf("ResyncFromJSON: %v", err)
	}
	if !report.Success {
		t.Errorf("Success = false")
	}

	verify, err := store.VerifySync(original)
	if err != nil {
		t.Fatalf("VerifySync post-resync: %v", err)
	}
	if !verify.Consistent {
		t.Errorf("post-resync verify NOT consistent: %+v", verify.Diffs)
	}

	var ghostCount int
	if err := store.db.QueryRow(
		`SELECT COUNT(*) FROM videos WHERE code='GHOST-999'`,
	).Scan(&ghostCount); err != nil {
		t.Fatalf("ghost count: %v", err)
	}
	if ghostCount != 0 {
		t.Errorf("ghost row not wiped: count=%d", ghostCount)
	}
}

func TestResyncFromJSON_RollbacksOnUnresolvedActress(t *testing.T) {
	store := migrateTestStore(t)
	original := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(original, MigrationOptions{}); err != nil {
		t.Fatalf("initial migrate: %v", err)
	}

	bad := minimalRoot()
	bad.Videos["STARS-707"].Actresses = []string{"田中美奈実", "未知女優"}
	badSrc := writeJSONDB(t, bad)

	_, err := store.ResyncFromJSON(badSrc, MigrationOptions{})
	if err == nil {
		t.Fatal("ResyncFromJSON with unresolved should fail")
	}

	// Original three videos must still be present — wipe got rolled back.
	var count int
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM videos`).Scan(&count); err != nil {
		t.Fatalf("count videos: %v", err)
	}
	if count != 3 {
		t.Errorf("videos rows after failed resync = %d, want 3 (wipe must rollback)", count)
	}
}

func TestResyncFromJSON_RejectsMissingSourceFile(t *testing.T) {
	store := migrateTestStore(t)
	_, err := store.ResyncFromJSON("/no/such.json", MigrationOptions{})
	if err == nil {
		t.Error("ResyncFromJSON(/no/such) returned nil error")
	}
}
