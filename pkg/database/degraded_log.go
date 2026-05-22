package database

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// DegradedLogPathDefault is the on-disk JSONL location used by
// DualWriteStore when a SQLite write fails after the JSON write succeeded.
// Spec § 4.1: callers may override; defaults to data/sync_degraded.jsonl.
const DegradedLogPathDefault = "data/sync_degraded.jsonl"

// DegradedSizeWarnThreshold is the byte threshold at which the per-write
// stat check logs a warning (without blocking the write). Spec § 4.1
// suggests 32 KiB as the initial dogfood value.
const DegradedSizeWarnThreshold int64 = 32 * 1024

// degradedOpKind enumerates the mutation kinds the degraded log can
// re-apply. Kept short — replay only needs to know which SQLite call to
// re-issue.
type degradedOpKind string

const (
	degradedOpVideoUpsert   degradedOpKind = "video.upsert"
	degradedOpVideoDelete   degradedOpKind = "video.delete"
	degradedOpActressUpsert degradedOpKind = "actress.upsert"
	degradedOpActressDelete degradedOpKind = "actress.delete"
)

// degradedEntry is one line of the degraded log. The Data field holds
// the marshalled VideoData / ActressData for upsert kinds; nil for
// delete kinds. Key is the primary identifier (video code or actress id).
type degradedEntry struct {
	Ts   string          `json:"ts"`
	Op   degradedOpKind  `json:"op"`
	Key  string          `json:"key"`
	Data json.RawMessage `json:"data,omitempty"`
	Err  string          `json:"err,omitempty"`
}

// DegradedLog appends-only file storing SQLite writes that failed
// after the JSON write succeeded. Re-replayed at DualWriteStore startup
// and after each write (in background). Empty log file is removed on
// successful drain.
type DegradedLog struct {
	mu        sync.Mutex
	path      string
	successes int64
	failures  int64
}

// NewDegradedLog returns a DegradedLog rooted at path. path may be
// empty to disable persistent recording (degraded entries are then
// silently dropped — used by tests that don't care about persistence).
func NewDegradedLog(path string) *DegradedLog {
	return &DegradedLog{path: path}
}

// Path returns the on-disk path; empty means the log is in-memory only.
func (d *DegradedLog) Path() string {
	if d == nil {
		return ""
	}
	return d.path
}

// Record appends one entry. Returns nil if recording is disabled (empty
// path). I/O errors propagate — callers should log and continue rather
// than fail the caller's write.
func (d *DegradedLog) Record(entry degradedEntry) error {
	if d == nil || d.path == "" {
		return nil
	}
	if entry.Ts == "" {
		entry.Ts = time.Now().UTC().Format(time.RFC3339Nano)
	}
	raw, err := json.Marshal(entry)
	if err != nil {
		return fmt.Errorf("marshal degraded entry: %w", err)
	}

	d.mu.Lock()
	defer d.mu.Unlock()
	if err := os.MkdirAll(filepath.Dir(d.path), 0o755); err != nil {
		return fmt.Errorf("mkdir degraded log: %w", err)
	}
	f, err := os.OpenFile(d.path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600)
	if err != nil {
		return fmt.Errorf("open degraded log: %w", err)
	}
	defer f.Close()
	if _, err := f.Write(append(raw, '\n')); err != nil {
		return fmt.Errorf("append degraded log: %w", err)
	}
	return nil
}

// SizeBytes returns the current file size (0 if absent / disabled). Used
// by DualWriteStore for the per-write threshold warning per spec § 4.1.
func (d *DegradedLog) SizeBytes() int64 {
	if d == nil || d.path == "" {
		return 0
	}
	d.mu.Lock()
	defer d.mu.Unlock()
	info, err := os.Stat(d.path)
	if err != nil {
		return 0
	}
	return info.Size()
}

// SuccessesAndFailures returns the cumulative replay counts since the
// process started (or since the log was created). Used for diagnostics
// and stats; not persisted.
func (d *DegradedLog) SuccessesAndFailures() (successes, failures int64) {
	if d == nil {
		return 0, 0
	}
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.successes, d.failures
}

// replayHandler applies one degraded entry. Returns nil on success
// (entry will be dropped), or an error to retain the entry for a future
// replay attempt.
type replayHandler func(entry degradedEntry) error

// Replay walks the log file, invoking handler for each entry. Successes
// drop their entry; failures are kept. If the log becomes empty the
// underlying file is removed. The mutex is held for the whole replay —
// callers must not call Record from inside handler.
func (d *DegradedLog) Replay(handler replayHandler) error {
	if d == nil || d.path == "" {
		return nil
	}

	d.mu.Lock()
	defer d.mu.Unlock()

	src, err := os.Open(d.path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil
		}
		return fmt.Errorf("open degraded log for replay: %w", err)
	}
	scanner := bufio.NewScanner(src)
	scanner.Buffer(make([]byte, 0, 64*1024), 4*1024*1024)
	var keep []degradedEntry
	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}
		var e degradedEntry
		if err := json.Unmarshal(line, &e); err != nil {
			// Treat corrupted line as a failure that we keep so a human
			// can inspect — silently dropping it would lose data.
			d.failures++
			keep = append(keep, degradedEntry{Ts: time.Now().UTC().Format(time.RFC3339Nano), Op: "", Err: "unparseable: " + err.Error()})
			continue
		}
		if err := handler(e); err != nil {
			e.Err = err.Error()
			keep = append(keep, e)
			d.failures++
			continue
		}
		d.successes++
	}
	if err := scanner.Err(); err != nil {
		src.Close()
		return fmt.Errorf("scan degraded log: %w", err)
	}
	src.Close()

	if len(keep) == 0 {
		if err := os.Remove(d.path); err != nil && !errors.Is(err, os.ErrNotExist) {
			return fmt.Errorf("remove drained degraded log: %w", err)
		}
		return nil
	}

	// Rewrite the file with only the retained entries.
	tmp := d.path + ".tmp"
	out, err := os.Create(tmp)
	if err != nil {
		return fmt.Errorf("rewrite degraded log: %w", err)
	}
	enc := json.NewEncoder(out)
	for _, e := range keep {
		if err := enc.Encode(e); err != nil {
			out.Close()
			os.Remove(tmp)
			return fmt.Errorf("encode degraded entry on rewrite: %w", err)
		}
	}
	if err := out.Close(); err != nil {
		os.Remove(tmp)
		return fmt.Errorf("close degraded rewrite: %w", err)
	}
	if err := os.Rename(tmp, d.path); err != nil {
		os.Remove(tmp)
		return fmt.Errorf("rename degraded rewrite: %w", err)
	}
	return nil
}
