import React, { useState, useRef } from 'react';
import { MainLayout } from '@/components/MainLayout';
import { DirectoryPicker } from '@/components/DirectoryPicker';
import { VideoList } from '@/components/VideoList';
import { SearchPanel } from '@/components/SearchPanel';
import { ProgressBar } from '@/components/ProgressBar';
import { StatusBar } from '@/components/StatusBar';
import { SearchResultDialog } from '@/components/SearchResultDialog';
import { OperationHistoryDialog } from '@/components/OperationHistoryDialog';
import { PreferencesDialog } from '@/components/PreferencesDialog';
import { ConflictResolutionDialog, ConflictItem } from '@/components/ConflictResolutionDialog';
import {
  MultiActressDialog,
  MultiActressItem,
  MultiActressResolution,
  ActressChoice,
} from '@/components/MultiActressDialog';
import { Button } from '@/components/ui/button';
import { useTaskStore } from '@/stores/taskStore';
import { useWailsEvents } from '@/lib/wailsEvents';
import { ScanDirectory, BatchSearch, BatchSearchAVWiki, BatchSearchJAVDB, BatchMove, BatchMoveDirs, CheckDirConflicts, CancelOperation, GetActressPrimaryStudios, GetStudiosByCodes, CheckConflicts, PlanDirMergeMoves, DbGetVideo } from '../wailsjs/go/backend/App';
import { backend, mover } from '../wailsjs/go/models';
import type { database } from '../wailsjs/go/models';
import { Scan, Search, FolderOutput, RotateCcw, ChevronDown, History, Settings, StopCircle } from 'lucide-react';

type ScanResult = backend.ScanResult;
type ConflictStrategy = 'skip' | 'overwrite' | 'rename';
type ConflictDialogMode = 'file' | 'directory';
type SearchSource = 'AV-WIKI' | 'JAVDB';
type SearchStatusField = 'avwiki_actress_status' | 'javdb_actress_status';
type VideoDataWithSourceStatus = database.VideoData & Partial<Record<SearchStatusField, string>>;
const FOUND_SEARCH_STATUSES = new Set(['found', 'searched_found']);

function isFoundSearchStatus(status?: string): boolean {
  return status !== undefined && FOUND_SEARCH_STATUSES.has(status);
}

function emptyBatchResult(): mover.BatchResult {
  return mover.BatchResult.createFrom({
    operation_id: '',
    total_items: 0,
    success_count: 0,
    failed_count: 0,
    skipped_count: 0,
    results: [],
    status: '',
    summary: '',
    duration: '',
  });
}

function normalizeDirKey(p: string): string {
  return p.replace(/\//g, '\\').replace(/[\\]+$/, '').toLowerCase();
}

function parentDir(p: string): string {
  const sep = p.includes('\\') ? '\\' : '/';
  return p.split(sep).slice(0, -1).join(sep);
}

function dirName(p: string): string {
  return p.split(/[/\\]/).filter(Boolean).pop() ?? '';
}

function mergeBatchResults(
  totalItems: number,
  first: mover.BatchResult,
  second: mover.BatchResult
): mover.BatchResult {
  const successCount = (first.success_count ?? 0) + (second.success_count ?? 0);
  const failedCount = (first.failed_count ?? 0) + (second.failed_count ?? 0);
  const skippedCount = (first.skipped_count ?? 0) + (second.skipped_count ?? 0);
  return mover.BatchResult.createFrom({
    operation_id: second.operation_id || first.operation_id,
    total_items: totalItems,
    success_count: successCount,
    failed_count: failedCount,
    skipped_count: skippedCount,
    results: [...(first.results ?? []), ...(second.results ?? [])],
    status: second.status || first.status,
    summary: `移動完成：${successCount} 個資料夾成功 / ${failedCount} 失敗 / ${skippedCount} 略過`,
    duration: second.duration || first.duration,
  });
}

function removeMovedDirectories(
  allResults: ScanResult[],
  movedDirs: Set<string>
): ScanResult[] {
  return allResults.filter((r) => !movedDirs.has(normalizeDirKey(parentDir(r.path))));
}

function removeMovedFiles(
  allResults: ScanResult[],
  movedFiles: Set<string>
): ScanResult[] {
  return allResults.filter((r) => !movedFiles.has(r.path));
}

function ActionToolbar() {
  const {
    inputDir,
    outputDir,
    status,
    scanResults,
    searchResults,
    selectedCodes,
    conflictStrategy,
    scanWorkers,
    recursive,
    setScanResults,
    setStatus,
    setStatusMessage,
    pushEvent,
    resetProgress,
    clearSearchResults,
    setLastBatchResult,
    setShowSearchResults,
  } = useTaskStore();

  const isRunning = status !== 'idle' && status !== 'error';

  const getSearchTargets = () =>
    scanResults.filter((r) => selectedCodes.size === 0 || selectedCodes.has(r.code));

  async function runSourceSearch(
    source: SearchSource,
    codes: string[],
    searchFn: (codes: string[], workers: number) => Promise<backend.SearchResult[]>
  ) {
    setStatus('searching');
    clearSearchResults();
    resetProgress();
    pushEvent('info', `🔍 ${source} 開始搜尋 ${codes.length} 筆番號…`);
    setStatusMessage(`${source} 搜尋中：0 / ${codes.length}`, 'info');

    try {
      const results = await searchFn(codes, 0);
      if (results) {
        let success = 0;
        let failed = 0;
        for (const r of results) {
          if (r.error) {
            failed++;
          } else {
            success++;
          }
        }
        const summary = `${source} 搜尋完成：${success} 成功 / ${failed} 失敗`;
        setStatusMessage(summary, failed > 0 ? 'warning' : 'success');
        if (success > 0) setShowSearchResults(true);
      }
    } catch (err) {
      const msg = `❌ ${source} 批次搜尋失敗：${err}`;
      setStatusMessage(msg, 'error');
      pushEvent('error', msg);
      setStatus('error');
      return;
    }

    setStatus('idle');
    resetProgress();
  }

  // ── 衝突對話框狀態 ──────────────────────────────────────────────────────────
  const [conflictDialogOpen, setConflictDialogOpen] = useState(false);
  const [conflictItems, setConflictItems] = useState<ConflictItem[]>([]);
  const [movedCount, setMovedCount] = useState(0);
  const [conflictDialogMode, setConflictDialogMode] = useState<ConflictDialogMode>('file');
  // Promise resolve 函式，當使用者在對話框確認/取消後呼叫
  const conflictResolveRef = useRef<((strategies: Record<string, ConflictStrategy> | null) => void) | null>(null);

  // ── 多女優選擇對話框狀態 ────────────────────────────────────────────────────
  const MULTI_ACTRESS_PREFS_KEY = 'multiActressPrefs';
  const [multiActressDialogOpen, setMultiActressDialogOpen] = useState(false);
  const [multiActressItems, setMultiActressItems] = useState<MultiActressItem[]>([]);
  const multiActressResolveRef = useRef<((resolutions: MultiActressResolution[] | null) => void) | null>(null);

  /** 每個番號的上次偏好選擇，從 localStorage 初始化 */
  const [multiActressPrefs, setMultiActressPrefs] = useState<Record<string, ActressChoice>>(() => {
    try {
      const raw = localStorage.getItem(MULTI_ACTRESS_PREFS_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  });

  /** 顯示多女優選擇對話框，返回使用者的選擇（null = 取消） */
  function waitForMultiActressResolution(
    items: MultiActressItem[]
  ): Promise<MultiActressResolution[] | null> {
    return new Promise((resolve) => {
      multiActressResolveRef.current = resolve;
      setMultiActressItems(items);
      setMultiActressDialogOpen(true);
    });
  }

  function handleMultiActressConfirm(resolutions: MultiActressResolution[]) {
    setMultiActressDialogOpen(false);
    // 儲存本次選擇作為下次預設偏好
    const updated = { ...multiActressPrefs };
    for (const r of resolutions) {
      updated[r.code] = r.choice;
    }
    setMultiActressPrefs(updated);
    try {
      localStorage.setItem(MULTI_ACTRESS_PREFS_KEY, JSON.stringify(updated));
    } catch {
      // localStorage 不可用時靜默忽略
    }
    multiActressResolveRef.current?.(resolutions);
    multiActressResolveRef.current = null;
  }

  function handleMultiActressCancel() {
    setMultiActressDialogOpen(false);
    multiActressResolveRef.current?.(null);
    multiActressResolveRef.current = null;
  }

  const removeMovedDirectoriesFromStore = (batchResult: mover.BatchResult) => {
    if (!batchResult.results) return;
    const movedDirs = new Set(
      batchResult.results
        .filter((r) => r.success && !r.skipped)
        .map((r) => normalizeDirKey(r.source))
    );
    if (movedDirs.size === 0) return;
    const currentResults = useTaskStore.getState().scanResults;
    setScanResults(removeMovedDirectories(currentResults, movedDirs));
  };

  const removeMovedFilesFromStore = (batchResult: mover.BatchResult) => {
    if (!batchResult.results) return;
    const movedFiles = new Set(
      batchResult.results
        .filter((r) => r.success && !r.skipped)
        .map((r) => r.source)
    );
    if (movedFiles.size === 0) return;
    const currentResults = useTaskStore.getState().scanResults;
    setScanResults(removeMovedFiles(currentResults, movedFiles));
  };

  /** 顯示衝突對話框，返回使用者選擇的策略（null = 略過全部並取消）*/
  function waitForConflictResolution(
    items: ConflictItem[],
    alreadyMoved: number,
    mode: ConflictDialogMode = 'file'
  ): Promise<Record<string, ConflictStrategy> | null> {
    return new Promise((resolve) => {
      conflictResolveRef.current = resolve;
      setConflictDialogMode(mode);
      setConflictItems(items);
      setMovedCount(alreadyMoved);
      setConflictDialogOpen(true);
    });
  }

  function handleConflictConfirm(strategies: Record<string, ConflictStrategy>) {
    setConflictDialogOpen(false);
    conflictResolveRef.current?.(strategies);
    conflictResolveRef.current = null;
  }

  function handleConflictCancel() {
    setConflictDialogOpen(false);
    conflictResolveRef.current?.(null);
    conflictResolveRef.current = null;
  }

  // ── 核心：帶衝突處理的批次移動 ───────────────────────────────────────────────
  async function executeMoveWithConflictHandling(
    items: Array<{ source: string; destination: string; on_conflict: string }>
  ): Promise<mover.BatchResult> {
    // 1. 偵測衝突
    const conflicts: ConflictItem[] = await CheckConflicts(
      items.map((i) => ({ source: i.source, destination: i.destination, on_conflict: i.on_conflict }))
    );

    if (conflicts.length === 0) {
      // 無衝突，直接移動全部
      return BatchMove(items, conflictStrategy);
    }

    const conflictSources = new Set(conflicts.map((c) => c.source));
    const nonConflictItems = items.filter((i) => !conflictSources.has(i.source));

    // 2. 先移動無衝突的檔案
    let partialResult = emptyBatchResult();
    if (nonConflictItems.length > 0) {
      pushEvent('info', `📦 先移動 ${nonConflictItems.length} 個無衝突檔案…`);
      partialResult = await BatchMove(nonConflictItems, conflictStrategy);
    }

    // 3. 顯示衝突對話框，等使用者選擇
    const strategies = await waitForConflictResolution(conflicts, partialResult.success_count, 'file');

    if (strategies === null) {
      // 使用者取消 → 略過所有衝突
      pushEvent('warning', `⏭️ 略過 ${conflicts.length} 個衝突檔案`);
      return mover.BatchResult.createFrom({
        ...partialResult,
        total_items: items.length,
        skipped_count: (partialResult.skipped_count ?? 0) + conflicts.length,
      });
    }

    // 4. 以使用者選擇的策略移動衝突項目
    const conflictMoveItems = items
      .filter((i) => conflictSources.has(i.source))
      .map((i) => ({
        source: i.source,
        destination: i.destination,
        on_conflict: strategies[i.source] ?? 'skip',
      }));

    const conflictResult = await BatchMove(conflictMoveItems, 'skip');

    // 5. 合併兩次結果
    return mover.BatchResult.createFrom({
      operation_id: conflictResult.operation_id || partialResult.operation_id,
      total_items: items.length,
      success_count: (partialResult.success_count ?? 0) + (conflictResult.success_count ?? 0),
      failed_count: (partialResult.failed_count ?? 0) + (conflictResult.failed_count ?? 0),
      skipped_count: (partialResult.skipped_count ?? 0) + (conflictResult.skipped_count ?? 0),
      results: [...(partialResult.results ?? []), ...(conflictResult.results ?? [])],
      status: conflictResult.status,
      summary: conflictResult.summary,
      duration: conflictResult.duration,
    });
  }

  // ── 掃描 ──────────────────────────────────────────────────────────────────
  async function handleScan() {
    if (!inputDir.trim()) {
      setStatusMessage('請先選擇輸入目錄', 'warning');
      return;
    }
    setStatus('scanning');
    setStatusMessage('🚀 開始掃描…', 'info');
    pushEvent('info', `🚀 掃描目錄：${inputDir}`);
    resetProgress();
    try {
      const results: ScanResult[] = await ScanDirectory(inputDir, scanWorkers, recursive);
      setScanResults(results ?? []);
      const msg = `✅ 掃描完成，找到 ${results?.length ?? 0} 筆結果`;
      setStatusMessage(msg, 'success');
      pushEvent('success', msg);
    } catch (err) {
      const msg = `❌ 掃描失敗：${err}`;
      setStatusMessage(msg, 'error');
      pushEvent('error', msg);
      setStatus('error');
      return;
    }
    setStatus('idle');
  }

  async function handleSearch() {
    const targets = getSearchTargets();
    if (targets.length === 0) {
      setStatusMessage('沒有可搜尋的項目', 'warning');
      return;
    }
    setStatus('searching');
    clearSearchResults();
    resetProgress();
    pushEvent('info', `🔍 開始搜尋 ${targets.length} 筆番號…`);
    setStatusMessage(`搜尋中：0 / ${targets.length}`, 'info');

    const codes = targets.map((r) => r.code);
    try {
      // BatchSearch 在 Go 端以 goroutine pool 並發執行，並透過 Wails Events
      // 即時推送 search:progress / search:result / search:done 到前端。
      // 回傳值為完整結果清單，作為補充（Events 已更新 store）。
      const results = await BatchSearch(codes, 0);
      if (results) {
        let success = 0;
        let failed = 0;
        for (const r of results) {
          if (r.error) {
            failed++;
          } else {
            success++;
          }
        }
        const summary = `搜尋完成：${success} 成功 / ${failed} 失敗`;
        setStatusMessage(summary, failed > 0 ? 'warning' : 'success');
        if (success > 0) setShowSearchResults(true);
      }
    } catch (err) {
      const msg = `❌ 批次搜尋失敗：${err}`;
      setStatusMessage(msg, 'error');
      pushEvent('error', msg);
      setStatus('error');
      return;
    }
    setStatus('idle');
    resetProgress();
  }

  /** 通用單源搜尋：跳過任一來源已找到女優資料的影片 */
  async function handleSourceSearch(
    source: SearchSource,
    searchFn: (codes: string[], workers: number) => Promise<backend.SearchResult[]>
  ) {
    const targets = getSearchTargets();
    if (targets.length === 0) {
      setStatusMessage('沒有可搜尋的項目', 'warning');
      return;
    }

    const videoStates = await Promise.all(
      targets.map(async ({ code }) => {
        try {
          const video = (await DbGetVideo(code)) as VideoDataWithSourceStatus | null;
          return { code, video };
        } catch {
          return { code, video: null };
        }
      })
    );

    // 跳過：任一來源已找到女優資料（無論搜尋順序）
    const codes = videoStates
      .filter(
        ({ video }) =>
          !isFoundSearchStatus(video?.['avwiki_actress_status']) &&
          !isFoundSearchStatus(video?.['javdb_actress_status'])
      )
      .map(({ code }) => code);

    if (codes.length === 0) {
      setStatusMessage(`${source}：沒有需要重新搜尋的項目`, 'warning');
      return;
    }
    await runSourceSearch(source, codes, searchFn);
  }

  async function handleSearchAVWiki() {
    await handleSourceSearch('AV-WIKI', BatchSearchAVWiki);
  }

  async function handleSearchJAVDB() {
    await handleSourceSearch('JAVDB', BatchSearchJAVDB);
  }

  async function handleMove() {
    const targets = scanResults.filter(
      (r) => selectedCodes.size === 0 || selectedCodes.has(r.code)
    );
    if (targets.length === 0) {
      setStatusMessage('沒有可移動的項目', 'warning');
      return;
    }
    if (!outputDir.trim()) {
      setStatusMessage('請先設定輸出目錄', 'warning');
      return;
    }
    setStatus('moving');
    resetProgress();

    const pathExt = (p: string): string => {
      const lastDot = p.lastIndexOf('.');
      const lastSep = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'));
      return lastDot > lastSep ? p.slice(lastDot) : '';
    };

    // code → 女優名映射
    // 若番號有多位女優，先詢問使用者要分到哪裡
    const multiActressSearchResults = searchResults.filter(
      (sr) => (sr.actresses?.length ?? 0) > 1
    );
    // 只保留本次移動目標中有多女優的項目
    const targetCodes = new Set(targets.map((r) => r.code));
    const multiActressTargets = multiActressSearchResults.filter((sr) =>
      targetCodes.has(sr.code)
    );

    // 若有多女優項目，彈出選擇對話框
    let multiActressChoices = new Map<string, string>();
    if (multiActressTargets.length > 0) {
      const dialogItems: MultiActressItem[] = multiActressTargets.map((sr) => ({
        code: sr.code,
        path: targets.find((r) => r.code === sr.code)?.path ?? sr.code,
        actresses: sr.actresses ?? [],
      }));
      const resolutions = await waitForMultiActressResolution(dialogItems);
      if (resolutions === null) {
        // 使用者取消
        setStatus('idle');
        resetProgress();
        return;
      }
      for (const r of resolutions) {
        const choice: ActressChoice = r.choice;
        if (choice.type === 'actress') {
          multiActressChoices.set(r.code, choice.name);
        } else if (choice.type === 'multi') {
          multiActressChoices.set(r.code, choice.label);
        } else {
          multiActressChoices.set(r.code, '未分類');
        }
      }
    }

    const codeToActress = new Map<string, string>(
      searchResults.map((sr) => {
        // 多女優項目使用使用者選擇的結果
        if (multiActressChoices.has(sr.code)) {
          return [sr.code, multiActressChoices.get(sr.code)!];
        }
        // 單女優或無結果
        return [sr.code, sr.actresses?.[0] ?? '未分類'];
      })
    );

    // T6 預覽：計算實際資料夾分配並顯示
    const folderSet = new Set(targets.map((r) => codeToActress.get(r.code) ?? '未分類'));
    pushEvent(
      'info',
      `📦 開始移動 ${targets.length} 個檔案 → ${folderSet.size} 個資料夾（${outputDir}）`
    );

    // T5 女優資料夾：目標路徑為 outputDir\女優名\番號.ext
    const items = targets.map((r) => {
      const actress = codeToActress.get(r.code) ?? '未分類';
      return {
        source: r.path,
        destination: `${outputDir}\\${actress}\\${r.code}${pathExt(r.path)}`,
        on_conflict: conflictStrategy,
      };
    });

    try {
      const result = await executeMoveWithConflictHandling(items);
      setLastBatchResult(result);
      const summary = `移動完成：${result.success_count} 成功 / ${result.failed_count} 失敗 / ${result.skipped_count} 略過`;
      setStatusMessage(summary, result.failed_count > 0 ? 'warning' : 'success');
      pushEvent(result.failed_count > 0 ? 'warning' : 'success', summary);

      // Debug: 逐筆記錄移動詳情
      for (const r of result.results ?? []) {
        if (r.skipped) {
          const reason = r.source === r.destination ? '來源=目標（同路徑）' : (r.error || '衝突略過');
          pushEvent('debug', `[略過] ${r.source} → ${r.destination}（${reason}）`);
        } else if (!r.success) {
          pushEvent('debug', `[失敗] ${r.source} → ${r.destination}（${r.error}）`);
        } else {
          pushEvent('debug', `[移動] ${r.source} → ${r.destination}`);
        }
      }

      // T3 清除已成功移動的項目，避免 scanResults 殘留過期路徑
      removeMovedFilesFromStore(result);
    } catch (err) {
      const msg = `❌ 移動失敗：${err}`;
      setStatusMessage(msg, 'error');
      pushEvent('error', msg);
      setStatus('error');
      return;
    }
    setStatus('idle');
    resetProgress();
  }

  async function handleStudioMove() {
    if (!outputDir.trim()) {
      setStatusMessage('請先設定輸出目錄', 'warning');
      return;
    }
    const targets = scanResults.filter(
      (r) => selectedCodes.size === 0 || selectedCodes.has(r.code)
    );
    if (targets.length === 0) {
      setStatusMessage('沒有可移動的項目', 'warning');
      return;
    }
    setStatus('moving');
    resetProgress();
    const inputDirKey = normalizeDirKey(inputDir);

    // code → 第一位女優名（從 searchResults）
    const codeToActress = new Map<string, string>(
      searchResults.map((sr) => [sr.code, sr.actresses?.[0] ?? ''])
    );

    // --- 以女優資料夾分組 ---
    // 排除直接在 inputDir 根目錄下的檔案（parentDir === inputDir），避免移動整個 inputDir
    const rootLevelCodes: string[] = [];
    const folderToCodes = new Map<string, string[]>();
    for (const r of targets) {
      const folder = parentDir(r.path);
      if (normalizeDirKey(folder) === inputDirKey) {
        rootLevelCodes.push(r.code);
        continue;
      }
      if (!folderToCodes.has(folder)) folderToCodes.set(folder, []);
      folderToCodes.get(folder)!.push(r.code);
    }
    if (rootLevelCodes.length > 0) {
      pushEvent('warning', `⚠️ 略過 ${rootLevelCodes.length} 個直接放在輸入目錄根目錄的檔案（${rootLevelCodes.join('、')}），請先整理進女優資料夾`);
    }
    if (folderToCodes.size === 0) {
      setStatusMessage('沒有可移動的女優資料夾', 'warning');
      setStatus('idle');
      return;
    }

    // 每個資料夾取一個代表番號用於查片商
    const repCodes = [...folderToCodes.values()].map((codes) => codes[0]);
    const codeStudioMap: Record<string, string> = await GetStudiosByCodes(repCodes);

    const actressLookupByCode = new Map<string, string>();
    for (const [actressDir, codes] of folderToCodes) {
      const repCode = codes[0];
      const actress = codeToActress.get(repCode) ?? '';
      const actressName = dirName(actressDir) || actress || '未知女優';
      actressLookupByCode.set(repCode, actress || actressName);
    }

    // fallback：對前綴未命中的番號，補查女優→DB 統計
    const missingActresses = [
      ...new Set(
        repCodes
          .filter((c) => !codeStudioMap[c])
          .map((c) => actressLookupByCode.get(c) ?? '')
          .filter((name) => Boolean(name) && name !== '未分類' && name !== '未知女優')
      ),
    ];
    const actressStudioMap: Record<string, string> =
      missingActresses.length > 0
        ? await GetActressPrimaryStudios(missingActresses)
        : {};

    // 建立資料夾移動清單
    const studioCounts: Record<string, number> = {};
    const dirItems: Array<{ source: string; destination: string; on_conflict?: string }> = [];

    for (const [actressDir, codes] of folderToCodes) {
      const repCode = codes[0];
      const actress = codeToActress.get(repCode) ?? '';
      const actressName = dirName(actressDir) || actress || '未知女優';
      const actressLookupName = actressLookupByCode.get(repCode) ?? '';

      let studio = codeStudioMap[repCode] ?? '';
      if (!studio && actressLookupName) studio = actressStudioMap[actressLookupName] ?? '';
      if (!studio) studio = '未分類';

      studioCounts[studio] = (studioCounts[studio] ?? 0) + 1;

      const dst =
        studio === '未分類'
          ? `${outputDir}\\未分類\\${actressName}`
          : `${outputDir}\\${studio}\\${actressName}`;

      // 防止 dst 是 src 的子目錄（例如：未分類資料夾分類到自身底下）
      const normSrc = actressDir.toLowerCase().split("\\").join("/");
      const normDst = dst.toLowerCase().split("\\").join("/");
      if (normDst === normSrc || normDst.startsWith(normSrc + "/")) {
        pushEvent("warning", `⚠ 略過 ${actressName}：目標目錄是來源的子目錄`);
        studioCounts[studio] = (studioCounts[studio] ?? 1) - 1;
        if (studioCounts[studio] <= 0) delete studioCounts[studio];
        continue;
      }

      dirItems.push({ source: actressDir, destination: dst });
    }

    const studioSummary = Object.entries(studioCounts)
      .sort((a, b) => b[1] - a[1])
      .map(([s, n]) => `${s}(${n})`)
      .join('、');
    pushEvent(
      'info',
      `🏢 片商分類：移動 ${dirItems.length} 個女優資料夾 → ${Object.keys(studioCounts).length} 個片商`
    );
    pushEvent('info', `📊 分類結果：${studioSummary}`);

    // ── 目錄層級分流：全新目標直接搬移；同名目標先做 file-level merge，再 finalize ──
    let cleanDirResult = emptyBatchResult();
    let mergeFinalizeResult = emptyBatchResult();
    try {
      const dirConflicts = await CheckDirConflicts(dirItems);
      const mergeDirKeys = new Set(dirConflicts.map((c) => normalizeDirKey(c.destination)));
      const cleanDirItems = dirItems.filter((i) => !mergeDirKeys.has(normalizeDirKey(i.destination)));
      const mergeDirItems = dirItems.filter((i) => mergeDirKeys.has(normalizeDirKey(i.destination)));

      if (cleanDirItems.length > 0) {
        pushEvent('info', `📦 先移動 ${cleanDirItems.length} 個全新目標女優資料夾…`);
        cleanDirResult = await BatchMoveDirs(cleanDirItems, conflictStrategy);
        removeMovedDirectoriesFromStore(cleanDirResult);
      }

      if (mergeDirItems.length > 0) {
        pushEvent('info', `🧩 發現 ${mergeDirItems.length} 個同名女優資料夾，改以檔案層級合併處理…`);
        const mergeMoveItems = await PlanDirMergeMoves(mergeDirItems);
        const mergeFileResult = await executeMoveWithConflictHandling(
          mergeMoveItems.map((item) => ({
            source: item.source,
            destination: item.destination,
            on_conflict: item.on_conflict ?? conflictStrategy,
          }))
        );
        removeMovedFilesFromStore(mergeFileResult);

        pushEvent('info', '📂 檔案層級合併完成，開始同步空子目錄並清理已搬空來源資料夾…');
        mergeFinalizeResult = await BatchMoveDirs(mergeDirItems, 'skip');
      }
    } catch (err) {
      const msg = `❌ 片商分類移動失敗：${err}`;
      setStatusMessage(msg, 'error');
      pushEvent('error', msg);
      setStatus('error');
      return;
    }

    const finalResult = mergeBatchResults(dirItems.length, cleanDirResult, mergeFinalizeResult);
    const summary = `移動完成：${finalResult.success_count} 個資料夾成功 / ${finalResult.failed_count} 失敗 / ${finalResult.skipped_count} 略過`;
    setStatusMessage(summary, finalResult.failed_count > 0 ? 'warning' : 'success');
    pushEvent(finalResult.failed_count > 0 ? 'warning' : 'success', summary);

    // Debug: 片商分類逐筆詳情
    for (const r of [...(cleanDirResult.results ?? []), ...(mergeFinalizeResult.results ?? [])]) {
      if (r.skipped) {
        const reason = r.source === r.destination ? '來源=目標（同路徑）' : (r.error || '衝突略過');
        pushEvent('debug', `[略過] ${r.source} → ${r.destination}（${reason}）`);
      } else if (!r.success) {
        pushEvent('debug', `[失敗] ${r.source} → ${r.destination}（${r.error}）`);
      } else {
        pushEvent('debug', `[移動] ${r.source} → ${r.destination}`);
      }
    }

    // 移除已成功移動的女優資料夾下的所有 scanResults
    removeMovedDirectoriesFromStore(finalResult);
    setLastBatchResult(finalResult);
    setStatus('idle');
    resetProgress();
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {/* 衝突處理對話框（掛在此層，供 handleMove / handleStudioMove 共用）*/}
      <ConflictResolutionDialog
        open={conflictDialogOpen}
        conflictItems={conflictItems}
        movedCount={movedCount}
        itemKind={conflictDialogMode}
        onConfirm={handleConflictConfirm}
        onCancel={handleConflictCancel}
      />
      {/* 多女優分類選擇對話框 */}
      <MultiActressDialog
        open={multiActressDialogOpen}
        items={multiActressItems}
        savedChoices={multiActressPrefs}
        onConfirm={handleMultiActressConfirm}
        onCancel={handleMultiActressCancel}
      />
      <Button onClick={handleScan} disabled={isRunning} size="sm">
        <Scan className="h-4 w-4 mr-1" />
        掃描
      </Button>
      <Button
        onClick={handleSearch}
        disabled={isRunning || scanResults.length === 0}
        variant="secondary"
        size="sm"
      >
        <Search className="h-4 w-4 mr-1" />
        搜尋{selectedCodes.size > 0 ? ` (${selectedCodes.size})` : '全部'}
      </Button>
      <Button
        onClick={handleSearchAVWiki}
        disabled={isRunning || scanResults.length === 0}
        variant="secondary"
        size="sm"
      >
        AV-WIKI 搜尋
      </Button>
      <Button
        onClick={handleSearchJAVDB}
        disabled={isRunning || scanResults.length === 0}
        variant="secondary"
        size="sm"
      >
        JAVDB 搜尋
      </Button>
      <Button
        onClick={handleMove}
        disabled={isRunning || scanResults.length === 0}
        variant="outline"
        size="sm"
      >
        <FolderOutput className="h-4 w-4 mr-1" />
        移動{selectedCodes.size > 0 ? ` (${selectedCodes.size})` : '全部'}
      </Button>
      <Button
        onClick={handleStudioMove}
        disabled={isRunning || scanResults.length === 0}
        size="sm"
        variant="outline"
      >
        🏢 片商分類{selectedCodes.size > 0 ? ` (${selectedCodes.size})` : '全部'}
      </Button>
      {isRunning && (
        <Button
          onClick={() => {
            CancelOperation();
            setStatus('idle');
            setStatusMessage('⛔ 已取消操作', 'warning');
          }}
          variant="destructive"
          size="sm"
        >
          <StopCircle className="h-4 w-4 mr-1" />
          取消
        </Button>
      )}
    </div>
  );
}

function ConflictStrategySelect() {
  const { conflictStrategy, setConflictStrategy } = useTaskStore();
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-slate-400">衝突策略：</span>
      <div className="relative">
        <select
          value={conflictStrategy}
          onChange={(e) =>
            setConflictStrategy(e.target.value as 'skip' | 'overwrite' | 'rename')
          }
          className="bg-slate-800 border border-slate-600 text-slate-200 text-xs rounded px-2 py-1 pr-6 appearance-none focus:outline-none focus:ring-1 focus:ring-indigo-500"
        >
          <option value="skip">略過</option>
          <option value="overwrite">覆蓋</option>
          <option value="rename">重新命名</option>
        </select>
        <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 text-slate-400 pointer-events-none" />
      </div>
    </div>
  );
}

/**
 * App — 主應用程式元件。
 */
export default function App() {
  useWailsEvents();

  const {
    inputDir,
    outputDir,
    setInputDir,
    setOutputDir,
    status,
    recursive,
    setRecursive,
    scanWorkers,
    setScanWorkers,
    searchResults,
    showPreferences,
    showOperationHistory,
    showSearchResults,
    setShowPreferences,
    setShowOperationHistory,
    setShowSearchResults,
  } = useTaskStore();

  const isRunning = status !== 'idle' && status !== 'error';

  return (
    <MainLayout>
      {/* Top toolbar */}
      <header
        data-wails-drag
        className="flex items-center gap-3 px-4 py-2 bg-slate-900 border-b border-slate-700 shrink-0 flex-wrap"
      >
        <span className="text-sm font-bold text-indigo-400 mr-1 whitespace-nowrap">
          女優分類系統
        </span>
        <ActionToolbar />
        <div className="ml-auto flex items-center gap-2">
          <ConflictStrategySelect />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowOperationHistory(true)}
            title="操作歷史"
          >
            <History className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowPreferences(true)}
            title="偏好設定"
          >
            <Settings className="h-4 w-4" />
          </Button>
        </div>
      </header>

      {/* Directory pickers */}
      <section className="px-4 py-3 bg-slate-900/50 border-b border-slate-700 shrink-0 space-y-2">
        <DirectoryPicker
          label="輸入目錄"
          value={inputDir}
          onChange={setInputDir}
          placeholder="要掃描的影片目錄…"
          disabled={isRunning}
        />
        <DirectoryPicker
          label="輸出目錄"
          value={outputDir}
          onChange={setOutputDir}
          placeholder="移動後的目的目錄…"
          disabled={isRunning}
        />
        {/* Scan options */}
        <div className="flex items-center gap-4 text-xs text-slate-400">
          <label className="flex items-center gap-1.5 cursor-pointer select-none" title="掃描所有子目錄（建議保持開啟）">
            <input
              type="checkbox"
              checked={recursive}
              onChange={(e) => setRecursive(e.target.checked)}
              disabled={isRunning}
              className="rounded border-slate-600 bg-slate-800 text-indigo-500 focus:ring-indigo-500"
            />
            含子目錄{recursive ? '（全部深度）' : '（僅第一層）'}
          </label>
          <label className="flex items-center gap-1.5">
            並行數：
            <input
              type="number"
              min={1}
              max={50}
              value={scanWorkers}
              onChange={(e) => setScanWorkers(Number(e.target.value))}
              disabled={isRunning}
              className="w-14 bg-slate-800 border border-slate-600 text-slate-200 text-xs rounded px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </label>
        </div>
      </section>

      {/* Progress bar */}
      <ProgressBar />

      {/* Main content: VideoList + SearchPanel */}
      <div className="flex flex-1 min-h-0 divide-x divide-slate-700">
        <VideoList className="w-1/2" />
        <SearchPanel className="w-1/2" />
      </div>

      {/* Status bar */}
      <StatusBar />

      {/* Dialogs */}
      <SearchResultDialog
        open={showSearchResults}
        onClose={() => setShowSearchResults(false)}
        results={searchResults}
      />
      <OperationHistoryDialog
        open={showOperationHistory}
        onClose={() => setShowOperationHistory(false)}
      />
      <PreferencesDialog
        open={showPreferences}
        onClose={() => setShowPreferences(false)}
      />
    </MainLayout>
  );
}
