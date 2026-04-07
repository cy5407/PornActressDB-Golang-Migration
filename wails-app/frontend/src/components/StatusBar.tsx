import React from 'react';
import { cn } from '@/lib/utils';
import { useTaskStore } from '@/stores/taskStore';
import { CheckCircle, AlertCircle, Info, AlertTriangle, Loader2 } from 'lucide-react';

interface StatusBarProps {
  className?: string;
}

const iconMap = {
  info: <Info className="h-3.5 w-3.5 text-slate-400" />,
  success: <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />,
  error: <AlertCircle className="h-3.5 w-3.5 text-red-400" />,
  warning: <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />,
};

const textColorMap = {
  info: 'text-slate-300',
  success: 'text-emerald-300',
  error: 'text-red-300',
  warning: 'text-amber-300',
};

const statusLabelMap: Record<string, string> = {
  idle: '就緒',
  scanning: '掃描中',
  searching: '搜尋中',
  moving: '移動中',
  error: '錯誤',
};

/**
 * StatusBar — 顯示目前任務狀態與最新訊息。
 * 固定在畫面底部，提供視覺回饋。
 */
export function StatusBar({ className }: StatusBarProps) {
  const { statusMessage, statusType, status } = useTaskStore();

  const isRunning = status !== 'idle' && status !== 'error';

  return (
    <div
      className={cn(
        'flex items-center gap-2 px-4 py-1.5 bg-slate-900 border-t border-slate-700',
        'text-xs select-none',
        className
      )}
    >
      {/* Task status badge */}
      <span
        className={cn(
          'flex items-center gap-1 px-2 py-0.5 rounded-sm font-medium',
          isRunning
            ? 'bg-indigo-600/30 text-indigo-300'
            : status === 'error'
            ? 'bg-red-600/30 text-red-300'
            : 'bg-slate-700 text-slate-400'
        )}
      >
        {isRunning && <Loader2 className="h-3 w-3 animate-spin" />}
        {statusLabelMap[status] ?? status}
      </span>

      {/* Separator */}
      <span className="text-slate-600">|</span>

      {/* Status message */}
      <span className={cn('flex items-center gap-1.5 flex-1 truncate', textColorMap[statusType])}>
        {iconMap[statusType]}
        <span className="truncate">{statusMessage}</span>
      </span>
    </div>
  );
}
