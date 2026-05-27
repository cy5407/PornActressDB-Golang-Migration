package database

import (
	"database/sql"
	"errors"
	"fmt"
	"strings"
)

// ErrMsgStoreNotOpen is the canonical message used when a *SQLiteStore
// method is invoked against a nil-db handle. Defined here as the single
// source of truth; ErrSQLiteStoreClosed (sqlite_read_store.go) wraps it
// so callers across the package can use errors.Is uniformly.
const ErrMsgStoreNotOpen string = "sqlite store is not open"

// UpsertVideo writes (insert-or-replace) the given video into the SQLite
// store. It is the strict, link-preserving primitive — runtime callers
// (AddVideo / UpdateVideo / UpdateVideoFields in sqlite_runtime.go) go
// through upsertVideoRuntime instead so unknown actress names are auto-
// created rather than silently dropped. UpsertVideo itself is reserved
// for paths that have already validated their actress set, notably
// MigrateFromJSON and the merge helper.
//
// The link rows for this video are rebuilt from v.Actresses: existing
// links for this video_code are deleted then re-inserted in the slice's
// natural order. Actress entities are NOT created here — callers must
// ensure they already exist (MigrateFromJSON populates root.actresses{}
// before any video.actresses[] reference is resolved). When v.Actresses
// references an unknown actress name the link row is silently skipped;
// the strict migrate path reports the unresolved name separately.
func (s *SQLiteStore) UpsertVideo(code string, v *VideoData) error {
	if s == nil || s.db == nil {
		return ErrSQLiteStoreClosed
	}
	if v == nil {
		return errors.New("UpsertVideo: video is nil")
	}
	tx, err := s.db.Begin()
	if err != nil {
		return fmt.Errorf("UpsertVideo begin tx: %w", err)
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
	if err := rebuildLinksForVideo(tx, code, v); err != nil {
		return err
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("UpsertVideo commit: %w", err)
	}
	committed = true
	return nil
}

// DeleteVideo removes a video and (via FK ON DELETE CASCADE) its links.
// Idempotent — deleting an absent code is not an error.
func (s *SQLiteStore) DeleteVideo(code string) error {
	if s == nil || s.db == nil {
		return ErrSQLiteStoreClosed
	}
	if _, err := s.db.Exec(`DELETE FROM videos WHERE code = ?`, code); err != nil {
		return fmt.Errorf("DeleteVideo %q: %w", code, err)
	}
	return nil
}

// UpsertActress inserts or updates an actress + its aliases. Aliases are
// fully replaced (delete-then-insert) so that callers do not accumulate
// stale aliases. SQLite is the canonical runtime store as of Slice C2;
// JSON callers reach this data only through export / backup snapshots.
func (s *SQLiteStore) UpsertActress(a *ActressData) error {
	if s == nil || s.db == nil {
		return ErrSQLiteStoreClosed
	}
	if a == nil || a.ID == "" {
		return errors.New("UpsertActress: actress or id is empty")
	}
	tx, err := s.db.Begin()
	if err != nil {
		return fmt.Errorf("UpsertActress begin tx: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()

	if _, err := tx.Exec(
		`INSERT INTO actresses(id, name, created_at, updated_at)
		   VALUES(?, ?, ?, ?)
		 ON CONFLICT(id) DO UPDATE SET
		       name=excluded.name,
		       updated_at=excluded.updated_at`,
		a.ID, a.Name, a.CreatedAt, a.UpdatedAt,
	); err != nil {
		return fmt.Errorf("UpsertActress %q: %w", a.ID, err)
	}
	if _, err := tx.Exec(`DELETE FROM actress_aliases WHERE actress_id = ?`, a.ID); err != nil {
		return fmt.Errorf("UpsertActress wipe aliases %q: %w", a.ID, err)
	}
	for _, alias := range a.Aliases {
		if _, err := tx.Exec(
			`INSERT INTO actress_aliases(actress_id, alias) VALUES(?, ?)`,
			a.ID, alias,
		); err != nil {
			return fmt.Errorf("UpsertActress alias %q/%q: %w", a.ID, alias, err)
		}
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("UpsertActress commit: %w", err)
	}
	committed = true
	return nil
}

// DeleteActress removes an actress and (via FK ON DELETE CASCADE) her
// aliases and links. Idempotent.
func (s *SQLiteStore) DeleteActress(id string) error {
	if s == nil || s.db == nil {
		return ErrSQLiteStoreClosed
	}
	if _, err := s.db.Exec(`DELETE FROM actresses WHERE id = ?`, id); err != nil {
		return fmt.Errorf("DeleteActress %q: %w", id, err)
	}
	return nil
}

// upsertVideoRow performs the single-row insert-or-replace inside an
// open transaction. Used by both MigrateFromJSON (Pass 2) and the
// runtime UpsertVideo path.
func upsertVideoRow(tx *sql.Tx, code string, v *VideoData) error {
	_, err := tx.Exec(
		`INSERT INTO videos(
			code, id, title, studio, studio_code, release_date, url,
			search_status, search_method, last_search_date,
			avwiki_actress_status, avwiki_last_search_date,
			javdb_actress_status, javdb_last_search_date,
			metadata_source, metadata_confidence,
			created_at, updated_at, original_filename, file_path,
			error, error_kind
		) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		 ON CONFLICT(code) DO UPDATE SET
		       id=excluded.id,
		       title=excluded.title,
		       studio=excluded.studio,
		       studio_code=excluded.studio_code,
		       release_date=excluded.release_date,
		       url=excluded.url,
		       search_status=excluded.search_status,
		       search_method=excluded.search_method,
		       last_search_date=excluded.last_search_date,
		       avwiki_actress_status=excluded.avwiki_actress_status,
		       avwiki_last_search_date=excluded.avwiki_last_search_date,
		       javdb_actress_status=excluded.javdb_actress_status,
		       javdb_last_search_date=excluded.javdb_last_search_date,
		       metadata_source=excluded.metadata_source,
		       metadata_confidence=excluded.metadata_confidence,
		       created_at=excluded.created_at,
		       updated_at=excluded.updated_at,
		       original_filename=excluded.original_filename,
		       file_path=excluded.file_path,
		       error=excluded.error,
		       error_kind=excluded.error_kind`,
		code,
		v.ID,
		v.Title,
		v.Studio,
		v.StudioCode,
		v.ReleaseDate,
		v.URL,
		v.SearchStatus,
		v.SearchMethod,
		v.LastSearchDate,
		v.AVWikiActressStatus,
		v.AVWikiLastSearchDate,
		v.JAVDBActressStatus,
		v.JAVDBLastSearchDate,
		v.Metadata.Source,
		v.Metadata.Confidence,
		v.CreatedAt,
		v.UpdatedAt,
		v.OriginalFilename,
		v.FilePath,
		v.Error,
		v.ErrorKind,
	)
	if err != nil {
		return fmt.Errorf("upsert video %q: %w", code, err)
	}
	return nil
}

// rebuildLinksForVideo wipes and reinserts the link rows for one video.
// Names that resolve neither to an actresses.name nor to an alias are
// skipped (logged via display_name lookup); caller is expected to keep
// the actress table populated via UpsertActress.
func rebuildLinksForVideo(tx *sql.Tx, code string, v *VideoData) error {
	if _, err := tx.Exec(`DELETE FROM video_actress_links WHERE video_code = ?`, code); err != nil {
		return fmt.Errorf("wipe links for %q: %w", code, err)
	}
	if len(v.Actresses) == 0 {
		return nil
	}

	for ordinal, display := range v.Actresses {
		actressID, displayName, found, err := lookupActressForLink(tx, display)
		if err != nil {
			return err
		}
		if !found {
			// Skip this link silently — the canonical truth is on the
			// JSON side, verify-sync will surface the divergence.
			continue
		}
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

// lookupActressForLink resolves a video.actresses[] display string to
// the SQLite actress_id. Match order: actresses.name, then
// actress_aliases.alias. Returns the resolved id, the display_name to
// store (empty if it matches actress.name verbatim, otherwise the raw
// display preserving JSON-side spelling), and a boolean found flag.
func lookupActressForLink(tx *sql.Tx, display string) (id, displayName string, found bool, err error) {
	display = strings.TrimSpace(display)
	if display == "" {
		return "", "", false, nil
	}

	var actressID, actressName string
	row := tx.QueryRow(`SELECT id, name FROM actresses WHERE name = ? LIMIT 1`, display)
	switch err := row.Scan(&actressID, &actressName); {
	case err == sql.ErrNoRows:
		// fall through to alias lookup
	case err != nil:
		return "", "", false, fmt.Errorf("lookup actress by name %q: %w", display, err)
	default:
		return actressID, "", true, nil
	}

	row = tx.QueryRow(
		`SELECT a.id, a.name
		   FROM actress_aliases al
		   JOIN actresses a ON a.id = al.actress_id
		  WHERE al.alias = ? LIMIT 1`,
		display,
	)
	switch err := row.Scan(&actressID, &actressName); {
	case err == sql.ErrNoRows:
		return "", "", false, nil
	case err != nil:
		return "", "", false, fmt.Errorf("lookup actress by alias %q: %w", display, err)
	}
	// display_name preserves the alias spelling.
	return actressID, display, true, nil
}
