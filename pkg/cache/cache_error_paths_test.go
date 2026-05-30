package cache

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

// writeCorruptIndex puts invalid JSON at cache_index.json so loadIndex
// hits the json.Unmarshal failure branch.
func writeCorruptIndex(t *testing.T, dir string) {
	t.Helper()
	path := filepath.Join(dir, "cache_index.json")
	if err := os.WriteFile(path, []byte("{not json"), 0o600); err != nil {
		t.Fatalf("write corrupt index: %v", err)
	}
}

func TestLoadIndex_CorruptJSONReturnsError(t *testing.T) {
	dir := t.TempDir()
	writeCorruptIndex(t, dir)
	cm := NewCacheManager(dir)
	if _, err := cm.loadIndex(); err == nil {
		t.Fatal("loadIndex on corrupt JSON returned nil error, want error")
	}
}

func TestLoadIndex_NilEntriesInitialised(t *testing.T) {
	dir := t.TempDir()
	// Index with no entries field at all → unmarshal succeeds, Entries nil,
	// loader must initialise an empty map.
	if err := os.WriteFile(filepath.Join(dir, "cache_index.json"),
		[]byte(`{"metadata":{"version":"1.0","created_at":0}}`), 0o600); err != nil {
		t.Fatal(err)
	}
	cm := NewCacheManager(dir)
	idx, err := cm.loadIndex()
	if err != nil {
		t.Fatalf("loadIndex: %v", err)
	}
	if idx.Entries == nil {
		t.Error("Entries map was nil, want initialised empty map")
	}
}

func TestGetStats_CorruptIndexPropagates(t *testing.T) {
	dir := t.TempDir()
	writeCorruptIndex(t, dir)
	cm := NewCacheManager(dir)
	if _, err := cm.GetStats(); err == nil {
		t.Error("GetStats on corrupt index returned nil, want error")
	}
}

func TestClearAll_CorruptIndexPropagates(t *testing.T) {
	dir := t.TempDir()
	writeCorruptIndex(t, dir)
	cm := NewCacheManager(dir)
	if _, err := cm.ClearAll(false); err == nil {
		t.Error("ClearAll on corrupt index returned nil, want error")
	}
}

func TestAutoCleanup_CorruptIndexPropagates(t *testing.T) {
	dir := t.TempDir()
	writeCorruptIndex(t, dir)
	cm := NewCacheManager(dir)
	if _, err := cm.AutoCleanup(context.Background(), PruneConfig{TTLDays: 7, MaxSizeMB: 500, MinKeepEntries: 100, DryRun: false}); err == nil {
		t.Error("AutoCleanup on corrupt index returned nil, want error")
	}
}

func TestClearAll_FileOutsideCacheDirCountsAsError(t *testing.T) {
	outside := t.TempDir() // separate temp tree
	rogue := filepath.Join(outside, "rogue.json")
	if err := os.WriteFile(rogue, []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	cacheDir := t.TempDir()
	createTestIndex(t, cacheDir, map[string]IndexEntry{
		"rogue": {FilePath: rogue, SizeBytes: 1},
	})
	cm := NewCacheManager(cacheDir)
	res, err := cm.ClearAll(false)
	if err != nil {
		t.Fatalf("ClearAll: %v", err)
	}
	if res.Errors == 0 {
		t.Error("Errors = 0, want >0 (file outside cache dir should be refused)")
	}
}

func TestValidateCachePath_BadCacheDirReturnsFalse(t *testing.T) {
	cm := NewCacheManager("bad\x00dir") // filepath.Abs rejects null byte
	if cm.validateCachePath(filepath.Join(t.TempDir(), "x")) {
		t.Error("validateCachePath returned true for bad cache dir")
	}
}

func TestValidateCachePath_BadFilePathReturnsFalse(t *testing.T) {
	cm := NewCacheManager(t.TempDir())
	if cm.validateCachePath("bad\x00file") {
		t.Error("validateCachePath returned true for bad file path")
	}
}
