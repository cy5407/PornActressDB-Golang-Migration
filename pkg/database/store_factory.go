package database

import (
	"context"
	"errors"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
)

// StoreMode selects how NewStore wires the underlying *JSONDatabase and
// *SQLiteStore.
type StoreMode int

const (
	// ModeDualWrite (default): JSON write is canonical; every mutation
	// is mirrored best-effort into SQLite, with the failures recorded
	// to a degraded log per spec § 4.1.
	ModeDualWrite StoreMode = iota

	// ModeJSONOnly disables the SQLite mirror entirely. The returned
	// *DualWriteStore embeds *JSONDatabase and behaves identically to
	// *JSONDatabase for every method — the embed pattern lets callers
	// keep a single static type. Used by ACTRESS_DB_MODE=json_only as
	// the spec § 4.1 / § 4.4 rollback path.
	ModeJSONOnly
)

// StoreConfig parameterises NewStore. DataDir is required; other
// fields fall back to spec-recommended defaults if zero.
type StoreConfig struct {
	Mode StoreMode

	// DataDir is forwarded straight into ResolveDataDirPaths. Empty
	// uses DefaultDataDir (data/json_db) and the sibling SQLite path.
	DataDir string

	// SQLitePath overrides the path derived from DataDir. Leave empty
	// to use the spec § 7.1 compatibility lookup default.
	SQLitePath string

	// DegradedLogPath overrides the on-disk degraded log location.
	// Leave empty for the spec § 4.1 default
	// (<data-parent>/sync_degraded.jsonl beside the SQLite file).
	DegradedLogPath string

	// LoadContext is passed to JSONDatabase.Load. context.Background()
	// is used when zero.
	LoadContext context.Context

	// UseSQLiteReads opts the returned *DualWriteStore into the Phase B1
	// shadow-read path: GetVideo / ListVideos / GetAllVideos pull from
	// SQLite first and fall back to JSON only when the SQLite query
	// returns an availability / schema / query error. The default (false)
	// keeps reads on JSONDatabase, preserving the Phase A3 behaviour
	// exactly. NewStore wires this onto the returned store; the SQLite
	// mirror still writes regardless of this flag.
	UseSQLiteReads bool
}

// ResolveStoreMode reads the ACTRESS_DB_MODE environment variable.
// Recognised values (case-insensitive):
//
//	"json_only" / "json-only" / "jsononly"  → ModeJSONOnly
//	anything else (incl. unset)             → ModeDualWrite
//
// This is the spec § 4.1 / § 4.4 documented rollback knob: setting
// ACTRESS_DB_MODE=json_only at process start turns the SQLite mirror
// off for that run without rebuilding.
func ResolveStoreMode() StoreMode {
	switch strings.ToLower(strings.TrimSpace(os.Getenv("ACTRESS_DB_MODE"))) {
	case "json_only", "json-only", "jsononly":
		return ModeJSONOnly
	default:
		return ModeDualWrite
	}
}

// ResolveUseSQLiteReads reads the USE_SQLITE_READS environment variable
// and reports whether the Phase B1 shadow-read path should be active.
// Recognised truthy values (case-insensitive, surrounding whitespace
// trimmed): "true", "1", "yes", "on". Anything else — including unset,
// empty, "false", "0", "no", "off" or arbitrary garbage — returns false.
//
// Spec § 4.1 / § 4.4: this is the in-process knob that flips
// GetVideo/ListVideos/GetAllVideos onto the SQLite mirror for a single
// classifier.exe invocation. Mutations and the SQLite write mirror are
// unaffected.
func ResolveUseSQLiteReads() bool {
	return parseBoolEnv(os.Getenv("USE_SQLITE_READS"))
}

// parseBoolEnv recognises the truthy spellings ResolveUseSQLiteReads
// documents. Exported via that helper rather than directly so callers
// uniformly read the same env var and stay aligned with the comment.
func parseBoolEnv(raw string) bool {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "true", "1", "yes", "on":
		return true
	default:
		return false
	}
}

// NewStore is the canonical factory for the runtime data store. It
// loads the JSON DB, opens (and lazily inits) the SQLite mirror when
// the mode permits, and returns a *DualWriteStore wrapping both.
//
// When cfg.Mode is ModeJSONOnly the SQLite path is not touched at all
// and the returned store has its sqlite field set to nil — every
// mirror call becomes a noop, identical to using *JSONDatabase
// directly. The static return type stays *DualWriteStore so callers
// can avoid type-switching.
//
// SQLite open or schema init failures in ModeDualWrite degrade to
// JSON-only mode at runtime (with a logged warning) rather than
// failing the whole process. This matches spec § 4.1 / § 4.4: the
// JSON side is canonical and must remain usable even when SQLite is
// unhealthy.
func NewStore(cfg StoreConfig) (*DualWriteStore, error) {
	paths := ResolveDataDirPaths(cfg.DataDir)
	jsonDB := NewJSONDatabase(paths.DataDir)

	loadCtx := cfg.LoadContext
	if loadCtx == nil {
		loadCtx = context.Background()
	}
	if err := jsonDB.Load(loadCtx); err != nil {
		return nil, fmt.Errorf("load JSON database at %q: %w", paths.DataDir, err)
	}

	if cfg.Mode == ModeJSONOnly {
		store, err := NewDualWriteStore(jsonDB, nil, nil)
		if err != nil {
			return nil, err
		}
		store.SetUseSQLiteReads(cfg.UseSQLiteReads)
		return store, nil
	}

	sqlitePath := cfg.SQLitePath
	if sqlitePath == "" {
		sqlitePath = paths.SQLitePath
	}
	sqlite, sqliteErr := openAndInitSQLite(sqlitePath)
	if sqliteErr != nil {
		log.Printf("dual-write: SQLite unavailable at %q (%v); collapsing to JSON-only for this process",
			sqlitePath, sqliteErr)
		store, err := NewDualWriteStore(jsonDB, nil, nil)
		if err != nil {
			return nil, err
		}
		store.SetUseSQLiteReads(cfg.UseSQLiteReads)
		// Spec § 4.1 / Phase B1: when the caller asked for SQLite reads
		// but open/init failed, the read path is silently downgraded to
		// JSON for the entire process. Count it once so db stats'
		// sqlite_read_fallback_total reflects the open-time fallback.
		// ModeJSONOnly returns above this branch and is not counted —
		// that is an explicit rollback, not an availability failure.
		if cfg.UseSQLiteReads {
			store.sqliteReadFallbackTotal.Add(1)
		}
		return store, nil
	}

	degradedPath := cfg.DegradedLogPath
	if degradedPath == "" {
		degradedPath = defaultDegradedLogPath(paths)
	}
	degraded := NewDegradedLog(degradedPath)

	store, err := NewDualWriteStore(jsonDB, sqlite, degraded)
	if err != nil {
		sqlite.Close()
		return nil, err
	}
	store.SetUseSQLiteReads(cfg.UseSQLiteReads)

	// Spec § 4.1: drain any pending degraded entries synchronously at
	// startup so the store presents a coherent view ASAP.
	if err := store.Replay(); err != nil {
		log.Printf("dual-write: startup replay error (continuing): %v", err)
	}
	return store, nil
}

func openAndInitSQLite(path string) (*SQLiteStore, error) {
	if path == "" {
		return nil, errors.New("sqlite path is empty")
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, fmt.Errorf("mkdir sqlite parent: %w", err)
	}
	sqlite, err := OpenSQLiteStore(path)
	if err != nil {
		return nil, err
	}
	if err := sqlite.InitSchema(); err != nil {
		sqlite.Close()
		return nil, err
	}
	return sqlite, nil
}

// defaultDegradedLogPath places the log next to the SQLite file:
//   - For the default data-dir mapping (data/json_db → data/db.sqlite)
//     this yields data/sync_degraded.jsonl, matching spec § 4.1.
//   - For custom data-dirs (<dir>/db.sqlite) it yields
//     <dir>/sync_degraded.jsonl so the JSON DB, SQLite mirror, and the
//     degraded log all live together.
func defaultDegradedLogPath(paths DataDirPaths) string {
	return filepath.Join(filepath.Dir(paths.SQLitePath), "sync_degraded.jsonl")
}
