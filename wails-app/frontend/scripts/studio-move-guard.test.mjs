// Unit test for src/lib/studioMoveGuard.ts and src/lib/paths.ts.
//
// Frontend has no test runner; this script transpiles the TS helpers with
// esbuild (already installed) and runs assertions via node:assert. Run with:
//   node scripts/studio-move-guard.test.mjs
import esbuild from 'esbuild';
import { readFileSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';

const here = dirname(fileURLToPath(import.meta.url));

async function loadTs(relPathFromFrontendRoot, outName) {
  const src = readFileSync(join(here, '..', relPathFromFrontendRoot), 'utf8');
  const { code } = esbuild.transformSync(src, {
    loader: 'ts',
    format: 'esm',
    target: 'es2022',
  });
  const outDir = mkdtempSync(join(tmpdir(), 'guard-test-'));
  const outFile = join(outDir, outName);
  writeFileSync(outFile, code);
  return import(pathToFileURL(outFile).href);
}

const { evaluateStudioMoveGuard, formatStudioMoveBlockedMessage } =
  await loadTs('src/lib/studioMoveGuard.ts', 'studioMoveGuard.mjs');
const { basenameOf } = await loadTs('src/lib/paths.ts', 'paths.mjs');

function move(o) {
  return {
    source: '',
    destination: '',
    success: false,
    skipped: false,
    error: '',
    ...o,
  };
}

function batch(results) {
  return { results };
}

let cases = 0;
function ok(name, fn) {
  fn();
  cases++;
  console.log(`  ✓ ${name}`);
}

console.log('studioMoveGuard');

ok('lastBatchResult null → no blocks', () => {
  const r = evaluateStudioMoveGuard({
    scanResults: [{ path: 'C:\\A\\KUSE-042-1.mp4', code: 'KUSE-042' }],
    lastBatchResult: null,
  });
  assert.deepEqual(r.blocked, []);
  assert.deepEqual(r.movedActressDirs, []);
});

ok('lastBatchResult with empty results → no blocks', () => {
  const r = evaluateStudioMoveGuard({
    scanResults: [{ path: 'C:\\A\\KUSE-042-1.mp4', code: 'KUSE-042' }],
    lastBatchResult: { results: [] },
  });
  assert.deepEqual(r.blocked, []);
});

ok('all moves succeeded → no blocks; movedActressDirs is exposed', () => {
  const r = evaluateStudioMoveGuard({
    scanResults: [],
    lastBatchResult: batch([
      move({
        source: 'C:\\A\\KUSE-042-1.mp4',
        destination: 'D:\\out\\夏目響\\KUSE-042-1.mp4',
        success: true,
      }),
    ]),
  });
  assert.deepEqual(r.blocked, []);
  assert.equal(r.movedActressDirs.length, 1);
  assert.match(r.movedActressDirs[0], /夏目響/);
});

ok('skipped source not present in scanResults → no block', () => {
  const r = evaluateStudioMoveGuard({
    scanResults: [{ path: 'C:\\C\\OTHER-001.mp4', code: 'OTHER-001' }],
    lastBatchResult: batch([
      move({
        source: 'C:\\B\\KUSE-042-1.mp4',
        destination: 'D:\\out\\夏目響\\KUSE-042-1.mp4',
        skipped: true,
        success: true,
        error: '',
      }),
    ]),
  });
  assert.deepEqual(r.blocked, []);
});

ok('T3 scenario — same-name cross-dir skip leaves B in scanResults → blocked', () => {
  const r = evaluateStudioMoveGuard({
    scanResults: [{ path: 'C:\\B\\KUSE-042-1.mp4', code: 'KUSE-042' }],
    lastBatchResult: batch([
      move({
        source: 'C:\\A\\KUSE-042-1.mp4',
        destination: 'D:\\out\\夏目響\\KUSE-042-1.mp4',
        success: true,
      }),
      move({
        source: 'C:\\B\\KUSE-042-1.mp4',
        destination: 'D:\\out\\夏目響\\KUSE-042-1.mp4',
        success: true,
        skipped: true,
      }),
    ]),
  });
  assert.equal(r.blocked.length, 1);
  assert.equal(r.blocked[0].path, 'C:\\B\\KUSE-042-1.mp4');
  assert.equal(r.blocked[0].code, 'KUSE-042');
  assert.equal(r.blocked[0].parentDir, 'C:\\B');
  assert.equal(r.blocked[0].skippedDestination, 'D:\\out\\夏目響\\KUSE-042-1.mp4');
});

ok('path normalization — forward slashes match backward slashes', () => {
  const r = evaluateStudioMoveGuard({
    scanResults: [{ path: 'C:/B/KUSE-042-1.mp4', code: 'KUSE-042' }],
    lastBatchResult: batch([
      move({
        source: 'C:\\B\\KUSE-042-1.mp4',
        destination: 'D:\\out\\夏目響\\KUSE-042-1.mp4',
        skipped: true,
        success: true,
      }),
    ]),
  });
  assert.equal(r.blocked.length, 1);
});

ok('case-insensitive matching (Windows)', () => {
  const r = evaluateStudioMoveGuard({
    scanResults: [{ path: 'c:\\b\\kuse-042-1.MP4', code: 'KUSE-042' }],
    lastBatchResult: batch([
      move({
        source: 'C:\\B\\KUSE-042-1.mp4',
        destination: 'D:\\out\\夏目響\\KUSE-042-1.mp4',
        skipped: true,
        success: true,
      }),
    ]),
  });
  assert.equal(r.blocked.length, 1);
});

ok('blocks only the skipped entries even when scanResults has unrelated extras', () => {
  const r = evaluateStudioMoveGuard({
    scanResults: [
      { path: 'C:\\B\\KUSE-042-1.mp4', code: 'KUSE-042' },
      { path: 'C:\\Other\\GOOD-001.mp4', code: 'GOOD-001' },
    ],
    lastBatchResult: batch([
      move({
        source: 'C:\\A\\KUSE-042-1.mp4',
        destination: 'D:\\out\\夏目響\\KUSE-042-1.mp4',
        success: true,
      }),
      move({
        source: 'C:\\B\\KUSE-042-1.mp4',
        destination: 'D:\\out\\夏目響\\KUSE-042-1.mp4',
        success: true,
        skipped: true,
      }),
    ]),
  });
  assert.equal(r.blocked.length, 1);
  assert.equal(r.blocked[0].code, 'KUSE-042');
});

ok('formatStudioMoveBlockedMessage — empty input returns empty string', () => {
  assert.equal(formatStudioMoveBlockedMessage([]), '');
});

ok('formatStudioMoveBlockedMessage — lists distinct codes (capped at 5)', () => {
  const msg = formatStudioMoveBlockedMessage([
    { path: '', code: 'KUSE-042', parentDir: '', skippedDestination: '', skippedReason: '' },
    { path: '', code: 'ABC-123', parentDir: '', skippedDestination: '', skippedReason: '' },
  ]);
  assert.match(msg, /偵測到 2 個檔案/);
  assert.match(msg, /KUSE-042/);
  assert.match(msg, /ABC-123/);
  assert.match(msg, /上次移動結果/);
});

ok('formatStudioMoveBlockedMessage — overflow indicates more codes', () => {
  const items = Array.from({ length: 8 }, (_, i) => ({
    path: '',
    code: `CODE-${i.toString().padStart(3, '0')}`,
    parentDir: '',
    skippedDestination: '',
    skippedReason: '',
  }));
  const msg = formatStudioMoveBlockedMessage(items);
  assert.match(msg, /等 8 個番號/);
});

ok('same-path skip (source == destination) does NOT block', () => {
  // Go MoveFile 的同路徑保護：來源已經在目標位置 → success+skipped 的合法 no-op。
  // 即使來源仍在 scanResults，也不該被 T3 guard 誤判。
  const samePath = 'D:\\out\\夏目響\\KUSE-042-1.mp4';
  const r = evaluateStudioMoveGuard({
    scanResults: [{ path: samePath, code: 'KUSE-042' }],
    lastBatchResult: batch([
      move({
        source: samePath,
        destination: samePath,
        success: true,
        skipped: true,
      }),
    ]),
  });
  assert.deepEqual(r.blocked, []);
});

ok('same-path skip with forward-slash variant still treated as no-op', () => {
  const r = evaluateStudioMoveGuard({
    scanResults: [{ path: 'D:/out/夏目響/KUSE-042-1.mp4', code: 'KUSE-042' }],
    lastBatchResult: batch([
      move({
        source: 'D:\\out\\夏目響\\KUSE-042-1.mp4',
        destination: 'D:/out/夏目響/KUSE-042-1.mp4',
        success: true,
        skipped: true,
      }),
    ]),
  });
  assert.deepEqual(r.blocked, []);
});

ok('regression — cross-dir same-name skip still blocks alongside same-path skip', () => {
  const r = evaluateStudioMoveGuard({
    scanResults: [
      { path: 'C:\\B\\KUSE-042-1.mp4', code: 'KUSE-042' },
      { path: 'D:\\out\\夏目響\\OTHER-001.mp4', code: 'OTHER-001' },
    ],
    lastBatchResult: batch([
      move({
        source: 'C:\\B\\KUSE-042-1.mp4',
        destination: 'D:\\out\\夏目響\\KUSE-042-1.mp4',
        success: true,
        skipped: true,
      }),
      move({
        source: 'D:\\out\\夏目響\\OTHER-001.mp4',
        destination: 'D:\\out\\夏目響\\OTHER-001.mp4',
        success: true,
        skipped: true,
      }),
    ]),
  });
  assert.equal(r.blocked.length, 1);
  assert.equal(r.blocked[0].code, 'KUSE-042');
});

console.log('\nbasenameOf');

ok('multi-part same code different basenames produce distinct destinations', () => {
  const outputDir = 'D:\\out';
  const actress = '夏目響';
  const src1 = 'C:\\in\\A\\KUSE-042-1.mp4';
  const src2 = 'C:\\in\\A\\KUSE-042-2.mp4';
  const dst1 = `${outputDir}\\${actress}\\${basenameOf(src1)}`;
  const dst2 = `${outputDir}\\${actress}\\${basenameOf(src2)}`;
  assert.equal(dst1, 'D:\\out\\夏目響\\KUSE-042-1.mp4');
  assert.equal(dst2, 'D:\\out\\夏目響\\KUSE-042-2.mp4');
  assert.notEqual(dst1, dst2);
});

ok('basename with spaces is preserved verbatim', () => {
  assert.equal(basenameOf('C:\\in\\A\\STARS-707 4K.mp4'), 'STARS-707 4K.mp4');
});

ok('basenameOf accepts forward slashes', () => {
  assert.equal(basenameOf('C:/in/A/KUSE-042-1.mp4'), 'KUSE-042-1.mp4');
});

ok('basenameOf returns empty string for empty input', () => {
  assert.equal(basenameOf(''), '');
});

ok('basenameOf returns the input itself when no separator present', () => {
  assert.equal(basenameOf('KUSE-042-1.mp4'), 'KUSE-042-1.mp4');
});

console.log(`\nOK — ${cases} case(s) passed`);
