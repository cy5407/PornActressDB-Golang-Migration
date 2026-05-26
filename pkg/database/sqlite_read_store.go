package database

import (
	"database/sql"
	"errors"
	"fmt"
)

// ErrSQLiteStoreClosed signals that a *SQLiteStore method was invoked
// against a store whose underlying *sql.DB is nil (either never opened
// or already Close()'d). Slice C2 made SQLite the sole runtime store,
// so there is no JSON-side fallback to flip onto; callers (and tests)
// just need a distinct sentinel that means "handle unavailable" so
// they can tell it apart from a real query error.
var ErrSQLiteStoreClosed = errors.New("sqlite store is not open")

// videoColumns lists the videos table columns in the order GetVideo and
// GetAllVideos scan. Kept in one place so the SELECT/Scan halves stay in
// lock-step with sqlite_crud.go's INSERT.
const videoColumns = `
	code, id, title, studio, studio_code, release_date, url,
	search_status, search_method, last_search_date,
	avwiki_actress_status, avwiki_last_search_date,
	javdb_actress_status, javdb_last_search_date,
	metadata_source, metadata_confidence,
	created_at, updated_at, original_filename, file_path,
	error, error_kind`

// scanVideo reads a videos row in the canonical column order into v.
func scanVideo(scanner interface {
	Scan(dest ...any) error
}, v *VideoData) error {
	return scanner.Scan(
		&v.Code, &v.ID, &v.Title, &v.Studio, &v.StudioCode, &v.ReleaseDate, &v.URL,
		&v.SearchStatus, &v.SearchMethod, &v.LastSearchDate,
		&v.AVWikiActressStatus, &v.AVWikiLastSearchDate,
		&v.JAVDBActressStatus, &v.JAVDBLastSearchDate,
		&v.Metadata.Source, &v.Metadata.Confidence,
		&v.CreatedAt, &v.UpdatedAt, &v.OriginalFilename, &v.FilePath,
		&v.Error, &v.ErrorKind,
	)
}

// GetVideo loads a single VideoData from SQLite. Returns ErrNotFound
// when no row matches code (a successful query with zero rows is
// distinct from a query error). Any other failure — unavailable
// handle, missing schema, query error — is wrapped and returned.
func (s *SQLiteStore) GetVideo(code string) (*VideoData, error) {
	if s == nil || s.db == nil {
		return nil, ErrSQLiteStoreClosed
	}
	if code == "" {
		return nil, ErrInvalidCode
	}

	v := &VideoData{}
	row := s.db.QueryRow(`SELECT `+videoColumns+` FROM videos WHERE code = ?`, code)
	if err := scanVideo(row, v); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, fmt.Errorf("sqlite GetVideo %q: %w", code, err)
	}

	actresses, err := s.loadVideoActresses(code)
	if err != nil {
		return nil, err
	}
	v.Actresses = actresses
	return v, nil
}

// ListVideos returns every video code currently stored in SQLite. The
// order matches the JSONDatabase analogue — unspecified — but consumers
// of either path should sort if they rely on a particular ordering.
func (s *SQLiteStore) ListVideos() ([]string, error) {
	if s == nil || s.db == nil {
		return nil, ErrSQLiteStoreClosed
	}
	rows, err := s.db.Query(`SELECT code FROM videos`)
	if err != nil {
		return nil, fmt.Errorf("sqlite ListVideos: %w", err)
	}
	defer rows.Close()

	out := make([]string, 0)
	for rows.Next() {
		var c string
		if err := rows.Scan(&c); err != nil {
			return nil, fmt.Errorf("sqlite ListVideos scan: %w", err)
		}
		out = append(out, c)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("sqlite ListVideos rows: %w", err)
	}
	return out, nil
}

// GetAllVideos returns every video row joined with its ordered actress
// display names. The result matches the shape JSONDatabase.GetAllVideos
// returned so callers that round-trip through both paths (tests,
// JSON import / export) cannot tell the two apart.
func (s *SQLiteStore) GetAllVideos() ([]*VideoData, error) {
	if s == nil || s.db == nil {
		return nil, ErrSQLiteStoreClosed
	}
	rows, err := s.db.Query(`SELECT ` + videoColumns + ` FROM videos`)
	if err != nil {
		return nil, fmt.Errorf("sqlite GetAllVideos: %w", err)
	}
	defer rows.Close()

	videos := make([]*VideoData, 0)
	for rows.Next() {
		v := &VideoData{}
		if err := scanVideo(rows, v); err != nil {
			return nil, fmt.Errorf("sqlite GetAllVideos scan: %w", err)
		}
		videos = append(videos, v)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("sqlite GetAllVideos rows: %w", err)
	}

	for _, v := range videos {
		actresses, err := s.loadVideoActresses(v.Code)
		if err != nil {
			return nil, err
		}
		v.Actresses = actresses
	}
	return videos, nil
}

// loadVideoActresses reconstructs the JSON-side `video.actresses[]`
// strings from video_actress_links: the alias spelling preserved in
// display_name when present, falling back to actresses.name otherwise.
// Order is the link's ordinal, matching the JSON-side ordering carried
// across MigrateFromJSON / UpsertVideo.
func (s *SQLiteStore) loadVideoActresses(code string) ([]string, error) {
	rows, err := s.db.Query(
		`SELECT COALESCE(NULLIF(l.display_name, ''), a.name)
		   FROM video_actress_links l
		   JOIN actresses a ON a.id = l.actress_id
		  WHERE l.video_code = ?
		  ORDER BY l.ordinal`,
		code,
	)
	if err != nil {
		return nil, fmt.Errorf("sqlite load actresses %q: %w", code, err)
	}
	defer rows.Close()

	// Always return a non-nil slice so callers (and JSON consumers that
	// json.Marshal the video) get [] instead of null for videos with no
	// actresses — matching JSONDatabase, GetEmptyVideo and NewVideo.
	names := make([]string, 0)
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return nil, fmt.Errorf("sqlite load actresses scan %q: %w", code, err)
		}
		names = append(names, name)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("sqlite load actresses rows %q: %w", code, err)
	}
	return names, nil
}
