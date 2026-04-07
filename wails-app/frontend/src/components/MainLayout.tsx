import React from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useTaskStore } from '@/stores/taskStore';
import { Settings, History, Search, Film } from 'lucide-react';

interface SidebarProps {
  className?: string;
}

function Sidebar({ className }: SidebarProps) {
  const { setShowPreferences, setShowOperationHistory, setShowSearchResults } = useTaskStore();

  return (
    <aside
      className={cn(
        'flex flex-col w-14 bg-slate-900 border-r border-slate-700 py-3 items-center gap-2 shrink-0',
        className
      )}
    >
      <div className="flex flex-col items-center gap-1 text-slate-500 mb-auto mt-2">
        <Film className="h-6 w-6 text-indigo-400" />
        <span className="text-[8px] font-bold tracking-widest text-indigo-400 mt-0.5">ACV</span>
      </div>

      <div className="flex flex-col items-center gap-2 mt-auto">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setShowSearchResults(true)}
          title="搜尋結果"
          className="rounded-lg"
        >
          <Search className="h-5 w-5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setShowOperationHistory(true)}
          title="操作歷史"
          className="rounded-lg"
        >
          <History className="h-5 w-5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setShowPreferences(true)}
          title="偏好設定"
          className="rounded-lg"
        >
          <Settings className="h-5 w-5" />
        </Button>
      </div>
    </aside>
  );
}

interface MainLayoutProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * MainLayout — 側邊欄 + 主內容區。
 * 側邊欄提供快速存取搜尋結果、操作歷史與偏好設定。
 * 主內容區域由 children 填充。
 */
export function MainLayout({ children, className }: MainLayoutProps) {
  return (
    <div className={cn('flex h-screen w-screen overflow-hidden bg-slate-950', className)}>
      <Sidebar />
      <main className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {children}
      </main>
    </div>
  );
}
