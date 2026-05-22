package database

import (
	"path/filepath"
	"testing"
)

func TestResolveDataDirPaths_DefaultDataDir(t *testing.T) {
	got := ResolveDataDirPaths(DefaultDataDir)

	wantDir := filepath.Clean(DefaultDataDir)
	if got.DataDir != wantDir {
		t.Errorf("DataDir = %q, want %q", got.DataDir, wantDir)
	}
	if got.DataFile != filepath.Join(wantDir, DataFileName) {
		t.Errorf("DataFile = %q, want %q", got.DataFile, filepath.Join(wantDir, DataFileName))
	}
	if got.JournalFile != filepath.Join(wantDir, JournalFileName) {
		t.Errorf("JournalFile = %q, want %q", got.JournalFile, filepath.Join(wantDir, JournalFileName))
	}
	if got.IndexFile != filepath.Join(wantDir, IndexFileName) {
		t.Errorf("IndexFile = %q, want %q", got.IndexFile, filepath.Join(wantDir, IndexFileName))
	}
}

func TestResolveDataDirPaths_CustomDir(t *testing.T) {
	custom := filepath.Join("D:"+string(filepath.Separator)+"custom", "db_dir")
	got := ResolveDataDirPaths(custom)

	if got.DataDir != filepath.Clean(custom) {
		t.Errorf("DataDir = %q, want %q", got.DataDir, filepath.Clean(custom))
	}
	if got.DataFile != filepath.Join(custom, DataFileName) {
		t.Errorf("DataFile = %q, want %q", got.DataFile, filepath.Join(custom, DataFileName))
	}
	if got.JournalFile != filepath.Join(custom, JournalFileName) {
		t.Errorf("JournalFile = %q, want %q", got.JournalFile, filepath.Join(custom, JournalFileName))
	}
	if got.IndexFile != filepath.Join(custom, IndexFileName) {
		t.Errorf("IndexFile = %q, want %q", got.IndexFile, filepath.Join(custom, IndexFileName))
	}
}

func TestResolveDataDirPaths_NonExistentPath(t *testing.T) {
	// Resolution must not depend on whether the directory exists;
	// callers (e.g. JSONDatabase.Load) decide what to do when files are missing.
	missing := filepath.Join(t.TempDir(), "does", "not", "exist")
	got := ResolveDataDirPaths(missing)

	if got.DataDir != filepath.Clean(missing) {
		t.Errorf("DataDir = %q, want %q", got.DataDir, filepath.Clean(missing))
	}
	if got.DataFile == "" || got.JournalFile == "" || got.IndexFile == "" {
		t.Fatalf("expected non-empty file paths, got %+v", got)
	}
	if filepath.Dir(got.DataFile) != filepath.Clean(missing) {
		t.Errorf("DataFile parent = %q, want %q", filepath.Dir(got.DataFile), filepath.Clean(missing))
	}
}

func TestResolveDataDirPaths_TrailingSeparatorNormalized(t *testing.T) {
	withSlash := DefaultDataDir + string(filepath.Separator)

	gotPlain := ResolveDataDirPaths(DefaultDataDir)
	gotSlash := ResolveDataDirPaths(withSlash)

	if gotPlain != gotSlash {
		t.Errorf("trailing-separator path resolved differently:\n  plain = %+v\n  slash = %+v", gotPlain, gotSlash)
	}
}

func TestResolveDataDirPaths_DotPrefixNormalized(t *testing.T) {
	prefixed := "." + string(filepath.Separator) + DefaultDataDir

	gotPlain := ResolveDataDirPaths(DefaultDataDir)
	gotPrefixed := ResolveDataDirPaths(prefixed)

	if gotPlain != gotPrefixed {
		t.Errorf("./-prefixed path resolved differently:\n  plain    = %+v\n  prefixed = %+v", gotPlain, gotPrefixed)
	}
}

func TestResolveDataDirPaths_RelativeAndAbsoluteAgreeWhenAbsified(t *testing.T) {
	// "相對 vs 絕對路徑經 filepath.Clean 後一致" — once both inputs are
	// normalized to absolute, the helper must agree on every derived path.
	relative := DefaultDataDir
	absolute, err := filepath.Abs(relative)
	if err != nil {
		t.Fatalf("filepath.Abs(%q) failed: %v", relative, err)
	}

	gotRel := ResolveDataDirPaths(relative)
	gotAbs := ResolveDataDirPaths(absolute)

	absOfRelDir, err := filepath.Abs(gotRel.DataDir)
	if err != nil {
		t.Fatalf("filepath.Abs(gotRel.DataDir) failed: %v", err)
	}
	if absOfRelDir != gotAbs.DataDir {
		t.Errorf("DataDir mismatch after Abs:\n  rel→abs = %q\n  abs     = %q", absOfRelDir, gotAbs.DataDir)
	}

	absOfRelData, err := filepath.Abs(gotRel.DataFile)
	if err != nil {
		t.Fatalf("filepath.Abs(gotRel.DataFile) failed: %v", err)
	}
	if absOfRelData != gotAbs.DataFile {
		t.Errorf("DataFile mismatch after Abs:\n  rel→abs = %q\n  abs     = %q", absOfRelData, gotAbs.DataFile)
	}
}

func TestDefaultDataDir_MatchesCLIDefault(t *testing.T) {
	// The CLI default in cmd/scanner/db_cmd.go is "data/json_db".
	// Use forward slashes deliberately so the spec value is portable.
	const wantSpec = "data/json_db"
	if DefaultDataDir != wantSpec {
		t.Errorf("DefaultDataDir = %q, want %q (matches cmd/scanner db flag default)", DefaultDataDir, wantSpec)
	}
}
