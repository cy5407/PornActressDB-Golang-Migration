package database

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// seededBackupSource returns an initialised SQLiteStore with two videos
// and one actress so backup files have non-trivial content to verify.
// The caller does not have to close it; t.Cleanup is wired by
// newSQLiteStoreForTest.
func seededBackupSource(t *testing.T, name string) *SQLiteStore {
	t.Helper()
	store := newSQLiteStoreForTest(t, name)
	if err := store.InitSchema(); err != nil {
		t.Fatalf("InitSchema: %v", err)
	}
	if err := store.UpsertActress(&ActressData{
		ID:        "actress-1",
		Name:      "測試女優",
		Aliases:   []string{},
		CreatedAt: "2026-05-23T00:00:00Z",
		UpdatedAt: "2026-05-23T00:00:00Z",
	}); err != nil {
		t.Fatalf("UpsertActress: %v", err)
	}
	for _, code := range []string{"STARS-707", "MIDV-567"} {
		v := NewVideo(code)
		v.Title = code
		v.Actresses = []string{"測試女優"}
		if err := store.UpsertVideo(code, v); err != nil {
			t.Fatalf("UpsertVideo %q: %v", code, err)
		}
	}
	return store
}

func TestBackup_AutoStrategy_UsesVacuumIntoOnHappyPath(t *testing.T) {
	src := seededBackupSource(t, "src-auto.sqlite")
	dst := filepath.Join(t.TempDir(), "backup-auto.sqlite")

	res, err := src.Backup(BackupOptions{DestPath: dst})
	if err != nil {
		t.Fatalf("Backup: %v", err)
	}
	if res.Strategy != BackupStrategyVacuumInto {
		t.Errorf("strategy = %s, want vacuum_into", res.Strategy)
	}
	if res.DestPath != dst {
		t.Errorf("dest = %q, want %q", res.DestPath, dst)
	}
	if res.Bytes <= 0 {
		t.Errorf("bytes = %d, want > 0", res.Bytes)
	}
	if _, err := os.Stat(dst); err != nil {
		t.Fatalf("backup file not produced: %v", err)
	}

	// Reopen the backup and confirm both videos round-trip.
	restored, err := OpenSQLiteStore(dst)
	if err != nil {
		t.Fatalf("OpenSQLiteStore(backup): %v", err)
	}
	defer restored.Close()
	v, err := restored.SchemaVersion()
	if err != nil {
		t.Fatalf("SchemaVersion(backup): %v", err)
	}
	if v != SQLiteSchemaVersion {
		t.Errorf("backup user_version = %d, want %d", v, SQLiteSchemaVersion)
	}
	codes, err := restored.ListVideos()
	if err != nil {
		t.Fatalf("ListVideos(backup): %v", err)
	}
	if len(codes) != 2 {
		t.Errorf("backup video count = %d, want 2 (%v)", len(codes), codes)
	}
}

func TestBackup_AutoStrategy_FallsBackToCheckpointCopyWhenVacuumIntoFails(t *testing.T) {
	src := seededBackupSource(t, "src-fallback.sqlite")
	dst := filepath.Join(t.TempDir(), "backup-fallback.sqlite")

	original := vacuumIntoExecutor
	vacuumIntoExecutor = func(_ *SQLiteStore, _ string) error {
		return errors.New("simulated vacuum_into failure")
	}
	t.Cleanup(func() { vacuumIntoExecutor = original })

	res, err := src.Backup(BackupOptions{DestPath: dst})
	if err != nil {
		t.Fatalf("Backup: %v", err)
	}
	if res.Strategy != BackupStrategyCheckpointCopy {
		t.Errorf("strategy = %s, want checkpoint_copy", res.Strategy)
	}
	if _, err := os.Stat(dst); err != nil {
		t.Fatalf("backup file not produced: %v", err)
	}

	restored, err := OpenSQLiteStore(dst)
	if err != nil {
		t.Fatalf("OpenSQLiteStore(backup): %v", err)
	}
	defer restored.Close()
	codes, err := restored.ListVideos()
	if err != nil {
		t.Fatalf("ListVideos(backup): %v", err)
	}
	if len(codes) != 2 {
		t.Errorf("backup video count = %d, want 2", len(codes))
	}
}

func TestBackup_AutoStrategy_ReportsBothErrorsWhenBothStrategiesFail(t *testing.T) {
	src := seededBackupSource(t, "src-both-fail.sqlite")
	dst := filepath.Join(t.TempDir(), "backup-both-fail.sqlite")

	original := vacuumIntoExecutor
	vacuumIntoExecutor = func(_ *SQLiteStore, _ string) error {
		return errors.New("simulated vacuum_into failure")
	}
	t.Cleanup(func() { vacuumIntoExecutor = original })

	// Sabotage the copy fallback by emptying SQLiteStore.path, so
	// checkpointAndCopy hits "source path unknown".
	savedPath := src.path
	src.path = ""
	t.Cleanup(func() { src.path = savedPath })

	if _, err := src.Backup(BackupOptions{DestPath: dst}); err == nil {
		t.Fatalf("Backup should have failed when both strategies error")
	} else if !strings.Contains(err.Error(), "vacuum_into failed") ||
		!strings.Contains(err.Error(), "checkpoint_copy fallback failed") {
		t.Errorf("error %q must reference both strategies", err.Error())
	}
}

func TestBackup_ExplicitVacuumInto(t *testing.T) {
	src := seededBackupSource(t, "src-vi.sqlite")
	dst := filepath.Join(t.TempDir(), "backup-vi.sqlite")

	res, err := src.Backup(BackupOptions{DestPath: dst, Strategy: BackupStrategyVacuumInto})
	if err != nil {
		t.Fatalf("Backup: %v", err)
	}
	if res.Strategy != BackupStrategyVacuumInto {
		t.Errorf("strategy = %s, want vacuum_into", res.Strategy)
	}
}

func TestBackup_ExplicitCheckpointCopy(t *testing.T) {
	src := seededBackupSource(t, "src-cc.sqlite")
	dst := filepath.Join(t.TempDir(), "backup-cc.sqlite")

	res, err := src.Backup(BackupOptions{DestPath: dst, Strategy: BackupStrategyCheckpointCopy})
	if err != nil {
		t.Fatalf("Backup: %v", err)
	}
	if res.Strategy != BackupStrategyCheckpointCopy {
		t.Errorf("strategy = %s, want checkpoint_copy", res.Strategy)
	}
	if _, err := os.Stat(dst); err != nil {
		t.Fatalf("backup file not produced: %v", err)
	}
}

func TestBackup_RemovesPreExistingDestination(t *testing.T) {
	src := seededBackupSource(t, "src-overwrite.sqlite")
	dst := filepath.Join(t.TempDir(), "backup-overwrite.sqlite")
	if err := os.WriteFile(dst, []byte("not a sqlite file"), 0o600); err != nil {
		t.Fatalf("seed pre-existing dest: %v", err)
	}

	res, err := src.Backup(BackupOptions{DestPath: dst})
	if err != nil {
		t.Fatalf("Backup with pre-existing dest: %v", err)
	}
	if res.Strategy != BackupStrategyVacuumInto {
		t.Errorf("strategy = %s, want vacuum_into", res.Strategy)
	}
	// The output must be a real SQLite file, not the seeded junk.
	restored, err := OpenSQLiteStore(dst)
	if err != nil {
		t.Fatalf("OpenSQLiteStore(backup): %v", err)
	}
	defer restored.Close()
	if _, err := restored.SchemaVersion(); err != nil {
		t.Fatalf("backup not valid SQLite: %v", err)
	}
}

func TestBackup_RejectsEmptyDestPath(t *testing.T) {
	src := seededBackupSource(t, "src-empty-dst.sqlite")
	if _, err := src.Backup(BackupOptions{DestPath: "   "}); err == nil {
		t.Fatal("Backup with empty DestPath should fail")
	}
}

func TestRestoreSQLiteFile_RoundTrips(t *testing.T) {
	src := seededBackupSource(t, "src-restore.sqlite")
	backupPath := filepath.Join(t.TempDir(), "backup-restore.sqlite")
	if _, err := src.Backup(BackupOptions{DestPath: backupPath}); err != nil {
		t.Fatalf("Backup: %v", err)
	}

	// Mutate the source after the backup so we can detect the restore.
	if err := src.DeleteVideo("STARS-707"); err != nil {
		t.Fatalf("DeleteVideo: %v", err)
	}
	codes, err := src.ListVideos()
	if err != nil {
		t.Fatalf("ListVideos before restore: %v", err)
	}
	if len(codes) != 1 {
		t.Fatalf("expected 1 video after mutation, got %d (%v)", len(codes), codes)
	}

	// Close the source so the file lock releases (Windows requires this).
	targetPath := src.path
	if err := src.Close(); err != nil {
		t.Fatalf("Close source: %v", err)
	}

	if err := RestoreSQLiteFile(targetPath, backupPath); err != nil {
		t.Fatalf("RestoreSQLiteFile: %v", err)
	}

	restored, err := OpenSQLiteStore(targetPath)
	if err != nil {
		t.Fatalf("OpenSQLiteStore(post-restore): %v", err)
	}
	defer restored.Close()
	codes, err = restored.ListVideos()
	if err != nil {
		t.Fatalf("ListVideos(post-restore): %v", err)
	}
	if len(codes) != 2 {
		t.Errorf("post-restore video count = %d, want 2 (%v)", len(codes), codes)
	}
}

func TestRestoreSQLiteFile_RejectsInvalidBackup(t *testing.T) {
	dir := t.TempDir()
	bogus := filepath.Join(dir, "not-sqlite.bin")
	if err := os.WriteFile(bogus, []byte("not a sqlite file"), 0o600); err != nil {
		t.Fatalf("seed bogus backup: %v", err)
	}
	target := filepath.Join(dir, "target.sqlite")

	err := RestoreSQLiteFile(target, bogus)
	if err == nil {
		t.Fatal("RestoreSQLiteFile should reject a non-SQLite backup")
	}
}

func TestRestoreSQLiteFile_RejectsMissingBackup(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "target.sqlite")
	missing := filepath.Join(dir, "does-not-exist.sqlite")

	if err := RestoreSQLiteFile(target, missing); err == nil {
		t.Fatal("RestoreSQLiteFile should reject a missing backup")
	}
}

func TestRestoreSQLiteFile_RemovesWALSidecars(t *testing.T) {
	src := seededBackupSource(t, "src-wal-restore.sqlite")
	backupPath := filepath.Join(t.TempDir(), "backup-wal.sqlite")
	if _, err := src.Backup(BackupOptions{DestPath: backupPath}); err != nil {
		t.Fatalf("Backup: %v", err)
	}
	targetPath := src.path
	if err := src.Close(); err != nil {
		t.Fatalf("Close: %v", err)
	}

	// Plant fake WAL/SHM sidecars on the target — restore must clean them
	// so the next open does not honour their state.
	if err := os.WriteFile(targetPath+"-wal", []byte{0}, 0o600); err != nil {
		t.Fatalf("seed wal: %v", err)
	}
	if err := os.WriteFile(targetPath+"-shm", []byte{0}, 0o600); err != nil {
		t.Fatalf("seed shm: %v", err)
	}

	if err := RestoreSQLiteFile(targetPath, backupPath); err != nil {
		t.Fatalf("RestoreSQLiteFile: %v", err)
	}

	if _, err := os.Stat(targetPath + "-wal"); !os.IsNotExist(err) {
		t.Errorf("wal sidecar should be removed, stat err = %v", err)
	}
	if _, err := os.Stat(targetPath + "-shm"); !os.IsNotExist(err) {
		t.Errorf("shm sidecar should be removed, stat err = %v", err)
	}
}

// TestRestoreSQLiteFile_RollsBackOriginalOnCopyFailure forces the copy
// step to fail after the original target file has been moved aside, and
// verifies that RestoreSQLiteFile renames the staged old file back into
// place so the caller is never left without a database. This regression-
// guards the prior implementation, which used `os.Remove(targetPath)`
// before copying: a copy failure there would have lost the live DB.
func TestRestoreSQLiteFile_RollsBackOriginalOnCopyFailure(t *testing.T) {
	// 1. Seed a live target with content we can verify after rollback.
	live := seededBackupSource(t, "live-pre-restore.sqlite")
	targetPath := live.path
	if err := live.Close(); err != nil {
		t.Fatalf("Close live source: %v", err)
	}

	// 2. Build a valid SQLite backup so the probe step passes — the
	//    rollback must trigger on a *copy* failure, not a validation
	//    failure.
	srcStore := seededBackupSource(t, "good-src.sqlite")
	backupPath := filepath.Join(t.TempDir(), "good-backup.sqlite")
	if _, err := srcStore.Backup(BackupOptions{DestPath: backupPath}); err != nil {
		t.Fatalf("Backup source: %v", err)
	}
	if err := srcStore.Close(); err != nil {
		t.Fatalf("Close srcStore: %v", err)
	}

	// 3. Inject a copy failure. The hook must observe that targetPath
	//    has already been moved aside (so the production code is
	//    rollback-driven, not "remove then copy").
	original := restoreCopyFile
	var sawTargetMoved bool
	restoreCopyFile = func(src, dst string) error {
		if dst == targetPath {
			if _, err := os.Stat(targetPath); os.IsNotExist(err) {
				sawTargetMoved = true
			}
		}
		return errors.New("simulated copy failure mid-restore")
	}
	t.Cleanup(func() { restoreCopyFile = original })

	err := RestoreSQLiteFile(targetPath, backupPath)
	if err == nil {
		t.Fatal("RestoreSQLiteFile should propagate the injected copy failure")
	}
	if !strings.Contains(err.Error(), "simulated copy failure") {
		t.Errorf("error %q must surface the original copy failure", err.Error())
	}
	if !sawTargetMoved {
		t.Fatalf("rollback path expected: hook saw target still in place — production code " +
			"must rename target aside *before* copy, not remove it")
	}

	// 4. The original target must be back in place AND still openable
	//    with the original two videos.
	if _, statErr := os.Stat(targetPath); statErr != nil {
		t.Fatalf("target file lost after rollback: %v", statErr)
	}
	restored, err := OpenSQLiteStore(targetPath)
	if err != nil {
		t.Fatalf("OpenSQLiteStore(post-rollback): %v", err)
	}
	defer restored.Close()
	codes, err := restored.ListVideos()
	if err != nil {
		t.Fatalf("ListVideos(post-rollback): %v", err)
	}
	if len(codes) != 2 {
		t.Errorf("post-rollback video count = %d, want 2 (%v)", len(codes), codes)
	}

	// 5. No staged ".pre_restore_*" file should be left lying around in
	//    the target's directory either — rollback should rename it back,
	//    not leave the artefact for the operator to clean up.
	entries, err := os.ReadDir(filepath.Dir(targetPath))
	if err != nil {
		t.Fatalf("ReadDir(target dir): %v", err)
	}
	for _, e := range entries {
		if strings.Contains(e.Name(), ".pre_restore_") {
			t.Errorf("rollback should not leave staged artefact %q", e.Name())
		}
	}
}

func TestBackupStrategy_String(t *testing.T) {
	cases := map[BackupStrategy]string{
		BackupStrategyAuto:           "auto",
		BackupStrategyVacuumInto:     "vacuum_into",
		BackupStrategyCheckpointCopy: "checkpoint_copy",
		BackupStrategy(99):           "unknown",
	}
	for s, want := range cases {
		if got := s.String(); got != want {
			t.Errorf("(%d).String() = %q, want %q", s, got, want)
		}
	}
}
