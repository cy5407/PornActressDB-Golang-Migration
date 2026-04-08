import React, { useState, useCallback } from 'react';
import { DialogShell } from '@/components/DialogShell';
import { Button } from '@/components/ui/button';
import { AlertTriangle, SkipForward, RefreshCw, Copy } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface ConflictItem {
  source: string;
  destination: string;
}

type ConflictStrategy = 'skip' | 'overwrite' | 'rename';
type ConflictItemKind = 'file' | 'directory';

interface ConflictResolutionDialogProps {
  open: boolean;
  conflictItems: ConflictItem[];
  /** 已成功移動（無衝突）的項目數量，用於顯示進度提示 */
  movedCount: number;
  itemKind?: ConflictItemKind;
  onConfirm: (strategies: Record<string, ConflictStrategy>) => void;
  onCancel: () => void;
}

function basename(path: string): string {
  return path.replace(/.*[/\\]/, '');
}

function shortenPath(path: string, maxLen = 60): string {
  if (path.length <= maxLen) return path;
  const half = Math.floor(maxLen / 2) - 2;
  return path.slice(0, half) + '…' + path.slice(-half);
}

const STRATEGY_LABELS: Record<ConflictStrategy, string> = {
  skip: '略過',
  overwrite: '覆蓋',
  rename: '重新命名',
};

const STRATEGY_COLORS: Record<ConflictStrategy, string> = {
  skip: 'text-slate-400',
  overwrite: 'text-red-400',
  rename: 'text-amber-400',
};

/**
 * ConflictResolutionDialog — 同名衝突處理對話框
 *
 * 顯示衝突清單，讓使用者逐筆或批次選擇「略過 / 覆蓋 / 重新命名」策略。
 * 其他無衝突的檔案已先行移動；本對話框只處理尚未移動的衝突項目。
 */
export function ConflictResolutionDialog({
  open,
  conflictItems,
  movedCount,
  itemKind = 'file',
  onConfirm,
  onCancel,
}: ConflictResolutionDialogProps) {
  const [strategies, setStrategies] = useState<Record<string, ConflictStrategy>>(() =>
    Object.fromEntries(conflictItems.map((c) => [c.source, 'skip' as ConflictStrategy]))
  );

  // Reset when items change (new batch)
  React.useEffect(() => {
    setStrategies(
      Object.fromEntries(conflictItems.map((c) => [c.source, 'skip' as ConflictStrategy]))
    );
  }, [conflictItems]);

  const setAll = useCallback(
    (strategy: ConflictStrategy) => {
      setStrategies(
        Object.fromEntries(conflictItems.map((c) => [c.source, strategy]))
      );
    },
    [conflictItems]
  );

  const setOne = (source: string, strategy: ConflictStrategy) => {
    setStrategies((prev) => ({ ...prev, [source]: strategy }));
  };

  function handleConfirm() {
    onConfirm(strategies);
  }

  function handleSkipAll() {
    onCancel();
  }

  const skipCount = Object.values(strategies).filter((s) => s === 'skip').length;
  const overwriteCount = Object.values(strategies).filter((s) => s === 'overwrite').length;
  const renameCount = Object.values(strategies).filter((s) => s === 'rename').length;
  const itemLabel = itemKind === 'directory' ? '資料夾' : '檔案';
  const sourceLabel = itemKind === 'directory' ? '來源資料夾' : '來源檔名';

  return (
    <DialogShell
      open={open}
      onClose={onCancel}
      title={`⚠️ 發現 ${conflictItems.length} 個${itemLabel}衝突`}
      description={
        movedCount > 0
          ? `其他 ${movedCount} 個${itemLabel}已完成移動。以下${itemLabel}的目的地已存在，請選擇處理方式：`
          : `以下 ${conflictItems.length} 個${itemLabel}的目的地已存在，請選擇處理方式：`
      }
      maxWidth="max-w-3xl"
      footer={
        <div className="flex items-center gap-2 w-full flex-wrap">
          {/* 批次選擇按鈕 */}
          <span className="text-xs text-slate-500 mr-1">全部套用：</span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAll('skip')}
            className="text-xs"
          >
            <SkipForward className="h-3.5 w-3.5 mr-1" />
            略過
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAll('overwrite')}
            className="text-xs text-red-400 border-red-800 hover:bg-red-900/30"
          >
            <Copy className="h-3.5 w-3.5 mr-1" />
            覆蓋
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAll('rename')}
            className="text-xs text-amber-400 border-amber-800 hover:bg-amber-900/30"
          >
            <RefreshCw className="h-3.5 w-3.5 mr-1" />
            重新命名
          </Button>

          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-slate-500">
              略過 {skipCount} · 覆蓋 {overwriteCount} · 重命名 {renameCount}
            </span>
            <Button variant="ghost" size="sm" onClick={handleSkipAll} className="text-slate-400">
              略過全部並關閉
            </Button>
            <Button size="sm" onClick={handleConfirm}>
              確認並移動
            </Button>
          </div>
        </div>
      }
    >
      {/* 衝突清單 */}
      <div className="overflow-auto max-h-[400px] rounded border border-slate-700">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-800 border-b border-slate-700 z-10">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider w-[35%]">
                {sourceLabel}
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                目的地（已存在）
              </th>
              <th className="px-3 py-2 text-center text-xs font-medium text-slate-400 uppercase tracking-wider w-32">
                處理方式
              </th>
            </tr>
          </thead>
          <tbody>
            {conflictItems.map((item) => {
              const strategy = strategies[item.source] ?? 'skip';
              return (
                <tr
                  key={item.source}
                  className="border-b border-slate-800 hover:bg-slate-700/30"
                >
                  {/* 來源檔名 */}
                  <td
                    className="px-3 py-2 font-mono text-indigo-300 truncate max-w-0"
                    title={item.source}
                  >
                    {basename(item.source)}
                  </td>

                  {/* 目的地路徑 */}
                  <td
                    className="px-3 py-2 text-slate-400 truncate max-w-0"
                    title={item.destination}
                  >
                    {shortenPath(item.destination)}
                  </td>

                  {/* 策略選擇 */}
                  <td className="px-3 py-2 text-center">
                    <div className="flex justify-center gap-1">
                      {(['skip', 'overwrite', 'rename'] as ConflictStrategy[]).map((s) => (
                        <button
                          key={s}
                          onClick={() => setOne(item.source, s)}
                          className={cn(
                            'px-2 py-0.5 rounded text-xs border transition-colors',
                            strategy === s
                              ? s === 'skip'
                                ? 'bg-slate-600 border-slate-500 text-slate-100'
                                : s === 'overwrite'
                                ? 'bg-red-900/60 border-red-700 text-red-300'
                                : 'bg-amber-900/60 border-amber-700 text-amber-300'
                              : 'bg-slate-800 border-slate-700 text-slate-500 hover:border-slate-500 hover:text-slate-300'
                          )}
                        >
                          {STRATEGY_LABELS[s]}
                        </button>
                      ))}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* 說明提示 */}
      <div className="mt-2 flex items-start gap-1.5 text-xs text-slate-500">
        <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-amber-500" />
        <span>
          <span className="text-red-400 font-medium">覆蓋</span>
          {itemKind === 'directory'
            ? ' 會把來源資料夾內容合併並覆蓋到既有目標資料夾中的同名檔案。'
            : ' 會永久取代目的地的同名檔案。'}
          <span className="text-amber-400 font-medium ml-2">重新命名</span>
          {itemKind === 'directory'
            ? ' 不會重新命名整個資料夾；同名資料夾會直接合併，只有內部同名檔案才會加上數字後綴。'
            : ' 會自動在檔名後加上數字後綴。'}
        </span>
      </div>
    </DialogShell>
  );
}
