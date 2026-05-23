package database

import (
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"sync"
	"sync/atomic"
)

// DualWriteStore implements the Phase A3 "雙寫" runtime described in
// docs/superpowers/specs/2026-05-23-sqlite-migration-design.md § 4.1.
//
// It embeds *JSONDatabase so every read method (and every method
// DualWriteStore does NOT override) flows through the JSON side
// unchanged — readers cannot tell DualWriteStore from JSONDatabase.
//
// The five mutating methods that have a SQLite analogue are overridden
// to:
//
//  1. Apply the JSON write first. Spec § 4.1: JSON is the canonical
//     side during Phase A/B; if the JSON write fails the whole
//     operation fails — SQLite is NOT touched.
//
//  2. On JSON success, attempt the SQLite write. Failure does NOT
//     propagate to the caller; it is best-effort. The failure is
//     recorded to the degraded log and the warning counter
//     SyncDegradedTotal is incremented.
//
//  3. After each write, kick off a background replay attempt of any
//     prior degraded entries (non-blocking). A size-based warning fires
//     when the degraded log exceeds DegradedSizeWarnThreshold.
type DualWriteStore struct {
	*JSONDatabase

	sqlite   *SQLiteStore
	degraded *DegradedLog

	mu                sync.Mutex
	syncDegradedTotal int64

	// replayMu serialises Replay() calls so multiple concurrent callers
	// (e.g. the post-write background goroutine and a synchronous
	// caller in tests) execute one after another instead of short-
	// circuiting. Each acquired pass drains whatever entries remain
	// at that moment against the current SQLite handle.
	replayMu sync.Mutex

	// lifecycle tracks in-flight background replay goroutines so Close()
	// can wait for them to finish before the caller (or test cleanup)
	// removes the degraded log directory. Without this, on Windows we
	// race the goroutine's tmp-file rewrite against TempDir RemoveAll
	// and hit "Access is denied" / "directory is not empty".
	lifecycleMu sync.Mutex
	closed      bool
	replayWg    sync.WaitGroup

	// useSQLiteReads selects the Phase B1 shadow-read routing. When true
	// AND sqlite != nil, GetVideo/ListVideos/GetAllVideos prefer SQLite
	// and fall back to JSONDatabase only on availability/schema/query
	// errors (drift, i.e. ErrNotFound, is NOT a fallback). Mutated only
	// via SetUseSQLiteReads / NewStore; the read path uses an atomic
	// load to avoid a per-read mutex acquisition.
	useSQLiteReads atomic.Bool

	// sqliteReadFallbackTotal counts how many times a SQLite read errored
	// and DualWriteStore had to fall back to JSON. Surfaced through
	// GetStats so operators can spot a misbehaving SQLite mirror.
	sqliteReadFallbackTotal atomic.Int64
}

// NewDualWriteStore wires up an existing *JSONDatabase, an open
// *SQLiteStore, and a degraded log. The caller is responsible for
// having loaded the JSON DB and initialised the SQLite schema.
//
// sqlite may be nil — in that case the store collapses to JSON-only
// behaviour: every mirror call is a noop, the degraded log is never
// touched, and SyncDegradedTotal stays at zero. This is the
// ACTRESS_DB_MODE=json_only rollback path.
func NewDualWriteStore(jsonDB *JSONDatabase, sqlite *SQLiteStore, degraded *DegradedLog) (*DualWriteStore, error) {
	if jsonDB == nil {
		return nil, errors.New("NewDualWriteStore: jsonDB is nil")
	}
	if degraded == nil {
		degraded = NewDegradedLog("")
	}
	return &DualWriteStore{
		JSONDatabase: jsonDB,
		sqlite:       sqlite,
		degraded:     degraded,
	}, nil
}

// SyncDegradedTotal returns the number of SQLite write failures
// observed since the store was created (or since the process began).
// Replay successes do NOT decrement it — the count reflects history,
// not current backlog. Use DegradedLog.SizeBytes() for the live size.
func (d *DualWriteStore) SyncDegradedTotal() int64 {
	if d == nil {
		return 0
	}
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.syncDegradedTotal
}

// DegradedLog exposes the underlying degraded log for diagnostics and
// stats wiring. Returns nil when the dual store was constructed without
// one.
func (d *DualWriteStore) DegradedLog() *DegradedLog {
	if d == nil {
		return nil
	}
	return d.degraded
}

// SQLite returns the underlying SQLite store. Exposed so wiring code
// (cmd/scanner main, wails app) can close it on shutdown.
func (d *DualWriteStore) SQLite() *SQLiteStore {
	if d == nil {
		return nil
	}
	return d.sqlite
}

// SetUseSQLiteReads toggles the Phase B1 shadow-read routing. NewStore
// calls this from cfg.UseSQLiteReads at construction time; callers may
// flip it at runtime when wiring up the eventual CLI env knob in B1b.
// Safe to call concurrently with reads — backed by an atomic bool.
func (d *DualWriteStore) SetUseSQLiteReads(use bool) {
	if d == nil {
		return
	}
	d.useSQLiteReads.Store(use)
}

// UseSQLiteReads reports the current shadow-read routing flag. Exposed
// for tests and stats wiring.
func (d *DualWriteStore) UseSQLiteReads() bool {
	if d == nil {
		return false
	}
	return d.useSQLiteReads.Load()
}

// SQLiteReadFallbackTotal returns the number of SQLite read failures
// that triggered a fallback to JSONDatabase since the store was
// constructed. Drift (SQLite reports no row while JSON has one) does
// NOT increment this counter — see GetVideo.
func (d *DualWriteStore) SQLiteReadFallbackTotal() int64 {
	if d == nil {
		return 0
	}
	return d.sqliteReadFallbackTotal.Load()
}

// Close marks the store as closed, waits for any background replay
// goroutines spawned by postWriteHook to finish, then releases the
// SQLite handle. Callers (including test cleanup) MUST call Close
// before tearing down the degraded log directory, otherwise on Windows
// the still-running goroutine's tmp-file rewrite races directory
// removal. The embedded *JSONDatabase has no Close; callers should
// call Save() / CompactJournal() explicitly per existing JSONDatabase
// contract.
func (d *DualWriteStore) Close() error {
	if d == nil {
		return nil
	}
	d.lifecycleMu.Lock()
	d.closed = true
	d.lifecycleMu.Unlock()

	// Wait for any background replay goroutines spawned via
	// postWriteHook before they were marked closed. A concurrent Close
	// must also block here for the same reason.
	d.replayWg.Wait()

	if d.sqlite == nil {
		return nil
	}
	return d.sqlite.Close()
}

// Replay drains the degraded log against the live SQLite store. Called
// at construction (synchronously) and by background goroutines after
// each write. Concurrent callers serialise on replayMu; each acquired
// pass drains whatever entries remain at that moment. This matters in
// tests where a post-write background goroutine and a synchronous
// caller race: both passes need to run so the second one sees any
// SQLite handle changes the test made between them.
func (d *DualWriteStore) Replay() error {
	if d == nil || d.degraded == nil {
		return nil
	}
	d.replayMu.Lock()
	defer d.replayMu.Unlock()
	return d.degraded.Replay(d.applyDegraded)
}

// applyDegraded re-applies one degraded entry against the SQLite store.
// Returns nil on success (so the entry is dropped from the log).
func (d *DualWriteStore) applyDegraded(e degradedEntry) error {
	switch e.Op {
	case degradedOpVideoUpsert:
		var v VideoData
		if err := json.Unmarshal(e.Data, &v); err != nil {
			return fmt.Errorf("decode video upsert data: %w", err)
		}
		return d.sqlite.UpsertVideo(e.Key, &v)
	case degradedOpVideoDelete:
		return d.sqlite.DeleteVideo(e.Key)
	case degradedOpActressUpsert:
		var a ActressData
		if err := json.Unmarshal(e.Data, &a); err != nil {
			return fmt.Errorf("decode actress upsert data: %w", err)
		}
		return d.sqlite.UpsertActress(&a)
	case degradedOpActressDelete:
		return d.sqlite.DeleteActress(e.Key)
	default:
		// Unknown op: drop with a warning so we don't accumulate junk.
		log.Printf("dual-write degraded: unknown op %q for key %q — dropping", e.Op, e.Key)
		return nil
	}
}

// GetStats overrides the embedded JSONDatabase.GetStats() to surface
// dual-write diagnostics. Existing JSON keys are preserved verbatim so
// Python helpers parsing the JSON stays compatible (see
// tests/test_go_cli_contracts.py::test_db_stats_subcommand_returns_full_stats_dict).
//
// Adds:
//
//	sync_degraded_total    int64 — cumulative SQLite-mirror failures
//	                                since the store was constructed.
//	sync_degraded_log_size int64 — current degraded-log file size in
//	                                bytes (0 when the log is absent or
//	                                disabled).
func (d *DualWriteStore) GetStats() (map[string]any, error) {
	stats, err := d.JSONDatabase.GetStats()
	if err != nil {
		return nil, err
	}
	stats["sync_degraded_total"] = d.SyncDegradedTotal()
	var logSize int64
	if d.degraded != nil {
		logSize = d.degraded.SizeBytes()
	}
	stats["sync_degraded_log_size"] = logSize
	stats["sqlite_read_fallback_total"] = d.SQLiteReadFallbackTotal()
	return stats, nil
}

// --- Read overrides (Phase B1 shadow reads) ------------------------------
//
// GetVideo / ListVideos / GetAllVideos route through SQLite when
// UseSQLiteReads is true AND a SQLite handle is wired. A drift case
// (SQLite query returns no rows while JSON would have answered) is
// intentionally surfaced verbatim — DualWriteStore does not "fix" the
// answer by consulting JSON, so an operator flipping the flag sees the
// actual SQLite state. Real read errors (closed handle, missing schema,
// query failure) increment SQLiteReadFallbackTotal and fall back to
// JSONDatabase so callers never lose service.

// GetVideo overrides JSONDatabase.GetVideo. JSON path remains unchanged
// when UseSQLiteReads is off (Phase A3 behaviour).
func (d *DualWriteStore) GetVideo(code string) (*Video, error) {
	if !d.shouldReadFromSQLite() {
		return d.JSONDatabase.GetVideo(code)
	}
	v, err := d.sqlite.GetVideo(code)
	if err == nil {
		return v, nil
	}
	if errors.Is(err, ErrNotFound) || errors.Is(err, ErrInvalidCode) {
		// Successful query — drift or caller-side bad input. Do NOT fall
		// back: spec § 4.1 keeps SQLite truthful when it is reachable.
		return nil, err
	}
	d.sqliteReadFallbackTotal.Add(1)
	log.Printf("dual-write shadow read: GetVideo %q SQLite error (%v); falling back to JSON", code, err)
	return d.JSONDatabase.GetVideo(code)
}

// ListVideos overrides JSONDatabase.ListVideos following the same
// routing as GetVideo. An empty SQLite list is NOT a fallback trigger.
func (d *DualWriteStore) ListVideos() ([]string, error) {
	if !d.shouldReadFromSQLite() {
		return d.JSONDatabase.ListVideos()
	}
	codes, err := d.sqlite.ListVideos()
	if err == nil {
		return codes, nil
	}
	d.sqliteReadFallbackTotal.Add(1)
	log.Printf("dual-write shadow read: ListVideos SQLite error (%v); falling back to JSON", err)
	return d.JSONDatabase.ListVideos()
}

// GetAllVideos overrides JSONDatabase.GetAllVideos following the same
// routing as GetVideo.
func (d *DualWriteStore) GetAllVideos() ([]*VideoData, error) {
	if !d.shouldReadFromSQLite() {
		return d.JSONDatabase.GetAllVideos()
	}
	videos, err := d.sqlite.GetAllVideos()
	if err == nil {
		return videos, nil
	}
	d.sqliteReadFallbackTotal.Add(1)
	log.Printf("dual-write shadow read: GetAllVideos SQLite error (%v); falling back to JSON", err)
	return d.JSONDatabase.GetAllVideos()
}

// shouldReadFromSQLite reports whether the shadow-read path is active.
// Returns false when the flag is off OR when no SQLite handle is wired
// (ACTRESS_DB_MODE=json_only or open-time collapse). Returning false
// here is the central guarantee that "flag=false → JSON behaviour
// unchanged" — every shadow-read override delegates this single check.
func (d *DualWriteStore) shouldReadFromSQLite() bool {
	if d == nil || d.sqlite == nil {
		return false
	}
	return d.useSQLiteReads.Load()
}

// --- Mutation overrides ---------------------------------------------------

// UpdateVideo writes through to JSON first, then attempts the SQLite
// mirror. SQLite failure does not propagate.
func (d *DualWriteStore) UpdateVideo(code string, v *Video) error {
	if err := d.JSONDatabase.UpdateVideo(code, v); err != nil {
		return err
	}
	d.mirrorVideoUpsert(code, v)
	return nil
}

// AddVideo: see UpdateVideo. AddVideo and UpdateVideo collapse onto the
// same SQLite UPSERT — JSON-side semantics differ (Add fails on
// existing code, Update fails on missing) but the SQLite mirror does
// not care because the JSON write already arbitrated the contract.
func (d *DualWriteStore) AddVideo(v *Video) error {
	if err := d.JSONDatabase.AddVideo(v); err != nil {
		return err
	}
	if v == nil {
		return nil
	}
	d.mirrorVideoUpsert(v.GetCode(), v)
	return nil
}

// UpdateVideoFields: JSONDatabase applies a partial map, so we re-read
// the full row from the JSON side and mirror that into SQLite. This is
// the simplest correct path — the JSON side already merged the diff.
func (d *DualWriteStore) UpdateVideoFields(code string, updates map[string]any) error {
	if err := d.JSONDatabase.UpdateVideoFields(code, updates); err != nil {
		return err
	}
	v, err := d.JSONDatabase.GetVideo(code)
	if err != nil {
		// Should not happen — JSON just confirmed the update. Record
		// a degraded entry without data so verify-sync notices.
		d.recordDegraded(degradedEntry{
			Op:  degradedOpVideoUpsert,
			Key: code,
			Err: fmt.Sprintf("re-fetch after UpdateVideoFields: %v", err),
		})
		return nil
	}
	d.mirrorVideoUpsert(code, v)
	return nil
}

// DeleteVideo: JSON first, then SQLite delete.
func (d *DualWriteStore) DeleteVideo(code string) error {
	if err := d.JSONDatabase.DeleteVideo(code); err != nil {
		return err
	}
	d.mirrorVideoDelete(code)
	return nil
}

// UpsertActress: JSON first, then SQLite.
func (d *DualWriteStore) UpsertActress(a *ActressData) error {
	if err := d.JSONDatabase.UpsertActress(a); err != nil {
		return err
	}
	if a == nil {
		return nil
	}
	d.mirrorActressUpsert(a)
	return nil
}

// DeleteActress: JSON first, then SQLite.
func (d *DualWriteStore) DeleteActress(id string) error {
	if err := d.JSONDatabase.DeleteActress(id); err != nil {
		return err
	}
	d.mirrorActressDelete(id)
	return nil
}

// --- Mirror helpers ------------------------------------------------------

func (d *DualWriteStore) mirrorVideoUpsert(code string, v *Video) {
	if d.sqlite == nil {
		return
	}
	if err := d.sqlite.UpsertVideo(code, v); err != nil {
		raw, _ := json.Marshal(v)
		d.recordDegraded(degradedEntry{
			Op:   degradedOpVideoUpsert,
			Key:  code,
			Data: raw,
			Err:  err.Error(),
		})
	}
	d.postWriteHook()
}

func (d *DualWriteStore) mirrorVideoDelete(code string) {
	if d.sqlite == nil {
		return
	}
	if err := d.sqlite.DeleteVideo(code); err != nil {
		d.recordDegraded(degradedEntry{
			Op:  degradedOpVideoDelete,
			Key: code,
			Err: err.Error(),
		})
	}
	d.postWriteHook()
}

func (d *DualWriteStore) mirrorActressUpsert(a *ActressData) {
	if d.sqlite == nil {
		return
	}
	if err := d.sqlite.UpsertActress(a); err != nil {
		raw, _ := json.Marshal(a)
		d.recordDegraded(degradedEntry{
			Op:   degradedOpActressUpsert,
			Key:  a.ID,
			Data: raw,
			Err:  err.Error(),
		})
	}
	d.postWriteHook()
}

func (d *DualWriteStore) mirrorActressDelete(id string) {
	if d.sqlite == nil {
		return
	}
	if err := d.sqlite.DeleteActress(id); err != nil {
		d.recordDegraded(degradedEntry{
			Op:  degradedOpActressDelete,
			Key: id,
			Err: err.Error(),
		})
	}
	d.postWriteHook()
}

func (d *DualWriteStore) recordDegraded(entry degradedEntry) {
	d.mu.Lock()
	d.syncDegradedTotal++
	d.mu.Unlock()
	if err := d.degraded.Record(entry); err != nil {
		// Last-ditch: log to stderr. We do not propagate — the JSON
		// write has already succeeded, the user must not see a runtime
		// error for a shadow-mirror hiccup.
		log.Printf("dual-write degraded: failed to record %s %q: %v", entry.Op, entry.Key, err)
	}
}

func (d *DualWriteStore) postWriteHook() {
	// Spec § 4.1: per-write only does a lightweight Stat + threshold
	// warning; full replay runs in a background goroutine.
	if size := d.degraded.SizeBytes(); size > DegradedSizeWarnThreshold {
		log.Printf("dual-write degraded log size = %d bytes (threshold %d); consider classifier.exe db resync-from-json",
			size, DegradedSizeWarnThreshold)
	}

	// Register the goroutine under lifecycleMu so Close() can either
	// (a) skip spawning new replays once shutdown has begun or
	// (b) wait for any goroutine we let spawn here.
	d.lifecycleMu.Lock()
	if d.closed {
		d.lifecycleMu.Unlock()
		return
	}
	d.replayWg.Add(1)
	d.lifecycleMu.Unlock()

	go func() {
		defer d.replayWg.Done()
		if err := d.Replay(); err != nil {
			log.Printf("dual-write background replay error: %v", err)
		}
	}()
}
