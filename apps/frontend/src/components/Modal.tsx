import type { PropsWithChildren } from 'react';
import { X } from 'lucide-react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  onConfirm?: () => void;
  confirmText?: string;
  confirmDisabled?: boolean;
}

export const Modal = ({
  isOpen,
  onClose,
  title,
  children,
  onConfirm,
  confirmText = '保存',
  confirmDisabled = false,
}: PropsWithChildren<ModalProps>) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-2 md:p-4">
      <div
        className="absolute inset-0 backdrop-blur-sm"
        style={{ backgroundColor: 'var(--theme-overlay)' }}
        onClick={onClose}
      />
      <div className="theme-surface w-full max-w-lg rounded-2xl md:rounded-[2.5rem] shadow-2xl relative z-10 overflow-hidden animate-in zoom-in-95 duration-200 max-h-[90vh] flex flex-col border theme-border">
        <div className="px-4 md:px-8 pt-6 md:pt-8 pb-4 flex justify-between items-center border-b theme-border shrink-0">
          <h3 className="text-lg md:text-xl font-black theme-text tracking-tight pr-2">
            {title}
          </h3>
          <button
            onClick={onClose}
            className="p-2 theme-surface-hover rounded-full theme-text-muted transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center shrink-0"
            aria-label="关闭"
          >
            <X size={20} />
          </button>
        </div>
        <div className="px-4 md:px-8 py-4 md:py-6 theme-text max-h-[calc(90vh-140px)] overflow-y-auto custom-scrollbar flex-1">
          {children}
        </div>
        <div className="px-4 md:px-8 pb-4 md:pb-8 pt-4 flex gap-2 md:gap-3 border-t theme-border shrink-0">
          <button
            onClick={onClose}
            className="flex-1 py-3 rounded-2xl font-bold theme-text-muted theme-surface-hover transition-all min-h-[44px]"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            disabled={confirmDisabled}
            className="flex-1 py-3 rounded-2xl font-bold theme-btn-primary theme-on-primary shadow-lg transition-all min-h-[44px] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
};
