import React from 'react';
import { cn } from '@/lib/utils';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';

interface DialogShellProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
  /** Override max-width; default is max-w-2xl */
  maxWidth?: string;
}

/**
 * DialogShell — 共用 Modal 基底。
 * 所有對話框（SearchResultDialog、OperationHistoryDialog、PreferencesDialog）
 * 都應以此元件為容器，確保視覺一致性。
 */
export function DialogShell({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  className,
  maxWidth = 'max-w-3xl',
}: DialogShellProps) {
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className={cn(maxWidth, 'max-h-[90vh] flex flex-col overflow-hidden', className)}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <div className="flex-1 overflow-auto py-2">{children}</div>
        {footer && <DialogFooter>{footer}</DialogFooter>}
      </DialogContent>
    </Dialog>
  );
}
