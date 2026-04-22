import assert from 'node:assert/strict';
import type { backend, database } from '../wailsjs/go/models';
import {
  buildCodeToActressMap,
  collectMultiActressCandidates,
  mergeSearchResultsWithCachedVideos,
  sanitizeActressNames,
  shouldFetchCachedVideoFallback,
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
  const live = [makeSearchResult({ code: 'LIVE-001', actresses: ['現場女優A'] })];
  const cached = [
    {
      code: 'CACHE-001',
      video: makeVideo({
        code: 'CACHE-001',
        actresses: ['葵司'],
        search_method: 'avwiki',
        avwiki_actress_status: 'found',
      }),
    },
  ];

  const merged = mergeSearchResultsWithCachedVideos(live, cached);
  assert.equal(merged.length, 2);
  assert.equal(merged[1].code, 'CACHE-001');
  assert.deepEqual(merged[1].actresses, ['葵司']);
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

(function testBuildCodeToActressMapSanitizesJoinedFallbackNames() {
  const scanResults = [makeScanResult({ code: 'JUQ-001', path: 'Z:/分類/JUQ-001.mp4' })];
  const codeToActress = buildCodeToActressMap(scanResults, [], [
    {
      code: 'JUQ-001',
      video: makeVideo({
        code: 'JUQ-001',
        actresses: ['木下ひまり #森沢かな #橘メアリー #百永さりな'],
        search_status: 'success',
      }),
    },
  ]);

  assert.equal(codeToActress.get('JUQ-001'), '木下ひまり');
})();

(function testSanitizeActressNamesFiltersTitleLikeNames() {
  const sanitized = sanitizeActressNames([
    '葵司',
    '可愛い顔した魔性少女がおっぱ',
    '木下ひまり #森沢かな #橘メアリー #百永さりな',
    '多人共演',
  ]);

  assert.deepEqual(sanitized, ['葵司', '木下ひまり', '森沢かな', '橘メアリー', '百永さりな']);
})();

(function testSanitizeActressNamesKeepsSingleLatinStageNames() {
  const sanitized = sanitizeActressNames(['RION', 'AIKA', 'JULIA', 'Rio']);
  assert.deepEqual(sanitized, ['RION', 'AIKA', 'JULIA', 'Rio']);
})();

(function testBuildCodeToActressMapFallsBackToCachedWhenLiveResultSanitizesEmpty() {
  const scanResults = [makeScanResult({ code: 'SSIS-001', path: 'Z:/分類/SSIS-001.mp4' })];
  const live = [
    makeSearchResult({
      code: 'SSIS-001',
      actresses: ['可愛い顔した魔性少女がおっぱ'],
    }),
  ];
  const cached = [
    {
      code: 'SSIS-001',
      video: makeVideo({
        code: 'SSIS-001',
        actresses: ['RION'],
        search_status: 'success',
      }),
    },
  ];

  const codeToActress = buildCodeToActressMap(scanResults, live, cached);
  assert.equal(codeToActress.get('SSIS-001'), 'RION');
})();

(function testShouldFetchCachedVideoFallbackWhenLiveResultMissingOrSanitizedEmpty() {
  assert.equal(shouldFetchCachedVideoFallback(undefined), true);
  assert.equal(
    shouldFetchCachedVideoFallback(makeSearchResult({ code: 'A', actresses: ['可愛い顔した魔性少女がおっぱ'] })),
    true
  );
  assert.equal(
    shouldFetchCachedVideoFallback(makeSearchResult({ code: 'B', actresses: ['RION'] })),
    false
  );
})();

(function testCollectMultiActressCandidatesIncludesFallbackCachedVideos() {
  const scanResults = [
    makeScanResult({ code: 'MIDE-001', path: 'Z:/分類/MIDE-001.mp4' }),
  ];
  const candidates = collectMultiActressCandidates(scanResults, [], [
    {
      code: 'MIDE-001',
      video: makeVideo({
        code: 'MIDE-001',
        actresses: ['森沢かな', '橘メアリー'],
        search_status: 'success',
      }),
    },
  ]);

  assert.equal(candidates.length, 1);
  assert.equal(candidates[0].code, 'MIDE-001');
  assert.deepEqual(candidates[0].actresses, ['森沢かな', '橘メアリー']);
})();

console.log('classification tests passed');

