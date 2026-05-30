// Package database — journal.go retains only the videoFieldUpdateHandlers
// map shared between ApplyVideoFieldUpdates (runtime SQLite UpdateVideoFields)
// and the jsonfixture.JSONDatabase mirror. Every other journal-handling
// method moved with JSONDatabase to pkg/database/jsonfixture.
package database

// videoFieldUpdateHandlers enumerates the per-key updaters that
// ApplyVideoFieldUpdates dispatches to. Kept unexported here so it
// stays a single source of truth; jsonfixture must go through the
// exported ApplyVideoFieldUpdates helper (see sqlite_runtime.go) rather
// than touching this map across package boundaries.
var videoFieldUpdateHandlers = map[string]func(*VideoData, any){
	"id": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.ID = v
		}
	},
	"code": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.Code = v
		}
	},
	"created_at": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.CreatedAt = v
		}
	},
	"metadata": func(video *VideoData, value any) {
		if m, ok := value.(map[string]any); ok {
			if src, ok := m["source"].(string); ok {
				video.Metadata.Source = src
			}
			if conf, ok := m["confidence"].(float64); ok {
				video.Metadata.Confidence = conf
			}
		}
	},
	"title": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.Title = v
		}
	},
	"studio": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.Studio = v
		}
	},
	"studio_code": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.StudioCode = v
		}
	},
	"release_date": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.ReleaseDate = v
		}
	},
	"url": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.URL = v
		}
	},
	"actresses": func(video *VideoData, value any) {
		if v, ok := value.([]any); ok {
			actresses := make([]string, 0, len(v))
			for _, a := range v {
				if s, ok := a.(string); ok {
					actresses = append(actresses, s)
				}
			}
			video.Actresses = actresses
		}
	},
	"search_status": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.SearchStatus = v
		}
	},
	"last_search_date": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.LastSearchDate = v
		}
	},
	"avwiki_actress_status": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.AVWikiActressStatus = v
		}
	},
	"avwiki_last_search_date": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.AVWikiLastSearchDate = v
		}
	},
	"javdb_actress_status": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.JAVDBActressStatus = v
		}
	},
	"javdb_last_search_date": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.JAVDBLastSearchDate = v
		}
	},
	"original_filename": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.OriginalFilename = v
		}
	},
	"file_path": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.FilePath = v
		}
	},
	"search_method": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.SearchMethod = v
		}
	},
	"error": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.Error = v
		}
	},
	"error_kind": func(video *VideoData, value any) {
		if v, ok := value.(string); ok {
			video.ErrorKind = v
		}
	},
}
