package database

import (
	"testing"
)

func crudSetupStore(t *testing.T) *SQLiteStore {
	t.Helper()
	store := migrateTestStore(t)
	src := writeJSONDB(t, minimalRoot())
	if _, err := store.MigrateFromJSON(src, MigrationOptions{}); err != nil {
		t.Fatalf("setup migrate: %v", err)
	}
	return store
}

func TestUpsertVideo_InsertsNewVideoWithLinks(t *testing.T) {
	store := crudSetupStore(t)

	v := &VideoData{
		Code:      "NEW-001",
		Title:     "new video",
		Studio:    "FALENO",
		Actresses: []string{"佐藤亞美"},
		UpdatedAt: "2026-06-01T00:00:00Z",
		Metadata:  Metadata{Source: "test", Confidence: 0.5},
	}
	if err := store.UpsertVideo("NEW-001", v); err != nil {
		t.Fatalf("UpsertVideo: %v", err)
	}

	var title string
	if err := store.db.QueryRow(`SELECT title FROM videos WHERE code='NEW-001'`).Scan(&title); err != nil {
		t.Fatalf("read back NEW-001: %v", err)
	}
	if title != "new video" {
		t.Errorf("title = %q, want new video", title)
	}

	var linkActressID string
	if err := store.db.QueryRow(
		`SELECT actress_id FROM video_actress_links WHERE video_code='NEW-001'`,
	).Scan(&linkActressID); err != nil {
		t.Fatalf("read link: %v", err)
	}
	if linkActressID != "sato-ami" {
		t.Errorf("actress_id = %q, want sato-ami", linkActressID)
	}
}

func TestUpsertVideo_UpdatesExistingVideoAndRebuildsLinks(t *testing.T) {
	store := crudSetupStore(t)

	// STARS-707 had one actress (tanaka-minami). Update to two different
	// actresses; old link must be wiped.
	updated := &VideoData{
		Code:      "STARS-707",
		Title:     "rewritten",
		Studio:    "S1",
		Actresses: []string{"佐藤亞美", "鈴木花子"},
		UpdatedAt: "2026-06-01T00:00:00Z",
	}
	if err := store.UpsertVideo("STARS-707", updated); err != nil {
		t.Fatalf("UpsertVideo: %v", err)
	}

	rows, err := store.db.Query(
		`SELECT actress_id, ordinal FROM video_actress_links
		  WHERE video_code='STARS-707' ORDER BY ordinal`,
	)
	if err != nil {
		t.Fatalf("query links: %v", err)
	}
	defer rows.Close()
	var ids []string
	for rows.Next() {
		var id string
		var ord int
		if err := rows.Scan(&id, &ord); err != nil {
			t.Fatalf("scan: %v", err)
		}
		ids = append(ids, id)
	}
	want := []string{"sato-ami", "suzuki-hanako"}
	if !equalStringSlices(ids, want) {
		t.Errorf("STARS-707 links = %v, want %v", ids, want)
	}

	var title string
	if err := store.db.QueryRow(`SELECT title FROM videos WHERE code='STARS-707'`).Scan(&title); err != nil {
		t.Fatalf("read title: %v", err)
	}
	if title != "rewritten" {
		t.Errorf("title = %q, want rewritten", title)
	}
}

func TestUpsertVideo_ResolvesAlias(t *testing.T) {
	store := crudSetupStore(t)

	// tanaka-minami has alias "田中みなみ".
	v := &VideoData{
		Code:      "ALIAS-001",
		Title:     "alias test",
		Actresses: []string{"田中みなみ"},
		UpdatedAt: "2026-06-01T00:00:00Z",
	}
	if err := store.UpsertVideo("ALIAS-001", v); err != nil {
		t.Fatalf("UpsertVideo: %v", err)
	}

	var actressID, displayName string
	if err := store.db.QueryRow(
		`SELECT actress_id, display_name FROM video_actress_links
		   WHERE video_code='ALIAS-001'`,
	).Scan(&actressID, &displayName); err != nil {
		t.Fatalf("read link: %v", err)
	}
	if actressID != "tanaka-minami" {
		t.Errorf("actress_id = %q, want tanaka-minami", actressID)
	}
	if displayName != "田中みなみ" {
		t.Errorf("display_name = %q, want 田中みなみ (alias preserved)", displayName)
	}
}

func TestUpsertVideo_SkipsUnresolvedActressName(t *testing.T) {
	store := crudSetupStore(t)

	v := &VideoData{
		Code:      "UNKNOWN-001",
		Title:     "unknown actress",
		Actresses: []string{"完全不存在的名字"},
		UpdatedAt: "2026-06-01T00:00:00Z",
	}
	if err := store.UpsertVideo("UNKNOWN-001", v); err != nil {
		t.Fatalf("UpsertVideo: %v (should NOT fail on unknown actress, only skip link)", err)
	}

	var linkCount int
	if err := store.db.QueryRow(
		`SELECT COUNT(*) FROM video_actress_links WHERE video_code='UNKNOWN-001'`,
	).Scan(&linkCount); err != nil {
		t.Fatalf("count links: %v", err)
	}
	if linkCount != 0 {
		t.Errorf("link rows = %d, want 0 (unresolved name should be skipped)", linkCount)
	}

	var videoCount int
	if err := store.db.QueryRow(
		`SELECT COUNT(*) FROM videos WHERE code='UNKNOWN-001'`,
	).Scan(&videoCount); err != nil {
		t.Fatalf("count videos: %v", err)
	}
	if videoCount != 1 {
		t.Errorf("video row = %d, want 1 (video must still upsert)", videoCount)
	}
}

func TestDeleteVideo_CascadesLinks(t *testing.T) {
	store := crudSetupStore(t)

	if err := store.DeleteVideo("MIDV-567"); err != nil {
		t.Fatalf("DeleteVideo: %v", err)
	}
	var videoCount, linkCount int
	if err := store.db.QueryRow(
		`SELECT COUNT(*) FROM videos WHERE code='MIDV-567'`,
	).Scan(&videoCount); err != nil {
		t.Fatalf("count: %v", err)
	}
	if videoCount != 0 {
		t.Errorf("video count = %d, want 0", videoCount)
	}
	if err := store.db.QueryRow(
		`SELECT COUNT(*) FROM video_actress_links WHERE video_code='MIDV-567'`,
	).Scan(&linkCount); err != nil {
		t.Fatalf("count: %v", err)
	}
	if linkCount != 0 {
		t.Errorf("link count = %d, want 0 (FK CASCADE)", linkCount)
	}
}

func TestDeleteVideo_IsIdempotent(t *testing.T) {
	store := crudSetupStore(t)
	if err := store.DeleteVideo("NEVER-EXISTED"); err != nil {
		t.Errorf("DeleteVideo on absent code: %v", err)
	}
}

func TestUpsertActress_InsertsThenUpdates(t *testing.T) {
	store := crudSetupStore(t)

	a := &ActressData{
		ID:        "new-actress",
		Name:      "新女優",
		Aliases:   []string{"a1", "a2"},
		CreatedAt: "2026-06-01T00:00:00Z",
		UpdatedAt: "2026-06-01T00:00:00Z",
	}
	if err := store.UpsertActress(a); err != nil {
		t.Fatalf("UpsertActress insert: %v", err)
	}

	a.Name = "改名後"
	a.Aliases = []string{"a3"} // alias 集合縮減 — wipe-then-insert 應反映
	if err := store.UpsertActress(a); err != nil {
		t.Fatalf("UpsertActress update: %v", err)
	}

	var name string
	if err := store.db.QueryRow(
		`SELECT name FROM actresses WHERE id='new-actress'`,
	).Scan(&name); err != nil {
		t.Fatalf("read name: %v", err)
	}
	if name != "改名後" {
		t.Errorf("name = %q, want 改名後", name)
	}

	rows, err := store.db.Query(
		`SELECT alias FROM actress_aliases WHERE actress_id='new-actress' ORDER BY alias`,
	)
	if err != nil {
		t.Fatalf("query aliases: %v", err)
	}
	defer rows.Close()
	var aliases []string
	for rows.Next() {
		var al string
		if err := rows.Scan(&al); err != nil {
			t.Fatalf("scan: %v", err)
		}
		aliases = append(aliases, al)
	}
	if !equalStringSlices(aliases, []string{"a3"}) {
		t.Errorf("aliases = %v, want [a3] (wipe-then-insert)", aliases)
	}
}

func TestDeleteActress_CascadesAliasesAndLinks(t *testing.T) {
	store := crudSetupStore(t)

	if err := store.DeleteActress("tanaka-minami"); err != nil {
		t.Fatalf("DeleteActress: %v", err)
	}
	var n int
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM actresses WHERE id='tanaka-minami'`).Scan(&n); err != nil {
		t.Fatalf("count: %v", err)
	}
	if n != 0 {
		t.Errorf("actresses count = %d, want 0", n)
	}
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM actress_aliases WHERE actress_id='tanaka-minami'`).Scan(&n); err != nil {
		t.Fatalf("count: %v", err)
	}
	if n != 0 {
		t.Errorf("alias count = %d, want 0", n)
	}
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM video_actress_links WHERE actress_id='tanaka-minami'`).Scan(&n); err != nil {
		t.Fatalf("count: %v", err)
	}
	if n != 0 {
		t.Errorf("link count = %d, want 0", n)
	}
}
