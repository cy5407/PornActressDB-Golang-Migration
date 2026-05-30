// Package database — jsondb.go now hosts only the JSON-shaped helpers
// that the SQLite runtime still depends on (merge source loading,
// backup file housekeeping, primary-studio tie-breaking, ...). The
// JSONDatabase type itself moved to pkg/database/jsonfixture; it is
// only used for import / export / legacy-tools fixtures and is not on
// the runtime path.
package database

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"actress-classifier/pkg/safefile"
)

var (
	// ErrNotFound 資料不存在錯誤
	ErrNotFound = errors.New("video not found")
	// ErrInvalidCode 無效番號錯誤
	ErrInvalidCode = errors.New("invalid video code")
)

// Video 是 VideoData 的別名（向後相容；runtime API 簽章共用）
type Video = VideoData

// LoadMergeSourceData reads a JSON merge source file and returns the
// parsed DatabaseData with nil maps / slices normalised. Used by both
// the SQLite runtime MergeFromFile path and the jsonfixture
// JSONDatabase.MergeFromFile path.
func LoadMergeSourceData(sourceFile string) (*DatabaseData, error) {
	absPath, err := resolveMergeSourcePath(sourceFile)
	if err != nil {
		return nil, err
	}

	sourceData, err := safefile.ReadFile(absPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read source file: %w", err)
	}

	var sourceRoot DatabaseData
	if err := json.Unmarshal(sourceData, &sourceRoot); err != nil {
		return nil, fmt.Errorf("failed to parse source JSON: %w", err)
	}

	normalizeMergeSourceData(&sourceRoot)
	return &sourceRoot, nil
}

func resolveMergeSourcePath(sourceFile string) (string, error) {
	cleanedPath := filepath.Clean(sourceFile)
	absPath, err := filepath.Abs(cleanedPath)
	if err != nil {
		return "", fmt.Errorf("invalid source file path: %w", err)
	}
	if filepath.Clean(absPath) != absPath {
		return "", fmt.Errorf("suspicious source file path detected: %s", sourceFile)
	}
	return absPath, nil
}

func normalizeMergeSourceData(sourceRoot *DatabaseData) {
	if sourceRoot.Videos == nil {
		sourceRoot.Videos = make(map[string]*VideoData)
	}
	if sourceRoot.Actresses == nil {
		sourceRoot.Actresses = make(map[string]*ActressData)
	}
	if sourceRoot.Links == nil {
		sourceRoot.Links = []VideoActressLink{}
	}
}

// PrepareVideoForMerge normalises a per-row video before it is merged
// into the destination database. It returns the resolved code, a
// shallow copy of the video with code/ID fields rewritten and
// UpdatedAt stamped, and an ok=false sentinel when the row should be
// skipped entirely (nil video or unresolvable code).
func PrepareVideoForMerge(mapCode string, video *VideoData, now string) (string, *VideoData, bool) {
	if video == nil {
		return "", nil, false
	}

	code := strings.TrimSpace(video.GetCode())
	if code == "" {
		code = strings.TrimSpace(mapCode)
	}
	if code == "" {
		return "", nil, false
	}

	videoCopy := *video
	videoCopy.Code = code
	if videoCopy.Code == "" && videoCopy.ID != "" {
		videoCopy.Code = videoCopy.ID
	}
	if videoCopy.Code != "" {
		videoCopy.ID = ""
	}
	videoCopy.UpdatedAt = now
	return code, &videoCopy, true
}

// IsBackupJSONFileName reports whether a backup directory entry name
// matches the `backup_*.json` convention used by JSON-side backups
// (and now also surfaced by the SQLite runtime BackupList).
func IsBackupJSONFileName(name string) bool {
	return strings.HasPrefix(name, "backup_") && strings.HasSuffix(name, ".json")
}

// DeleteExpiredBackups removes backup_*.json entries older than
// `cutoff` (parsed from the filename) from the given directory and
// returns the count of removed files.
func DeleteExpiredBackups(backupDir string, entries []os.DirEntry, cutoff time.Time) int {
	deleted := 0
	for _, entry := range entries {
		name := entry.Name()
		if entry.IsDir() || !IsBackupJSONFileName(name) {
			continue
		}
		backupDate, ok := parseBackupDate(name)
		if !ok || !backupDate.Before(cutoff) {
			continue
		}
		if os.Remove(filepath.Join(backupDir, name)) == nil {
			deleted++
		}
	}
	return deleted
}

func parseBackupDate(name string) (time.Time, bool) {
	stem := strings.TrimSuffix(strings.TrimPrefix(name, "backup_"), ".json")
	parts := strings.SplitN(stem, "_", 2)
	if len(parts) == 0 {
		return time.Time{}, false
	}
	backupDate, err := time.Parse("2006-01-02", parts[0])
	if err != nil {
		return time.Time{}, false
	}
	return backupDate, true
}

// RemoveOldestBackups trims a sorted ascending list of backup file
// paths down to maxCount entries by deleting the oldest from disk and
// returns the count of files removed.
func RemoveOldestBackups(paths []string, maxCount int) int {
	deleted := 0
	for len(paths) > maxCount {
		if os.Remove(paths[0]) == nil {
			deleted++
		}
		paths = paths[1:]
	}
	return deleted
}

// SelectPrimaryStudio picks the studio with the highest count from
// `studioCounts`; on ties it returns the lexicographically smaller
// name. An empty map returns "".
func SelectPrimaryStudio(studioCounts map[string]int) string {
	if len(studioCounts) == 0 {
		return ""
	}
	maxStudio, maxCount := "", 0
	for studio, count := range studioCounts {
		if count > maxCount || (count == maxCount && studio < maxStudio) {
			maxStudio, maxCount = studio, count
		}
	}
	return maxStudio
}
