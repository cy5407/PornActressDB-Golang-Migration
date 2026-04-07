import React, { useState, useMemo } from 'react';
import { DialogShell } from '@/components/DialogShell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { backend } from '../../wailsjs/go/models';
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  ArrowUpDown,
  Download,
  Copy,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { cn } from '@/lib/utils';

type SearchResult = backend.SearchResult;
type FilterType = 'all' | 'success' | 'failed';
type SortDir = 'asc' | 'desc';

// ============================================================================
// SearchResultDetailModal — 單筆詳情 Modal
// ============================================================================

interface SearchResultDetailModalProps {
  result: SearchResult | null;
  onClose: () => void;
}

export function SearchResultDetailModal({ result, onClose }: SearchResultDetailModalProps) {
  if (!result) return null;
  const isSuccess = !result.error && result.actresses?.length > 0;

  return (
    <DialogShell
      open={!!result}
      onClose={onClose}
      title={`詳細資訊 — ${result.code}`}
      maxWidth="max-w-lg"
      footer={
        <Button variant="secondary" onClick={onClose}>
          關閉
        </Button>
      }
    >
      <div className="space-y-3 text-sm">
        <Row label="番號" value={result.code} />
        <Row
          label="狀態"
          value={
            <span className={isSuccess ? 'text-emerald-400' : 'text-red-400'}>
              {isSuccess ? '✅ 成功' : '❌ 失敗'}
            </span>
          }
        />
        <Row label="標題" value={result.title || '-'} />
        <Row label="片商" value={result.studio || '-'} />
        <Row label="發行日期" value={result.release_date || '-'} />
        <Row label="來源方法" value={result.method || '-'} />
        <Row
          label="女優"
          value={
            result.actresses?.length > 0 ? (
              <ul className="space-y-0.5">
                {result.actresses.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            ) : (
              <span className="text-slate-500">未找到</span>
            )
          }
        />
        {result.url && (
          <Row
            label="URL"
            value={
              <a
                href={result.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-indigo-400 underline break-all"
              >
                {result.url}
              </a>
            }
          />
        )}
        {result.error && (
          <Row
            label="錯誤"
            value={<span className="text-red-400 break-all">{result.error}</span>}
          />
        )}
      </div>
    </DialogShell>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] gap-2">
      <span className="text-slate-400 font-medium">{label}：</span>
      <span className="text-slate-100">{value}</span>
    </div>
  );
}

// ============================================================================
// SearchResultTable — 可排序篩選的表格
// ============================================================================

interface SearchResultTableProps {
  results: SearchResult[];
  onRowDoubleClick: (r: SearchResult) => void;
}

type ColumnKey = 'code' | 'actresses' | 'source' | 'studio' | 'status';

function getStatus(r: SearchResult): 'success' | 'failed' {
  return !r.error && r.actresses?.length > 0 ? 'success' : 'failed';
}

export function SearchResultTable({ results, onRowDoubleClick }: SearchResultTableProps) {
  const [sortCol, setSortCol] = useState<ColumnKey>('code');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const toggleSort = (col: ColumnKey) => {
    if (sortCol === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortCol(col);
      setSortDir('asc');
    }
  };

  const sorted = useMemo(() => {
    return [...results].sort((a, b) => {
      let av = '';
      let bv = '';
      switch (sortCol) {
        case 'code':
          av = a.code;
          bv = b.code;
          break;
        case 'actresses':
          av = (a.actresses ?? []).join(',');
          bv = (b.actresses ?? []).join(',');
          break;
        case 'source':
          av = a.method ?? '';
          bv = b.method ?? '';
          break;
        case 'studio':
          av = a.studio ?? '';
          bv = b.studio ?? '';
          break;
        case 'status':
          av = getStatus(a);
          bv = getStatus(b);
          break;
      }
      return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    });
  }, [results, sortCol, sortDir]);

  const ColHeader = ({
    col,
    label,
    className,
  }: {
    col: ColumnKey;
    label: string;
    className?: string;
  }) => (
    <th
      className={cn(
        'px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider cursor-pointer select-none hover:text-slate-200 whitespace-nowrap',
        className
      )}
      onClick={() => toggleSort(col)}
    >
      <span className="flex items-center gap-1">
        {label}
        {sortCol === col ? (
          sortDir === 'asc' ? (
            <ChevronUp className="h-3 w-3" />
          ) : (
            <ChevronDown className="h-3 w-3" />
          )
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-30" />
        )}
      </span>
    </th>
  );

  return (
    <div className="overflow-auto flex-1 rounded border border-slate-700">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-slate-800 border-b border-slate-700">
          <tr>
            <ColHeader col="code" label="番號" />
            <ColHeader col="actresses" label="女優" className="min-w-[160px]" />
            <ColHeader col="source" label="來源" />
            <ColHeader col="studio" label="片商" />
            <ColHeader col="status" label="狀態" />
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => {
            const status = getStatus(r);
            const actressStr =
              (r.actresses ?? []).length > 3
                ? r.actresses.slice(0, 3).join(', ') + ` (+${r.actresses.length - 3})`
                : (r.actresses ?? []).join(', ') || '❌ 未找到';
            return (
              <tr
                key={r.code}
                onDoubleClick={() => onRowDoubleClick(r)}
                className="border-b border-slate-800 hover:bg-slate-700/40 cursor-pointer"
              >
                <td className="px-3 py-2 font-mono text-indigo-300">{r.code}</td>
                <td className="px-3 py-2 text-slate-300 max-w-[200px] truncate" title={actressStr}>
                  {actressStr}
                </td>
                <td className="px-3 py-2 text-slate-400 whitespace-nowrap">{r.method || '-'}</td>
                <td className="px-3 py-2 text-slate-400 whitespace-nowrap">{r.studio || '-'}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {status === 'success' ? (
                    <span className="flex items-center gap-1 text-emerald-400">
                      <CheckCircle className="h-3.5 w-3.5" />
                      成功
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-red-400">
                      <XCircle className="h-3.5 w-3.5" />
                      失敗
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ============================================================================
// SearchResultDialog — 主對話框
// ============================================================================

interface SearchResultDialogProps {
  open: boolean;
  onClose: () => void;
  results: SearchResult[];
}

export function SearchResultDialog({ open, onClose, results }: SearchResultDialogProps) {
  const [filter, setFilter] = useState<FilterType>('all');
  const [search, setSearch] = useState('');
  const [detailTarget, setDetailTarget] = useState<SearchResult | null>(null);

  const successCount = results.filter((r) => getStatus(r) === 'success').length;
  const failedCount = results.length - successCount;

  const filtered = useMemo(() => {
    return results.filter((r) => {
      if (filter === 'success' && getStatus(r) !== 'success') return false;
      if (filter === 'failed' && getStatus(r) !== 'failed') return false;
      if (search) {
        const q = search.toLowerCase();
        const haystack = [r.code, r.studio, r.method, ...(r.actresses ?? [])].join(' ').toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [results, filter, search]);

  function copyToClipboard(codes: string[]) {
    if (codes.length === 0) return;
    navigator.clipboard.writeText(codes.join('\n')).catch(() => {});
  }

  function exportCSV() {
    const header = '番號,女優,來源,片商,狀態,錯誤\n';
    const rows = results
      .map(
        (r) =>
          [
            r.code,
            (r.actresses ?? []).join(' # '),
            r.method ?? '',
            r.studio ?? '',
            getStatus(r),
            r.error ?? '',
          ]
            .map((v) => `"${String(v).replace(/"/g, '""')}"`)
            .join(',')
      )
      .join('\n');
    const blob = new Blob(['\uFEFF' + header + rows], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'search_results.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <DialogShell
        open={open}
        onClose={onClose}
        title="🔍 搜尋結果預覽"
        description={`共 ${results.length} 筆 | ✅ ${successCount} 成功 / ❌ ${failedCount} 失敗`}
        maxWidth="max-w-5xl"
        footer={
          <div className="flex items-center gap-2 flex-wrap w-full">
            <Button variant="outline" size="sm" onClick={exportCSV}>
              <Download className="h-3.5 w-3.5 mr-1" />
              匯出 CSV
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                copyToClipboard(
                  results.filter((r) => getStatus(r) === 'failed').map((r) => r.code)
                )
              }
            >
              <Copy className="h-3.5 w-3.5 mr-1" />
              複製失敗番號
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                copyToClipboard(
                  results.filter((r) => getStatus(r) === 'success').map((r) => r.code)
                )
              }
            >
              <Copy className="h-3.5 w-3.5 mr-1" />
              複製成功番號
            </Button>
            <div className="ml-auto">
              <Button onClick={onClose}>關閉</Button>
            </div>
          </div>
        }
      >
        {/* Toolbar */}
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          {/* Filter buttons */}
          <div className="flex rounded border border-slate-700 overflow-hidden text-xs">
            {(['all', 'success', 'failed'] as FilterType[]).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={cn(
                  'px-3 py-1.5 transition-colors',
                  filter === f
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                )}
              >
                {f === 'all' ? '全部' : f === 'success' ? '✅ 成功' : '❌ 失敗'}
              </button>
            ))}
          </div>
          {/* Search */}
          <Input
            placeholder="搜尋番號 / 女優 / 片商…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-52 h-8 text-sm bg-slate-800 border-slate-700"
          />
          <span className="text-xs text-slate-500 ml-auto">
            顯示 {filtered.length} / {results.length} 筆
          </span>
        </div>

        {/* Table */}
        <div className="flex flex-col min-h-0 h-[380px]">
          {filtered.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
              <AlertTriangle className="h-5 w-5 mr-2" />
              沒有符合條件的結果
            </div>
          ) : (
            <SearchResultTable results={filtered} onRowDoubleClick={setDetailTarget} />
          )}
        </div>
        <p className="text-xs text-slate-500 mt-1.5">提示：雙擊列可查看詳細資訊</p>
      </DialogShell>

      <SearchResultDetailModal
        result={detailTarget}
        onClose={() => setDetailTarget(null)}
      />
    </>
  );
}
