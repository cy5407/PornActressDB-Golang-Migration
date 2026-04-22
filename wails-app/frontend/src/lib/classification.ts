import type { backend, database } from '../../wailsjs/go/models';

type SearchStatusField = 'avwiki_actress_status' | 'javdb_actress_status';
export type VideoDataWithSourceStatus = database.VideoData & Partial<Record<SearchStatusField, string>>;
export type CachedVideoLookup = { code: string; video: VideoDataWithSourceStatus | null };
export type CachedVideoLookupError = { code: string; error: unknown };

const FOUND_SEARCH_STATUSES = new Set(['found', 'searched_found']);

export function isFoundSearchStatus(status?: string): boolean {
  return status !== undefined && FOUND_SEARCH_STATUSES.has(status);
}

function createSearchResultFromVideo(
  code: string,
  video: VideoDataWithSourceStatus
): backend.SearchResult {
  return {
    code,
    title: video.title ?? '',
    studio: video.studio ?? '',
    release_date: video.release_date ?? '',
    url: video.url ?? '',
    actresses: video.actresses ?? [],
    method: video.search_method ?? '',
    error: '',
  } as backend.SearchResult;
}

export function mergeSearchResultsWithCachedVideos(
  searchResults: backend.SearchResult[],
  cachedVideos: Array<{ code: string; video: VideoDataWithSourceStatus | null }>
): backend.SearchResult[] {
  const merged = [...searchResults];
  const existingCodes = new Set(merged.map((sr) => sr.code));

  for (const { code, video } of cachedVideos) {
    if (!video || existingCodes.has(code)) {
      continue;
    }
    if (
      !isFoundSearchStatus(video.avwiki_actress_status) &&
      !isFoundSearchStatus(video.javdb_actress_status)
    ) {
      continue;
    }

    merged.push(createSearchResultFromVideo(code, video));
    existingCodes.add(code);
  }

  return merged;
}

export function buildCodeToActressMap(
  scanResults: backend.ScanResult[],
  searchResults: backend.SearchResult[],
  cachedVideos: Array<{ code: string; video: VideoDataWithSourceStatus | null }> = []
): Map<string, string> {
  const effectiveResults = mergeSearchResultsWithCachedVideos(searchResults, cachedVideos);
  const codeToActress = new Map<string, string>();

  for (const sr of effectiveResults) {
    codeToActress.set(sr.code, sr.actresses?.[0] ?? '未分類');
  }

  for (const scanResult of scanResults) {
    if (codeToActress.has(scanResult.code)) {
      continue;
    }
    const cachedVideo = cachedVideos.find((entry) => entry.code === scanResult.code)?.video;
    const cachedActress = cachedVideo?.actresses?.[0];
    if (cachedActress) {
      codeToActress.set(scanResult.code, cachedActress);
    }
  }

  return codeToActress;
}
