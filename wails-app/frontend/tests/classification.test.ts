import assert from 'node:assert/strict';
import type { backend, database } from '../wailsjs/go/models';
import {
  buildCodeToActressMap,
  mergeSearchResultsWithCachedVideos,
} from '../src/lib/classification.ts';

function makeSearchResult(source: Partial<backend.SearchResult>): backend.SearchResult {
  return {
    code: '',
    title: '',
    studio: '',
    release_date: '',
    url: '',
    actresses: [],
    method: '',
    ...source,
  } as backend.SearchResult;
}

function makeScanResult(source: Partial<backend.ScanResult>): backend.ScanResult {
  return {
    path: '',
    code: '',
    ...source,
  } as backend.ScanResult;
}

function makeVideo(source: Partial<database.VideoData>): database.VideoData {
  return {
    code: '',
    title: '',
    studio: '',
    release_date: '',
    url: '',
    actresses: [],
    search_status: '',
    last_search_date: '',
    created_at: '',
    updated_at: '',
    metadata: { source: '', confidence: 0 },
    ...source,
  } as database.VideoData;
}

(function testMergeSearchResultsWithCachedVideosAddsFoundCachedEntries() {
  const live = [makeSearchResult({ code: 'LIVE-001', actresses: ['現場女優'] })];
  const cached = [
    {
      code: 'CACHE-001',
      video: makeVideo({
        code: 'CACHE-001',
        actresses: ['快取女優'],
        search_method: 'avwiki',
        avwiki_actress_status: 'found',
      }),
    },
  ];

  const merged = mergeSearchResultsWithCachedVideos(live, cached);
  assert.equal(merged.length, 2);
  assert.equal(merged[1].code, 'CACHE-001');
  assert.deepEqual(merged[1].actresses, ['快取女優']);
  assert.equal(merged[1].method, 'avwiki');
})();

(function testMergeSearchResultsWithCachedVideosSkipsNotFoundCachedEntries() {
  const merged = mergeSearchResultsWithCachedVideos([], [
    {
      code: 'MISS-001',
      video: makeVideo({
        code: 'MISS-001',
        actresses: ['不應納入'],
        avwiki_actress_status: 'not_found',
      }),
    },
  ]);

  assert.equal(merged.length, 0);
})();

(function testBuildCodeToActressMapFallsBackToCachedVideosForMove() {
  const scanResults = [makeScanResult({ code: 'WAAA-609', path: 'Z:/分類/WAAA-609.mp4' })];
  const codeToActress = buildCodeToActressMap(scanResults, [], [
    {
      code: 'WAAA-609',
      video: makeVideo({
        code: 'WAAA-609',
        actresses: ['葵司'],
        search_status: 'success',
      }),
    },
  ]);

  assert.equal(codeToActress.get('WAAA-609'), '葵司');
})();

console.log('classification tests passed');
