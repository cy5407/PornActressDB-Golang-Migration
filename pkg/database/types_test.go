package database

import (
	"errors"
	"strings"
	"testing"
	"time"
)

func TestDatabaseErrorFormatsAndUnwrapsCause(t *testing.T) {
	cause := errors.New("disk full")
	err := &DatabaseError{Op: "save", Err: cause}

	if got := err.Error(); got != "save: disk full" {
		t.Fatalf("unexpected error string: %q", got)
	}
	if !errors.Is(err, cause) {
		t.Fatal("expected DatabaseError to unwrap the original cause")
	}
}

func TestDatabaseErrorFormatsUnknownCause(t *testing.T) {
	err := &DatabaseError{Op: "load"}

	if got := err.Error(); got != "load: unknown error" {
		t.Fatalf("unexpected error string: %q", got)
	}
	if err.Unwrap() != nil {
		t.Fatal("expected nil unwrap cause")
	}
}

func TestNewJournalEntryRejectsUnmarshalableData(t *testing.T) {
	_, err := NewJournalEntry(OpAdd, TypeVideo, "ABC-123", make(chan int))
	if err == nil {
		t.Fatal("expected marshal error for channel data")
	}
}

func TestNewJournalEntryAllowsNilData(t *testing.T) {
	entry, err := NewJournalEntry(OpDelete, TypeVideo, "ABC-123", nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if entry.Op != OpDelete || entry.Type != TypeVideo || entry.ID != "ABC-123" {
		t.Fatalf("unexpected journal entry identity: %+v", entry)
	}
	if len(entry.Data) != 0 {
		t.Fatalf("expected empty raw data for nil payload, got %s", string(entry.Data))
	}
	if _, err := time.Parse(time.RFC3339, entry.Ts); err != nil {
		t.Fatalf("expected RFC3339 timestamp, got %q: %v", entry.Ts, err)
	}
}

func TestGetCurrentTimestampRFC3339IsParseable(t *testing.T) {
	timestamp := GetCurrentTimestampRFC3339()

	if _, err := time.Parse(time.RFC3339, timestamp); err != nil {
		t.Fatalf("expected RFC3339 timestamp, got %q: %v", timestamp, err)
	}
}

func TestGetEmptyActressInitializesCompatibleDefaults(t *testing.T) {
	actress := GetEmptyActress()

	if actress.ID != "" || actress.Name != "" || actress.VideoCount != 0 {
		t.Fatalf("unexpected empty actress core fields: %+v", actress)
	}
	if actress.Aliases == nil || len(actress.Aliases) != 0 {
		t.Fatalf("expected initialized empty aliases slice, got %#v", actress.Aliases)
	}
	if !strings.HasSuffix(actress.CreatedAt, "Z") || !strings.HasSuffix(actress.UpdatedAt, "Z") {
		t.Fatalf("expected UTC timestamps, got created=%q updated=%q", actress.CreatedAt, actress.UpdatedAt)
	}
}

func TestNewEmptyDirtyIndexInitializesSlicesAndTimestamp(t *testing.T) {
	index := NewEmptyDirtyIndex()

	if index.Videos == nil || len(index.Videos) != 0 {
		t.Fatalf("expected initialized empty video slice, got %#v", index.Videos)
	}
	if index.Actresses == nil || len(index.Actresses) != 0 {
		t.Fatalf("expected initialized empty actress slice, got %#v", index.Actresses)
	}
	if index.Links == nil || len(index.Links) != 0 {
		t.Fatalf("expected initialized empty link slice, got %#v", index.Links)
	}
	if index.JournalSize != 0 {
		t.Fatalf("expected zero journal size, got %d", index.JournalSize)
	}
	if _, err := time.Parse(time.RFC3339, index.CreatedAt); err != nil {
		t.Fatalf("expected RFC3339 created_at, got %q: %v", index.CreatedAt, err)
	}
}
