import React from 'react';
import { MainLayout } from '@/components/MainLayout';
import { DirectoryPicker } from '@/components/DirectoryPicker';
import { VideoList } from '@/components/VideoList';
import { SearchPanel } from '@/components/SearchPanel';
import { ProgressBar } from '@/components/ProgressBar';
import { StatusBar } from '@/components/StatusBar';
import { SearchResultDialog } from '@/components/SearchResultDialog';
import { OperationHistoryDialog } from '@/components/OperationHistoryDialog';
import { PreferencesDialog } from '@/components/PreferencesDialog';
import { Button } from '@/components/ui/button';
import { useTaskStore } from '@/stores/taskStore';
import { useWailsEvents } from '@/lib/wailsEvents';
import { ScanDirectory, BatchSearch, BatchMove, CancelOperation, GetActressPrimaryStudios } from '../wailsjs/go/backend/App';
import { backend } from '../wailsjs/go/models';
import { Scan, Search, FolderOutput, RotateCcw, ChevronDown, History, Settings, StopCircle } from 'lucide-react';

type ScanResult = backend.ScanResult;

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
    const targets = scanResults.filter(
      (r) => selectedCodes.size === 0 || selectedCodes.has(r.code)
    );
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

    // code → 女優名映射（用第一位女優；無搜尋結果則放到「未分類」）
    const codeToActress = new Map<string, string>(
      searchResults.map((sr) => [sr.code, sr.actresses?.[0] ?? '未分類'])
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
      const result = await BatchMove(items, conflictStrategy);
      setLastBatchResult(result);
      const summary = `移動完成：${result.success_count} 成功 / ${result.failed_count} 失敗 / ${result.skipped_count} 略過`;
      setStatusMessage(summary, result.failed_count > 0 ? 'warning' : 'success');
      pushEvent(result.failed_count > 0 ? 'warning' : 'success', summary);

      // T3 清除已成功移動的項目，避免 scanResults 殘留過期路徑
      if (result.results) {
        const movedSources = new Set(
          result.results.filter((mv) => mv.success).map((mv) => mv.source)
        );
        setScanResults(scanResults.filter((r) => !movedSources.has(r.path)));
      }
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

    const pathExt = (p: string): string => {
      const lastDot = p.lastIndexOf('.');
      const lastSep = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'));
      return lastDot > lastSep ? p.slice(lastDot) : '';
    };

    // code → 第一位女優名（從 searchResults）
    const codeToActress = new Map<string, string>(
      searchResults.map((sr) => [sr.code, sr.actresses?.[0] ?? ''])
    );

    // 批次查詢女優主片商（去重）
    const actressNames = [
      ...new Set(
        targets.map((r) => codeToActress.get(r.code) ?? '').filter(Boolean)
      ),
    ];
    const studioMap: Record<string, string> =
      actressNames.length > 0
        ? await GetActressPrimaryStudios(actressNames)
        : {};

    const items = targets.map((r) => {
      const actress = codeToActress.get(r.code) ?? '';
      let studioFolder = actress ? (studioMap[actress] ?? '') : '';
      if (!actress || studioFolder === '') {
        studioFolder = '未分類';
      }

      const dst =
        studioFolder === '未分類'
          ? `${outputDir}\\未分類\\${r.code}${pathExt(r.path)}`
          : `${outputDir}\\${studioFolder}\\${actress}\\${r.code}${pathExt(r.path)}`;

      return { source: r.path, destination: dst, on_conflict: conflictStrategy };
    });

    const folderSet = new Set(
      items.map((i) => i.destination.split('\\').slice(0, -1).join('\\'))
    );
    pushEvent(
      'info',
      `🏢 片商分類移動 ${targets.length} 個檔案 → ${folderSet.size} 個資料夾`
    );

    try {
      const result = await BatchMove(items, conflictStrategy);
      setLastBatchResult(result);
      const summary = `移動完成：${result.success_count} 成功 / ${result.failed_count} 失敗 / ${result.skipped_count} 略過`;
      setStatusMessage(summary, result.failed_count > 0 ? 'warning' : 'success');
      pushEvent(result.failed_count > 0 ? 'warning' : 'success', summary);

      if (result.results) {
        const movedSources = new Set(
          result.results.filter((mv) => mv.success).map((mv) => mv.source)
        );
        setScanResults(scanResults.filter((r) => !movedSources.has(r.path)));
      }
    } catch (err) {
      const msg = `❌ 片商分類移動失敗：${err}`;
      setStatusMessage(msg, 'error');
      pushEvent('error', msg);
      setStatus('error');
      return;
    }
    setStatus('idle');
    resetProgress();
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
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
