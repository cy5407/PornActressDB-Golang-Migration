import type { backend, mover } from '../../wailsjs/go/models';

type ScanResultLike = Pick<backend.ScanResult, 'path' | 'code'>;
type MoveResultLike = Pick<mover.MoveResult, 'source' | 'destination' | 'success' | 'skipped' | 'error'>;
type BatchResultLike = { results?: MoveResultLike[] | null };

export interface StudioMoveBlockedItem {
  path: string;
  code: string;
  parentDir: string;
  skippedDestination: string;
  skippedReason: string;
}

export interface StudioMoveGuardResult {
  blocked: StudioMoveBlockedItem[];
  movedActressDirs: string[];
}

function normalizePath(p: string): string {
  if (!p) return '';
  return p.replace(/\//g, '\\').replace(/[\\]+$/, '').toLowerCase();
}

function parentDirOf(p: string): string {
  if (!p) return '';
  const sep = p.includes('\\') ? '\\' : '/';
  return p.split(sep).slice(0, -1).join(sep);
}

/**
 * Decide whether片商分類 should be blocked because a previous BatchMove left
 * skipped files in scanResults. The dangerous case is same-name cross-dir
 * skip — the file stays at e.g. `B\KUSE-042-1.mp4`, whose parentDir is NOT
 * an actress folder; handleStudioMove would otherwise treat `B\` as an actress
 * dir and sweep up unrelated siblings.
 */
export function evaluateStudioMoveGuard(args: {
  scanResults: readonly ScanResultLike[];
  lastBatchResult: BatchResultLike | null | undefined;
}): StudioMoveGuardResult {
  const { scanResults, lastBatchResult } = args;
  const results = lastBatchResult?.results;
  if (!results || results.length === 0) {
    return { blocked: [], movedActressDirs: [] };
  }

  const skippedSources = new Map<string, MoveResultLike>();
  const movedDirSet = new Set<string>();

  for (const r of results) {
    if (!r) continue;
    if (r.skipped) {
      const srcKey = normalizePath(r.source);
      const dstKey = normalizePath(r.destination ?? '');
      // source == destination 在 Go 端是合法 no-op skip（MoveFile 的同路徑保護），
      // 來源並未真的留在「不是女優目錄」的位置 — 不應觸發 T3 guard。
      if (srcKey && srcKey !== dstKey && !skippedSources.has(srcKey)) {
        skippedSources.set(srcKey, r);
      }
    }
    if (r.success && !r.skipped && r.destination) {
      const dir = parentDirOf(r.destination);
      if (dir) movedDirSet.add(normalizePath(dir));
    }
  }

  if (skippedSources.size === 0) {
    return { blocked: [], movedActressDirs: [...movedDirSet] };
  }

  const blocked: StudioMoveBlockedItem[] = [];
  for (const r of scanResults) {
    const skipped = skippedSources.get(normalizePath(r.path));
    if (!skipped) continue;
    blocked.push({
      path: r.path,
      code: r.code,
      parentDir: parentDirOf(r.path),
      skippedDestination: skipped.destination ?? '',
      skippedReason: skipped.error ?? '同名跨目錄略過',
    });
  }

  return { blocked, movedActressDirs: [...movedDirSet] };
}

export function formatStudioMoveBlockedMessage(
  blocked: readonly StudioMoveBlockedItem[]
): string {
  if (blocked.length === 0) return '';
  const codes = Array.from(new Set(blocked.map((b) => b.code))).filter(Boolean);
  const head = codes.slice(0, 5).join('、');
  const more = codes.length > 5 ? `…等 ${codes.length} 個番號` : '';
  const codeHint = head ? `（番號：${head}${more}）` : '';
  return `偵測到 ${blocked.length} 個檔案未進入女優目錄${codeHint}，請先處理略過清單或重新 scan。詳見「上次移動結果」對話框。`;
}
