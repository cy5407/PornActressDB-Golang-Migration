import React, { useRef } from 'react';
import { FolderOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { SelectDirectory } from '../../wailsjs/go/backend/App';

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
 * 呼叫 Go binding SelectDirectory() 開啟原生目錄選擇對話框。
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
      const dir = await SelectDirectory(label);
      if (dir) onChange(dir);
    } catch {
      // 降級：讓使用者手動輸入
      inputRef.current?.focus();
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
