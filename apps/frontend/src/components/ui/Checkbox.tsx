import { forwardRef } from 'react';
import { Check } from 'lucide-react';

export interface CheckboxProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type' | 'onChange'> {
  checked: boolean;
  onCheckedChange?: (checked: boolean) => void;
}

const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  ({ checked, onCheckedChange, className = '', ...props }, ref) => {
    return (
      <>
        <input
          ref={ref}
          type="checkbox"
          checked={checked}
          onChange={(e) => onCheckedChange?.(e.target.checked)}
          className="peer sr-only"
          {...props}
        />
        <span
          className={`
            pointer-events-none inline-flex shrink-0 items-center justify-center w-5 h-5 rounded-lg border-2 transition-colors
            border-slate-300 bg-white
            peer-checked:bg-indigo-600 peer-checked:border-indigo-600
            peer-focus-visible:ring-2 peer-focus-visible:ring-indigo-500/30 peer-focus-visible:ring-offset-1
            peer-disabled:opacity-50
            ${className}
          `}
          aria-hidden
        >
          {checked && <Check size={12} strokeWidth={3} className="text-white" />}
        </span>
      </>
    );
  }
);

Checkbox.displayName = 'Checkbox';

export { Checkbox };
