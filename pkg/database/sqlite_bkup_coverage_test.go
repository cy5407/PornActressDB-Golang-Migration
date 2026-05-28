package database

import (
	"os"
	"path/filepath"
	"testing"
)

// --- validateRestoreInputs branches -----------------------------------

func TestValidateRestoreInputs_Branches(t *testing.T) {
	if err := validateRestoreInputs("  ", "src"); err == nil {
		t.Error("empty target should error")
	}
	if err := validateRestoreInputs("target", "  "); err == nil {
		t.Error("empty src should error")
	}
	if err := validateRestoreInputs("target", filepath.Join(t.TempDir(), "missing.sqlite")); err == nil {
		t.Error("missing src should error")
	}
	// Happy: existing src file.
	src := filepath.Join(t.TempDir(), "ok.sqlite")
	if err := os.WriteFile(src, []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := validateRestoreInputs("target", src); err != nil {
		t.Errorf("valid inputs returned error: %v", err)
	}
}

// --- probeBackupSource branches ----------------------------------------

func TestProbeBackupSource_NotASQLiteDatabase(t *testing.T) {
	// A text file is openable by the driver lazily, but SchemaVersion
	// (PRAGMA user_version) read fails → schema_version-unreadable branch.
	bad := filepath.Join(t.TempDir(), "notdb.sqlite")
	if err := os.WriteFile(bad, []byte("this is not sqlite"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := probeBackupSource(bad); err == nil {
		t.Error("probeBackupSource on non-sqlite file returned nil")
	}
}

func TestProbeBackupSource_ValidDatabase(t *testing.T) {
	// A real migrated store file probes cleanly.
	store := migrateTestStore(t)
	path := store.Path()
	_ = store.Close()
	if err := probeBackupSource(path); err != nil {
		t.Errorf("probeBackupSource on valid db: %v", err)
	}
}

func TestProbeBackupSource_EmptyPathErrors(t *testing.T) {
	if err := probeBackupSource(""); err == nil {
		t.Error("probeBackupSource empty path returned nil")
	}
}

// --- stageExistingTarget branches --------------------------------------

func TestStageExistingTarget_StatErrorOnBadPath(t *testing.T) {
	// Null byte → os.Stat returns a non-IsNotExist error.
	if _, err := stageExistingTarget("bad\x00target"); err == nil {
		t.Error("stageExistingTarget with bad path returned nil error")
	}
}

func TestStageExistingTarget_StagesExistingFile(t *testing.T) {
	target := filepath.Join(t.TempDir(), "live.sqlite")
	if err := os.WriteFile(target, []byte("data"), 0o600); err != nil {
		t.Fatal(err)
	}
	staged, err := stageExistingTarget(target)
	if err != nil {
		t.Fatalf("stageExistingTarget: %v", err)
	}
	if staged == "" {
		t.Fatal("expected non-empty staged path for existing target")
	}
	if _, err := os.Stat(staged); err != nil {
		t.Errorf("staged file not present: %v", err)
	}
	if _, err := os.Stat(target); !os.IsNotExist(err) {
		t.Error("original target should have been renamed aside")
	}
}

// --- rollbackAfterCopyFailure branches ---------------------------------

func TestRollbackAfterCopyFailure_NoStagedReturnsCopyErr(t *testing.T) {
	target := filepath.Join(t.TempDir(), "t.sqlite")
	err := rollbackAfterCopyFailure(os.ErrInvalid, target, "")
	if err == nil {
		t.Error("expected wrapped copy error")
	}
}

func TestRollbackAfterCopyFailure_RestoresStaged(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "t.sqlite")
	staged := filepath.Join(dir, "t.sqlite.pre_restore_x")
	if err := os.WriteFile(staged, []byte("original"), 0o600); err != nil {
		t.Fatal(err)
	}
	// target may or may not exist; rollback removes it then renames staged back.
	err := rollbackAfterCopyFailure(os.ErrInvalid, target, staged)
	if err == nil {
		t.Error("expected wrapped copy error even on successful rollback")
	}
	got, readErr := os.ReadFile(target)
	if readErr != nil {
		t.Fatalf("target not restored: %v", readErr)
	}
	if string(got) != "original" {
		t.Errorf("restored content = %q, want original", got)
	}
}

// --- copyFile happy path + Sync close (sqlite_backup) ------------------

func TestSQLiteBackupCopyFile_HappyPath(t *testing.T) {
	src := filepath.Join(t.TempDir(), "src.sqlite")
	if err := os.WriteFile(src, []byte("backup-bytes"), 0o600); err != nil {
		t.Fatal(err)
	}
	dst := filepath.Join(t.TempDir(), "dst.sqlite")
	if err := copyFile(src, dst); err != nil {
		t.Fatalf("copyFile: %v", err)
	}
	got, _ := os.ReadFile(dst)
	if string(got) != "backup-bytes" {
		t.Errorf("dst = %q, want backup-bytes", got)
	}
}

// --- Backup: bad dest dir + checkpoint_copy explicit strategy ----------

func TestBackup_BadDestParentErrors(t *testing.T) {
	store := migrateTestStore(t)
	// Null byte in dest → MkdirAll(Dir(dest)) fails.
	if _, err := store.Backup(BackupOptions{DestPath: "bad\x00/snap.sqlite"}); err == nil {
		t.Error("Backup with bad dest dir returned nil")
	}
}

func TestBackup_ExplicitCheckpointCopyStrategy(t *testing.T) {
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	dst := filepath.Join(t.TempDir(), "ckpt.sqlite")
	res, err := store.Backup(BackupOptions{DestPath: dst, Strategy: BackupStrategyCheckpointCopy})
	if err != nil {
		t.Fatalf("Backup checkpoint_copy: %v", err)
	}
	if res.Strategy != BackupStrategyCheckpointCopy {
		t.Errorf("Strategy = %v, want checkpoint_copy", res.Strategy)
	}
	// Resulting file must open as a valid SQLite db.
	reopened, err := OpenSQLiteStore(dst)
	if err != nil {
		t.Fatalf("reopen backup: %v", err)
	}
	defer reopened.Close()
	if v, _ := reopened.SchemaVersion(); v != SQLiteSchemaVersion {
		t.Errorf("backup user_version = %d, want %d", v, SQLiteSchemaVersion)
	}
}
