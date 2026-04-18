import React, { useState, useCallback } from 'react';
import { DialogShell } from '@/components/DialogShell';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface MultiActressItem {
  /** 番號 */
  code: string;
  /** 原始檔案路徑，用於顯示 */
  path: string;
  /** 可選擇的女優清單（至少 2 位） */
  actresses: string[];
}

/** 使用者對每個番號的選擇結果 */
export type ActressChoice =
  | { type: 'actress'; name: string }
  | { type: 'multi'; label: string }
  | { type: 'unclassified' };

export interface MultiActressResolution {
  code: string;
  choice: ActressChoice;
}

interface MultiActressDialogProps {
  open: boolean;
  /** 需要使用者決定分類的多女優項目 */
  items: MultiActressItem[];
  /** 「多人共演」資料夾的名稱，可由偏好設定覆寫 */
  multiLabel?: string;
  /** 上次確認的偏好選擇，key 為番號；初始化時優先採用 */
  savedChoices?: Record<string, ActressChoice>;
  onConfirm: (resolutions: MultiActressResolution[]) => void;
  onCancel: () => void;
}

function basename(path: string): string {
  return path.replace(/.*[/\\]/, '');
}

/**
 * MultiActressDialog — 多女優分類選擇對話框
 *
 * 當一個番號含有多位女優時，讓使用者為每筆記錄選擇：
 * - 其中一位女優資料夾
 * - 多人共演資料夾
 * - 未分類
 */
/** 從 savedChoices 取出此 item 的偏好；若女優已不在清單中則回退到第一位 */
function resolveInitialChoice(
  item: MultiActressItem,
  savedChoices?: Record<string, ActressChoice>
): ActressChoice {
  const saved = savedChoices?.[item.code];
  if (saved) {
    if (saved.type === 'actress' && item.actresses.includes(saved.name)) return saved;
    if (saved.type === 'multi' || saved.type === 'unclassified') return saved;
  }
  return { type: 'actress', name: item.actresses[0] };
}

export function MultiActressDialog({
  open,
  items,
  multiLabel = '多人共演',
  savedChoices,
  onConfirm,
  onCancel,
}: MultiActressDialogProps) {
  const [choices, setChoices] = useState<Record<string, ActressChoice>>(() =>
    Object.fromEntries(items.map((item) => [item.code, resolveInitialChoice(item, savedChoices)]))
  );

  React.useEffect(() => {
    setChoices(
      Object.fromEntries(items.map((item) => [item.code, resolveInitialChoice(item, savedChoices)]))
    );
  }, [items, savedChoices]);

  const setChoice = useCallback((code: string, choice: ActressChoice) => {
    setChoices((prev) => ({ ...prev, [code]: choice }));
  }, []);

  const setAll = useCallback(
    (choiceType: 'multi' | 'unclassified') => {
      const updated = Object.fromEntries(
        items.map((item) => [
          item.code,
          choiceType === 'multi'
            ? ({ type: 'multi', label: multiLabel } as ActressChoice)
            : ({ type: 'unclassified' } as ActressChoice),
        ])
      );
      setChoices(updated);
    },
    [items, multiLabel]
  );

  function handleConfirm() {
    const resolutions: MultiActressResolution[] = items.map((item) => ({
      code: item.code,
      choice: choices[item.code] ?? { type: 'actress', name: item.actresses[0] },
    }));
    onConfirm(resolutions);
  }

  function choiceLabel(choice: ActressChoice): string {
    if (choice.type === 'actress') return choice.name;
    if (choice.type === 'multi') return multiLabel;
    return '未分類';
  }

  const multiCount = Object.values(choices).filter((c) => c.type === 'multi').length;
  const unclassifiedCount = Object.values(choices).filter((c) => c.type === 'unclassified').length;
  const actressCount = Object.values(choices).filter((c) => c.type === 'actress').length;

  return (
    <DialogShell
      open={open}
      onClose={onCancel}
      title={`👥 ${items.length} 個番號含有多位女優，請選擇分類方式`}
      description="請為每筆記錄選擇要分入的女優資料夾、多人共演，或未分類。"
      maxWidth="max-w-4xl"
      footer={
        <div className="flex items-center gap-2 w-full flex-wrap">
          <span className="text-xs text-slate-500 mr-1">全部套用：</span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAll('multi')}
            className="text-xs text-purple-400 border-purple-800 hover:bg-purple-900/30"
          >
            👥 {multiLabel}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAll('unclassified')}
            className="text-xs text-slate-400"
          >
            📂 未分類
          </Button>

          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-slate-500">
              女優 {actressCount} · 共演 {multiCount} · 未分類 {unclassifiedCount}
            </span>
            <Button variant="ghost" size="sm" onClick={onCancel} className="text-slate-400">
              取消
            </Button>
            <Button size="sm" onClick={handleConfirm}>
              確認分類
            </Button>
          </div>
        </div>
      }
    >
      <div className="overflow-auto max-h-[480px] rounded border border-slate-700">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-800 border-b border-slate-700 z-10">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider w-[15%]">
                番號
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider w-[25%]">
                檔案
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                分類選擇
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider w-[20%]">
                目前選擇
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const current = choices[item.code];
              return (
                <tr key={item.code} className="border-b border-slate-800 hover:bg-slate-700/20">
                  {/* 番號 */}
                  <td className="px-3 py-2 font-mono text-indigo-300 font-medium">
                    {item.code}
                  </td>

                  {/* 檔名 */}
                  <td
                    className="px-3 py-2 text-slate-400 truncate max-w-0"
                    title={item.path}
                  >
                    {basename(item.path)}
                  </td>

                  {/* 選擇按鈕群 */}
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {/* 各女優按鈕 */}
                      {item.actresses.map((name) => {
                        const isSelected =
                          current?.type === 'actress' && current.name === name;
                        return (
                          <button
                            key={name}
                            onClick={() => setChoice(item.code, { type: 'actress', name })}
                            className={cn(
                              'px-2 py-0.5 rounded text-xs border transition-colors',
                              isSelected
                                ? 'bg-indigo-900/60 border-indigo-600 text-indigo-200'
                                : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                            )}
                          >
                            {name}
                          </button>
                        );
                      })}

                      {/* 多人共演 */}
                      <button
                        onClick={() =>
                          setChoice(item.code, { type: 'multi', label: multiLabel })
                        }
                        className={cn(
                          'px-2 py-0.5 rounded text-xs border transition-colors',
                          current?.type === 'multi'
                            ? 'bg-purple-900/60 border-purple-600 text-purple-200'
                            : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                        )}
                      >
                        👥 {multiLabel}
                      </button>

                      {/* 未分類 */}
                      <button
                        onClick={() => setChoice(item.code, { type: 'unclassified' })}
                        className={cn(
                          'px-2 py-0.5 rounded text-xs border transition-colors',
                          current?.type === 'unclassified'
                            ? 'bg-slate-600 border-slate-500 text-slate-200'
                            : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                        )}
                      >
                        📂 未分類
                      </button>
                    </div>
                  </td>

                  {/* 目前選擇結果 */}
                  <td className="px-3 py-2">
                    <span
                      className={cn(
                        'text-xs font-medium px-1.5 py-0.5 rounded',
                        current?.type === 'actress'
                          ? 'text-indigo-300'
                          : current?.type === 'multi'
                          ? 'text-purple-300'
                          : 'text-slate-400'
                      )}
                    >
                      {current ? choiceLabel(current) : '—'}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </DialogShell>
  );
}
