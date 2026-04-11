package database

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// ============================================================
// GetJournalSize
// ============================================================

func TestGetJournalSize_NoJournal(t *testing.T) {
	db, _ := setupTestDB(t)

	size, err := db.GetJournalSize()
	if err != nil {
		t.Fatalf("GetJournalSize error: %v", err)
	}
	if size != 0 {
		t.Errorf("expected 0 for no journal, got %d", size)
	}
}

func TestGetJournalSize_AfterWrite(t *testing.T) {
	db, _ := setupTestDB(t)

	video := NewVideo("STARS-001")
	if err := db.UpdateVideo("STARS-001", video); err != nil {
		t.Fatalf("UpdateVideo error: %v", err)
	}

	size, err := db.GetJournalSize()
	if err != nil {
		t.Fatalf("GetJournalSize error: %v", err)
	}
	if size <= 0 {
		t.Errorf("expected positive size after write, got %d", size)
	}
}

// ============================================================
// appendJournal — delete / add paths
// ============================================================

func TestAppendJournal_DeleteOp(t *testing.T) {
	db, _ := setupTestDB(t)

	// add first so there's something to delete
	if err := db.appendJournal("add", "IPX-001", NewVideo("IPX-001")); err != nil {
		t.Fatalf("appendJournal(add) error: %v", err)
	}
	if err := db.appendJournal("delete", "IPX-001", nil); err != nil {
		t.Fatalf("appendJournal(delete) error: %v", err)
	}

	count, err := db.GetJournalEntryCount()
	if err != nil {
		t.Fatalf("GetJournalEntryCount error: %v", err)
	}
	if count < 2 {
		t.Errorf("expected at least 2 journal entries, got %d", count)
	}
}

func TestAppendJournal_UnknownOpDefaultsToUpdate(t *testing.T) {
	db, _ := setupTestDB(t)

	if err := db.appendJournal("unknown_op", "SONE-001", NewVideo("SONE-001")); err != nil {
		t.Fatalf("appendJournal(unknown) error: %v", err)
	}
}

// ============================================================
// applyActressJournalDelete — through loadJournal path
// ============================================================

func TestApplyActressJournalDelete(t *testing.T) {
	dir := t.TempDir()
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load error: %v", err)
	}

	// Write an actress upsert entry followed by a delete entry directly to journal
	actressData, _ := json.Marshal(&ActressData{ID: "actress-1", Name: "Test Actress"})
	addEntry := JournalEntry{Op: OpAdd, Type: TypeActress, ID: "actress-1", Data: actressData, Ts: GetCurrentTimestamp()}
	delEntry := JournalEntry{Op: OpDelete, Type: TypeActress, ID: "actress-1", Ts: GetCurrentTimestamp()}

	f, err := os.OpenFile(filepath.Join(dir, JournalFileName), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0600)
	if err != nil {
		t.Fatalf("open journal error: %v", err)
	}
	enc := json.NewEncoder(f)
	_ = enc.Encode(addEntry)
	_ = enc.Encode(delEntry)
	f.Close()

	// Reload to trigger applyJournalEntry for actress delete
	db2 := NewJSONDatabase(dir)
	if err := db2.Load(context.Background()); err != nil {
		t.Fatalf("Reload error: %v", err)
	}
	if _, exists := db2.root.Actresses["actress-1"]; exists {
		t.Error("actress-1 should have been deleted")
	}
}

// ============================================================
// applyLegacyJournalEntry — through loadJournal path
// ============================================================

func TestApplyLegacyJournalEntry_Update(t *testing.T) {
	dir := t.TempDir()
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load error: %v", err)
	}

	// Write legacy format (no "op" field) to journal
	legacy := legacyJournalEntry{
		Timestamp: GetCurrentTimestamp(),
		Operation: "update",
		Code:      "ABW-001",
		Video:     NewVideo("ABW-001"),
	}
	data, _ := json.Marshal(legacy)

	f, err := os.OpenFile(filepath.Join(dir, JournalFileName), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0600)
	if err != nil {
		t.Fatalf("open journal error: %v", err)
	}
	f.Write(data)       //nolint:errcheck
	f.WriteString("\n") //nolint:errcheck
	f.Close()

	db2 := NewJSONDatabase(dir)
	if err := db2.Load(context.Background()); err != nil {
		t.Fatalf("Reload error: %v", err)
	}
	if _, exists := db2.root.Videos["ABW-001"]; !exists {
		t.Error("expected legacy update to add ABW-001")
	}
}

func TestApplyLegacyJournalEntry_Delete(t *testing.T) {
	dir := t.TempDir()
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load error: %v", err)
	}

	// First add via normal path
	if err := db.UpdateVideo("FC2-123", NewVideo("FC2-123")); err != nil {
		t.Fatalf("UpdateVideo error: %v", err)
	}

	// Now append a legacy delete entry
	legacy := legacyJournalEntry{
		Timestamp: GetCurrentTimestamp(),
		Operation: "delete",
		Code:      "FC2-123",
	}
	data, _ := json.Marshal(legacy)
	f, err := os.OpenFile(filepath.Join(dir, JournalFileName), os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		t.Fatalf("open journal error: %v", err)
	}
	f.Write(data)       //nolint:errcheck
	f.WriteString("\n") //nolint:errcheck
	f.Close()

	db2 := NewJSONDatabase(dir)
	if err := db2.Load(context.Background()); err != nil {
		t.Fatalf("Reload error: %v", err)
	}
	if _, exists := db2.root.Videos["FC2-123"]; exists {
		t.Error("expected legacy delete to remove FC2-123")
	}
}

func TestApplyLegacyJournalEntry_InvalidJSON(t *testing.T) {
	dir := t.TempDir()
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load error: %v", err)
	}

	// Write a line with no "op" field but invalid JSON for legacy format
	// This exercises the malformed-entry path (json.Unmarshal fails → return)
	f, err := os.OpenFile(filepath.Join(dir, JournalFileName), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0600)
	if err != nil {
		t.Fatalf("open journal error: %v", err)
	}
	// No "op" key → triggers legacy path. Nested invalid bytes → early return
	f.WriteString("{\"ts\":\"2024\",\"operation\":\"update\",\"code\":\"X\",\"video\":\"not-an-object\"}\n") //nolint:errcheck
	f.Close()

	db2 := NewJSONDatabase(dir)
	// Should not panic or error even with malformed data
	if err := db2.Load(context.Background()); err != nil {
		t.Fatalf("Load with invalid legacy entry should not error: %v", err)
	}
}

// ============================================================
// applyVideoJournalAdd — nil data path
// ============================================================

func TestApplyVideoJournalAdd_NilData(t *testing.T) {
	db, _ := setupTestDB(t)

	entry := &JournalEntry{Op: OpAdd, Type: TypeVideo, ID: "NIL-001", Data: nil}
	db.applyVideoJournalEntry(entry)

	// Should not add anything with nil data
	if _, exists := db.root.Videos["NIL-001"]; exists {
		t.Error("expected no video added for nil data")
	}
}

// ============================================================
// applyActressJournalUpsert — nil data path
// ============================================================

func TestApplyActressJournalUpsert_NilData(t *testing.T) {
	db, _ := setupTestDB(t)

	entry := &JournalEntry{Op: OpAdd, Type: TypeActress, ID: "nil-actress", Data: nil}
	db.applyActressJournalEntry(entry)

	if _, exists := db.root.Actresses["nil-actress"]; exists {
		t.Error("expected no actress added for nil data")
	}
}

// ============================================================
// loadJournal — empty lines are skipped
// ============================================================

func TestLoadJournal_EmptyLinesSkipped(t *testing.T) {
	dir := t.TempDir()
	db := NewJSONDatabase(dir)
	if err := db.Load(context.Background()); err != nil {
		t.Fatalf("Load error: %v", err)
	}

	// Write journal with blank lines between entries
	f, err := os.OpenFile(filepath.Join(dir, JournalFileName), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0600)
	if err != nil {
		t.Fatalf("open journal error: %v", err)
	}
	videoData, _ := json.Marshal(NewVideo("SSIS-999"))
	entry := JournalEntry{Op: OpAdd, Type: TypeVideo, ID: "SSIS-999", Data: videoData, Ts: GetCurrentTimestamp()}
	entryBytes, _ := json.Marshal(entry)
	f.WriteString("\n")   //nolint:errcheck
	f.Write(entryBytes)   //nolint:errcheck
	f.WriteString("\n\n") //nolint:errcheck
	f.Close()

	db2 := NewJSONDatabase(dir)
	if err := db2.Load(context.Background()); err != nil {
		t.Fatalf("Reload error: %v", err)
	}
	if _, exists := db2.root.Videos["SSIS-999"]; !exists {
		t.Error("expected SSIS-999 to be loaded despite empty lines")
	}
}
