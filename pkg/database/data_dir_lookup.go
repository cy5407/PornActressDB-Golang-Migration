package database

import "path/filepath"

// DefaultDataDir is the default -data-dir value used by every classifier.exe
// db subcommand. Kept in sync with cmd/scanner/db_cmd.go.
const DefaultDataDir = "data/json_db"

// DataDirPaths holds the resolved JSON DB + SQLite file paths for a given
// -data-dir value. The SQLite path follows the spec § 7.1 compatibility
// lookup: the default data dir maps to a sibling db.sqlite (so json_db/
// and db.sqlite share the data/ parent), while any custom directory
// keeps db.sqlite as a direct child.
type DataDirPaths struct {
	DataDir     string
	DataFile    string
	JournalFile string
	IndexFile   string
	SQLitePath  string
}

// ResolveDataDirPaths returns the JSON DB + SQLite paths derived from a
// -data-dir argument. The directory is normalized with filepath.Clean so
// callers can compare results without worrying about trailing separators
// or "./" prefixes. SQLite mapping follows spec § 7.1:
//
//  1. If the input resolves (via filepath.Abs) to the same absolute
//     directory as DefaultDataDir, SQLitePath is a sibling: e.g. the
//     default data/json_db gives data/db.sqlite, NOT data/json_db/db.sqlite.
//  2. Any other directory <path> gets SQLitePath = <path>/db.sqlite.
//
// Existence of the directory is not checked here; callers decide when
// missing files are an error.
func ResolveDataDirPaths(dataDir string) DataDirPaths {
	cleaned := filepath.Clean(dataDir)
	return DataDirPaths{
		DataDir:     cleaned,
		DataFile:    filepath.Join(cleaned, DataFileName),
		JournalFile: filepath.Join(cleaned, JournalFileName),
		IndexFile:   filepath.Join(cleaned, IndexFileName),
		SQLitePath:  resolveSQLitePath(cleaned),
	}
}

// resolveSQLitePath implements the spec § 7.1 compatibility lookup for
// the SQLite-side path. The cleanedDir argument must already be the
// output of filepath.Clean(dataDir).
//
// The match is performed in absolute form so that "data/json_db",
// "./data/json_db" and the cwd-relative absolute equivalent all collapse
// onto the same sibling rule. The returned path keeps the relative or
// absolute shape of the original input — we only swap the leaf when the
// match fires.
func resolveSQLitePath(cleanedDir string) string {
	if pathMatchesDefault(cleanedDir) {
		// Sibling of the JSON dir: e.g. data/json_db -> data/db.sqlite.
		parent := filepath.Dir(cleanedDir)
		return filepath.Join(parent, SQLiteFileName)
	}
	return filepath.Join(cleanedDir, SQLiteFileName)
}

// pathMatchesDefault reports whether cleanedDir refers to the same
// directory as DefaultDataDir after filepath.Abs normalization. If
// either filepath.Abs call fails the comparison falls back to a plain
// string match on the cleaned forms.
func pathMatchesDefault(cleanedDir string) bool {
	defaultClean := filepath.Clean(DefaultDataDir)
	if cleanedDir == defaultClean {
		return true
	}
	absDir, err := filepath.Abs(cleanedDir)
	if err != nil {
		return false
	}
	absDefault, err := filepath.Abs(defaultClean)
	if err != nil {
		return false
	}
	return absDir == absDefault
}
