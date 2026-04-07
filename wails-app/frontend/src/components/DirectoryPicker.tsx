import React, { useRef } from 'react';
import { FolderOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

interface DirectoryPickerProps {
  label: string;
  value: string;
  onChange: (path: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

/**
 * DirectoryPicker — 目錄選擇器。
 * 因為 Wails WebView 不支援原生 <input type="file" webkitdirectory>，
 * 使用者可直接在文字框中輸入路徑，或未來擴充為呼叫 Wails runtime.OpenDirectoryDialog。
 */
export function DirectoryPicker({
  label,
  value,
  onChange,
  placeholder = '輸入或貼上目錄路徑…',
  disabled = false,
  className,
}: DirectoryPickerProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleBrowse() {
    try {
      // Wails v2: runtime.OpenDirectoryDialog is exposed via window runtime
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const win = window as any;
      if (win.runtime?.OpenDirectoryDialog) {
        const dir: string = await win.runtime.OpenDirectoryDialog({
          Title: label,
        });
        if (dir) onChange(dir);
      } else {
        // Fallback: focus input so user can type
        inputRef.current?.focus();
      }
    } catch {
      // silently ignore
    }
  }

  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">
        {label}
      </label>
      <div className="flex gap-2">
        <Input
          ref={inputRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          className="flex-1"
        />
        <Button
          variant="outline"
          size="icon"
          onClick={handleBrowse}
          disabled={disabled}
          title="瀏覽目錄"
        >
          <FolderOpen className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
