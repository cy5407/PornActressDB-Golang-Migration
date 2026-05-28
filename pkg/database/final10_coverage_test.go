package database

import (
	"testing"
)

// appendIfClean / appendReplacementIfClean have branches CleanActresses
// never reaches (it pre-trims and skips blanks). Call them directly to
// cover the empty-name early return and the shouldRemove branch.
func TestAppendIfClean_DirectBranches(t *testing.T) {
	c := NewActressCleaner()

	cleaned := []string{}
	seen := map[string]struct{}{}
	removed := []string{}

	// Empty name → early return, nothing appended.
	c.appendIfClean(&cleaned, &seen, &removed, "")
	if len(cleaned) != 0 || len(removed) != 0 {
		t.Errorf("empty name should be a no-op; cleaned=%v removed=%v", cleaned, removed)
	}

	// Blocked name → removed via shouldRemove.
	c.appendIfClean(&cleaned, &seen, &removed, "デビュー")
	if len(removed) != 1 {
		t.Errorf("blocked name should be removed; removed=%v", removed)
	}

	// Fresh name → appended + marked seen.
	c.appendIfClean(&cleaned, &seen, &removed, "正常女優")
	if len(cleaned) != 1 || cleaned[0] != "正常女優" {
		t.Errorf("fresh name should be appended; cleaned=%v", cleaned)
	}

	// Duplicate → removed (seen branch).
	c.appendIfClean(&cleaned, &seen, &removed, "正常女優")
	if len(cleaned) != 1 {
		t.Errorf("duplicate should not be appended again; cleaned=%v", cleaned)
	}
}

func TestAppendReplacementIfClean_DirectBranches(t *testing.T) {
	c := NewActressCleaner()

	cleaned := []string{}
	seen := map[string]struct{}{}
	removed := []string{}

	// Empty replacement → early return.
	c.appendReplacementIfClean(&cleaned, &seen, &removed, "")
	if len(cleaned) != 0 {
		t.Errorf("empty replacement should be a no-op; cleaned=%v", cleaned)
	}

	// Blocked replacement → removed.
	c.appendReplacementIfClean(&cleaned, &seen, &removed, "デビュー")
	if len(removed) != 1 {
		t.Errorf("blocked replacement should be removed; removed=%v", removed)
	}

	// Fresh replacement → appended.
	c.appendReplacementIfClean(&cleaned, &seen, &removed, "替換女優")
	if len(cleaned) != 1 {
		t.Errorf("fresh replacement should be appended; cleaned=%v", cleaned)
	}

	// Duplicate replacement → silently skipped (no append, no removed).
	beforeRemoved := len(removed)
	c.appendReplacementIfClean(&cleaned, &seen, &removed, "替換女優")
	if len(cleaned) != 1 {
		t.Errorf("duplicate replacement should not append; cleaned=%v", cleaned)
	}
	if len(removed) != beforeRemoved {
		t.Errorf("duplicate replacement should not be added to removed; removed=%v", removed)
	}
}
