import React, { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import { useTaskStore, type ProgressEvent } from '@/stores/taskStore';
import { CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-react';

interface SearchPanelProps {
  className?: string;
}

const eventIcons: Record<ProgressEvent['type'], React.ReactNode> = {
  info: <Info className="h-3.5 w-3.5 text-slate-400 shrink-0 mt-0.5" />,
  success: <CheckCircle className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />,
  error: <AlertCircle className="h-3.5 w-3.5 text-red-400 shrink-0 mt-0.5" />,
  warning: <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0 mt-0.5" />,
  clear: <Info className="h-3.5 w-3.5 text-slate-600 shrink-0 mt-0.5" />,
};

const eventTextColors: Record<ProgressEvent['type'], string> = {
  info: 'text-slate-300',
  success: 'text-emerald-300',
  error: 'text-red-300',
  warning: 'text-amber-300',
  clear: 'text-slate-600',
};

function formatTime(ts: number) {
  return new Date(ts).toLocaleTimeString('zh-TW', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/**
 * SearchPanel — 顯示任務執行日誌與進度事件。
 * 新事件推入時自動捲動至底部。
 * 支援批次狀態（批次開始、處理中、成功、失敗、完成）。
 */
export function SearchPanel({ className }: SearchPanelProps) {
  const { events, clearEvents } = useTaskStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events.length]);

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-700 shrink-0">
        <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">
          執行日誌
        </span>
        {events.length > 0 && (
          <button
            onClick={clearEvents}
            className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
          >
            清除
          </button>
        )}
      </div>

      {/* Event list */}
      <div className="flex-1 overflow-y-auto font-mono text-xs p-2 space-y-0.5 bg-slate-950/50">
        {events.length === 0 ? (
          <p className="text-slate-600 p-2">尚無日誌…</p>
        ) : (
          events.map((ev, i) => (
            <div key={i} className={cn('flex gap-2 py-0.5', eventTextColors[ev.type])}>
              <span className="text-slate-600 shrink-0 whitespace-nowrap">
                {formatTime(ev.timestamp)}
              </span>
              {eventIcons[ev.type]}
              <span className="break-all">{ev.message}</span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
