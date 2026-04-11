package cache

import "testing"

func TestLimitCleanupCandidates_RespectsMinKeepEntries(t *testing.T) {
	candidates := []cacheEntryCandidate{
		{key: "oldest", orderValue: 1},
		{key: "middle", orderValue: 2},
		{key: "newest", orderValue: 3},
	}

	limited := limitCleanupCandidates(candidates, 4, 2)
	if len(limited) != 2 {
		t.Fatalf("len(limited) = %d, want 2", len(limited))
	}
	if limited[0].key != "oldest" || limited[1].key != "middle" {
		t.Fatalf("limited = %#v, want oldest then middle", limited)
	}
}

func TestCollectLRUCandidates_FallsBackToCreatedAt(t *testing.T) {
	candidates := collectLRUCandidates(map[string]IndexEntry{
		"older": {CreatedAt: 10},
		"newer": {CreatedAt: 20, LastAccessed: 30},
	})

	if len(candidates) != 2 {
		t.Fatalf("len(candidates) = %d, want 2", len(candidates))
	}
	if candidates[0].key != "older" {
		t.Fatalf("first candidate = %q, want older", candidates[0].key)
	}
	if candidates[0].orderValue != 10 {
		t.Fatalf("older orderValue = %v, want 10", candidates[0].orderValue)
	}
}
