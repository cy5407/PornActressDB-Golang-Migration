package database

import (
	"database/sql"
	_ "embed"
	"errors"
	"fmt"
	"time"

	_ "modernc.org/sqlite"
)

const (
	// SQLiteSchemaVersion is the structural schema version recorded via
	// PRAGMA user_version. Spec § 2.1: 3.
	SQLiteSchemaVersion = 3

	// SQLiteDriverName is the database/sql driver name registered by
	// modernc.org/sqlite.
	SQLiteDriverName = "sqlite"

	// SQLiteFileName is the on-disk filename used by the SQLite store.
	SQLiteFileName = "db.sqlite"
)

//go:embed sqlite_schema.sql
var sqliteSchemaSQL string

// ErrSchemaVersionMismatch is returned by InitSchema when an existing
// database has PRAGMA user_version set to a value that is neither 0
// (fresh) nor SQLiteSchemaVersion. Slice A1 does not implement a forced
// replace path — older files must be migrated explicitly by tooling.
var ErrSchemaVersionMismatch = errors.New("sqlite schema version mismatch")

// SQLiteStore is the runtime SQLite-backed store. It started life as
// the minimal handle Slice A1 stood up (open + schema + close) and
// grew the full JSONDatabase-compatible surface during Slice C2 so
// cmd/scanner, the Wails backend and the Python CLI contract can talk
// to a SQLite-only runtime without changing call sites.
//
// dataDir is the JSON-compatible data directory NewStore associated
// with this handle (see ResolveDataDirPaths). It is what the backup
// family keys off so SQLite-only callers land in the same
// <data-dir>/backup/ tree the JSON flow used. Empty for stores opened
// directly through OpenSQLiteStore (tests / one-shot CLI subcommands).
type SQLiteStore struct {
	db      *sql.DB
	path    string
	dataDir string
}

// OpenSQLiteStore opens (or creates) a SQLite database at path and
// applies the connection-level pragmas (WAL journal, foreign keys on).
// It does NOT initialize the schema; the caller decides whether to
// invoke InitSchema.
func OpenSQLiteStore(path string) (*SQLiteStore, error) {
	if path == "" {
		return nil, errors.New("sqlite path cannot be empty")
	}
	db, err := sql.Open(SQLiteDriverName, path)
	if err != nil {
		return nil, fmt.Errorf("open sqlite %q: %w", path, err)
	}
	if err := applySQLitePragmas(db); err != nil {
		_ = db.Close()
		return nil, err
	}
	return &SQLiteStore{db: db, path: path}, nil
}

func applySQLitePragmas(db *sql.DB) error {
	pragmas := []string{
		"PRAGMA journal_mode = WAL",
		"PRAGMA foreign_keys = ON",
		"PRAGMA synchronous = NORMAL",
	}
	for _, p := range pragmas {
		if _, err := db.Exec(p); err != nil {
			return fmt.Errorf("apply %q: %w", p, err)
		}
	}
	return nil
}

// InitSchema applies the embedded schema to a fresh database (and seeds
// db_meta singleton rows). It is idempotent for databases already at
// SQLiteSchemaVersion. For any other non-zero PRAGMA user_version it
// returns ErrSchemaVersionMismatch — A1 does not migrate older files.
func (s *SQLiteStore) InitSchema() error {
	if s == nil || s.db == nil {
		return errors.New("sqlite store is not open")
	}
	current, err := s.SchemaVersion()
	if err != nil {
		return err
	}
	switch current {
	case 0:
		return s.initFresh()
	case SQLiteSchemaVersion:
		return s.applySchemaObjects()
	default:
		return fmt.Errorf("%w: found user_version=%d, want %d",
			ErrSchemaVersionMismatch, current, SQLiteSchemaVersion)
	}
}

func (s *SQLiteStore) initFresh() error {
	if err := s.applySchemaObjects(); err != nil {
		return err
	}
	if err := s.seedDBMeta(); err != nil {
		return err
	}
	if _, err := s.db.Exec(fmt.Sprintf("PRAGMA user_version = %d", SQLiteSchemaVersion)); err != nil {
		return fmt.Errorf("set user_version: %w", err)
	}
	return nil
}

func (s *SQLiteStore) applySchemaObjects() error {
	if _, err := s.db.Exec(sqliteSchemaSQL); err != nil {
		return fmt.Errorf("apply schema: %w", err)
	}
	return nil
}

func (s *SQLiteStore) seedDBMeta() error {
	now := time.Now().UTC().Format(time.RFC3339)
	rows := []struct{ key, value string }{
		{"schema_version", SchemaVersion}, // JSON-semantic version, "1.0.0"
		{"description", "Python 女優分類系統 JSON 資料庫"},
		{"encoding", "UTF-8"},
		{"data_hash", ""},
		{"created_at", now},
		{"updated_at", now},
	}
	stmt, err := s.db.Prepare(`INSERT OR IGNORE INTO db_meta(key, value) VALUES (?, ?)`)
	if err != nil {
		return fmt.Errorf("prepare db_meta seed: %w", err)
	}
	defer stmt.Close()
	for _, r := range rows {
		if _, err := stmt.Exec(r.key, r.value); err != nil {
			return fmt.Errorf("seed db_meta key=%q: %w", r.key, err)
		}
	}
	return nil
}

// SchemaVersion reads PRAGMA user_version from the open database.
// Returns 0 for a database that has never run InitSchema successfully.
func (s *SQLiteStore) SchemaVersion() (int, error) {
	if s == nil || s.db == nil {
		return 0, errors.New("sqlite store is not open")
	}
	var v int
	if err := s.db.QueryRow("PRAGMA user_version").Scan(&v); err != nil {
		return 0, fmt.Errorf("read user_version: %w", err)
	}
	return v, nil
}

// Path returns the on-disk path the store was opened with.
func (s *SQLiteStore) Path() string {
	if s == nil {
		return ""
	}
	return s.path
}

// Close closes the underlying *sql.DB. Safe to call multiple times and
// on a nil receiver.
func (s *SQLiteStore) Close() error {
	if s == nil || s.db == nil {
		return nil
	}
	err := s.db.Close()
	s.db = nil
	return err
}
