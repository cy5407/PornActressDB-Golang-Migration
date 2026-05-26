package database

import (
	"errors"
	"fmt"
	"log"
	"os"
	"path/filepath"
)

// StoreConfig parameterises NewStore. DataDir is required (empty falls
// back to DefaultDataDir / data/json_db); other fields exist for tests
// or for explicit override of the bootstrap path.
//
// Phase C2 collapsed the runtime onto a SQLite-only path; the mode /
// shadow-read knobs from Phase A3 / B1 are retired and intentionally
// absent. Callers that used to flip ACTRESS_DB_MODE or USE_SQLITE_READS
// for the rollback knob now operate strictly against SQLite — the
// JSONDatabase type stays only as an import / export / legacy fixture
// helper.
type StoreConfig struct {
	// DataDir is forwarded straight into ResolveDataDirPaths. Empty
	// uses DefaultDataDir (data/json_db) and the sibling SQLite path
	// (data/db.sqlite) per the spec § 7.1 compatibility lookup.
	DataDir string

	// SQLitePath overrides the path derived from DataDir. Leave empty
	// to use the spec § 7.1 compatibility lookup default. Tests set it
	// to point at a tempdir; production callers should not.
	SQLitePath string

	// SkipBootstrap suppresses the one-shot bootstrap-from-JSON pass
	// NewStore otherwise runs against a brand-new (or empty) SQLite
	// file when a sibling data.json is on disk. Tests use this to keep
	// SQLite empty even when a fixture data.json is present in the
	// same directory.
	SkipBootstrap bool
}

// NewStore is the canonical factory for the runtime data store. It
// opens (and lazily inits) the SQLite mirror, and — on the first
// non-skipped open against an empty SQLite file — performs a one-shot
// migrate-from-json from the JSON-compatible data directory so the
// long-running runtime can switch over without a manual import step.
//
// Returns the open *SQLiteStore. The caller owns Close().
//
// Bootstrap behaviour (Slice C2):
//
//   - SQLite already populated → bootstrap is skipped entirely.
//     data.json is not even inspected, so a broken legacy JSON file
//     never blocks runtime startup.
//   - SQLite empty / missing AND data.json absent → greenfield install.
//     SQLite stays empty, no error.
//   - SQLite empty / missing AND data.json present → bootstrap MUST
//     run and MUST succeed. Any failure (parse error, strict-mode
//     unresolved actress, …) is fatal: the store is closed and the
//     error returned so callers do NOT silently mistake a failed
//     cutover for an empty greenfield install. Operators recover with
//     `classifier.exe db migrate-from-json
//     -auto-create-missing-actresses` (or by fixing the JSON file) and
//     retry.
//   - Production never touches the JSON file after a successful
//     bootstrap. The runtime is SQLite-only from that point on.
func NewStore(cfg StoreConfig) (*SQLiteStore, error) {
	dataDir := cfg.DataDir
	if dataDir == "" {
		// Empty DataDir means "fall back to DefaultDataDir" per the
		// StoreConfig contract. ResolveDataDirPaths("") would otherwise
		// resolve to "." and break the spec § 7.1 compatibility lookup
		// (the default JSON dir maps to the sibling SQLite file).
		dataDir = DefaultDataDir
	}
	paths := ResolveDataDirPaths(dataDir)
	sqlitePath := cfg.SQLitePath
	if sqlitePath == "" {
		sqlitePath = paths.SQLitePath
	}
	if sqlitePath == "" {
		return nil, errors.New("NewStore: sqlite path is empty")
	}
	if err := os.MkdirAll(filepath.Dir(sqlitePath), 0o750); err != nil {
		return nil, fmt.Errorf("mkdir sqlite parent: %w", err)
	}

	// Snapshot existence BEFORE opening: OpenSQLiteStore creates the
	// file as a side-effect of sql.Open + PRAGMA exec, so a post-open
	// stat would always report "exists".
	fileExisted := true
	if _, err := os.Stat(sqlitePath); errors.Is(err, os.ErrNotExist) {
		fileExisted = false
	} else if err != nil {
		return nil, fmt.Errorf("stat sqlite %q: %w", sqlitePath, err)
	}

	store, err := OpenSQLiteStore(sqlitePath)
	if err != nil {
		return nil, err
	}
	if err := store.InitSchema(); err != nil {
		_ = store.Close()
		return nil, err
	}
	store.SetDataDir(paths.DataDir)

	if cfg.SkipBootstrap {
		return store, nil
	}

	needsBootstrap := !fileExisted
	if !needsBootstrap {
		empty, emptyErr := store.isEmpty()
		if emptyErr != nil {
			_ = store.Close()
			return nil, emptyErr
		}
		needsBootstrap = empty
	}
	if !needsBootstrap {
		return store, nil
	}

	if err := bootstrapFromJSONIfPresent(store, paths.DataFile, sqlitePath); err != nil {
		// Bootstrap is the cutover safety gate: if data.json is present
		// but cannot be imported into an empty SQLite store, the worst
		// thing we can do is keep going and pretend the runtime is a
		// clean greenfield install. The operator (or anything that
		// inspects video_count) would not be able to tell that data
		// was silently dropped. Fail loudly instead — close the store
		// and surface the error so the caller can log it and refuse
		// to come up. Recovery is the explicit
		// `classifier.exe db migrate-from-json -auto-create-missing-actresses`
		// flow, or fixing the JSON fixture by hand.
		_ = store.Close()
		return nil, fmt.Errorf("bootstrap-from-json %q → %q failed: %w",
			paths.DataFile, sqlitePath, err)
	}
	return store, nil
}

// bootstrapFromJSONIfPresent runs the one-shot migration from the JSON
// DB at jsonPath into the (empty) SQLite store. Returns nil when no
// JSON file is present (greenfield install). Any other error — stat
// failure, parse error, strict-mode migration failure — is logged for
// the operator and returned so NewStore can fail loudly instead of
// silently coming up with an empty SQLite mirror.
func bootstrapFromJSONIfPresent(store *SQLiteStore, jsonPath, sqlitePath string) error {
	if _, err := os.Stat(jsonPath); err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil
		}
		log.Printf("bootstrap: stat %q failed (%v)", jsonPath, err)
		return err
	}
	report, mErr := store.MigrateFromJSON(jsonPath, MigrationOptions{})
	if mErr != nil {
		log.Printf("bootstrap: migrate-from-json %q → %q failed (%v); "+
			"runtime startup will be aborted — fix data.json or run "+
			"`classifier.exe db migrate-from-json -auto-create-missing-actresses` "+
			"and retry",
			jsonPath, sqlitePath, mErr)
		return mErr
	}
	log.Printf("bootstrap: migrated %d videos + %d actresses + %d links from %q into %q",
		report.VideosImported, report.ActressesImported, report.LinksImported,
		jsonPath, sqlitePath)
	return nil
}
