package jsonfixture

import (
	"slices"
	"testing"

	. "actress-classifier/pkg/database"
)

// TestActressCleaner_ApplyToDatabaseDryRunDoesNotMutateData and the
// mutating counterpart live here (not next to ActressCleaner in
// pkg/database) because they need the JSONDatabase fixture as their
// store. ActressCleanupTarget is a structural interface, so the *Video
// path through (*JSONDatabase) just works.

func TestActressCleaner_ApplyToDatabaseDryRunDoesNotMutateData(t *testing.T) {
	db, _ := setupTestDB(t)
	video := NewVideo("ABF-062")
	video.Actresses = []string{"蒼乃美月", "顔射の美学", "蒼乃美月蒼乃美月"}
	if err := db.UpdateVideo("ABF-062", video); err != nil {
		t.Fatalf("Failed to seed video: %v", err)
	}

	cleaner := NewActressCleaner()
	report, err := cleaner.ApplyToDatabase(db, false)
	if err != nil {
		t.Fatalf("ApplyToDatabase returned error: %v", err)
	}

	if report.ChangedVideos != 1 {
		t.Fatalf("expected 1 changed video, got %d", report.ChangedVideos)
	}
	if report.RemovedActresses != 2 {
		t.Fatalf("expected 2 removed actresses, got %d", report.RemovedActresses)
	}

	reloaded, err := db.GetVideo("ABF-062")
	if err != nil {
		t.Fatalf("Failed to fetch video: %v", err)
	}
	assertStringSliceEqualFixture(t, reloaded.Actresses, []string{"蒼乃美月", "顔射の美学", "蒼乃美月蒼乃美月"})
}

func TestActressCleaner_ApplyToDatabaseWriteMutatesData(t *testing.T) {
	db, _ := setupTestDB(t)
	video := NewVideo("ABF-177")
	video.Actresses = []string{"絶対", "瀧本雫葉", "リミットブレイク"}
	if err := db.UpdateVideo("ABF-177", video); err != nil {
		t.Fatalf("Failed to seed video: %v", err)
	}

	cleaner := NewActressCleaner()
	report, err := cleaner.ApplyToDatabase(db, true)
	if err != nil {
		t.Fatalf("ApplyToDatabase returned error: %v", err)
	}

	if report.ChangedVideos != 1 {
		t.Fatalf("expected 1 changed video, got %d", report.ChangedVideos)
	}
	if report.RemovedActresses != 2 {
		t.Fatalf("expected 2 removed actresses, got %d", report.RemovedActresses)
	}

	reloaded, err := db.GetVideo("ABF-177")
	if err != nil {
		t.Fatalf("Failed to fetch video: %v", err)
	}
	assertStringSliceEqualFixture(t, reloaded.Actresses, []string{"瀧本雫葉"})
}

func assertStringSliceEqualFixture(t *testing.T, got, want []string) {
	t.Helper()
	if got == nil {
		got = []string{}
	}
	if want == nil {
		want = []string{}
	}
	if !slices.Equal(got, want) {
		t.Fatalf("expected %#v, got %#v", want, got)
	}
}
