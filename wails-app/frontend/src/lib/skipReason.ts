import type { mover } from '../../wailsjs/go/models';

export interface SkipCompanion {
  destination: string;
  movedFrom: string;
}

function normalizePath(p: string): string {
  return p.replace(/\//g, '\\').replace(/[\\]+$/, '').toLowerCase();
}

export function buildSkipCompanionMap(
  results: readonly mover.MoveResult[] | undefined | null
): Map<string, SkipCompanion> {
  const out = new Map<string, SkipCompanion>();
  if (!results || results.length === 0) return out;

  const successByDest = new Map<string, mover.MoveResult>();
  for (const r of results) {
    if (r.success && !r.skipped && r.destination) {
      const key = normalizePath(r.destination);
      if (!successByDest.has(key)) successByDest.set(key, r);
    }
  }
  if (successByDest.size === 0) return out;

  for (const r of results) {
    if (!r.skipped || !r.destination) continue;
    const sibling = successByDest.get(normalizePath(r.destination));
    if (!sibling) continue;
    if (normalizePath(sibling.source) === normalizePath(r.source)) continue;
    out.set(r.source, { destination: sibling.destination, movedFrom: sibling.source });
  }
  return out;
}

export function formatSkipReason(
  result: mover.MoveResult,
  companions: Map<string, SkipCompanion>
): string {
  if (result.source === result.destination) return '來源=目標（同路徑）';
  const c = companions.get(result.source);
  if (c) return `同檔已從 ${c.movedFrom} 搬至此處`;
  return result.error || '衝突略過';
}
