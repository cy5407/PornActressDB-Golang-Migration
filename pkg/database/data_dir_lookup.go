package database

import "path/filepath"

// DefaultDataDir is the default -data-dir value used by every classifier.exe
// db subcommand. Kept in sync with cmd/scanner/db_cmd.go.
const DefaultDataDir = "data/json_db"

// DataDirPaths holds the resolved JSON DB file paths for a given -data-dir
// value. SQLite-side resolution (spec § 7.1 compatibility lookup) is
// intentionally deferred to Slice A1.
type DataDirPaths struct {
	DataDir     string
	DataFile    string
	JournalFile string
	IndexFile   string
}

// ResolveDataDirPaths returns the JSON DB paths derived from a -data-dir
// argument. The directory is normalized with filepath.Clean so callers can
// compare results without worrying about trailing separators or "./" prefixes.
//
// Existence of the directory is not checked here; callers (notably
// JSONDatabase.Load) decide when missing files are an error.
func ResolveDataDirPaths(dataDir string) DataDirPaths {
	cleaned := filepath.Clean(dataDir)
	return DataDirPaths{
		DataDir:     cleaned,
		DataFile:    filepath.Join(cleaned, DataFileName),
		JournalFile: filepath.Join(cleaned, JournalFileName),
		IndexFile:   filepath.Join(cleaned, IndexFileName),
	}
}
