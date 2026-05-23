package database

import (
	"errors"
	"path/filepath"
	"sort"
	"testing"
)

// readStoreFromMinimalFixture migrates the standard minimalRoot fixture
// into a fresh on-disk SQLite store so the read-path methods exercise
// the canonical column/link layout the dual-write mirror would build.
func readStoreFromMinimalFixture(t *testing.T) *SQLiteStore {
	t.Helper()
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("MigrateFromJSON: %v", err)
	}
	return store
}

func TestSQLiteStore_GetVideo_ReturnsRowAndOrderedActresses(t *testing.T) {
	store := readStoreFromMinimalFixture(t)

	v, err := store.GetVideo("MIDV-567")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	if v.Code != "MIDV-567" || v.Title != "B" || v.Studio != "MOODYZ" {
		t.Errorf("video scalars wrong: %+v", v)
	}
	// minimalRoot links MIDV-567 to 佐藤亞美 (ord 0) and 鈴木花子 (ord 1).
	want := []string{"佐藤亞美", "鈴木花子"}
	if !equalStringSlices(v.Actresses, want) {
		t.Errorf("Actresses = %v, want %v (ordinal-preserving)", v.Actresses, want)
	}
}

func TestSQLiteStore_GetVideo_PreservesAliasDisplay(t *testing.T) {
	// MigrateFromJSON should store the alias spelling in display_name so
	// GetVideo can hand it back instead of the canonical actresses.name.
	root := minimalRoot()
	root.Videos["STARS-707"].Actresses = []string{"田中みなみ"} // alias of tanaka-minami
	root.Links[0].ActressID = "tanaka-minami"
	src := writeJSONDB(t, root)

	store := migrateTestStore(t)
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("MigrateFromJSON: %v", err)
	}

	v, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	if want := []string{"田中みなみ"}; !equalStringSlices(v.Actresses, want) {
		t.Errorf("alias display lost: Actresses = %v, want %v", v.Actresses, want)
	}
}

func TestSQLiteStore_GetVideo_NotFoundIsErrNotFound(t *testing.T) {
	store := readStoreFromMinimalFixture(t)

	v, err := store.GetVideo("DOES-NOT-EXIST")
	if !errors.Is(err, ErrNotFound) {
		t.Errorf("err = %v, want ErrNotFound", err)
	}
	if v != nil {
		t.Errorf("video = %+v, want nil", v)
	}
}

func TestSQLiteStore_GetVideo_EmptyCodeIsErrInvalidCode(t *testing.T) {
	store := readStoreFromMinimalFixture(t)

	if _, err := store.GetVideo(""); !errors.Is(err, ErrInvalidCode) {
		t.Errorf("err = %v, want ErrInvalidCode", err)
	}
}

func TestSQLiteStore_GetVideo_ClosedStoreReportsUnavailable(t *testing.T) {
	store := readStoreFromMinimalFixture(t)
	_ = store.Close()

	_, err := store.GetVideo("STARS-707")
	if err == nil {
		t.Fatal("expected error from closed store, got nil")
	}
	if errors.Is(err, ErrNotFound) || errors.Is(err, ErrInvalidCode) {
		t.Errorf("closed store err must not look like a successful query: %v", err)
	}
	if !errors.Is(err, ErrSQLiteStoreClosed) {
		t.Errorf("err = %v, want wrapped ErrSQLiteStoreClosed", err)
	}
}

func TestSQLiteStore_ListVideos_ReturnsAllCodes(t *testing.T) {
	store := readStoreFromMinimalFixture(t)

	codes, err := store.ListVideos()
	if err != nil {
		t.Fatalf("ListVideos: %v", err)
	}
	sort.Strings(codes)
	want := []string{"MIDV-567", "SSIS-001", "STARS-707"}
	if !equalStringSlices(codes, want) {
		t.Errorf("ListVideos = %v, want %v", codes, want)
	}
}

func TestSQLiteStore_ListVideos_EmptyDBIsEmptySlice(t *testing.T) {
	store := migrateTestStore(t) // schema only, no data

	codes, err := store.ListVideos()
	if err != nil {
		t.Fatalf("ListVideos: %v", err)
	}
	if len(codes) != 0 {
		t.Errorf("ListVideos = %v, want empty", codes)
	}
}

func TestSQLiteStore_ListVideos_ClosedStoreIsUnavailable(t *testing.T) {
	store := readStoreFromMinimalFixture(t)
	_ = store.Close()

	if _, err := store.ListVideos(); !errors.Is(err, ErrSQLiteStoreClosed) {
		t.Errorf("err = %v, want wrapped ErrSQLiteStoreClosed", err)
	}
}

func TestSQLiteStore_GetAllVideos_PopulatesActresses(t *testing.T) {
	store := readStoreFromMinimalFixture(t)

	videos, err := store.GetAllVideos()
	if err != nil {
		t.Fatalf("GetAllVideos: %v", err)
	}
	if len(videos) != 3 {
		t.Fatalf("len(videos) = %d, want 3", len(videos))
	}

	byCode := make(map[string]*VideoData, len(videos))
	for _, v := range videos {
		byCode[v.Code] = v
	}

	stars, ok := byCode["STARS-707"]
	if !ok {
		t.Fatal("STARS-707 not in GetAllVideos result")
	}
	if want := []string{"田中美奈実"}; !equalStringSlices(stars.Actresses, want) {
		t.Errorf("STARS-707 Actresses = %v, want %v", stars.Actresses, want)
	}

	midv := byCode["MIDV-567"]
	if want := []string{"佐藤亞美", "鈴木花子"}; !equalStringSlices(midv.Actresses, want) {
		t.Errorf("MIDV-567 Actresses = %v, want %v", midv.Actresses, want)
	}
}

func TestSQLiteStore_GetAllVideos_ClosedStoreIsUnavailable(t *testing.T) {
	store := readStoreFromMinimalFixture(t)
	_ = store.Close()

	if _, err := store.GetAllVideos(); !errors.Is(err, ErrSQLiteStoreClosed) {
		t.Errorf("err = %v, want wrapped ErrSQLiteStoreClosed", err)
	}
}

func TestSQLiteStore_GetVideo_BrokenSchemaSurfacesQueryError(t *testing.T) {
	// Drop the videos table to simulate a schema/availability error
	// that's distinct from "no row". The DualWriteStore fallback path
	// uses this exact distinction.
	store := readStoreFromMinimalFixture(t)
	if _, err := store.db.Exec(`DROP TABLE videos`); err != nil {
		t.Fatalf("DROP TABLE: %v", err)
	}

	_, err := store.GetVideo("STARS-707")
	if err == nil {
		t.Fatal("expected query error after DROP TABLE, got nil")
	}
	if errors.Is(err, ErrNotFound) {
		t.Errorf("query error misclassified as ErrNotFound: %v", err)
	}
}

func TestSQLiteStore_GetVideo_RoundTripsUpsertedRow(t *testing.T) {
	// Independently exercise: UpsertVideo writes the row, GetVideo reads
	// the same shape back. This keeps the read SELECT and write INSERT
	// column lists in lock-step.
	store := migrateTestStore(t)
	if err := store.UpsertActress(&ActressData{ID: "x1", Name: "X"}); err != nil {
		t.Fatalf("UpsertActress: %v", err)
	}
	v := &VideoData{
		Code: "ABC-001", ID: "", Title: "round-trip", Studio: "RT",
		StudioCode:           "RTCODE",
		ReleaseDate:          "2026-05-01",
		URL:                  "https://example.test/abc-001",
		Actresses:            []string{"X"},
		SearchStatus:         "success",
		SearchMethod:         "test",
		LastSearchDate:       "2026-05-22T00:00:00Z",
		AVWikiActressStatus:  "ok",
		AVWikiLastSearchDate: "2026-05-22T00:00:00Z",
		JAVDBActressStatus:   "ok",
		JAVDBLastSearchDate:  "2026-05-22T00:00:00Z",
		CreatedAt:            "2026-05-22T00:00:00Z",
		UpdatedAt:            "2026-05-22T00:00:00Z",
		Metadata:             Metadata{Source: "rt", Confidence: 0.42},
		OriginalFilename:     "abc-001.mp4",
		FilePath:             "/tmp/abc-001.mp4",
		Error:                "",
		ErrorKind:            "",
	}
	if err := store.UpsertVideo("ABC-001", v); err != nil {
		t.Fatalf("UpsertVideo: %v", err)
	}

	got, err := store.GetVideo("ABC-001")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	if got.Title != v.Title || got.Studio != v.Studio || got.StudioCode != v.StudioCode {
		t.Errorf("string fields drift: got=%+v want=%+v", got, v)
	}
	if got.Metadata.Source != v.Metadata.Source || got.Metadata.Confidence != v.Metadata.Confidence {
		t.Errorf("metadata drift: got=%+v want=%+v", got.Metadata, v.Metadata)
	}
	if !equalStringSlices(got.Actresses, v.Actresses) {
		t.Errorf("Actresses = %v, want %v", got.Actresses, v.Actresses)
	}
	if filepath.IsAbs(got.FilePath) != filepath.IsAbs(v.FilePath) {
		t.Errorf("FilePath drift: got=%q want=%q", got.FilePath, v.FilePath)
	}
}
