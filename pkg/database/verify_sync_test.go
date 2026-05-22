package database

import (
	"testing"
)

// verifySetup runs a fresh migrate-from-json against a stored copy of
// minimalRoot, returning the store and the path to the source JSON the
// caller can subsequently mutate for diff scenarios.
func verifySetup(t *testing.T) (*SQLiteStore, string, *DatabaseData) {
	t.Helper()
	store := migrateTestStore(t)
	root := minimalRoot()
	src := writeJSONDB(t, root)
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("setup migrate: %v", err)
	}
	return store, src, root
}

func TestVerifySync_ConsistentAfterMigration(t *testing.T) {
	store, src, _ := verifySetup(t)

	report, err := store.VerifySync(src)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	if !report.Consistent {
		t.Errorf("Consistent = false, diffs = %+v", report.Diffs)
	}
	if report.VideoCount != 3 {
		t.Errorf("VideoCount = %d, want 3", report.VideoCount)
	}
	if report.ActressCount != 3 {
		t.Errorf("ActressCount = %d, want 3", report.ActressCount)
	}
	if report.LinkCount != 4 {
		t.Errorf("LinkCount = %d, want 4", report.LinkCount)
	}
}

func TestVerifySync_DetectsMissingVideoInSQLite(t *testing.T) {
	store, src, _ := verifySetup(t)

	// Drop one video from SQLite, then verify against the original JSON.
	if _, err := store.db.Exec(
		`DELETE FROM video_actress_links WHERE video_code='STARS-707'`,
	); err != nil {
		t.Fatalf("delete links: %v", err)
	}
	if _, err := store.db.Exec(`DELETE FROM videos WHERE code='STARS-707'`); err != nil {
		t.Fatalf("delete video: %v", err)
	}

	report, err := store.VerifySync(src)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	if report.Consistent {
		t.Errorf("Consistent = true, want false")
	}
	gotMissing := false
	for _, d := range report.Diffs {
		if d.Kind == "video" && d.Key == "STARS-707" && d.Reason == "missing_in_sqlite" {
			gotMissing = true
			break
		}
	}
	if !gotMissing {
		t.Errorf("expected video STARS-707 missing_in_sqlite diff, got %+v", report.Diffs)
	}
}

func TestVerifySync_DetectsFieldDifference(t *testing.T) {
	store, src, _ := verifySetup(t)

	// Mutate SQLite-side title for STARS-707.
	if _, err := store.db.Exec(
		`UPDATE videos SET title='mutated' WHERE code='STARS-707'`,
	); err != nil {
		t.Fatalf("mutate title: %v", err)
	}

	report, err := store.VerifySync(src)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	if report.Consistent {
		t.Errorf("Consistent = true after mutation")
	}
	var titleDiff *VerifyDiff
	for i := range report.Diffs {
		d := &report.Diffs[i]
		if d.Kind == "video" && d.Key == "STARS-707" && d.Field == "title" {
			titleDiff = d
			break
		}
	}
	if titleDiff == nil {
		t.Fatalf("expected title field_diff, diffs = %+v", report.Diffs)
	}
	if titleDiff.JSONValue != "A" || titleDiff.SQLiteValue != "mutated" {
		t.Errorf("title diff = %+v", *titleDiff)
	}
}

func TestVerifySync_IgnoresDataHash(t *testing.T) {
	store, src, root := verifySetup(t)

	// Set a wildly different data_hash on the JSON side; SQLite never
	// persists it, so verify must NOT raise a diff for data_hash.
	root.DataHash = "should-not-cause-diff"
	src2 := writeJSONDB(t, root)
	_ = src // keep original path alive

	report, err := store.VerifySync(src2)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	for _, d := range report.Diffs {
		if d.Kind == "db_meta" && d.Key == "data_hash" {
			t.Errorf("data_hash diff present: %+v", d)
		}
	}
}

func TestVerifySync_IgnoresUpdatedAtSubSecondDrift(t *testing.T) {
	store, src, _ := verifySetup(t)

	// Force SQLite to a tiny-difference timestamp that should still be
	// considered equal under the spec § 4.2 second tolerance rule.
	if _, err := store.db.Exec(
		`UPDATE videos SET updated_at='2026-05-22T12:00:00.500Z' WHERE code='STARS-707'`,
	); err != nil {
		t.Fatalf("mutate updated_at: %v", err)
	}
	report, err := store.VerifySync(src)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	for _, d := range report.Diffs {
		if d.Kind == "video" && d.Key == "STARS-707" && d.Field == "updated_at" {
			t.Errorf("sub-second drift triggered diff: %+v", d)
		}
	}
}

func TestVerifySync_DetectsTimestampDriftBeyondSecond(t *testing.T) {
	store, src, _ := verifySetup(t)
	if _, err := store.db.Exec(
		`UPDATE videos SET updated_at='2026-05-22T12:00:05Z' WHERE code='STARS-707'`,
	); err != nil {
		t.Fatalf("mutate updated_at: %v", err)
	}
	report, err := store.VerifySync(src)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	found := false
	for _, d := range report.Diffs {
		if d.Kind == "video" && d.Key == "STARS-707" && d.Field == "updated_at" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected updated_at diff (5s drift), diffs = %+v", report.Diffs)
	}
}

func TestVerifySync_DetectsExtraVideoInSQLite(t *testing.T) {
	store, src, _ := verifySetup(t)

	if _, err := store.db.Exec(
		`INSERT INTO videos(code, title) VALUES('EXTRA-001', 'extra')`,
	); err != nil {
		t.Fatalf("insert extra: %v", err)
	}
	report, err := store.VerifySync(src)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	found := false
	for _, d := range report.Diffs {
		if d.Kind == "video" && d.Key == "EXTRA-001" && d.Reason == "missing_in_json" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected EXTRA-001 missing_in_json diff, got %+v", report.Diffs)
	}
}

func TestVerifySync_DetectsLinkRoleDifference(t *testing.T) {
	store, src, _ := verifySetup(t)

	if _, err := store.db.Exec(
		`UPDATE video_actress_links SET role_type='客串'
		   WHERE video_code='STARS-707' AND actress_id='tanaka-minami'`,
	); err != nil {
		t.Fatalf("mutate role_type: %v", err)
	}
	report, err := store.VerifySync(src)
	if err != nil {
		t.Fatalf("VerifySync: %v", err)
	}
	found := false
	for _, d := range report.Diffs {
		if d.Kind == "link" && d.Key == "STARS-707|tanaka-minami" && d.Field == "role_type" {
			found = true
		}
	}
	if !found {
		t.Errorf("expected link role_type diff, got %+v", report.Diffs)
	}
}

func TestVerifySync_RejectsFileNotFound(t *testing.T) {
	store := migrateTestStore(t)
	_, err := store.VerifySync("/no/such/file.json")
	if err == nil {
		t.Error("VerifySync(/no/such/file) returned nil error")
	}
}
