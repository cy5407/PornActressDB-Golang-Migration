import { useEffect } from 'react';
import { useTaskStore } from '@/stores/taskStore';

/**
 * 已知 Wails 事件名稱。
 * 可在 Go 端透過 runtime.EventsEmit(ctx, EventScanProgress, ...) 發送。
 */
export const WailsEvents = {
  ScanProgress: 'scan:progress',
  ScanResult: 'scan:result',
  ScanDone: 'scan:done',
  SearchProgress: 'search:progress',
  SearchResult: 'search:result',
  SearchDone: 'search:done',
  MoveProgress: 'move:progress',
  MoveDone: 'move:done',
  Error: 'task:error',
} as const;

interface WailsRuntime {
  EventsOn: (event: string, callback: (...args: unknown[]) => void) => void;
  EventsOff: (...events: string[]) => void;
}

function getRuntime(): WailsRuntime | null {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (window as any).runtime ?? null;
}

/**
 * useWailsEvents — 串接 Wails Events 並更新 taskStore。
 * 在 App 頂層 mount 一次即可。
 */
export function useWailsEvents() {
  const store = useTaskStore();

  useEffect(() => {
    const rt = getRuntime();
    if (!rt) return; // dev mode outside Wails

    // -- scan:progress --
    rt.EventsOn(WailsEvents.ScanProgress, (...args) => {
      const [current, total] = args as [number, number];
      store.setProgress(current, total);
      store.pushEvent('debug', `掃描進度：${current} / ${total}`);
    });

    // -- scan:result --
    rt.EventsOn(WailsEvents.ScanResult, (...args) => {
      const result = args[0] as { path: string; code: string };
      if (result?.code) {
        store.pushEvent('debug', `[掃描] ${result.code}  ${result.path}`);
      }
    });

    // -- scan:done --
    rt.EventsOn(WailsEvents.ScanDone, (...args) => {
      const summary = args[0] as string | undefined;
      store.setStatus('idle');
      store.setStatusMessage(summary ?? '掃描完成', 'success');
      store.pushEvent('success', `掃描完成：${summary ?? ''}`);
      store.resetProgress();
    });

    // -- search:progress --
    rt.EventsOn(WailsEvents.SearchProgress, (...args) => {
      const [current, total, code] = args as [number, number, string];
      store.setProgress(current, total);
      store.pushEvent('debug', `[搜尋] (${current}/${total}) ${code}`);
    });

    // -- search:result --
    rt.EventsOn(WailsEvents.SearchResult, (...args) => {
      const result = args[0] as import('../../wailsjs/go/models').backend.SearchResult;
      if (result) {
        store.addSearchResult(result);
        if (result.error) {
          store.pushEvent('warning', `⚠ ${result.code}: ${result.error}`);
        } else {
          const { progressCurrent, progressTotal } = store;
          store.pushEvent('info', `(${progressCurrent}/${progressTotal}) 已搜尋到 ${result.code}`);
        }
      }
    });

    // -- search:done --
    rt.EventsOn(WailsEvents.SearchDone, (...args) => {
      const summary = args[0] as string | undefined;
      store.setStatus('idle');
      store.setStatusMessage(summary ?? '搜尋完成', 'success');
      store.pushEvent('success', `搜尋完成：${summary ?? ''}`);
      store.resetProgress();
    });

    // -- move:progress --
    rt.EventsOn(WailsEvents.MoveProgress, (...args) => {
      const [current, total, src] = args as [number, number, string];
      store.setProgress(current, total);
      store.pushEvent('debug', `[移動] (${current}/${total}) ${src}`);
    });

    // -- move:done --
    rt.EventsOn(WailsEvents.MoveDone, (...args) => {
      const summary = args[0] as string | undefined;
      store.setStatus('idle');
      store.setStatusMessage(summary ?? '移動完成', 'success');
      store.pushEvent('success', `移動完成：${summary ?? ''}`);
      store.resetProgress();
    });

    // -- task:error --
    rt.EventsOn(WailsEvents.Error, (...args) => {
      const msg = args[0] as string | undefined;
      store.setStatus('error');
      store.setStatusMessage(msg ?? '發生錯誤', 'error');
      store.pushEvent('error', msg ?? '未知錯誤');
    });

    return () => {
      rt.EventsOff(
        WailsEvents.ScanProgress,
        WailsEvents.ScanResult,
        WailsEvents.ScanDone,
        WailsEvents.SearchProgress,
        WailsEvents.SearchResult,
        WailsEvents.SearchDone,
        WailsEvents.MoveProgress,
        WailsEvents.MoveDone,
        WailsEvents.Error
      );
    };
  }, []);
}
