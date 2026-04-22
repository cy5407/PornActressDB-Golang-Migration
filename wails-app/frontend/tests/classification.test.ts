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

(function testSanitizeActressNamesKeepsTrustedNames() {
  const sanitized = sanitizeActressNames(['瀧本雫葉', '蒼乃美月', '綾瀬天', '東雲すみれ', '五芭', '天然美月']);
  assert.deepEqual(sanitized, ['瀧本雫葉', '蒼乃美月', '綾瀬天', '東雲すみれ', '五芭', '天然美月']);
})();

(function testSanitizeActressNamesKeepsRepeatedFormStageNames() {
  const sanitized = sanitizeActressNames(['COCO', 'MIMI']);
  assert.deepEqual(sanitized, ['COCO', 'MIMI']);
})();

(function testSanitizeActressNamesRejectsKnownPollutionStrings() {
  const sanitized = sanitizeActressNames([
    'ゆうきすず', '周年だよん', '限界突破', 'スペンス乳腺', '三田', 'ウブ女生徒に好かれ理性なくし',
    'アルバイト先の真面目なアノ娘', '白くて', '濃密セックス', '交わる体液', '可愛い', '優しい', 'いつ',
    '男クンのお宅に', '快感に逆らえずビックンガック', '気が弱い', 'よりシコい女体', 'おっ', 'メイド', '気持',
    '絶倫上司と新入', 'スプラッシュ雫葉', '汗だ', 'パンチラで誘惑するからかい上', '普通', '童貞君チ',
    'ヨダレだらだらナースの接吻と', '担任教師の僕は生徒の誘惑に負', '澪が気持ちよ', '主人', 'の指マンがストライクすぎ',
    '無防備すぎる幼馴染のノーブラ', 'ビンビン敏感チクビを澪が優', '究極の美肌スレンダー肉体の質', '嫁の連れ子を',
    '週間お貸ししま', 'みおっち激しゃぶフェラフェラ', '日曜の朝', '寝起きの澪が可愛く', '奇跡', '絶対',
    '舐めるのスキだからベロベロ', '顔射の美学', 'おねだりチ'
  ]);
  assert.deepEqual(sanitized, []);
})();

(function testSanitizeActressNamesRejectsMitaButKeepsMitaMarin() {
  const sanitized = sanitizeActressNames(['三田', '三田真鈴']);
  assert.deepEqual(sanitized, ['三田真鈴']);
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

(function testCollectMultiActressCandidatesDoesNotTreatSingleValidNamePlusJunkAsMulti() {
  const scanResults = [makeScanResult({ code: 'ABF-171', path: 'Z:/分類/ABF-171.mp4' })];
  const searchResults = [
    makeSearchResult({
      code: 'ABF-171',
      actresses: ['天然美月', '可愛い', 'メイド'],
    }),
  ];

  const candidates = collectMultiActressCandidates(scanResults, searchResults, []);
  assert.deepEqual(candidates, []);

  const codeToActress = buildCodeToActressMap(scanResults, searchResults, []);
  assert.equal(codeToActress.get('ABF-171'), '天然美月');
})();

(function testCollectMultiActressCandidatesKeepsTrueMultiAfterFilteringJunk() {
  const scanResults = [makeScanResult({ code: 'MIDV-488', path: 'Z:/分類/MIDV-488.mp4' })];
  const searchResults = [
    makeSearchResult({
      code: 'MIDV-488',
      actresses: ['瀧本雫葉', '蒼乃美月', '可愛い'],
    }),
  ];

  const candidates = collectMultiActressCandidates(scanResults, searchResults, []);
  assert.equal(candidates.length, 1);
  assert.deepEqual(candidates[0].actresses, ['瀧本雫葉', '蒼乃美月']);
})();

(function testCollectMultiActressCandidatesDoesNotTreatTruncatedMitaAsIndependentActress() {
  const scanResults = [makeScanResult({ code: 'MIDA-367', path: 'Z:/分類/MIDA-367.mp4' })];
  const searchResults = [
    makeSearchResult({
      code: 'MIDA-367',
      actresses: ['三田真鈴', '三田'],
    }),
  ];

  const candidates = collectMultiActressCandidates(scanResults, searchResults, []);
  assert.deepEqual(candidates, []);

  const codeToActress = buildCodeToActressMap(scanResults, searchResults, []);
  assert.equal(codeToActress.get('MIDA-367'), '三田真鈴');
})();

console.log('classification tests passed');

