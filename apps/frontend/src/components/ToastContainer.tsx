import type { FC } from "react";
import { Check, AlertCircle, X, type LucideIcon } from "lucide-react";

export type ToastType = "success" | "error";

export type ToastItem = {
  id: number;
  message: string;
  type: ToastType;
};

type ToastContainerProps = {
  toasts: ToastItem[];
  onDismiss: (id: number) => void;
};

const IconForType: Record<ToastType, LucideIcon> = {
  success: Check,
  error: AlertCircle,
};

export const ToastContainer: FC<ToastContainerProps> = ({
  toasts,
  onDismiss,
}) => {
  if (toasts.length === 0) {
    return null;
  }

  return (
    <div className="fixed bottom-8 right-8 z-[200] space-y-3">
      {toasts.map((toast) => {
        const Icon = IconForType[toast.type];
        const isSuccess = toast.type === "success";

        return (
          <div
            key={toast.id}
            className={`flex items-center gap-3 px-6 py-4 rounded-2xl shadow-xl animate-in slide-in-from-bottom-4 duration-300 ${
              isSuccess ? "bg-emerald-500 text-white" : "bg-rose-500 text-white"
            }`}
            role="status"
          >
            <Icon size={18} />
            <span className="text-sm font-medium">{toast.message}</span>
            <button
              type="button"
              className="ml-2 p-1 hover:bg-white/20 rounded-full transition-colors"
              onClick={() => onDismiss(toast.id)}
              aria-label="关闭通知"
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
};
