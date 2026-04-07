import React, { useState, useEffect } from 'react';
import { DialogShell } from '@/components/DialogShell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  GetPreferences,
  UpdatePreferences,
  ResetPreferences,
} from '../../wailsjs/go/backend/App';
import { backend } from '../../wailsjs/go/models';
import { RefreshCw, Save, RotateCcw, X } from 'lucide-react';
import { cn } from '@/lib/utils';

type Preferences = backend.Preferences;

type TabId = 'search' | 'classification' | 'studio' | 'system';

const TABS: { id: TabId; label: string }[] = [
  { id: 'search', label: '👩 女優搜尋' },
  { id: 'classification', label: '🔧 分類選項' },
  { id: 'studio', label: '🏢 片商分類' },
  { id: 'system', label: '⚙️ 系統設定' },
];

// ============================================================================
// Sub-forms for each tab
// ============================================================================

interface FormProps {
  prefs: Preferences;
  onChange: (p: Preferences) => void;
}

function SearchTab({ prefs, onChange }: FormProps) {
  const set = <K extends keyof Preferences>(k: K, v: Preferences[K]) =>
    onChange({ ...prefs, [k]: v });

  return (
    <div className="space-y-4 text-sm">
      <Section title="搜尋批次設定">
        <Field label="批次大小" hint="每批同時搜尋的影片數量">
          <InputNum value={prefs.batch_size} min={1} max={100} onChange={(v) => set('batch_size', v)} />
        </Field>
        <Field label="並行執行緒" hint="同時執行的搜尋執行緒數">
          <InputNum value={prefs.thread_count} min={1} max={20} onChange={(v) => set('thread_count', v)} />
        </Field>
        <Field label="批次延遲 (秒)" hint="批次之間的等待秒數">
          <InputFloat value={prefs.batch_delay} step={0.5} min={0} onChange={(v) => set('batch_delay', v)} />
        </Field>
        <Field label="請求逾時 (秒)" hint="單次 HTTP 請求的逾時秒數">
          <InputNum value={prefs.request_timeout} min={5} max={120} onChange={(v) => set('request_timeout', v)} />
        </Field>
      </Section>

      <Section title="AV-WIKI 並發設定">
        <Field label="啟用並發搜尋">
          <Toggle
            value={prefs.avwiki_concurrent_enabled}
            onChange={(v) => set('avwiki_concurrent_enabled', v)}
          />
        </Field>
        <Field label="最大並發數" hint="AV-WIKI 最大同時連線數">
          <InputNum
            value={prefs.avwiki_max_concurrent}
            min={1}
            max={50}
            disabled={!prefs.avwiki_concurrent_enabled}
            onChange={(v) => set('avwiki_max_concurrent', v)}
          />
        </Field>
      </Section>
    </div>
  );
}

function ClassificationTab({ prefs, onChange }: FormProps) {
  const set = <K extends keyof Preferences>(k: K, v: Preferences[K]) =>
    onChange({ ...prefs, [k]: v });

  return (
    <div className="space-y-4 text-sm">
      <Section title="分類模式">
        <Field label="分類模式" hint="interactive = 互動確認 / auto = 自動分類">
          <select
            value={prefs.mode}
            onChange={(e) => set('mode', e.target.value)}
            className="bg-slate-800 border border-slate-600 text-slate-200 text-sm rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="interactive">互動模式 (interactive)</option>
            <option value="auto">自動模式 (auto)</option>
          </select>
        </Field>
        <Field label="自動套用偏好設定" hint="自動根據偏好分類，不需每次確認">
          <Toggle
            value={prefs.auto_apply_preferences}
            onChange={(v) => set('auto_apply_preferences', v)}
          />
        </Field>
      </Section>

      <Section title="掃描設定">
        <Field label="掃描並行數" hint="Go 掃描引擎使用的並發 Worker 數量">
          <InputNum value={prefs.scan_workers} min={1} max={50} onChange={(v) => set('scan_workers', v)} />
        </Field>
      </Section>
    </div>
  );
}

function StudioTab({ prefs, onChange }: FormProps) {
  const set = <K extends keyof Preferences>(k: K, v: Preferences[K]) =>
    onChange({ ...prefs, [k]: v });

  return (
    <div className="space-y-4 text-sm">
      <Section title="移動策略">
        <Field label="衝突處理策略" hint="移動時遇到同名檔案的處理方式">
          <select
            value={prefs.move_conflict_strategy}
            onChange={(e) => set('move_conflict_strategy', e.target.value)}
            className="bg-slate-800 border border-slate-600 text-slate-200 text-sm rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="skip">略過 (skip)</option>
            <option value="overwrite">覆蓋 (overwrite)</option>
            <option value="rename">重新命名 (rename)</option>
          </select>
        </Field>
      </Section>

      <Section title="操作記錄">
        <Field label="啟用操作記錄" hint="記錄所有移動操作以便回滾">
          <Toggle
            value={prefs.enable_operation_log}
            onChange={(v) => set('enable_operation_log', v)}
          />
        </Field>
        <Field label="記錄目錄" hint="操作日誌存放的目錄路徑">
          <Input
            value={prefs.log_dir}
            onChange={(e) => set('log_dir', e.target.value)}
            disabled={!prefs.enable_operation_log}
            className={cn('h-8 text-sm bg-slate-800 border-slate-700', !prefs.enable_operation_log && 'opacity-50')}
          />
        </Field>
      </Section>
    </div>
  );
}

function SystemTab({ prefs, onChange }: FormProps) {
  const set = <K extends keyof Preferences>(k: K, v: Preferences[K]) =>
    onChange({ ...prefs, [k]: v });

  return (
    <div className="space-y-4 text-sm">
      <Section title="路徑設定">
        <Field label="預設輸入目錄" hint="啟動時預設掃描的目錄">
          <Input
            value={prefs.default_input_dir}
            onChange={(e) => set('default_input_dir', e.target.value)}
            className="h-8 text-sm bg-slate-800 border-slate-700"
          />
        </Field>
        <Field label="資料庫目錄" hint="JSON 資料庫檔案存放的目錄">
          <Input
            value={prefs.json_data_dir}
            onChange={(e) => set('json_data_dir', e.target.value)}
            className="h-8 text-sm bg-slate-800 border-slate-700"
          />
        </Field>
      </Section>

      <Section title="Go 整合">
        <Field label="啟用 Go 加速">
          <Toggle value={prefs.go_enabled} onChange={(v) => set('go_enabled', v)} />
        </Field>
        <Field label="Go CLI 路徑" hint="classifier.exe 的完整路徑（留空自動偵測）">
          <Input
            value={prefs.go_exe_path}
            onChange={(e) => set('go_exe_path', e.target.value)}
            disabled={!prefs.go_enabled}
            placeholder="自動偵測"
            className={cn('h-8 text-sm bg-slate-800 border-slate-700', !prefs.go_enabled && 'opacity-50')}
          />
        </Field>
      </Section>

      <Section title="快取設定">
        <Field label="快取保留天數">
          <InputNum value={prefs.cache_ttl_days} min={1} max={365} onChange={(v) => set('cache_ttl_days', v)} />
        </Field>
        <Field label="快取大小上限 (MB)">
          <InputNum value={prefs.cache_max_size_mb} min={50} max={10000} onChange={(v) => set('cache_max_size_mb', v)} />
        </Field>
        <Field label="退出時自動清理過期快取">
          <Toggle
            value={prefs.cache_auto_cleanup_on_exit}
            onChange={(v) => set('cache_auto_cleanup_on_exit', v)}
          />
        </Field>
      </Section>
    </div>
  );
}

// ============================================================================
// Small UI helpers
// ============================================================================

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">{title}</p>
      <div className="space-y-2.5 pl-1">{children}</div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-[1fr_auto] gap-x-4 items-center">
      <div>
        <span className="text-slate-200">{label}</span>
        {hint && <span className="ml-1.5 text-xs text-slate-500">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      onClick={() => onChange(!value)}
      className={cn(
        'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors',
        value ? 'bg-indigo-600' : 'bg-slate-600'
      )}
    >
      <span
        className={cn(
          'pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-lg transition-transform',
          value ? 'translate-x-4' : 'translate-x-0'
        )}
      />
    </button>
  );
}

function InputNum({
  value,
  min,
  max,
  disabled,
  onChange,
}: {
  value: number;
  min: number;
  max: number;
  disabled?: boolean;
  onChange: (v: number) => void;
}) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      disabled={disabled}
      onChange={(e) => onChange(Number(e.target.value))}
      className={cn(
        'w-20 bg-slate-800 border border-slate-600 text-slate-200 text-sm rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-indigo-500',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
    />
  );
}

function InputFloat({
  value,
  step,
  min,
  onChange,
}: {
  value: number;
  step: number;
  min: number;
  onChange: (v: number) => void;
}) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      step={step}
      onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
      className="w-20 bg-slate-800 border border-slate-600 text-slate-200 text-sm rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-indigo-500"
    />
  );
}

// ============================================================================
// PreferencesDialog — 主對話框
// ============================================================================

interface PreferencesDialogProps {
  open: boolean;
  onClose: () => void;
}

export function PreferencesDialog({ open, onClose }: PreferencesDialogProps) {
  const [tab, setTab] = useState<TabId>('search');
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  async function loadPrefs() {
    setLoading(true);
    setMsg(null);
    try {
      const p = await GetPreferences();
      setPrefs(p);
    } catch (e) {
      setMsg({ type: 'error', text: `❌ 讀取設定失敗：${e}` });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (open) loadPrefs();
  }, [open]);

  async function handleSave() {
    if (!prefs) return;
    setSaving(true);
    setMsg(null);
    try {
      await UpdatePreferences(prefs);
      setMsg({ type: 'success', text: '✅ 設定已儲存' });
    } catch (e) {
      setMsg({ type: 'error', text: `❌ 儲存失敗：${e}` });
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    if (!confirm('確定要重設所有設定為預設值嗎？')) return;
    setSaving(true);
    setMsg(null);
    try {
      await ResetPreferences();
      await loadPrefs();
      setMsg({ type: 'success', text: '✅ 已重設為預設值' });
    } catch (e) {
      setMsg({ type: 'error', text: `❌ 重設失敗：${e}` });
    } finally {
      setSaving(false);
    }
  }

  return (
    <DialogShell
      open={open}
      onClose={onClose}
      title="⚙️ 偏好設定"
      description="調整應用程式行為與搜尋參數"
      maxWidth="max-w-2xl"
      footer={
        <div className="flex items-center gap-2 w-full">
          <Button variant="outline" size="sm" onClick={handleReset} disabled={saving || loading}>
            <RotateCcw className="h-3.5 w-3.5 mr-1" />
            重設預設值
          </Button>
          <div className="ml-auto flex gap-2">
            <Button variant="secondary" onClick={onClose} disabled={saving}>
              <X className="h-3.5 w-3.5 mr-1" />
              取消
            </Button>
            <Button onClick={handleSave} disabled={saving || loading || !prefs}>
              {saving ? (
                <RefreshCw className="h-3.5 w-3.5 mr-1 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5 mr-1" />
              )}
              儲存設定
            </Button>
          </div>
        </div>
      }
    >
      {/* Status message */}
      {msg && (
        <div
          className={cn(
            'mb-3 text-sm rounded px-3 py-2',
            msg.type === 'success'
              ? 'bg-emerald-900/30 text-emerald-300 border border-emerald-700/50'
              : 'bg-red-900/30 text-red-300 border border-red-700/50'
          )}
        >
          {msg.text}
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-slate-700 mb-4 gap-1 -mx-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              'px-3 py-2 text-sm rounded-t transition-colors whitespace-nowrap',
              tab === t.id
                ? 'bg-slate-800 text-slate-100 border-b-2 border-indigo-500 -mb-px'
                : 'text-slate-400 hover:text-slate-200'
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center h-40 text-slate-500 gap-2">
          <RefreshCw className="h-5 w-5 animate-spin" />
          載入設定中…
        </div>
      ) : !prefs ? (
        <div className="flex items-center justify-center h-40 text-slate-500">
          無法讀取設定
        </div>
      ) : (
        <div className="overflow-auto max-h-[380px] pr-1">
          {tab === 'search' && <SearchTab prefs={prefs} onChange={setPrefs} />}
          {tab === 'classification' && <ClassificationTab prefs={prefs} onChange={setPrefs} />}
          {tab === 'studio' && <StudioTab prefs={prefs} onChange={setPrefs} />}
          {tab === 'system' && <SystemTab prefs={prefs} onChange={setPrefs} />}
        </div>
      )}
    </DialogShell>
  );
}
