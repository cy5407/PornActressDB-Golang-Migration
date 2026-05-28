package database

import (
	"database/sql"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"actress-classifier/pkg/safefile"
)

// Phase C2 — SQLite-only runtime helpers.
//
// pkg/database/sqlite_runtime.go layers the JSONDatabase-compatible
// surface (AddVideo, UpdateVideo, GetStats, backup family, …) onto
// *SQLiteStore so the rest of the codebase (cmd/scanner, wails-app,
// Python CLI contract) can talk to a SQLite-only runtime without
// learning a new vocabulary. The lower-level CRUD primitives still
// live in sqlite_crud.go / sqlite_read_store.go; this file only adds
// the strict-semantics, timestamp-management and metadata helpers that
// used to live on JSONDatabase / DualWriteStore.

// dataDirRoot returns the JSON-compatible data directory that owns
// this SQLite file. NewStore sets it via setDataDir; for SQLite stores
// opened directly through OpenSQLiteStore (tests, db migrate-from-json,
// …) it falls back to the SQLite file's parent so the backup family
// still resolves a sensible location.
func (s *SQLiteStore) dataDirRoot() string {
	if s == nil {
		return ""
	}
	if s.dataDir != "" {
		return s.dataDir
	}
	return filepath.Dir(s.path)
}

// SetDataDir attaches the JSON-compatible data directory to the store.
// The runtime backup family (BackupCreate / BackupList / BackupCleanup)
// keys all paths off this value so SQLite-only callers land in the same
// <data-dir>/backup/ tree the legacy JSON flow used.
func (s *SQLiteStore) SetDataDir(dataDir string) {
	if s == nil {
		return
	}
	s.dataDir = dataDir
}

// DataDir reports the directory passed to SetDataDir (or empty when
// the caller opened the store via OpenSQLiteStore directly).
func (s *SQLiteStore) DataDir() string {
	if s == nil {
		return ""
	}
	return s.dataDir
}

// isEmpty reports whether the videos / actresses tables are both empty.
// Used by NewStore to decide whether a bootstrap migrate-from-json
// should run on first open against an empty SQLite file.
func (s *SQLiteStore) isEmpty() (bool, error) {
	if s == nil || s.db == nil {
		return false, ErrSQLiteStoreClosed
	}
	var n int
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM videos`).Scan(&n); err != nil {
		return false, fmt.Errorf("count videos: %w", err)
	}
	if n > 0 {
		return false, nil
	}
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM actresses`).Scan(&n); err != nil {
		return false, fmt.Errorf("count actresses: %w", err)
	}
	return n == 0, nil
}

// --- Video runtime API --------------------------------------------------

// AddVideo mirrors JSONDatabase.AddVideo: created_at/updated_at are
// stamped with now before the upsert. Pre-existing rows are overwritten
// — the JSON-side implementation never enforced strict "fail on
// existing" semantics, so we keep the same observable contract.
//
// Unknown video.actresses[] names are auto-promoted to synthetic
// actress entities (StableActressID / auto_<sha1>) inside the same
// transaction so the runtime never silently drops actress data the way
// the strict migrate-from-json path would. The JSON-side equivalent
// effectively did the same thing by storing free-form names against
// the video map — there were no link rows to drop.
func (s *SQLiteStore) AddVideo(v *Video) error {
	if s == nil || s.db == nil {
		return ErrSQLiteStoreClosed
	}
	if v == nil {
		return errors.New("video cannot be nil")
	}
	code := v.GetCode()
	if code == "" {
		return ErrInvalidCode
	}
	now := time.Now().UTC().Format(ISODateTimeFormat)
	v.Code = code
	v.CreatedAt = now
	v.UpdatedAt = now
	return s.upsertVideoRuntime(code, v)
}

// UpdateVideo mirrors JSONDatabase.UpdateVideo: updated_at is refreshed
// to now; created_at is preserved when an existing row is present and
// stamped to now when the row is new. Returns ErrInvalidCode when code
// is empty. Auto-creates unknown actresses (see AddVideo).
func (s *SQLiteStore) UpdateVideo(code string, v *Video) error {
	if s == nil || s.db == nil {
		return ErrSQLiteStoreClosed
	}
	if code == "" {
		return ErrInvalidCode
	}
	if v == nil {
		return errors.New("video cannot be nil")
	}
	now := time.Now().UTC().Format(ISODateTimeFormat)
	v.UpdatedAt = now
	v.Code = code
	existing, err := s.GetVideo(code)
	if err != nil && !errors.Is(err, ErrNotFound) {
		return err
	}
	if existing == nil {
		v.CreatedAt = now
	} else if v.CreatedAt == "" {
		v.CreatedAt = existing.CreatedAt
	}
	return s.upsertVideoRuntime(code, v)
}

// UpdateVideoFields applies a partial update to an existing video and
// reuses the JSONDatabase field-handler map so the supported keys stay
// in lock-step. The row MUST already exist — missing rows return
// ErrNotFound, matching JSONDatabase.UpdateVideoFields.
func (s *SQLiteStore) UpdateVideoFields(code string, updates map[string]any) error {
	if s == nil || s.db == nil {
		return ErrSQLiteStoreClosed
	}
	if code == "" {
		return ErrInvalidCode
	}
	existing, err := s.GetVideo(code)
	if err != nil {
		return err
	}
	applyVideoFieldUpdates(existing, updates)
	return s.upsertVideoRuntime(code, existing)
}

// upsertVideoRuntime is the runtime cousin of UpsertVideo: it auto-
// creates actress entities for any video.actresses[] name that the
// strict lookup can't resolve. This keeps the BatchSearch / GUI write
// paths consistent with the JSON-side behaviour, where free-form
// actress strings could always be persisted against a video.
//
// Duplicate display strings inside the same actresses[] list collapse
// to one link (first occurrence wins) so the UNIQUE(video_code,
// actress_id, role_type) constraint never fires from caller-side
// dirty data. The strict migrate-from-json path still reports
// duplicates loudly — those are a data-quality signal users want to
// see, not a runtime hot path.
func (s *SQLiteStore) upsertVideoRuntime(code string, v *VideoData) error {
	tx, err := s.db.Begin()
	if err != nil {
		return fmt.Errorf("upsertVideoRuntime begin tx: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()
	if err := upsertVideoRow(tx, code, v); err != nil {
		return err
	}
	if err := rebuildLinksForVideoAutoCreate(tx, code, v); err != nil {
		return err
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("upsertVideoRuntime commit: %w", err)
	}
	committed = true
	return nil
}

func rebuildLinksForVideoAutoCreate(tx *sql.Tx, code string, v *VideoData) error {
	if _, err := tx.Exec(`DELETE FROM video_actress_links WHERE video_code = ?`, code); err != nil {
		return fmt.Errorf("wipe links for %q: %w", code, err)
	}
	if len(v.Actresses) == 0 {
		return nil
	}
	seen := make(map[string]struct{}, len(v.Actresses))
	for ordinal, display := range v.Actresses {
		trimmed := strings.TrimSpace(display)
		if trimmed == "" {
			continue
		}
		actressID, displayName, err := resolveOrSynthLinkActress(tx, trimmed, v.UpdatedAt)
		if err != nil {
			return err
		}
		if _, dup := seen[actressID]; dup {
			continue
		}
		seen[actressID] = struct{}{}
		if _, err := tx.Exec(
			`INSERT INTO video_actress_links(
				video_code, actress_id, role_type, ordinal, display_name, timestamp
			 ) VALUES(?, ?, ?, ?, ?, ?)`,
			code, actressID, RoleMain, ordinal, displayName, v.UpdatedAt,
		); err != nil {
			return fmt.Errorf("insert link %s↔%s: %w", code, actressID, err)
		}
	}
	return nil
}

// resolveOrSynthLinkActress resolves trimmed against actresses /
// actress_aliases, falling back to a synthesised entity keyed by
// StableActressID(trimmed) when nothing matches. The synth INSERT is
// idempotent (INSERT OR IGNORE) and uses v.UpdatedAt as the timestamp
// when present, otherwise current wall-clock UTC. The returned
// displayName is "" for the synth path (the row's name IS the trimmed
// display) and the alias-resolved spelling otherwise.
func resolveOrSynthLinkActress(tx *sql.Tx, trimmed, updatedAt string) (actressID, displayName string, err error) {
	id, dispName, found, err := lookupActressForLink(tx, trimmed)
	if err != nil {
		return "", "", err
	}
	if found {
		return id, dispName, nil
	}
	id = StableActressID(trimmed)
	now := updatedAt
	if now == "" {
		now = time.Now().UTC().Format(time.RFC3339)
	}
	if _, err := tx.Exec(
		`INSERT OR IGNORE INTO actresses(id, name, created_at, updated_at)
		 VALUES(?, ?, ?, ?)`,
		id, trimmed, now, now,
	); err != nil {
		return "", "", fmt.Errorf("auto-create actress %q: %w", trimmed, err)
	}
	return id, "", nil
}

// applyVideoFieldUpdates is the package-level twin of
// (*JSONDatabase).applyVideoFieldUpdates so the SQLite runtime can
// reuse the field handler table without standing up a JSONDatabase
// instance.
func applyVideoFieldUpdates(video *VideoData, updates map[string]any) {
	hasUpdatedAt := false
	for key, value := range updates {
		if key == "updated_at" {
			if v, ok := value.(string); ok {
				video.UpdatedAt = v
				hasUpdatedAt = true
			}
			continue
		}
		if handler, ok := videoFieldUpdateHandlers[key]; ok {
			handler(video, value)
		}
	}
	if !hasUpdatedAt {
		video.UpdatedAt = GetCurrentTimestamp()
	}
}

// --- Actress runtime API ------------------------------------------------

// GetActress returns the actress entity plus its aliases for the given id.
// Returns ErrNotFound when no row matches.
func (s *SQLiteStore) GetActress(id string) (*ActressData, error) {
	if s == nil || s.db == nil {
		return nil, ErrSQLiteStoreClosed
	}
	if id == "" {
		return nil, ErrInvalidCode
	}
	a := &ActressData{Aliases: []string{}}
	row := s.db.QueryRow(
		`SELECT id, name, created_at, updated_at FROM actresses WHERE id = ?`,
		id,
	)
	if err := row.Scan(&a.ID, &a.Name, &a.CreatedAt, &a.UpdatedAt); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, fmt.Errorf("sqlite GetActress %q: %w", id, err)
	}
	rows, err := s.db.Query(
		`SELECT alias FROM actress_aliases WHERE actress_id = ? ORDER BY alias`,
		id,
	)
	if err != nil {
		return nil, fmt.Errorf("sqlite GetActress aliases %q: %w", id, err)
	}
	defer rows.Close()
	for rows.Next() {
		var alias string
		if err := rows.Scan(&alias); err != nil {
			return nil, fmt.Errorf("sqlite GetActress alias scan %q: %w", id, err)
		}
		a.Aliases = append(a.Aliases, alias)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("sqlite GetActress alias rows %q: %w", id, err)
	}
	// video_count comes from the canonical view.
	var n int
	if err := s.db.QueryRow(
		`SELECT video_count FROM actress_video_counts WHERE id = ?`, id,
	).Scan(&n); err != nil && !errors.Is(err, sql.ErrNoRows) {
		return nil, fmt.Errorf("sqlite GetActress video_count %q: %w", id, err)
	}
	a.VideoCount = n
	return a, nil
}

// ListActresses returns every actress id in the store.
func (s *SQLiteStore) ListActresses() ([]string, error) {
	if s == nil || s.db == nil {
		return nil, ErrSQLiteStoreClosed
	}
	rows, err := s.db.Query(`SELECT id FROM actresses`)
	if err != nil {
		return nil, fmt.Errorf("sqlite ListActresses: %w", err)
	}
	defer rows.Close()
	ids := make([]string, 0)
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, fmt.Errorf("sqlite ListActresses scan: %w", err)
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

// --- Aggregate / stats helpers -----------------------------------------

// GetVideoCount returns the total video row count.
func (s *SQLiteStore) GetVideoCount() (int, error) {
	if s == nil || s.db == nil {
		return 0, ErrSQLiteStoreClosed
	}
	var n int
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM videos`).Scan(&n); err != nil {
		return 0, fmt.Errorf("sqlite GetVideoCount: %w", err)
	}
	return n, nil
}

// GetStats returns the dict the Python helper / Wails frontend expect.
// Every key JSONDatabase.GetStats used to emit is still here so existing
// parsers stay green. Retired journal / dirty / dual-write counters
// return zero/false values per spec § 7.1 — they are no longer
// meaningful on a SQLite-only runtime, but the keys must exist so the
// Python wrapper (and historical UI components) don't KeyError.
func (s *SQLiteStore) GetStats() (map[string]any, error) {
	if s == nil || s.db == nil {
		return nil, ErrSQLiteStoreClosed
	}
	videoCount, err := s.GetVideoCount()
	if err != nil {
		return nil, err
	}
	var actressCount int
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM actresses`).Scan(&actressCount); err != nil {
		return nil, fmt.Errorf("sqlite GetStats actresses: %w", err)
	}
	var linkCount int
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM video_actress_links`).Scan(&linkCount); err != nil {
		return nil, fmt.Errorf("sqlite GetStats links: %w", err)
	}
	meta, err := s.readDBMeta()
	if err != nil {
		return nil, err
	}

	stats := map[string]any{
		"video_count":    videoCount,
		"actress_count":  actressCount,
		"link_count":     linkCount,
		"schema_version": meta.schemaVersion,
		"created_at":     meta.createdAt,
		"updated_at":     meta.updatedAt,
		// SQLite has no journal; retired counters stay so Python helpers
		// keep parsing the stats dict uniformly. Spec § 7.1 / plan C2.
		"journal_size":               0,
		"journal_age_seconds":        0.0,
		"dirty_videos":               0,
		"dirty_actresses":            0,
		"dirty_links":                0,
		"needs_compact":              false,
		"total_videos":               videoCount,
		"sync_degraded_total":        int64(0),
		"sync_degraded_log_size":     int64(0),
		"sqlite_read_fallback_total": int64(0),
	}
	return stats, nil
}

type dbMetaSnapshot struct {
	schemaVersion string
	createdAt     string
	updatedAt     string
}

func (s *SQLiteStore) readDBMeta() (dbMetaSnapshot, error) {
	snap := dbMetaSnapshot{schemaVersion: SchemaVersion}
	rows, err := s.db.Query(`SELECT key, value FROM db_meta`)
	if err != nil {
		return snap, fmt.Errorf("sqlite readDBMeta: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var k, v string
		if err := rows.Scan(&k, &v); err != nil {
			return snap, fmt.Errorf("sqlite readDBMeta scan: %w", err)
		}
		switch k {
		case "schema_version":
			if v != "" {
				snap.schemaVersion = v
			}
		case "created_at":
			snap.createdAt = v
		case "updated_at":
			snap.updatedAt = v
		}
	}
	return snap, rows.Err()
}

// GetActressStats returns the per-actress video count list sorted by
// count descending (matching JSONDatabase.GetActressStats).
func (s *SQLiteStore) GetActressStats() ([]map[string]any, error) {
	if s == nil || s.db == nil {
		return nil, ErrSQLiteStoreClosed
	}
	rows, err := s.db.Query(`SELECT name, video_count FROM actress_video_counts`)
	if err != nil {
		return nil, fmt.Errorf("sqlite GetActressStats: %w", err)
	}
	defer rows.Close()
	results := make([]map[string]any, 0)
	for rows.Next() {
		var name string
		var count int
		if err := rows.Scan(&name, &count); err != nil {
			return nil, fmt.Errorf("sqlite GetActressStats scan: %w", err)
		}
		results = append(results, map[string]any{
			"actress_name": name,
			"video_count":  count,
		})
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("sqlite GetActressStats rows: %w", err)
	}
	sort.Slice(results, func(i, j int) bool {
		vi, _ := results[i]["video_count"].(int) //nolint:errcheck
		vj, _ := results[j]["video_count"].(int) //nolint:errcheck
		return vi > vj
	})
	return results, nil
}

// GetStudioStats returns one entry per studio with the matching video
// count. UNKNOWN / empty studios are bucketed into "UNKNOWN" to keep
// parity with JSONDatabase.GetStudioStats.
func (s *SQLiteStore) GetStudioStats() ([]map[string]any, error) {
	if s == nil || s.db == nil {
		return nil, ErrSQLiteStoreClosed
	}
	rows, err := s.db.Query(`
		SELECT CASE WHEN studio = '' THEN 'UNKNOWN' ELSE studio END AS studio,
		       COUNT(*) AS video_count
		  FROM videos
		 GROUP BY studio
	`)
	if err != nil {
		return nil, fmt.Errorf("sqlite GetStudioStats: %w", err)
	}
	defer rows.Close()
	results := make([]map[string]any, 0)
	for rows.Next() {
		var studio string
		var count int
		if err := rows.Scan(&studio, &count); err != nil {
			return nil, fmt.Errorf("sqlite GetStudioStats scan: %w", err)
		}
		results = append(results, map[string]any{
			"studio":      studio,
			"video_count": count,
		})
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("sqlite GetStudioStats rows: %w", err)
	}
	sort.Slice(results, func(i, j int) bool {
		vi, _ := results[i]["video_count"].(int) //nolint:errcheck
		vj, _ := results[j]["video_count"].(int) //nolint:errcheck
		return vi > vj
	})
	return results, nil
}

// GetActressPrimaryStudio returns the studio that hosts the most videos
// for actressName. Empty actressName, no studio data, or no match
// returns "" — same contract as JSONDatabase.GetActressPrimaryStudio.
// Ties resolve to the lexicographically smaller studio so the answer is
// stable across runs.
func (s *SQLiteStore) GetActressPrimaryStudio(actressName string) string {
	if s == nil || s.db == nil || strings.TrimSpace(actressName) == "" {
		return ""
	}
	rows, err := s.db.Query(`
		SELECT v.studio, COUNT(*)
		  FROM video_actress_links l
		  JOIN videos v ON v.code = l.video_code
		  JOIN actresses a ON a.id = l.actress_id
		 WHERE v.studio <> '' AND v.studio <> 'UNKNOWN'
		   AND (a.name = ? OR EXISTS (
		         SELECT 1 FROM actress_aliases al
		          WHERE al.actress_id = a.id AND al.alias = ?
		   ))
		 GROUP BY v.studio
	`, actressName, actressName)
	if err != nil {
		return ""
	}
	defer rows.Close()
	counts := map[string]int{}
	for rows.Next() {
		var studio string
		var n int
		if err := rows.Scan(&studio, &n); err != nil {
			return ""
		}
		counts[studio] += n
	}
	if err := rows.Err(); err != nil {
		return ""
	}
	return selectPrimaryStudio(counts)
}

// --- Lifecycle / journal-shaped no-ops ----------------------------------
//
// SQLite has no JSON-style journal so the compact family collapses to
// no-ops. They stay defined so cmd/scanner and wails-app code that used
// to call db.Save() / db.Compact() keeps compiling, and so Python /
// Wails callers can keep dispatching the same method names without
// branching on backend.

// Save is a no-op for SQLite (WAL handles durability per-write).
func (s *SQLiteStore) Save() error { return nil }

// Compact is a no-op alias kept for JSONDatabase API parity.
func (s *SQLiteStore) Compact() error { return nil }

// CompactJournal is a no-op alias kept for JSONDatabase API parity.
func (s *SQLiteStore) CompactJournal() error { return nil }

// CompactIfNeeded always reports "no compaction performed" on SQLite.
func (s *SQLiteStore) CompactIfNeeded() (bool, error) { return false, nil }

// --- Merge ---------------------------------------------------------------

// MergeFromFile imports another JSON DB into this SQLite store. The
// semantics mirror JSONDatabase.MergeFromFile:
//
//   - Videos / actresses with the same key are skipped unless
//     overwrite=true.
//   - Links are deduplicated by (video_code, actress_id, role_type,
//     timestamp).
//
// The whole import runs inside one SQLite transaction so a mid-run
// failure leaves the store unchanged.
func (s *SQLiteStore) MergeFromFile(sourceFile string, overwrite bool) (*MergeStats, error) {
	if s == nil || s.db == nil {
		return nil, ErrSQLiteStoreClosed
	}
	if strings.TrimSpace(sourceFile) == "" {
		return nil, errors.New("source file path cannot be empty")
	}
	sourceRoot, err := loadMergeSourceData(sourceFile)
	if err != nil {
		return nil, err
	}
	return s.mergeFromRoot(sourceRoot, overwrite)
}

func (s *SQLiteStore) mergeFromRoot(root *DatabaseData, overwrite bool) (*MergeStats, error) {
	stats := &MergeStats{}
	now := time.Now().UTC().Format(ISODateTimeFormat)

	// Actresses first so videos can resolve their actresses[] names.
	if err := s.mergeActressesFromRoot(root, overwrite, now, stats); err != nil {
		return nil, err
	}

	if err := s.mergeVideosFromRoot(root, overwrite, now, stats); err != nil {
		return nil, err
	}

	// Links: SQLite already enforces UNIQUE(video_code, actress_id, role_type).
	// Re-apply JSON-side overrides via the same path migrate-from-json uses.
	if len(root.Links) > 0 {
		tx, err := s.db.Begin()
		if err != nil {
			return nil, fmt.Errorf("merge links begin tx: %w", err)
		}
		committed := false
		defer func() {
			if !committed {
				_ = tx.Rollback()
			}
		}()
		if err := applyLinkOverrides(tx, root.Links); err != nil {
			return nil, err
		}
		if err := tx.Commit(); err != nil {
			return nil, fmt.Errorf("merge links commit: %w", err)
		}
		committed = true
		stats.LinksAdded = len(root.Links)
	}
	return stats, nil
}

// mergeVideosFromRoot iterates root.Videos{} and applies each entry
// through mergeOneVideo, propagating the first error. The actresses
// path must have completed before this runs because video links rely
// on actress identifiers being present (see mergeFromRoot ordering).
func (s *SQLiteStore) mergeVideosFromRoot(root *DatabaseData, overwrite bool, now string, stats *MergeStats) error {
	for mapCode, video := range root.Videos {
		if err := s.mergeOneVideo(mapCode, video, overwrite, now, stats); err != nil {
			return err
		}
	}
	return nil
}

// mergeOneVideo applies a single videos{} entry to the SQLite store.
// prepareVideoForMerge handles the legacy-id and mapCode-fallback
// translation; an `!ok` result means the entry has no usable code and
// is silently skipped. On existing rows in non-overwrite mode the call
// counts VideosSkipped (the actresses path returns silently — that
// asymmetry is intentional and matches the pre-refactor behaviour).
// Each UpsertVideo opens its own SQLite tx; this layer adds no
// transaction boundary.
func (s *SQLiteStore) mergeOneVideo(mapCode string, video *VideoData, overwrite bool, now string, stats *MergeStats) error {
	code, videoCopy, ok := prepareVideoForMerge(mapCode, video, now)
	if !ok {
		return nil
	}
	existing, err := s.GetVideo(code)
	if err != nil && !errors.Is(err, ErrNotFound) {
		return err
	}
	if existing != nil {
		if !overwrite {
			stats.VideosSkipped++
			return nil
		}
		if videoCopy.CreatedAt == "" {
			videoCopy.CreatedAt = existing.CreatedAt
		}
		if err := s.UpsertVideo(code, videoCopy); err != nil {
			return err
		}
		stats.VideosUpdated++
		return nil
	}
	if videoCopy.CreatedAt == "" {
		videoCopy.CreatedAt = now
	}
	if err := s.UpsertVideo(code, videoCopy); err != nil {
		return err
	}
	stats.VideosAdded++
	return nil
}

// mergeActressesFromRoot iterates root.Actresses{} and applies each
// non-nil entry through mergeOneActress, propagating the first error.
// Ordering is map-iteration order; merge semantics do not depend on a
// stable order across runs.
func (s *SQLiteStore) mergeActressesFromRoot(root *DatabaseData, overwrite bool, now string, stats *MergeStats) error {
	for id, a := range root.Actresses {
		if a == nil {
			continue
		}
		if err := s.mergeOneActress(id, a, overwrite, now, stats); err != nil {
			return err
		}
	}
	return nil
}

// mergeOneActress applies a single actresses{} entry to the SQLite
// store. Skips when id (after TrimSpace) is empty or when the row
// already exists and overwrite=false. On existing rows it preserves
// the stored CreatedAt unless the JSON side has its own; on new rows
// it falls back to now. Each call upserts through UpsertActress which
// opens its own SQLite transaction — there is no caller-visible tx
// boundary at this layer.
func (s *SQLiteStore) mergeOneActress(id string, a *ActressData, overwrite bool, now string, stats *MergeStats) error {
	id = strings.TrimSpace(id)
	if id == "" {
		return nil
	}
	existing, err := s.GetActress(id)
	if err != nil && !errors.Is(err, ErrNotFound) {
		return err
	}
	actressCopy := *a
	actressCopy.ID = id
	actressCopy.UpdatedAt = now
	if existing != nil {
		if !overwrite {
			return nil
		}
		if actressCopy.CreatedAt == "" {
			actressCopy.CreatedAt = existing.CreatedAt
		}
		if err := s.UpsertActress(&actressCopy); err != nil {
			return err
		}
		stats.ActressesUpdated++
		return nil
	}
	if actressCopy.CreatedAt == "" {
		actressCopy.CreatedAt = now
	}
	if err := s.UpsertActress(&actressCopy); err != nil {
		return err
	}
	stats.ActressesAdded++
	return nil
}

// --- Backup family ------------------------------------------------------

// BackupCreate writes a SQLite snapshot to <data-dir>/backup/backup_<ts>.sqlite
// and returns its path. The "backup_" prefix matches the JSON-side
// helper so BackupList / BackupCleanup still find the file, even though
// the on-disk artefact is now a SQLite database.
func (s *SQLiteStore) BackupCreate() (string, error) {
	if s == nil || s.db == nil {
		return "", ErrSQLiteStoreClosed
	}
	backupDir := filepath.Join(s.dataDirRoot(), "backup")
	if err := safefile.MkdirAll(backupDir, 0o700); err != nil {
		return "", fmt.Errorf("無法建立備份目錄: %w", err)
	}
	ts := time.Now().Format("2006-01-02_15-04-05")
	dest := filepath.Join(backupDir, "backup_"+ts+".sqlite")
	if _, err := s.Backup(BackupOptions{DestPath: dest}); err != nil {
		return "", fmt.Errorf("無法建立 SQLite 備份: %w", err)
	}
	return dest, nil
}

// BackupRestore restores SQLite data from a backup file. .sqlite paths
// go through RestoreSQLiteFile (raw file swap); .json paths are treated
// as a JSON DB export and re-imported via ResyncFromJSON so the legacy
// "restore from data.json snapshot" flow (still used by the Python
// JSONDBManager helper) keeps working on a SQLite-only runtime.
//
// Returns an error when the file extension is neither .sqlite nor .json
// so silent no-ops don't pretend a half-handled restore succeeded.
func (s *SQLiteStore) BackupRestore(backupPath string) error {
	if s == nil || s.db == nil {
		return ErrSQLiteStoreClosed
	}
	lower := strings.ToLower(strings.TrimSpace(backupPath))
	switch {
	case strings.HasSuffix(lower, ".sqlite"):
		target := s.path
		if err := s.Close(); err != nil {
			return fmt.Errorf("釋放 SQLite 連線失敗: %w", err)
		}
		return RestoreSQLiteFile(target, backupPath)
	case strings.HasSuffix(lower, ".json"):
		// JSONDBManager.restore_from_backup keeps shipping a JSON file
		// through `db backup-restore -backup-path`; route those through
		// resync-from-json so SQLite picks up the new state without a
		// file swap. Mirrors runBackupRestoreFromJSON in cmd/scanner.
		_, err := s.ResyncFromJSON(backupPath, MigrationOptions{})
		return err
	default:
		return fmt.Errorf("不支援的備份檔案副檔名：%s (期望 .sqlite 或 .json)", backupPath)
	}
}

// BackupList returns every JSON-snapshot file under <data-dir>/backup/.
// Only the .json siblings are surfaced — this matches the JSONDatabase
// contract Python helpers parse today and the parsing in
// removeOldestBackups / deleteExpiredBackups which both key off
// isBackupJSONFileName. The matching .sqlite sibling lives next to each
// JSON entry; cmd/scanner's runDBBackupRestore routes by extension.
func (s *SQLiteStore) BackupList() ([]string, error) {
	backupDir := filepath.Join(s.dataDirRoot(), "backup")
	entries, err := os.ReadDir(backupDir)
	if err != nil {
		if os.IsNotExist(err) {
			return []string{}, nil
		}
		return nil, fmt.Errorf("無法讀取備份目錄: %w", err)
	}
	var paths []string
	for _, e := range entries {
		if !e.IsDir() && isBackupJSONFileName(e.Name()) {
			paths = append(paths, filepath.Join(backupDir, e.Name()))
		}
	}
	sort.Strings(paths)
	if paths == nil {
		paths = []string{}
	}
	return paths, nil
}

// BackupCleanup deletes expired and surplus backups. days controls the
// age cutoff; maxCount caps the total backup count after the age sweep.
// Returns the number of files removed.
func (s *SQLiteStore) BackupCleanup(days, maxCount int) (int, error) {
	backupDir := filepath.Join(s.dataDirRoot(), "backup")
	entries, err := os.ReadDir(backupDir)
	if err != nil {
		if os.IsNotExist(err) {
			return 0, nil
		}
		return 0, fmt.Errorf("無法讀取備份目錄: %w", err)
	}
	cutoff := time.Now().AddDate(0, 0, -days)
	deleted := deleteExpiredBackups(backupDir, entries, cutoff)
	remaining, err := s.BackupList()
	if err != nil {
		return deleted, nil //nolint:nilerr // mirror JSONDatabase.BackupCleanup: best-effort tail trim
	}
	deleted += removeOldestBackups(remaining, maxCount)
	return deleted, nil
}

// --- helpers shared with the JSON-side merge path ----------------------

// loadMergeSourceData / prepareVideoForMerge / deleteExpiredBackups /
// removeOldestBackups / isBackupJSONFileName are defined in
// pkg/database/jsondb.go and reused here so the merge + backup code
// paths stay byte-for-byte aligned with the legacy JSON helpers.
