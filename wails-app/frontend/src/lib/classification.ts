import type { backend, database } from '../../wailsjs/go/models';

export interface MultiActressCandidate {
  code: string;
  path: string;
  actresses: string[];
}

type SearchStatusField = 'avwiki_actress_status' | 'javdb_actress_status';
export type VideoDataWithSourceStatus = database.VideoData & Partial<Record<SearchStatusField, string>>;
export type CachedVideoLookup = { code: string; video: VideoDataWithSourceStatus | null };
export type CachedVideoLookupError = { code: string; error: unknown };

const FOUND_SEARCH_STATUSES = new Set(['found', 'searched_found']);
const TITLE_KEYWORDS = [
  '初めて', '初体験', 'デビュー', '新人', '中出し', '解禁', '痴女', '痴漢', '輪姦', '調教', '陵辱', '凌辱',
  '犯され', '犯す', '侵され', '姦', 'おっぱい', '巨乳', '美乳', '爆乳', '美脚', '美尻', '美少女', '学園',
  '学校', 'スポーツ', 'ビーチ', '温泉', '寝取', '不倫', '近親', '姪っ子', '義母', '義父', '義姉', '義妹',
  '兄嫁', '勃起', '興奮', '絶頂', 'イキ', '逝き', '喘ぎ', '乱れ', '水着', '制服', 'コスプレ', '下着', '裸',
  '全裸', '半裸', 'エレガンス', 'エロ', '共演', '出演者', '演員', '女優', '続編', '完全版', '総集編', '媚薬',
  'キメセク', '洗脳', 'ドキュメント', '企画', 'ガチ', '帰省', '成長期', '田舎', '中年', 'オジ', 'おじさん',
];
const TITLE_KEYWORDS_ZH = ['中出', '解禁', '初體驗', '新人', '巨乳', '美乳', '美腿', '學園', '學校', '溫泉', '制服', '泳裝', '共演'];
const VERB_PATTERNS = [/^て$/, /^つい/, /られ/, /させ/, /ちゃ/, /しちゃ/, /^した/, /^する/, /され/, /^を/, /^が/, /で$/];
const SENTENCE_FRAGMENT_PATTERNS = [/した/, /して/, /てる/, /たら/, /のに/, /れて/, /っ子/, /がお/, /を/];
const NAME_SPLIT_PATTERN = /[#／/,，、&＆]+/;

export function isFoundSearchStatus(status?: string): boolean {
  return status !== undefined && FOUND_SEARCH_STATUSES.has(status);
}

function containsKeyword(name: string, keywords: string[]): boolean {
  return keywords.some((keyword) => name.includes(keyword));
}

function looksLikeTruncatedTitle(name: string): boolean {
  return /[ガオ自香期]$/.test(name) && name.length > 10;
}

function isNumericOrSymbolOnly(name: string): boolean {
  return !/[A-Za-zぁ-ゟ゠-ヿ一-龯々ー]/.test(name);
}

function countHiragana(name: string): number {
  return (name.match(/[ぁ-ゟ]/g) ?? []).length;
}

function failsHiraganaRatio(name: string): boolean {
  const hiraganaCount = countHiragana(name);
  return name.length > 5 && hiraganaCount > name.length * 0.6;
}

function looksLikeSentenceFragment(name: string): boolean {
  const hiraganaCount = countHiragana(name);
  if (name.length <= 6 || hiraganaCount < 3) {
    return false;
  }
  return SENTENCE_FRAGMENT_PATTERNS.some((pattern) => pattern.test(name));
}

function passesLanguageShape(name: string): boolean {
  if (/[ぁ-ゟ゠-ヿ一-龯]/.test(name)) {
    return true;
  }
  if (/^[A-Za-z\s]+$/.test(name)) {
    return name.includes(' ') || /^[A-Za-z]{2,12}$/.test(name);
  }
  return false;
}

function expandActressCandidates(raw: string): string[] {
  const normalized = raw.trim();
  if (!normalized) {
    return [];
  }
  const parts = normalized
    .split(NAME_SPLIT_PATTERN)
    .map((part) => part.trim())
    .filter(Boolean);
  return parts.length > 1 ? parts : [normalized];
}

export function isValidActressName(name: string): boolean {
  const normalized = name.trim();
  if (!normalized || normalized.length < 2 || normalized.length > 15) {
    return false;
  }
  if (normalized.includes('#')) {
    return false;
  }
  if (containsKeyword(normalized, TITLE_KEYWORDS) || containsKeyword(normalized, TITLE_KEYWORDS_ZH)) {
    return false;
  }
  if (VERB_PATTERNS.some((pattern) => pattern.test(normalized))) {
    return false;
  }
  if (
    looksLikeTruncatedTitle(normalized) ||
    looksLikeSentenceFragment(normalized) ||
    isNumericOrSymbolOnly(normalized) ||
    failsHiraganaRatio(normalized)
  ) {
    return false;
  }
  return passesLanguageShape(normalized);
}

export function sanitizeActressNames(actresses: string[]): string[] {
  const seen = new Set<string>();
  const sanitized: string[] = [];
  for (const actress of actresses) {
    for (const candidate of expandActressCandidates(actress)) {
      const normalized = candidate.trim();
      if (!isValidActressName(normalized) || seen.has(normalized)) {
        continue;
      }
      seen.add(normalized);
      sanitized.push(normalized);
    }
  }
  return sanitized;
}

export function shouldFetchCachedVideoFallback(searchResult?: backend.SearchResult | null): boolean {
  return !searchResult || sanitizeActressNames(searchResult.actresses ?? []).length === 0;
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
    actresses: sanitizeActressNames(video.actresses ?? []),
    method: video.search_method ?? '',
    error: '',
  } as backend.SearchResult;
}

export function mergeSearchResultsWithCachedVideos(
  searchResults: backend.SearchResult[],
  cachedVideos: Array<{ code: string; video: VideoDataWithSourceStatus | null }>
): backend.SearchResult[] {
  const merged = searchResults.map((sr) => ({
    ...sr,
    actresses: sanitizeActressNames(sr.actresses ?? []),
  }));
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

export function collectMultiActressCandidates(
  scanResults: backend.ScanResult[],
  searchResults: backend.SearchResult[],
  cachedVideos: Array<{ code: string; video: VideoDataWithSourceStatus | null }> = []
): MultiActressCandidate[] {
  const targetsByCode = new Map(scanResults.map((result) => [result.code, result]));
  const mergedCandidates = mergeSearchResultsWithCachedVideos(searchResults, cachedVideos)
    .filter((sr) => targetsByCode.has(sr.code))
    .map((sr) => ({
      code: sr.code,
      path: targetsByCode.get(sr.code)?.path ?? sr.code,
      actresses: sanitizeActressNames(sr.actresses ?? []),
    }));

  const candidateByCode = new Map<string, MultiActressCandidate>();
  for (const candidate of mergedCandidates) {
    if (candidate.actresses.length > 1) {
      candidateByCode.set(candidate.code, candidate);
    }
  }

  for (const { code, video } of cachedVideos) {
    if (!video || candidateByCode.has(code) || !targetsByCode.has(code)) {
      continue;
    }
    const actresses = sanitizeActressNames(video.actresses ?? []);
    if (actresses.length > 1) {
      candidateByCode.set(code, {
        code,
        path: targetsByCode.get(code)?.path ?? code,
        actresses,
      });
    }
  }

  return Array.from(candidateByCode.values());
}

export function buildCodeToActressMap(
  scanResults: backend.ScanResult[],
  searchResults: backend.SearchResult[],
  cachedVideos: Array<{ code: string; video: VideoDataWithSourceStatus | null }> = []
): Map<string, string> {
  const effectiveResults = mergeSearchResultsWithCachedVideos(searchResults, cachedVideos);
  const codeToActress = new Map<string, string>();

  for (const sr of effectiveResults) {
    const sanitizedActress = sanitizeActressNames(sr.actresses ?? [])[0];
    if (sanitizedActress) {
      codeToActress.set(sr.code, sanitizedActress);
    }
  }

  for (const scanResult of scanResults) {
    if (codeToActress.has(scanResult.code)) {
      continue;
    }
    const cachedVideo = cachedVideos.find((entry) => entry.code === scanResult.code)?.video;
    const cachedActress = sanitizeActressNames(cachedVideo?.actresses ?? [])[0];
    if (cachedActress) {
      codeToActress.set(scanResult.code, cachedActress);
    }
  }

  return codeToActress;
}
