import React, { useState, useEffect, useCallback } from 'react';
import { DialogShell } from '@/components/DialogShell';
import { Button } from '@/components/ui/button';
import { mover } from '../../wailsjs/go/models';
import {
  ListOperations,
  GetOperation,
  RollbackOperation,
} from '../../wailsjs/go/backend/App';
import {
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  Undo2,
  Eye,
} from 'lucide-react';
import { cn } from '@/lib/utils';

type OperationLog = mover.OperationLog;
type MoveLog = mover.MoveLog;

// ============================================================================
// RollbackConfirmModal
// ============================================================================

interface RollbackConfirmModalProps {
  op: OperationLog | null;
  onConfirm: () => void;
  onCancel: () => void;
  loading: boolean;
}

export function RollbackConfirmModal({
  op,
  onConfirm,
  onCancel,
  loading,
}: RollbackConfirmModalProps) {
  if (!op) return null;
  return (
    <DialogShell
      open={!!op}
      onClose={onCancel}
      title="⏪ 確認回滾"
      maxWidth="max-w-md"
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={loading}>
            取消
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={loading}>
            {loading ? '回滾中…' : '確認回滾'}
          </Button>
        </>
      }
    >
      <div className="text-sm text-slate-300 space-y-3">
        <p>確定要回滾此操作嗎？回滾後所有已移動的檔案將被移回原位置。</p>
        <div className="bg-slate-800 rounded p-3 space-y-1.5 text-xs">
          <div className="flex justify-between">
            <span className="text-slate-400">操作 ID</span>
            <span className="font-mono text-indigo-300">{op.id.slice(0, 16)}…</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">類型</span>
            <span>{formatType(op.type)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">項目數</span>
            <span>{op.total_items}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">狀態</span>
            <span>{formatStatus(op.status)}</span>
          </div>
        </div>
      </div>
    </DialogShell>
  );
}

// ============================================================================
// OperationDetailModal
// ============================================================================

interface OperationDetailModalProps {
  op: OperationLog | null;
  onClose: () => void;
}

function OperationDetailModal({ op, onClose }: OperationDetailModalProps) {
  if (!op) return null;
  return (
    <DialogShell
      open={!!op}
      onClose={onClose}
      title={`操作詳情 — ${op.id.slice(0, 12)}…`}
      maxWidth="max-w-2xl"
      footer={
        <Button variant="secondary" onClick={onClose}>
          關閉
        </Button>
      }
    >
      <div className="space-y-3 text-sm">
        {/* summary */}
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 bg-slate-800 rounded p-3 text-xs">
          <InfoRow label="操作 ID" value={<span className="font-mono text-indigo-300">{op.id}</span>} />
          <InfoRow label="類型" value={formatType(op.type)} />
          <InfoRow label="狀態" value={formatStatus(op.status)} />
          <InfoRow label="總項目" value={String(op.total_items)} />
          <InfoRow label="成功" value={<span className="text-emerald-400">{op.success_count}</span>} />
          <InfoRow label="失敗" value={<span className="text-red-400">{op.failed_count}</span>} />
          <InfoRow label="略過" value={String(op.skipped_count)} />
        </div>

        {/* items */}
        <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">移動項目</p>
        <div className="overflow-auto max-h-64 rounded border border-slate-700">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-slate-800">
              <tr>
                <th className="px-3 py-1.5 text-left text-slate-400">來源</th>
                <th className="px-3 py-1.5 text-left text-slate-400">目標</th>
                <th className="px-3 py-1.5 text-left text-slate-400">狀態</th>
              </tr>
            </thead>
            <tbody>
              {(op.items ?? []).map((item: MoveLog, i: number) => (
                <tr key={i} className="border-t border-slate-800">
                  <td className="px-3 py-1.5 font-mono text-slate-400 max-w-[200px] truncate" title={item.source}>
                    {item.source}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-slate-400 max-w-[200px] truncate" title={item.destination}>
                    {item.destination}
                  </td>
                  <td className="px-3 py-1.5 whitespace-nowrap">
                    {item.status === 'success' ? (
                      <span className="text-emerald-400 flex items-center gap-1">
                        <CheckCircle className="h-3 w-3" /> 成功
                      </span>
                    ) : item.error ? (
                      <span className="text-red-400 flex items-center gap-1" title={item.error}>
                        <XCircle className="h-3 w-3" /> {item.error.slice(0, 30)}
                      </span>
                    ) : (
                      <span className="text-slate-400">{item.status}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </DialogShell>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <>
      <span className="text-slate-400">{label}：</span>
      <span className="text-slate-200">{value}</span>
    </>
  );
}

// ============================================================================
// OperationHistoryTable
// ============================================================================

interface OperationHistoryTableProps {
  operations: OperationLog[];
  onDetail: (op: OperationLog) => void;
  onRollback: (op: OperationLog) => void;
}

export function OperationHistoryTable({
  operations,
  onDetail,
  onRollback,
}: OperationHistoryTableProps) {
  if (operations.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-500 text-sm gap-2">
        <Clock className="h-5 w-5" />
        尚無操作紀錄
      </div>
    );
  }

  return (
    <div className="overflow-auto rounded border border-slate-700 flex-1">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-slate-800 border-b border-slate-700">
          <tr>
            <th className="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">操作 ID</th>
            <th className="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider whitespace-nowrap">時間</th>
            <th className="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">類型</th>
            <th className="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">狀態</th>
            <th className="px-3 py-2 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">項目</th>
            <th className="px-3 py-2 text-center text-xs font-medium text-slate-400 uppercase tracking-wider">操作</th>
          </tr>
        </thead>
        <tbody>
          {operations.map((op) => (
            <tr
              key={op.id}
              onDoubleClick={() => onDetail(op)}
              className="border-b border-slate-800 hover:bg-slate-700/40 cursor-pointer"
            >
              <td className="px-3 py-2 font-mono text-xs text-indigo-300">
                {op.id.slice(0, 12)}…
              </td>
              <td className="px-3 py-2 text-slate-400 text-xs whitespace-nowrap">
                {formatTimestamp(op.timestamp)}
              </td>
              <td className="px-3 py-2 text-slate-300 whitespace-nowrap">{formatType(op.type)}</td>
              <td className="px-3 py-2">
                <StatusBadge status={op.status} />
              </td>
              <td className="px-3 py-2 text-right text-slate-400">{op.total_items}</td>
              <td className="px-3 py-2">
                <div className="flex items-center justify-center gap-1">
                  <button
                    onClick={(e) => { e.stopPropagation(); onDetail(op); }}
                    className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-slate-200"
                    title="查看詳情"
                  >
                    <Eye className="h-4 w-4" />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); onRollback(op); }}
                    disabled={op.status === 'rolled_back'}
                    className={cn(
                      'p-1 rounded text-slate-400',
                      op.status === 'rolled_back'
                        ? 'opacity-30 cursor-not-allowed'
                        : 'hover:bg-slate-700 hover:text-amber-400'
                    )}
                    title="回滾此操作"
                  >
                    <Undo2 className="h-4 w-4" />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string; Icon: React.FC<{ className?: string }> }> = {
    completed: { label: '完成', cls: 'text-emerald-400', Icon: CheckCircle },
    failed: { label: '失敗', cls: 'text-red-400', Icon: XCircle },
    partial: { label: '部分', cls: 'text-amber-400', Icon: AlertTriangle },
    started: { label: '進行中', cls: 'text-blue-400', Icon: Clock },
    rolled_back: { label: '已回滾', cls: 'text-slate-400', Icon: Undo2 },
  };
  const cfg = map[status] ?? { label: status, cls: 'text-slate-400', Icon: Clock };
  return (
    <span className={cn('flex items-center gap-1 text-xs whitespace-nowrap', cfg.cls)}>
      <cfg.Icon className="h-3.5 w-3.5" />
      {cfg.label}
    </span>
  );
}

// ============================================================================
// OperationHistoryDialog — 主對話框
// ============================================================================

interface OperationHistoryDialogProps {
  open: boolean;
  onClose: () => void;
}

export function OperationHistoryDialog({ open, onClose }: OperationHistoryDialogProps) {
  const [operations, setOperations] = useState<OperationLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailOp, setDetailOp] = useState<OperationLog | null>(null);
  const [rollbackTarget, setRollbackTarget] = useState<OperationLog | null>(null);
  const [rollbackLoading, setRollbackLoading] = useState(false);
  const [rollbackMsg, setRollbackMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const ops = await ListOperations();
      setOperations(ops ?? []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      loadHistory();
      setRollbackMsg(null);
    }
  }, [open, loadHistory]);

  async function handleDetail(op: OperationLog) {
    try {
      const full = await GetOperation(op.id);
      setDetailOp(full ?? op);
    } catch {
      setDetailOp(op);
    }
  }

  async function handleRollbackConfirm() {
    if (!rollbackTarget) return;
    setRollbackLoading(true);
    setRollbackMsg(null);
    try {
      await RollbackOperation(rollbackTarget.id);
      setRollbackMsg({ type: 'success', text: `✅ 已成功回滾操作 ${rollbackTarget.id.slice(0, 12)}…` });
      setRollbackTarget(null);
      await loadHistory();
    } catch (e) {
      setRollbackMsg({ type: 'error', text: `❌ 回滾失敗：${e}` });
      setRollbackTarget(null);
    } finally {
      setRollbackLoading(false);
    }
  }

  return (
    <>
      <DialogShell
        open={open}
        onClose={onClose}
        title="📜 操作歷史"
        description="檔案移動操作記錄（雙擊列可查看詳情）"
        maxWidth="max-w-4xl"
        footer={
          <div className="flex items-center gap-2 w-full">
            <Button variant="outline" size="sm" onClick={loadHistory} disabled={loading}>
              <RefreshCw className={cn('h-3.5 w-3.5 mr-1', loading && 'animate-spin')} />
              重新整理
            </Button>
            <div className="ml-auto">
              <Button onClick={onClose}>關閉</Button>
            </div>
          </div>
        }
      >
        {/* Status message */}
        {rollbackMsg && (
          <div
            className={cn(
              'mb-3 text-sm rounded px-3 py-2',
              rollbackMsg.type === 'success'
                ? 'bg-emerald-900/30 text-emerald-300 border border-emerald-700/50'
                : 'bg-red-900/30 text-red-300 border border-red-700/50'
            )}
          >
            {rollbackMsg.text}
          </div>
        )}

        {error && (
          <div className="mb-3 text-sm rounded px-3 py-2 bg-red-900/30 text-red-300 border border-red-700/50">
            ❌ 載入失敗：{error}
          </div>
        )}

        <div className="flex flex-col h-[400px]">
          {loading ? (
            <div className="flex-1 flex items-center justify-center text-slate-500 gap-2">
              <RefreshCw className="h-5 w-5 animate-spin" />
              載入中…
            </div>
          ) : (
            <OperationHistoryTable
              operations={operations}
              onDetail={handleDetail}
              onRollback={setRollbackTarget}
            />
          )}
        </div>
        <p className="text-xs text-slate-500 mt-1.5">
          共 {operations.length} 筆記錄
        </p>
      </DialogShell>

      <OperationDetailModal op={detailOp} onClose={() => setDetailOp(null)} />

      <RollbackConfirmModal
        op={rollbackTarget}
        onConfirm={handleRollbackConfirm}
        onCancel={() => setRollbackTarget(null)}
        loading={rollbackLoading}
      />
    </>
  );
}

// ============================================================================
// Helpers
// ============================================================================

function formatType(t: string): string {
  const map: Record<string, string> = {
    move: '📁 移動',
    batch_move: '📦 批次移動',
    move_batch: '📦 批次移動',
    rollback: '↩️ 回滾',
    copy: '📋 複製',
  };
  return map[t] ?? t;
}

function formatStatus(s: string): string {
  const map: Record<string, string> = {
    started: '🕓 進行中',
    completed: '✅ 完成',
    partial: '⚠️ 部分',
    failed: '❌ 失敗',
    rolled_back: '↩️ 已回滾',
  };
  return map[s] ?? s;
}

function formatTimestamp(ts: any): string {
  if (!ts) return '-';
  try {
    return new Date(ts).toLocaleString('zh-TW');
  } catch {
    return String(ts);
  }
}
