package database

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

// seededJSONDB returns a loaded JSONDatabase with a couple of videos and
// an actress, plus a persisted data.json on disk (Save called).
func seededJSONDB(t *testing.T) *JSONDatabase {
	t.Helper()
	db := loadedJSONDB(t)
	if err := db.AddVideo(&Video{Code: "BK-001", Title: "one", Studio: "S1", Actresses: []string{"明日花"}}); err != nil {
		t.Fatalf("AddVideo: %v", err)
	}
	if err := db.AddVideo(&Video{Code: "BK-002", Title: "two", Studio: "S1"}); err != nil {
		t.Fatalf("AddVideo: %v", err)
	}
	if err := db.UpsertActress(&ActressData{ID: "ak", Name: "明日花"}); err != nil {
		t.Fatalf("UpsertActress: %v", err)
	}
	if err := db.Save(); err != nil {
		t.Fatalf("Save: %v", err)
	}
	return db
}

// --- BackupCreate / BackupList / BackupRestore / BackupCleanup ---------

func TestJSONDatabase_BackupCreateListRestoreRoundTrip(t *testing.T) {
	db := seededJSONDB(t)

	path, err := db.BackupCreate()
	if err != nil {
		t.Fatalf("BackupCreate: %v", err)
	}
	if filepath.Ext(path) != ".json" {
		t.Errorf("backup path = %q, want .json", path)
	}

	list, err := db.BackupList()
	if err != nil {
		t.Fatalf("BackupList: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("BackupList len = %d, want 1", len(list))
	}

	// Mutate then restore → BK-003 should vanish.
	if err := db.AddVideo(&Video{Code: "BK-003", Title: "transient"}); err != nil {
		t.Fatalf("AddVideo: %v", err)
	}
	if err := db.Save(); err != nil {
		t.Fatalf("Save: %v", err)
	}
	if err := db.BackupRestore(path); err != nil {
		t.Fatalf("BackupRestore: %v", err)
	}
	if _, err := db.GetVideo("BK-003"); err == nil {
		t.Error("BK-003 should be gone after restore")
	}
	if _, err := db.GetVideo("BK-001"); err != nil {
		t.Errorf("BK-001 should survive restore: %v", err)
	}
}

func TestJSONDatabase_BackupRestoreMissingFileErrors(t *testing.T) {
	db := seededJSONDB(t)
	if err := db.BackupRestore(filepath.Join(t.TempDir(), "nope.json")); err == nil {
		t.Error("BackupRestore missing file returned nil")
	}
}

func TestJSONDatabase_BackupRestoreInvalidJSONErrors(t *testing.T) {
	db := seededJSONDB(t)
	bad := filepath.Join(t.TempDir(), "bad.json")
	if err := os.WriteFile(bad, []byte("{not json"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := db.BackupRestore(bad); err == nil {
		t.Error("BackupRestore invalid JSON returned nil")
	}
}

func TestJSONDatabase_BackupListEmptyDir(t *testing.T) {
	db := loadedJSONDB(t)
	list, err := db.BackupList()
	if err != nil {
		t.Fatalf("BackupList: %v", err)
	}
	if len(list) != 0 {
		t.Errorf("BackupList = %v, want empty", list)
	}
}

func TestJSONDatabase_BackupCleanupCapsCount(t *testing.T) {
	db := seededJSONDB(t)
	// Create several backups, then cap to 2.
	for i := 0; i < 4; i++ {
		if _, err := db.BackupCreate(); err != nil {
			t.Fatalf("BackupCreate %d: %v", i, err)
		}
	}
	// Use writeBackupWithMtime to add age variety under the JSON data dir.
	writeBackupWithMtime(t, db.dataDir, "backup_2024-01-01_00-00-00.json", 400)

	deleted, err := db.BackupCleanup(30, 2)
	if err != nil {
		t.Fatalf("BackupCleanup: %v", err)
	}
	if deleted == 0 {
		t.Error("expected some backups deleted by age+cap")
	}
}

func TestJSONDatabase_BackupCleanupNoDirIsZero(t *testing.T) {
	db := loadedJSONDB(t)
	deleted, err := db.BackupCleanup(7, 5)
	if err != nil {
		t.Fatalf("BackupCleanup: %v", err)
	}
	if deleted != 0 {
		t.Errorf("deleted = %d, want 0 (no backup dir)", deleted)
	}
}

// --- GetActress / GetVideo error + happy ------------------------------

func TestJSONDatabase_GetActressNotFoundAndEmpty(t *testing.T) {
	db := seededJSONDB(t)
	if _, err := db.GetActress(""); err == nil {
		t.Error("GetActress empty id returned nil error")
	}
	if _, err := db.GetActress("ghost"); err == nil {
		t.Error("GetActress missing id returned nil error")
	}
	a, err := db.GetActress("ak")
	if err != nil {
		t.Fatalf("GetActress: %v", err)
	}
	if a.Name != "明日花" {
		t.Errorf("Name = %q, want 明日花", a.Name)
	}
}

func TestJSONDatabase_NotLoadedReadsError(t *testing.T) {
	db := NewJSONDatabase(t.TempDir()) // never Load'd
	if _, err := db.GetActress("x"); err == nil {
		t.Error("GetActress on unloaded db returned nil")
	}
	if _, err := db.GetStatsStruct(); err == nil {
		t.Error("GetStatsStruct on unloaded db returned nil")
	}
	if _, err := db.ListVideos(); err == nil {
		t.Error("ListVideos on unloaded db returned nil")
	}
	if _, err := db.ListActresses(); err == nil {
		t.Error("ListActresses on unloaded db returned nil")
	}
}

// --- GetStudioStats / GetActressStats / GetStatsStruct -----------------

func TestJSONDatabase_StatsHelpers(t *testing.T) {
	db := seededJSONDB(t)

	studioStats, err := db.GetStudioStats()
	if err != nil {
		t.Fatalf("GetStudioStats: %v", err)
	}
	if len(studioStats) == 0 {
		t.Error("expected at least one studio stat")
	}

	actressStats, err := db.GetActressStats()
	if err != nil {
		t.Fatalf("GetActressStats: %v", err)
	}
	_ = actressStats // exercised the loop

	st, err := db.GetStatsStruct()
	if err != nil {
		t.Fatalf("GetStatsStruct: %v", err)
	}
	if st.TotalVideos != 2 {
		t.Errorf("TotalVideos = %d, want 2", st.TotalVideos)
	}
}

// --- Load: missing data file (fresh), then with persisted data --------

func TestJSONDatabase_LoadReadsPersistedData(t *testing.T) {
	dir := t.TempDir()
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("first Load: %v", err)
	}
	if err := db.AddVideo(&Video{Code: "PERSIST-1", Title: "p"}); err != nil {
		t.Fatalf("AddVideo: %v", err)
	}
	if err := db.Save(); err != nil {
		t.Fatalf("Save: %v", err)
	}

	// Second instance loads the persisted data.json.
	db2 := NewJSONDatabase(dir)
	if err := db2.Load(context.Background()); err != nil {
		t.Fatalf("second Load: %v", err)
	}
	if _, err := db2.GetVideo("PERSIST-1"); err != nil {
		t.Errorf("persisted video not loaded: %v", err)
	}
}

func TestJSONDatabase_LoadCorruptDataFileErrors(t *testing.T) {
	dir := t.TempDir()
	// Pre-write a corrupt data.json so Load's unmarshal fails.
	jsonDir := filepath.Join(dir)
	if err := os.MkdirAll(jsonDir, 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(jsonDir, "data.json"), []byte("{bad"), 0o600); err != nil {
		t.Fatal(err)
	}
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err == nil {
		t.Error("Load on corrupt data.json returned nil error")
	}
}
