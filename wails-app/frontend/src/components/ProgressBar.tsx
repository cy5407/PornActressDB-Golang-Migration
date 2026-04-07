import React from 'react';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { useTaskStore } from '@/stores/taskStore';

interface ProgressBarProps {
  className?: string;
}

/**
 * ProgressBar — 顯示目前任務進度。
 * 從 taskStore 讀取 progress / progressCurrent / progressTotal。
 * 進度為 0 且狀態為 idle 時隱藏。
 */
export function ProgressBar({ className }: ProgressBarProps) {
  const { progress, progressCurrent, progressTotal, status } = useTaskStore();

  const isActive = status !== 'idle' || progress > 0;

  if (!isActive) return null;

  return (
    <div className={cn('flex items-center gap-3 px-4 py-1 bg-slate-800/50', className)}>
      <Progress value={progress} className="flex-1" />
      <span className="text-xs text-slate-400 whitespace-nowrap min-w-[6rem] text-right">
        {progressTotal > 0
          ? `${progressCurrent} / ${progressTotal} (${progress}%)`
          : progress > 0
          ? `${progress}%`
          : '處理中…'}
      </span>
    </div>
  );
}
