package database

import (
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// BackupStrategy selects how SQLiteStore.Backup produces the destination
// file. modernc.org/sqlite does not expose the sqlite3_backup_* C API
// over database/sql, so Phase C1 sticks to two pure-SQL strategies that
// the driver actually supports.
//
// See implementation-notes.md for the tradeoff rationale.
type BackupStrategy int

const (
	// BackupStrategyAuto runs VACUUM INTO first; if that fails (Windows
	// file lock, low disk space mid-write, etc.) it falls back to a WAL
	// checkpoint followed by a byte-for-byte file copy. This is the CLI
	// default.
	BackupStrategyAuto BackupStrategy = iota

	// BackupStrategyVacuumInto forces the VACUUM INTO branch only.
	// Useful for tests that pin the primary path.
	BackupStrategyVacuumInto

	// BackupStrategyCheckpointCopy forces the checkpoint+copy branch.
	// Useful for tests that pin the fallback path, and for callers who
	// know the primary will fail (e.g. a known long-running writer).
	BackupStrategyCheckpointCopy
)

// String renders the strategy for log lines and the JSON CLI reply.
func (s BackupStrategy) String() string {
	switch s {
	case BackupStrategyAuto:
		return "auto"
	case BackupStrategyVacuumInto:
		return "vacuum_into"
	case BackupStrategyCheckpointCopy:
		return "checkpoint_copy"
	default:
		return "unknown"
	}
}

// BackupOptions parameterises SQLiteStore.Backup.
type BackupOptions struct {
	// DestPath is the on-disk path of the resulting SQLite snapshot.
	// The parent directory is created on demand; any existing file at
	// DestPath is removed before the strategy runs (VACUUM INTO refuses
	// to overwrite, and a half-written copy from a previous failure
	// must not contaminate the new attempt).
	DestPath string

	// Strategy selects which branch the backup takes. The zero value
	// (BackupStrategyAuto) is what the CLI uses.
	Strategy BackupStrategy
}

// BackupResult reports the outcome of a successful SQLiteStore.Backup.
// Strategy is the branch that actually produced DestPath — when
// Strategy is BackupStrategyAuto on input, BackupResult.Strategy is
// either BackupStrategyVacuumInto or BackupStrategyCheckpointCopy.
type BackupResult struct {
	DestPath string         `json:"dest_path"`
	Strategy BackupStrategy `json:"strategy"`
	Duration time.Duration  `json:"duration"`
	Bytes    int64          `json:"bytes"`
}

// vacuumIntoExecutor isolates the VACUUM INTO call so tests can inject
// failure on the primary path without involving the real SQLite driver.
// Production code never replaces it.
var vacuumIntoExecutor = func(s *SQLiteStore, dst string) error {
	// SQLite does not accept a placeholder for the VACUUM INTO target,
	// so we have to embed it as a literal. Escape single quotes the
	// SQL-standard way; the path comes from the CLI, not user data, so
	// the surface area is small but the escape stays correct.
	escaped := strings.ReplaceAll(dst, "'", "''")
	_, err := s.db.Exec(fmt.Sprintf("VACUUM INTO '%s'", escaped))
	return err
}

// Backup writes a self-contained SQLite snapshot to opts.DestPath.
// The default strategy (auto) tries VACUUM INTO first, then falls
// back to checkpoint+copy. Both strategies produce a file that opens
// as a stand-alone SQLite database with the same user_version.
func (s *SQLiteStore) Backup(opts BackupOptions) (*BackupResult, error) {
	if s == nil || s.db == nil {
		return nil, errors.New("sqlite store is not open")
	}
	if strings.TrimSpace(opts.DestPath) == "" {
		return nil, errors.New("backup destination path is empty")
	}
	if err := os.MkdirAll(filepath.Dir(opts.DestPath), 0o755); err != nil {
		return nil, fmt.Errorf("mkdir backup dir: %w", err)
	}
	if err := os.Remove(opts.DestPath); err != nil && !os.IsNotExist(err) {
		return nil, fmt.Errorf("remove existing backup destination: %w", err)
	}

	start := time.Now()
	chosen, err := s.runBackupStrategy(opts)
	if err != nil {
		return nil, err
	}

	info, statErr := os.Stat(opts.DestPath)
	if statErr != nil {
		return nil, fmt.Errorf("stat backup output %q: %w", opts.DestPath, statErr)
	}
	return &BackupResult{
		DestPath: opts.DestPath,
		Strategy: chosen,
		Duration: time.Since(start),
		Bytes:    info.Size(),
	}, nil
}

func (s *SQLiteStore) runBackupStrategy(opts BackupOptions) (BackupStrategy, error) {
	switch opts.Strategy {
	case BackupStrategyVacuumInto:
		if err := vacuumIntoExecutor(s, opts.DestPath); err != nil {
			return 0, fmt.Errorf("vacuum_into backup: %w", err)
		}
		return BackupStrategyVacuumInto, nil
	case BackupStrategyCheckpointCopy:
		if err := s.checkpointAndCopy(opts.DestPath); err != nil {
			return 0, fmt.Errorf("checkpoint_copy backup: %w", err)
		}
		return BackupStrategyCheckpointCopy, nil
	case BackupStrategyAuto:
		if err := vacuumIntoExecutor(s, opts.DestPath); err == nil {
			return BackupStrategyVacuumInto, nil
		} else {
			// Wipe a partial VACUUM INTO output before the fallback runs.
			_ = os.Remove(opts.DestPath)
			if copyErr := s.checkpointAndCopy(opts.DestPath); copyErr != nil {
				return 0, fmt.Errorf("auto backup: vacuum_into failed (%v); checkpoint_copy fallback failed: %w",
					err, copyErr)
			}
			return BackupStrategyCheckpointCopy, nil
		}
	default:
		return 0, fmt.Errorf("unknown backup strategy: %d", opts.Strategy)
	}
}

func (s *SQLiteStore) checkpointAndCopy(dst string) error {
	if _, err := s.db.Exec(`PRAGMA wal_checkpoint(FULL)`); err != nil {
		return fmt.Errorf("wal_checkpoint(FULL): %w", err)
	}
	if s.path == "" {
		return errors.New("checkpoint_copy: source path unknown")
	}
	return copyFile(s.path, dst)
}

// restoreCopyFile is the package-level hook RestoreSQLiteFile uses to
// copy the backup file into place. Tests override it to simulate a
// failure mid-restore (after the existing target has been moved aside)
// and assert that the rollback path puts the original target back. The
// production value never changes.
var restoreCopyFile = copyFile

// RestoreSQLiteFile replaces targetPath with the contents of srcPath
// after verifying srcPath is a usable SQLite database. The replacement
// is rollback-safe: if any step after the existing target is moved
// aside fails (copy, sync, validation), the original target file is
// renamed back into place so callers never observe a missing database.
//
// On success: the staged old target plus the target's stale WAL/SHM
// sidecars are removed so SQLite re-derives them on the next open.
//
// The caller is responsible for releasing any open handle on
// targetPath (e.g. SQLiteStore.Close) before calling this — on Windows
// the rename will otherwise fail with "Access is denied".
func RestoreSQLiteFile(targetPath, srcPath string) error {
	if strings.TrimSpace(targetPath) == "" {
		return errors.New("restore: target path is empty")
	}
	if strings.TrimSpace(srcPath) == "" {
		return errors.New("restore: source path is empty")
	}
	if _, err := os.Stat(srcPath); err != nil {
		return fmt.Errorf("restore: backup %q not accessible: %w", srcPath, err)
	}

	// Open-and-close to validate the backup is a usable SQLite DB
	// before we touch the live target. A bad backup must NEVER trigger
	// the rename-aside step below.
	probe, err := OpenSQLiteStore(srcPath)
	if err != nil {
		return fmt.Errorf("restore: backup %q is not a SQLite database: %w", srcPath, err)
	}
	if _, err := probe.SchemaVersion(); err != nil {
		_ = probe.Close()
		return fmt.Errorf("restore: backup %q schema_version unreadable: %w", srcPath, err)
	}
	if err := probe.Close(); err != nil {
		return fmt.Errorf("restore: close probe handle: %w", err)
	}

	if err := os.MkdirAll(filepath.Dir(targetPath), 0o755); err != nil {
		return fmt.Errorf("restore: mkdir target dir: %w", err)
	}

	// Stage the existing target so we can roll back if the copy or any
	// later step fails. Using a sibling ".pre_restore_<ts>" file keeps
	// the rename on the same filesystem (atomic on POSIX, supported on
	// NTFS). Nanosecond suffix avoids collisions when restore retries
	// run back-to-back inside the same second.
	stagedOld := ""
	if _, statErr := os.Stat(targetPath); statErr == nil {
		ts := time.Now().UTC().Format("20060102T150405.000000000")
		stagedOld = targetPath + ".pre_restore_" + ts
		if err := os.Remove(stagedOld); err != nil && !os.IsNotExist(err) {
			return fmt.Errorf("restore: clear stale staged backup %q: %w", stagedOld, err)
		}
		if err := os.Rename(targetPath, stagedOld); err != nil {
			return fmt.Errorf("restore: stage existing target %q: %w", targetPath, err)
		}
	} else if !os.IsNotExist(statErr) {
		return fmt.Errorf("restore: stat target %q: %w", targetPath, statErr)
	}

	if err := restoreCopyFile(srcPath, targetPath); err != nil {
		// copyFile removes a partially written destination on copy
		// errors but leaves it on sync errors. Remove unconditionally
		// so we never roll back over a half-written file.
		_ = os.Remove(targetPath)
		if stagedOld != "" {
			if rbErr := os.Rename(stagedOld, targetPath); rbErr != nil {
				return fmt.Errorf("restore: copy backup into target: %w; rollback also failed (staged copy left at %q): %v",
					err, stagedOld, rbErr)
			}
		}
		return fmt.Errorf("restore: copy backup into target: %w", err)
	}

	// WAL/SHM sidecars from the prior (now overwritten) database would
	// confuse the next open; SQLite recreates them as needed.
	_ = os.Remove(targetPath + "-wal")
	_ = os.Remove(targetPath + "-shm")

	if stagedOld != "" {
		if err := os.Remove(stagedOld); err != nil && !os.IsNotExist(err) {
			return fmt.Errorf("restore: remove staged old target %q after success: %w", stagedOld, err)
		}
	}
	return nil
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return fmt.Errorf("open source %q: %w", src, err)
	}
	defer in.Close()

	out, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o600)
	if err != nil {
		return fmt.Errorf("open destination %q: %w", dst, err)
	}
	if _, err := io.Copy(out, in); err != nil {
		_ = out.Close()
		_ = os.Remove(dst)
		return fmt.Errorf("copy %q -> %q: %w", src, dst, err)
	}
	if err := out.Sync(); err != nil {
		_ = out.Close()
		return fmt.Errorf("sync destination %q: %w", dst, err)
	}
	return out.Close()
}
