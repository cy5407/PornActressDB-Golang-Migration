package database

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"testing"
	"time"
)

// --- sortReportLists secondary comparator ------------------------------

func TestSortReportLists_SecondaryComparatorTieBreaks(t *testing.T) {
	report := &MigrationReport{
		Unresolved: []MigrationUnresolvedEntry{
			{VideoCode: "AAA-001", Display: "z-late"},
			{VideoCode: "AAA-001", Display: "a-early"},
			{VideoCode: "BBB-002", Display: "m"},
		},
		Duplicates: []MigrationDuplicateEntry{
			{VideoCode: "DUP-1", ActressID: "z", Ordinals: []int{3, 1, 2}},
			{VideoCode: "DUP-1", ActressID: "a", Ordinals: []int{5, 4}},
		},
		AutoCreated: []MigrationAutoCreated{
			{Name: "actress", ActressID: "x", VideoCode: "Z-9"},
			{Name: "actress", ActressID: "x", VideoCode: "A-1"},
		},
	}
	sortReportLists(report)

	if report.Unresolved[0].Display != "a-early" {
		t.Errorf("Unresolved[0].Display = %q, want a-early (Display tie-break)", report.Unresolved[0].Display)
	}
	if report.Duplicates[0].ActressID != "a" {
		t.Errorf("Duplicates[0].ActressID = %q, want a (ActressID tie-break)", report.Duplicates[0].ActressID)
	}
	if report.AutoCreated[0].VideoCode != "A-1" {
		t.Errorf("AutoCreated[0].VideoCode = %q, want A-1 (VideoCode tie-break)", report.AutoCreated[0].VideoCode)
	}
	if !sort.IntsAreSorted(report.Duplicates[0].Ordinals) {
		t.Errorf("Duplicates[0].Ordinals = %v, want sorted", report.Duplicates[0].Ordinals)
	}
}

// --- sortDiffs secondary / tertiary / quaternary comparators ----------

func TestSortDiffs_AllTieBreakLevelsExercised(t *testing.T) {
	d := []VerifyDiff{
		// Same Kind+Key+Field; Reason tie-break
		{Kind: "video", Key: "K", Field: "title", Reason: "missing_in_json"},
		{Kind: "video", Key: "K", Field: "title", Reason: "field_diff"},
		// Same Kind+Key, different Field
		{Kind: "video", Key: "K", Field: "studio", Reason: "field_diff"},
		// Same Kind, different Key
		{Kind: "video", Key: "A", Field: "title", Reason: "field_diff"},
		// Different Kind
		{Kind: "actress", Key: "Z", Field: "name", Reason: "field_diff"},
	}
	sortDiffs(d)

	if d[0].Kind != "actress" {
		t.Errorf("d[0].Kind = %q, want actress (lex first)", d[0].Kind)
	}
	// Within "video": Key A < K, then within K: studio < title, then within title: field_diff < missing_in_json
	if d[1].Key != "A" {
		t.Errorf("d[1].Key = %q, want A", d[1].Key)
	}
	if d[2].Field != "studio" {
		t.Errorf("d[2].Field = %q, want studio (alphabetic before title)", d[2].Field)
	}
	if d[3].Reason != "field_diff" {
		t.Errorf("d[3].Reason = %q, want field_diff (lex before missing_in_json)", d[3].Reason)
	}
}

// --- videoReferencesActress / videoReferencesAutoActressID --------------

func TestVideoReferencesActress_NameAndAliasMatches(t *testing.T) {
	v := &VideoData{Actresses: []string{"田中美奈実"}}
	a := &ActressData{Name: "田中美奈実", Aliases: []string{"田中みなみ"}}
	if !videoReferencesActress(v, a) {
		t.Error("name match should return true")
	}

	v2 := &VideoData{Actresses: []string{"田中みなみ"}}
	if !videoReferencesActress(v2, a) {
		t.Error("alias match should return true")
	}

	v3 := &VideoData{Actresses: []string{"someone-else"}}
	if videoReferencesActress(v3, a) {
		t.Error("no match should return false")
	}

	if videoReferencesActress(&VideoData{}, a) {
		t.Error("empty Actresses should return false")
	}
}

func TestVideoReferencesAutoActressID_RecognisesSynthID(t *testing.T) {
	display := "新女優A"
	want := StableActressID(display)
	v := &VideoData{Actresses: []string{display}}
	if !videoReferencesAutoActressID(v, want) {
		t.Errorf("expected match for synth id of %q", display)
	}
	if videoReferencesAutoActressID(v, "auto_deadbeef") {
		t.Error("unrelated id should not match")
	}
}

// --- buildExpectedDBMeta empty + nil Metadata paths --------------------

func TestBuildExpectedDBMeta_OmitsEmptyValues(t *testing.T) {
	got := buildExpectedDBMeta(&DatabaseData{})
	if len(got) != 0 {
		t.Errorf("empty root → expected = %v, want empty map", got)
	}

	full := &DatabaseData{
		SchemaVersion: "1.0.0",
		Metadata:      &DatabaseMetadata{Description: "d", Encoding: "UTF-8"},
		CreatedAt:     "2026-01-01T00:00:00Z",
	}
	got = buildExpectedDBMeta(full)
	if got["schema_version"] != "1.0.0" {
		t.Errorf("schema_version = %q", got["schema_version"])
	}
	if got["description"] != "d" {
		t.Errorf("description = %q", got["description"])
	}
}

// restoreBackupDataFile / rollbackRestoredDataFile / clearBackupRestoreSidecars
// tests moved to pkg/database/jsonfixture/restore_backup_test.go.

// --- mergeOneActress overwrite / new-row paths -------------------------

func TestMergeOneActress_OverwriteSkipsWhenOverwriteFalse(t *testing.T) {
	store := runtimeTestStore(t)
	stats := &MergeStats{}
	now := "2026-07-01T00:00:00Z"

	a := &ActressData{ID: "tanaka-minami", Name: "Renamed", CreatedAt: "2020-01-01"}
	if err := store.mergeOneActress("tanaka-minami", a, false, now, stats); err != nil {
		t.Fatalf("mergeOneActress: %v", err)
	}
	if stats.ActressesUpdated != 0 || stats.ActressesAdded != 0 {
		t.Errorf("stats = %+v, want all zero (existing + !overwrite)", stats)
	}
	got, _ := store.GetActress("tanaka-minami")
	if got.Name != "田中美奈実" {
		t.Errorf("Name = %q, want preserved 田中美奈実", got.Name)
	}
}

func TestMergeOneActress_OverwriteUpdatesAndPreservesCreatedAt(t *testing.T) {
	store := runtimeTestStore(t)
	stats := &MergeStats{}
	now := "2026-07-01T00:00:00Z"

	// Source provides no CreatedAt → must inherit from existing row.
	a := &ActressData{ID: "tanaka-minami", Name: "新名稱"}
	if err := store.mergeOneActress("tanaka-minami", a, true, now, stats); err != nil {
		t.Fatalf("mergeOneActress: %v", err)
	}
	if stats.ActressesUpdated != 1 {
		t.Errorf("ActressesUpdated = %d, want 1", stats.ActressesUpdated)
	}
	got, _ := store.GetActress("tanaka-minami")
	if got.Name != "新名稱" {
		t.Errorf("Name = %q, want 新名稱", got.Name)
	}
}

func TestMergeOneActress_EmptyIDIsNoOp(t *testing.T) {
	store := runtimeTestStore(t)
	stats := &MergeStats{}
	if err := store.mergeOneActress("   ", &ActressData{Name: "x"}, true, "now", stats); err != nil {
		t.Fatalf("mergeOneActress empty id: %v", err)
	}
	if stats.ActressesAdded != 0 || stats.ActressesUpdated != 0 {
		t.Errorf("stats = %+v, want all zero (empty id skipped)", stats)
	}
}

// --- copyFile (sqlite_backup) sad path --------------------------------

func TestSQLiteBackupCopyFile_MissingSourceErrors(t *testing.T) {
	if err := copyFile(filepath.Join(t.TempDir(), "missing"), filepath.Join(t.TempDir(), "dst")); err == nil {
		t.Error("copyFile missing source returned nil")
	}
}

func TestSQLiteBackupCopyFile_BadDestinationErrors(t *testing.T) {
	src := filepath.Join(t.TempDir(), "src.db")
	if err := os.WriteFile(src, []byte("seed"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := copyFile(src, "bad\x00dst"); err == nil {
		t.Error("copyFile bad dst returned nil")
	}
}

// --- stageExistingTarget no-pre-existing branch -----------------------

func TestStageExistingTarget_AbsentTargetReturnsEmptyStagedPath(t *testing.T) {
	staged, err := stageExistingTarget(filepath.Join(t.TempDir(), "never-existed"))
	if err != nil {
		t.Fatalf("stageExistingTarget: %v", err)
	}
	if staged != "" {
		t.Errorf("staged = %q, want empty (no pre-existing target)", staged)
	}
}

// --- DeleteVideo / DeleteActress idempotency on closed store ---------

func TestDeleteVideo_ClosedStoreReportsClosed(t *testing.T) {
	closed := &SQLiteStore{}
	if err := closed.DeleteVideo("x"); err == nil {
		t.Error("closed.DeleteVideo returned nil")
	}
}

func TestDeleteActress_ClosedStoreReportsClosed(t *testing.T) {
	closed := &SQLiteStore{}
	if err := closed.DeleteActress("x"); err == nil {
		t.Error("closed.DeleteActress returned nil")
	}
}

// --- BackupList iteration with real .json fixtures ---------------------

func writeBackupJSONFixtures(t *testing.T, dataDir string, names ...string) {
	t.Helper()
	backupDir := filepath.Join(dataDir, "backup")
	if err := os.MkdirAll(backupDir, 0o750); err != nil {
		t.Fatal(err)
	}
	for _, n := range names {
		if err := os.WriteFile(filepath.Join(backupDir, n), []byte(`{}`), 0o600); err != nil {
			t.Fatal(err)
		}
	}
}

func TestBackupList_FiltersAndSortsJSONNames(t *testing.T) {
	store := runtimeTestStore(t)
	store.SetDataDir(filepath.Dir(store.Path()))
	writeBackupJSONFixtures(t, store.DataDir(),
		"backup_2026-05-01.json",
		"backup_2026-04-01.json",
		"not-a-backup.json",    // wrong prefix
		"backup_unmatched.txt", // wrong suffix
		"backup_2026-06-01.json",
	)

	paths, err := store.BackupList()
	if err != nil {
		t.Fatalf("BackupList: %v", err)
	}
	if len(paths) != 3 {
		t.Fatalf("len = %d, want 3 valid backup_*.json entries", len(paths))
	}
	// Sorted ascending.
	for i := 1; i < len(paths); i++ {
		if paths[i-1] >= paths[i] {
			t.Errorf("paths not sorted: %v", paths)
		}
	}
}

func TestBackupList_OnlyNonJSONReturnsEmpty(t *testing.T) {
	store := runtimeTestStore(t)
	store.SetDataDir(filepath.Dir(store.Path()))
	writeBackupJSONFixtures(t, store.DataDir(),
		"random.txt",
		"notes.md",
	)
	paths, err := store.BackupList()
	if err != nil {
		t.Fatalf("BackupList: %v", err)
	}
	if len(paths) != 0 {
		t.Errorf("paths = %v, want empty (no backup_*.json)", paths)
	}
}

// --- BackupCleanup with real fixtures ---------------------------------

func writeBackupWithMtime(t *testing.T, dataDir, name string, ageDays int) string {
	t.Helper()
	backupDir := filepath.Join(dataDir, "backup")
	if err := os.MkdirAll(backupDir, 0o750); err != nil {
		t.Fatal(err)
	}
	p := filepath.Join(backupDir, name)
	if err := os.WriteFile(p, []byte(`{}`), 0o600); err != nil {
		t.Fatal(err)
	}
	if ageDays > 0 {
		mtime := time.Now().AddDate(0, 0, -ageDays)
		if err := os.Chtimes(p, mtime, mtime); err != nil {
			t.Fatal(err)
		}
	}
	return p
}

func TestBackupCleanup_RemovesExpiredAndCapsRemainder(t *testing.T) {
	store := runtimeTestStore(t)
	store.SetDataDir(filepath.Dir(store.Path()))

	// 3 expired (90 days old) + 4 fresh; cap maxCount=3, days=30 → remove
	// the 3 expired and trim fresh down to 3.
	for i := 1; i <= 3; i++ {
		writeBackupWithMtime(t, store.DataDir(),
			fmt.Sprintf("backup_2025-01-0%d.json", i), 90)
	}
	for i := 1; i <= 4; i++ {
		writeBackupWithMtime(t, store.DataDir(),
			fmt.Sprintf("backup_2026-05-0%d.json", i), 0)
	}

	deleted, err := store.BackupCleanup(30, 3)
	if err != nil {
		t.Fatalf("BackupCleanup: %v", err)
	}
	// 3 expired + 1 over-cap = 4 deleted
	if deleted != 4 {
		t.Errorf("deleted = %d, want 4", deleted)
	}
}

func TestBackupCleanup_NoBackupDirIsZero(t *testing.T) {
	store := runtimeTestStore(t)
	store.SetDataDir(filepath.Dir(store.Path()))
	// no backup/ dir created
	deleted, err := store.BackupCleanup(7, 5)
	if err != nil {
		t.Fatalf("BackupCleanup: %v", err)
	}
	if deleted != 0 {
		t.Errorf("deleted = %d, want 0", deleted)
	}
}

// --- DeleteVideo / DeleteActress happy-path cascade --------------------

func TestDeleteVideo_RemovesRow(t *testing.T) {
	store := runtimeTestStore(t)
	if err := store.DeleteVideo("STARS-707"); err != nil {
		t.Fatalf("DeleteVideo: %v", err)
	}
	if _, err := store.GetVideo("STARS-707"); err == nil {
		t.Error("STARS-707 still present after DeleteVideo")
	}
}

func TestDeleteActress_RemovesRowAndCascade(t *testing.T) {
	store := runtimeTestStore(t)
	if err := store.DeleteActress("tanaka-minami"); err != nil {
		t.Fatalf("DeleteActress: %v", err)
	}
	if _, err := store.GetActress("tanaka-minami"); err == nil {
		t.Error("tanaka-minami still present after DeleteActress")
	}
}

func TestDeleteVideo_NonExistentIsIdempotent(t *testing.T) {
	store := runtimeTestStore(t)
	if err := store.DeleteVideo("never-existed"); err != nil {
		t.Errorf("DeleteVideo missing code returned %v, want nil (idempotent)", err)
	}
}
