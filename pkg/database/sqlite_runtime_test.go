package database

import (
	"errors"
	"path/filepath"
	"strings"
	"testing"
)

// runtimeTestStore is the runtime-API counterpart to crudSetupStore: it
// reuses migrateTestStore + the minimalRoot fixture so AddVideo /
// UpdateVideo / Merge* / GetActress tests can run against a populated
// SQLite shape rather than an empty one.
func runtimeTestStore(t *testing.T) *SQLiteStore {
	t.Helper()
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("setup migrate: %v", err)
	}
	return store
}

// --- AddVideo -----------------------------------------------------------

func TestAddVideo_InsertsRowAndStampsTimestamps(t *testing.T) {
	store := runtimeTestStore(t)

	v := &Video{
		Code:      "NEW-100",
		Title:     "fresh",
		Studio:    "FALENO",
		Actresses: []string{"佐藤亞美"},
	}
	if err := store.AddVideo(v); err != nil {
		t.Fatalf("AddVideo: %v", err)
	}
	if v.CreatedAt == "" || v.UpdatedAt == "" {
		t.Errorf("AddVideo did not stamp timestamps: created=%q updated=%q", v.CreatedAt, v.UpdatedAt)
	}

	got, err := store.GetVideo("NEW-100")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	if got.Title != "fresh" {
		t.Errorf("title = %q, want fresh", got.Title)
	}
	if len(got.Actresses) != 1 || got.Actresses[0] != "佐藤亞美" {
		t.Errorf("actresses = %v, want [佐藤亞美]", got.Actresses)
	}
}

func TestAddVideo_AutoCreatesUnknownActress(t *testing.T) {
	store := runtimeTestStore(t)

	v := &Video{
		Code:      "NEW-200",
		Title:     "auto",
		Actresses: []string{"新女優A"},
	}
	if err := store.AddVideo(v); err != nil {
		t.Fatalf("AddVideo: %v", err)
	}
	// Link must have been created against a synth actress whose id has
	// the AutoActressIDPrefix.
	var actressID string
	if err := store.db.QueryRow(
		`SELECT actress_id FROM video_actress_links WHERE video_code='NEW-200'`,
	).Scan(&actressID); err != nil {
		t.Fatalf("read link: %v", err)
	}
	if !strings.HasPrefix(actressID, AutoActressIDPrefix) {
		t.Errorf("actress_id = %q, want %s* prefix", actressID, AutoActressIDPrefix)
	}
}

func TestAddVideo_RejectsNilOrEmptyOrClosedStore(t *testing.T) {
	store := runtimeTestStore(t)
	if err := store.AddVideo(nil); err == nil {
		t.Error("AddVideo(nil) returned nil, want error")
	}
	if err := store.AddVideo(&Video{}); !errors.Is(err, ErrInvalidCode) {
		t.Errorf("AddVideo(empty code) = %v, want ErrInvalidCode", err)
	}

	closed := &SQLiteStore{}
	if err := closed.AddVideo(&Video{Code: "X"}); !errors.Is(err, ErrSQLiteStoreClosed) {
		t.Errorf("closed.AddVideo = %v, want ErrSQLiteStoreClosed", err)
	}
}

// --- UpdateVideo --------------------------------------------------------

func TestUpdateVideo_ExistingRowPreservesCreatedAt(t *testing.T) {
	store := runtimeTestStore(t)

	before, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("GetVideo before: %v", err)
	}
	origCreated := before.CreatedAt

	v := &Video{
		Code:      "STARS-707",
		Title:     "rewrite",
		Studio:    "S1",
		Actresses: []string{"田中美奈実"},
	}
	if err := store.UpdateVideo("STARS-707", v); err != nil {
		t.Fatalf("UpdateVideo: %v", err)
	}
	after, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("GetVideo after: %v", err)
	}
	if after.CreatedAt != origCreated {
		t.Errorf("CreatedAt changed: before=%q after=%q", origCreated, after.CreatedAt)
	}
	if after.Title != "rewrite" {
		t.Errorf("Title not updated: %q", after.Title)
	}
}

func TestUpdateVideo_NewRowStampsCreatedAt(t *testing.T) {
	store := runtimeTestStore(t)

	v := &Video{
		Code:      "GONE-001",
		Title:     "brand new",
		Actresses: []string{"田中美奈実"},
	}
	if err := store.UpdateVideo("GONE-001", v); err != nil {
		t.Fatalf("UpdateVideo: %v", err)
	}
	if v.CreatedAt == "" {
		t.Error("UpdateVideo did not stamp CreatedAt for new row")
	}
}

func TestUpdateVideo_RejectsBadInput(t *testing.T) {
	store := runtimeTestStore(t)
	if err := store.UpdateVideo("", &Video{}); !errors.Is(err, ErrInvalidCode) {
		t.Errorf("UpdateVideo empty code = %v, want ErrInvalidCode", err)
	}
	if err := store.UpdateVideo("X", nil); err == nil {
		t.Error("UpdateVideo nil video returned nil, want error")
	}
	closed := &SQLiteStore{}
	if err := closed.UpdateVideo("X", &Video{}); !errors.Is(err, ErrSQLiteStoreClosed) {
		t.Errorf("closed.UpdateVideo = %v, want ErrSQLiteStoreClosed", err)
	}
}

// --- UpdateVideoFields --------------------------------------------------

func TestUpdateVideoFields_AppliesHandlerAndPreservesUntouched(t *testing.T) {
	store := runtimeTestStore(t)

	if err := store.UpdateVideoFields("STARS-707", map[string]any{
		"id":         "video-id-42",
		"created_at": "1999-01-01T00:00:00Z",
		"updated_at": "2026-06-01T01:02:03Z",
	}); err != nil {
		t.Fatalf("UpdateVideoFields: %v", err)
	}

	got, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	if got.ID != "video-id-42" {
		t.Errorf("ID = %q, want video-id-42", got.ID)
	}
	if got.CreatedAt != "1999-01-01T00:00:00Z" {
		t.Errorf("CreatedAt = %q, want preserved 1999-...", got.CreatedAt)
	}
	if got.UpdatedAt != "2026-06-01T01:02:03Z" {
		t.Errorf("UpdatedAt = %q, want explicit override", got.UpdatedAt)
	}
	if got.Title != "A" {
		t.Errorf("Title clobbered: %q (want A from fixture)", got.Title)
	}
}

func TestUpdateVideoFields_MissingRowIsNotFound(t *testing.T) {
	store := runtimeTestStore(t)
	err := store.UpdateVideoFields("NOPE", map[string]any{"id": "x"})
	if !errors.Is(err, ErrNotFound) {
		t.Errorf("UpdateVideoFields missing = %v, want ErrNotFound", err)
	}
}

func TestUpdateVideoFields_RejectsBadInput(t *testing.T) {
	store := runtimeTestStore(t)
	if err := store.UpdateVideoFields("", nil); !errors.Is(err, ErrInvalidCode) {
		t.Errorf("UpdateVideoFields empty code = %v, want ErrInvalidCode", err)
	}
	closed := &SQLiteStore{}
	if err := closed.UpdateVideoFields("X", nil); !errors.Is(err, ErrSQLiteStoreClosed) {
		t.Errorf("closed.UpdateVideoFields = %v, want ErrSQLiteStoreClosed", err)
	}
}

func TestApplyVideoFieldUpdates_StampsUpdatedAtWhenAbsent(t *testing.T) {
	v := &VideoData{Code: "X"}
	applyVideoFieldUpdates(v, map[string]any{"id": "abc"})
	if v.ID != "abc" {
		t.Errorf("ID not applied: %q", v.ID)
	}
	if v.UpdatedAt == "" {
		t.Error("UpdatedAt not stamped when absent from updates")
	}
}

// --- GetActress / ListActresses ----------------------------------------

func TestGetActress_ReturnsAliasesAndVideoCount(t *testing.T) {
	store := runtimeTestStore(t)

	a, err := store.GetActress("tanaka-minami")
	if err != nil {
		t.Fatalf("GetActress: %v", err)
	}
	if a.Name != "田中美奈実" {
		t.Errorf("Name = %q, want 田中美奈実", a.Name)
	}
	if len(a.Aliases) != 1 || a.Aliases[0] != "田中みなみ" {
		t.Errorf("Aliases = %v, want [田中みなみ]", a.Aliases)
	}
	if a.VideoCount != 2 {
		t.Errorf("VideoCount = %d, want 2", a.VideoCount)
	}
}

func TestGetActress_NotFoundIsErrNotFound(t *testing.T) {
	store := runtimeTestStore(t)
	_, err := store.GetActress("nope")
	if !errors.Is(err, ErrNotFound) {
		t.Errorf("GetActress missing = %v, want ErrNotFound", err)
	}
}

func TestGetActress_RejectsBadInput(t *testing.T) {
	store := runtimeTestStore(t)
	if _, err := store.GetActress(""); !errors.Is(err, ErrInvalidCode) {
		t.Errorf("GetActress empty id = %v, want ErrInvalidCode", err)
	}
	closed := &SQLiteStore{}
	if _, err := closed.GetActress("X"); !errors.Is(err, ErrSQLiteStoreClosed) {
		t.Errorf("closed.GetActress = %v, want ErrSQLiteStoreClosed", err)
	}
}

func TestListActresses_ReturnsAllIDs(t *testing.T) {
	store := runtimeTestStore(t)

	ids, err := store.ListActresses()
	if err != nil {
		t.Fatalf("ListActresses: %v", err)
	}
	if len(ids) != 3 {
		t.Errorf("len = %d, want 3", len(ids))
	}
	want := map[string]bool{"tanaka-minami": true, "sato-ami": true, "suzuki-hanako": true}
	for _, id := range ids {
		if !want[id] {
			t.Errorf("unexpected id %q", id)
		}
	}
}

func TestListActresses_EmptyStoreReturnsEmptySlice(t *testing.T) {
	store := migrateTestStore(t)
	ids, err := store.ListActresses()
	if err != nil {
		t.Fatalf("ListActresses: %v", err)
	}
	if ids == nil {
		t.Error("ListActresses returned nil, want empty non-nil slice")
	}
	if len(ids) != 0 {
		t.Errorf("len = %d, want 0", len(ids))
	}
}

// --- MergeFromFile / mergeFromRoot helpers ------------------------------

// mergeSourceRoot is a minimal JSON DB intended to be MergeFromFile'd
// onto a store seeded by minimalRoot. It introduces one brand-new
// video + actress, one overlapping video (STARS-707) for the
// overwrite branch, and a link entry.
func mergeSourceRoot() *DatabaseData {
	return &DatabaseData{
		SchemaVersion: SchemaVersion,
		Videos: map[string]*VideoData{
			"NEW-300": {
				Code:      "NEW-300",
				Title:     "merge new",
				Studio:    "S1",
				Actresses: []string{"merge新人"},
				CreatedAt: "2026-07-01T00:00:00Z",
				UpdatedAt: "2026-07-01T00:00:00Z",
			},
			"STARS-707": {
				Code:      "STARS-707",
				Title:     "merge overwrite",
				Studio:    "S1",
				Actresses: []string{"田中美奈実"},
				UpdatedAt: "2026-07-01T00:00:00Z",
			},
		},
		Actresses: map[string]*ActressData{
			"merge-new": {ID: "merge-new", Name: "merge新人"},
		},
		Links: []VideoActressLink{
			{VideoCode: "NEW-300", ActressID: "merge-new", RoleType: "主演", Timestamp: "2026-07-01T00:00:00Z"},
		},
	}
}

func TestMergeFromFile_AddsNewAndSkipsExistingWithoutOverwrite(t *testing.T) {
	store := runtimeTestStore(t)
	src := writeJSONDB(t, mergeSourceRoot())

	stats, err := store.MergeFromFile(src, false /* overwrite */)
	if err != nil {
		t.Fatalf("MergeFromFile: %v", err)
	}
	if stats.VideosAdded != 1 {
		t.Errorf("VideosAdded = %d, want 1", stats.VideosAdded)
	}
	if stats.VideosSkipped != 1 {
		t.Errorf("VideosSkipped = %d, want 1 (STARS-707 already exists)", stats.VideosSkipped)
	}
	if stats.VideosUpdated != 0 {
		t.Errorf("VideosUpdated = %d, want 0", stats.VideosUpdated)
	}
	if stats.ActressesAdded != 1 {
		t.Errorf("ActressesAdded = %d, want 1 (merge-new)", stats.ActressesAdded)
	}
	if stats.LinksAdded != 1 {
		t.Errorf("LinksAdded = %d, want 1", stats.LinksAdded)
	}

	// STARS-707 must still have the original "A" title — not overwritten.
	got, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("GetVideo STARS-707: %v", err)
	}
	if got.Title != "A" {
		t.Errorf("STARS-707 Title = %q, want preserved A", got.Title)
	}
}

func TestMergeFromFile_OverwriteUpdatesExisting(t *testing.T) {
	store := runtimeTestStore(t)
	src := writeJSONDB(t, mergeSourceRoot())

	stats, err := store.MergeFromFile(src, true /* overwrite */)
	if err != nil {
		t.Fatalf("MergeFromFile: %v", err)
	}
	if stats.VideosUpdated != 1 {
		t.Errorf("VideosUpdated = %d, want 1 (STARS-707)", stats.VideosUpdated)
	}
	if stats.VideosAdded != 1 {
		t.Errorf("VideosAdded = %d, want 1 (NEW-300)", stats.VideosAdded)
	}
	if stats.VideosSkipped != 0 {
		t.Errorf("VideosSkipped = %d, want 0", stats.VideosSkipped)
	}

	got, err := store.GetVideo("STARS-707")
	if err != nil {
		t.Fatalf("GetVideo: %v", err)
	}
	if got.Title != "merge overwrite" {
		t.Errorf("Title = %q, want merge overwrite", got.Title)
	}
}

func TestMergeFromFile_RejectsBadInput(t *testing.T) {
	store := runtimeTestStore(t)
	if _, err := store.MergeFromFile("   ", false); err == nil {
		t.Error("MergeFromFile empty path returned nil, want error")
	}
	closed := &SQLiteStore{}
	if _, err := closed.MergeFromFile("x", false); !errors.Is(err, ErrSQLiteStoreClosed) {
		t.Errorf("closed.MergeFromFile = %v, want ErrSQLiteStoreClosed", err)
	}
}

func TestMergeFromFile_EmptyLinksSkipsTransaction(t *testing.T) {
	store := runtimeTestStore(t)
	src := writeJSONDB(t, &DatabaseData{
		SchemaVersion: SchemaVersion,
		Videos: map[string]*VideoData{
			"NEW-NOLINK": {
				Code: "NEW-NOLINK", Title: "no link", Studio: "S1",
				UpdatedAt: "2026-07-01T00:00:00Z",
			},
		},
	})

	stats, err := store.MergeFromFile(src, false)
	if err != nil {
		t.Fatalf("MergeFromFile: %v", err)
	}
	if stats.LinksAdded != 0 {
		t.Errorf("LinksAdded = %d, want 0 (no links in source)", stats.LinksAdded)
	}
	if stats.VideosAdded != 1 {
		t.Errorf("VideosAdded = %d, want 1", stats.VideosAdded)
	}
}

// --- Journal-shaped no-ops ----------------------------------------------

func TestJournalShapedNoOpsAreNotErrors(t *testing.T) {
	store := runtimeTestStore(t)
	if err := store.Compact(); err != nil {
		t.Errorf("Compact: %v", err)
	}
	done, err := store.CompactIfNeeded()
	if err != nil {
		t.Errorf("CompactIfNeeded: %v", err)
	}
	if done {
		t.Errorf("CompactIfNeeded = true, want false (SQLite has no journal)")
	}
}

// --- DataDir helpers ----------------------------------------------------

func TestSetDataDir_StoresAndReturnsValue(t *testing.T) {
	store := runtimeTestStore(t)
	if store.DataDir() != "" {
		t.Errorf("initial DataDir = %q, want empty (opened via OpenSQLiteStore)", store.DataDir())
	}
	store.SetDataDir(`C:\fake\dir`)
	if store.DataDir() != `C:\fake\dir` {
		t.Errorf("DataDir = %q, want C:\\fake\\dir", store.DataDir())
	}
}

func TestDataDirRoot_FallsBackToSQLiteFileDir(t *testing.T) {
	store := runtimeTestStore(t)
	want := filepath.Dir(store.Path())
	if got := store.dataDirRoot(); got != want {
		t.Errorf("dataDirRoot = %q, want %q (parent of SQLite path)", got, want)
	}
	store.SetDataDir(`C:\custom`)
	if got := store.dataDirRoot(); got != `C:\custom` {
		t.Errorf("after SetDataDir, dataDirRoot = %q, want C:\\custom", got)
	}
}

func TestDataDirRoot_NilReceiverReturnsEmpty(t *testing.T) {
	var s *SQLiteStore
	if got := s.dataDirRoot(); got != "" {
		t.Errorf("nil receiver dataDirRoot = %q, want empty", got)
	}
}

// --- isEmpty ------------------------------------------------------------

func TestIsEmpty_FreshStoreIsEmpty(t *testing.T) {
	store := migrateTestStore(t)
	empty, err := store.isEmpty()
	if err != nil {
		t.Fatalf("isEmpty: %v", err)
	}
	if !empty {
		t.Error("fresh store reported non-empty")
	}
}

func TestIsEmpty_PopulatedStoreIsNotEmpty(t *testing.T) {
	store := runtimeTestStore(t)
	empty, err := store.isEmpty()
	if err != nil {
		t.Fatalf("isEmpty: %v", err)
	}
	if empty {
		t.Error("populated store reported empty")
	}
}

func TestIsEmpty_ClosedStoreReportsError(t *testing.T) {
	closed := &SQLiteStore{}
	if _, err := closed.isEmpty(); !errors.Is(err, ErrSQLiteStoreClosed) {
		t.Errorf("closed.isEmpty err = %v, want ErrSQLiteStoreClosed", err)
	}
}

// --- BackupCreate / BackupList / BackupCleanup -------------------------

func TestBackupCreate_WritesSnapshotInDataDirBackupTree(t *testing.T) {
	store := runtimeTestStore(t)
	dataDir := filepath.Dir(store.Path())
	store.SetDataDir(dataDir)

	dest, err := store.BackupCreate()
	if err != nil {
		t.Fatalf("BackupCreate: %v", err)
	}
	if !strings.HasPrefix(filepath.Base(dest), "backup_") {
		t.Errorf("dest = %q, want backup_<ts>.sqlite prefix", dest)
	}
	if !strings.HasSuffix(dest, ".sqlite") {
		t.Errorf("dest = %q, want .sqlite suffix", dest)
	}
	if !strings.HasPrefix(dest, filepath.Join(dataDir, "backup")) {
		t.Errorf("dest = %q, want under %s/backup", dest, dataDir)
	}
}

func TestBackupCreate_ClosedStoreReportsClosed(t *testing.T) {
	closed := &SQLiteStore{}
	if _, err := closed.BackupCreate(); !errors.Is(err, ErrSQLiteStoreClosed) {
		t.Errorf("closed.BackupCreate = %v, want ErrSQLiteStoreClosed", err)
	}
}

func TestBackupList_MissingBackupDirIsEmpty(t *testing.T) {
	store := runtimeTestStore(t)
	store.SetDataDir(filepath.Dir(store.Path())) // backup/ does not exist yet
	paths, err := store.BackupList()
	if err != nil {
		t.Fatalf("BackupList: %v", err)
	}
	if len(paths) != 0 {
		t.Errorf("paths = %v, want empty", paths)
	}
}

func TestBackupCleanup_MissingDirIsZero(t *testing.T) {
	store := runtimeTestStore(t)
	store.SetDataDir(filepath.Dir(store.Path()))
	deleted, err := store.BackupCleanup(7, 5)
	if err != nil {
		t.Fatalf("BackupCleanup: %v", err)
	}
	if deleted != 0 {
		t.Errorf("deleted = %d, want 0 (no backup dir)", deleted)
	}
}

// --- Stats helpers ------------------------------------------------------

func TestGetActressStats_ReturnsCountsSortedDescending(t *testing.T) {
	store := runtimeTestStore(t)

	stats, err := store.GetActressStats()
	if err != nil {
		t.Fatalf("GetActressStats: %v", err)
	}
	// fixture: tanaka-minami → 2 videos, sato-ami / suzuki-hanako → 1 each
	if len(stats) != 3 {
		t.Fatalf("len = %d, want 3", len(stats))
	}
	if got := stats[0]["actress_name"]; got != "田中美奈実" {
		t.Errorf("top = %v, want 田中美奈実 (tanaka-minami has 2 videos)", got)
	}
	if got, _ := stats[0]["video_count"].(int); got != 2 {
		t.Errorf("top video_count = %d, want 2", got)
	}
}

func TestGetActressStats_ClosedStore(t *testing.T) {
	closed := &SQLiteStore{}
	if _, err := closed.GetActressStats(); !errors.Is(err, ErrSQLiteStoreClosed) {
		t.Errorf("closed.GetActressStats = %v, want ErrSQLiteStoreClosed", err)
	}
}

func TestGetStudioStats_AggregatesByStudioDescending(t *testing.T) {
	store := runtimeTestStore(t)

	stats, err := store.GetStudioStats()
	if err != nil {
		t.Fatalf("GetStudioStats: %v", err)
	}
	// fixture: S1 → 2 videos (STARS-707, SSIS-001), MOODYZ → 1 (MIDV-567)
	if len(stats) != 2 {
		t.Fatalf("len = %d, want 2 studios", len(stats))
	}
	if got := stats[0]["studio"]; got != "S1" {
		t.Errorf("top studio = %v, want S1 (2 videos)", got)
	}
	if got, _ := stats[0]["video_count"].(int); got != 2 {
		t.Errorf("top video_count = %d, want 2", got)
	}
}

func TestGetStudioStats_ClosedStore(t *testing.T) {
	closed := &SQLiteStore{}
	if _, err := closed.GetStudioStats(); !errors.Is(err, ErrSQLiteStoreClosed) {
		t.Errorf("closed.GetStudioStats = %v, want ErrSQLiteStoreClosed", err)
	}
}

func TestGetActressPrimaryStudio_ReturnsTopStudio(t *testing.T) {
	store := runtimeTestStore(t)
	// tanaka-minami appears in STARS-707 (S1) and SSIS-001 (S1) → S1.
	got := store.GetActressPrimaryStudio("田中美奈実")
	if got != "S1" {
		t.Errorf("GetActressPrimaryStudio = %q, want S1", got)
	}
}

func TestGetActressPrimaryStudio_ViaAliasLookup(t *testing.T) {
	store := runtimeTestStore(t)
	// "田中みなみ" is an alias of tanaka-minami in the fixture; same S1.
	if got := store.GetActressPrimaryStudio("田中みなみ"); got != "S1" {
		t.Errorf("alias path = %q, want S1", got)
	}
}

// --- BackupRestore extension routing -----------------------------------

func TestBackupRestore_RoutesSQLiteExtensionToFileSwap(t *testing.T) {
	store := runtimeTestStore(t)
	store.SetDataDir(filepath.Dir(store.Path()))
	dest, err := store.BackupCreate()
	if err != nil {
		t.Fatalf("BackupCreate: %v", err)
	}
	// BackupRestore for .sqlite closes the store + file-swaps the target.
	if err := store.BackupRestore(dest); err != nil {
		t.Fatalf("BackupRestore(.sqlite): %v", err)
	}
	// Re-open and confirm the rows are still there (round trip).
	reopened, err := OpenSQLiteStore(store.Path())
	if err != nil {
		t.Fatalf("re-open after restore: %v", err)
	}
	defer reopened.Close()
	codes, err := reopened.ListVideos()
	if err != nil {
		t.Fatalf("ListVideos: %v", err)
	}
	if len(codes) != 3 {
		t.Errorf("len = %d, want 3 (fixture)", len(codes))
	}
}

func TestBackupRestore_RoutesJSONExtensionToResync(t *testing.T) {
	store := runtimeTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	// Rename src.json into .json target (writeJSONDB already uses .json).
	if err := store.BackupRestore(src); err != nil {
		t.Fatalf("BackupRestore(.json): %v", err)
	}
	// resync wipes + reloads; counts should match the fixture.
	codes, err := store.ListVideos()
	if err != nil {
		t.Fatalf("ListVideos: %v", err)
	}
	if len(codes) != 3 {
		t.Errorf("len = %d, want 3 (fixture round trip)", len(codes))
	}
}

func TestBackupRestore_RejectsUnsupportedExtension(t *testing.T) {
	store := runtimeTestStore(t)
	if err := store.BackupRestore("backup.tar.gz"); err == nil {
		t.Error("BackupRestore unsupported extension returned nil, want error")
	}
	closed := &SQLiteStore{}
	if err := closed.BackupRestore("x.sqlite"); !errors.Is(err, ErrSQLiteStoreClosed) {
		t.Errorf("closed.BackupRestore = %v, want ErrSQLiteStoreClosed", err)
	}
}

func TestGetActressPrimaryStudio_EmptyInputsReturnEmpty(t *testing.T) {
	store := runtimeTestStore(t)
	if got := store.GetActressPrimaryStudio(""); got != "" {
		t.Errorf("empty name = %q, want empty", got)
	}
	if got := store.GetActressPrimaryStudio("   "); got != "" {
		t.Errorf("whitespace name = %q, want empty", got)
	}
	if got := store.GetActressPrimaryStudio("nobody"); got != "" {
		t.Errorf("unknown name = %q, want empty", got)
	}

	var closed *SQLiteStore
	if got := closed.GetActressPrimaryStudio("x"); got != "" {
		t.Errorf("nil receiver = %q, want empty", got)
	}
}
