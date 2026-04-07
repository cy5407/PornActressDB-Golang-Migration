import React from 'react';
import { cn } from '@/lib/utils';
import { backend } from '../../wailsjs/go/models';
import { useTaskStore } from '@/stores/taskStore';
import { FileVideo, CheckSquare, Square } from 'lucide-react';

interface VideoCardProps {
  result: backend.ScanResult;
  selected: boolean;
  onToggle: () => void;
}

/**
 * VideoCard — 顯示單一掃描結果的卡片。
 * 支援選取/取消選取，顯示番號與檔案路徑。
 */
export function VideoCard({ result, selected, onToggle }: VideoCardProps) {
  return (
    <div
      onClick={onToggle}
      className={cn(
        'flex items-start gap-3 p-3 rounded-md border cursor-pointer select-none',
        'transition-colors duration-150',
        selected
          ? 'bg-indigo-600/20 border-indigo-500/60 hover:bg-indigo-600/30'
          : 'bg-slate-800 border-slate-700 hover:bg-slate-700/80'
      )}
    >
      <div className="mt-0.5 shrink-0">
        {selected ? (
          <CheckSquare className="h-4 w-4 text-indigo-400" />
        ) : (
          <Square className="h-4 w-4 text-slate-500" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <FileVideo className="h-4 w-4 text-slate-400 shrink-0" />
          <span className="font-semibold text-sm text-indigo-300 truncate">{result.code}</span>
        </div>
        <p className="text-xs text-slate-500 truncate mt-0.5 pl-6" title={result.path}>
          {result.path}
        </p>
      </div>
    </div>
  );
}

interface VideoListProps {
  className?: string;
}

/**
 * VideoList — 掃描結果清單。
 * 從 taskStore 取得資料，支援全選/清除選取。
 */
export function VideoList({ className }: VideoListProps) {
  const { scanResults, selectedCodes, toggleSelected, selectAll, clearSelection } =
    useTaskStore();

  if (scanResults.length === 0) {
    return (
      <div className={cn('flex flex-col items-center justify-center h-full text-slate-500', className)}>
        <FileVideo className="h-12 w-12 mb-3 opacity-30" />
        <p className="text-sm">尚無掃描結果</p>
        <p className="text-xs mt-1">請選擇目錄並執行掃描</p>
      </div>
    );
  }

  const allSelected = selectedCodes.size === scanResults.length;

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Toolbar */}
      <div className="flex items-center justify-between px-1 py-1.5 text-xs text-slate-400 border-b border-slate-700 shrink-0">
        <span>
          共 <strong className="text-slate-200">{scanResults.length}</strong> 筆
          {selectedCodes.size > 0 && (
            <span className="ml-1 text-indigo-400">（已選 {selectedCodes.size}）</span>
          )}
        </span>
        <div className="flex gap-2">
          <button
            onClick={allSelected ? clearSelection : selectAll}
            className="hover:text-slate-200 transition-colors"
          >
            {allSelected ? '取消全選' : '全選'}
          </button>
          {selectedCodes.size > 0 && (
            <button onClick={clearSelection} className="hover:text-slate-200 transition-colors">
              清除選取
            </button>
          )}
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto space-y-1.5 p-2">
        {scanResults.map((r) => (
          <VideoCard
            key={r.path}
            result={r}
            selected={selectedCodes.has(r.code)}
            onToggle={() => toggleSelected(r.code)}
          />
        ))}
      </div>
    </div>
  );
}
