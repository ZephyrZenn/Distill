import type { FC } from 'react';
import { X } from 'lucide-react';

export type ConfirmDialogOptions = {
  title?: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: 'default' | 'danger';
};

type ConfirmDialogProps = {
  open: boolean;
  options?: ConfirmDialogOptions | null;
  onConfirm: () => void;
  onCancel: () => void;
};

export const ConfirmDialog: FC<ConfirmDialogProps> = ({
  open,
  options,
  onConfirm,
  onCancel,
}) => {
  if (!open || !options) {
    return null;
  }

  const {
    title = '确认操作',
    description = '请确认是否继续此操作。',
    confirmLabel = '确认',
    cancelLabel = '取消',
    tone = 'default',
  } = options;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 backdrop-blur-sm"
        style={{ backgroundColor: 'var(--theme-overlay)' }}
        onClick={onCancel}
      />
      <div className="theme-surface w-full max-w-md rounded-[2.5rem] shadow-2xl relative z-10 overflow-hidden animate-in zoom-in-95 duration-200 border theme-border">
        <div className="px-8 pt-8 pb-4 flex justify-between items-center border-b theme-border">
          <h3 className="text-xl font-black theme-text tracking-tight">
            {title}
          </h3>
          <button
            onClick={onCancel}
            className="p-2 theme-surface-hover rounded-full theme-text-muted transition-colors"
          >
            <X size={20} />
          </button>
        </div>
        <div className="px-8 py-6 theme-text">
          <p className="text-sm leading-relaxed">{description}</p>
        </div>
        <div className="px-8 pb-8 pt-4 flex gap-3 border-t theme-border">
          <button
            onClick={onCancel}
            className="flex-1 py-3 rounded-2xl font-bold theme-text-muted theme-surface-hover transition-all"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className={`flex-1 py-3 rounded-2xl font-bold shadow-lg transition-all ${
              tone === 'danger'
                ? 'bg-rose-500 text-white shadow-rose-100 hover:bg-rose-600'
                : 'bg-amber-600 text-white shadow-amber-100 hover:bg-amber-700'
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};
