package jsonfixture

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"

	. "actress-classifier/pkg/database"
)

// writeJSONDB writes the given DatabaseData (marshalled) to a file in
// t.TempDir and returns its path. Duplicated from pkg/database test
// helpers so jsonfixture tests can use the same fixture shapes without
// pulling unexported runtime helpers across a package boundary.
func writeJSONDB(t *testing.T, root *DatabaseData) string {
	t.Helper()
	raw, err := json.MarshalIndent(root, "", "  ")
	if err != nil {
		t.Fatalf("marshal root: %v", err)
	}
	path := filepath.Join(t.TempDir(), "source.json")
	if err := os.WriteFile(path, raw, 0o600); err != nil {
		t.Fatalf("write source: %v", err)
	}
	return path
}

// minimalRoot is a happy-path JSON DB shaped like the CI fixture: 3
// videos, 3 actresses, 4 links, with one actress referenced from two
// distinct videos. Duplicated from pkg/database test helpers.
func minimalRoot() *DatabaseData {
	return &DatabaseData{
		SchemaVersion: SchemaVersion,
		Metadata:      &DatabaseMetadata{Description: "test", Encoding: "UTF-8"},
		CreatedAt:     "2026-05-23T00:00:00Z",
		UpdatedAt:     "2026-05-23T00:00:00Z",
		Videos: map[string]*VideoData{
			"STARS-707": {
				Code: "STARS-707", Title: "A", Studio: "S1",
				Actresses: []string{"田中美奈実"},
				UpdatedAt: "2026-05-22T12:00:00Z",
			},
			"MIDV-567": {
				Code: "MIDV-567", Title: "B", Studio: "MOODYZ",
				Actresses: []string{"佐藤亞美", "鈴木花子"},
				UpdatedAt: "2026-05-22T12:30:00Z",
			},
			"SSIS-001": {
				Code: "SSIS-001", Title: "C", Studio: "S1",
				Actresses: []string{"田中美奈実"},
				UpdatedAt: "2026-05-22T13:00:00Z",
			},
		},
		Actresses: map[string]*ActressData{
			"tanaka-minami": {ID: "tanaka-minami", Name: "田中美奈実", Aliases: []string{"田中みなみ"}},
			"sato-ami":      {ID: "sato-ami", Name: "佐藤亞美"},
			"suzuki-hanako": {ID: "suzuki-hanako", Name: "鈴木花子"},
		},
		Links: []VideoActressLink{
			{VideoCode: "STARS-707", ActressID: "tanaka-minami", RoleType: "主演", Timestamp: "2026-05-22T12:00:00Z"},
			{VideoCode: "MIDV-567", ActressID: "sato-ami", RoleType: "主演", Timestamp: "2026-05-22T12:30:00Z"},
			{VideoCode: "MIDV-567", ActressID: "suzuki-hanako", RoleType: "主演", Timestamp: "2026-05-22T12:30:00Z"},
			{VideoCode: "SSIS-001", ActressID: "tanaka-minami", RoleType: "主演", Timestamp: "2026-05-22T13:00:00Z"},
		},
	}
}

// writeBackupWithMtime drops a backup_*.json fixture into <dataDir>/backup
// and (optionally) backdates its mtime by ageDays days. Duplicated from
// pkg/database test helpers so jsonfixture-side backup tests don't need
// to pull cross-package internals.
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
