import { Calendar, X } from 'lucide-react';
import { useEffect, useState, useRef } from 'react';
import { DayPicker, DateRange } from 'react-day-picker';
import { format, isAfter, isBefore, startOfDay, subDays } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import 'react-day-picker/style.css';

interface DateFilterProps {
  startDate?: string;
  endDate?: string;
  onStartDateChange?: (date: string) => void;
  onEndDateChange?: (date: string) => void;
}

const getTodayString = () => {
  const today = new Date();
  return format(today, 'yyyy-MM-dd');
};

const parseDate = (dateStr: string): Date => {
  return new Date(dateStr + 'T00:00:00');
};

const formatDateString = (date: Date): string => {
  return format(date, 'yyyy-MM-dd');
};

export const DateFilter = ({
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
}: DateFilterProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [error, setError] = useState<string>('');
  const popoverRef = useRef<HTMLDivElement>(null);

  // 默认设置为今天
  useEffect(() => {
    if (!startDate && !endDate && onStartDateChange && onEndDateChange) {
      const today = getTodayString();
      onStartDateChange(today);
      onEndDateChange(today);
    }
  }, []);

  // 验证日期
  useEffect(() => {
    if (startDate && endDate) {
      const start = parseDate(startDate);
      const end = parseDate(endDate);
      if (isAfter(start, end)) {
        setError('开始日期不能晚于结束日期');
      } else {
        setError('');
      }
    } else {
      setError('');
    }
  }, [startDate, endDate]);

  // 点击外部关闭
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleRangeSelect = (range: DateRange | undefined) => {
    if (range?.from) {
      onStartDateChange?.(formatDateString(range.from));
    }
    if (range?.to) {
      onEndDateChange?.(formatDateString(range.to));
    } else if (range?.from) {
      // 如果只选择了开始日期，结束日期也设为相同
      onEndDateChange?.(formatDateString(range.from));
    }
  };

  const selectedRange: DateRange | undefined = startDate && endDate ? {
    from: parseDate(startDate),
    to: parseDate(endDate),
  } : undefined;

  const displayText = startDate && endDate 
    ? `${startDate} → ${endDate}`
    : '选择日期范围';

  // 快捷选项处理函数
  const handleToday = () => {
    const today = getTodayString();
    onStartDateChange?.(today);
    onEndDateChange?.(today);
    setIsOpen(false);
  };

  const handleLastWeek = () => {
    const today = new Date();
    const weekAgo = subDays(today, 6); // 最近一周（包含今天，共7天）
    onStartDateChange?.(formatDateString(weekAgo));
    onEndDateChange?.(getTodayString());
    setIsOpen(false);
  };

  // 判断当前是否选中了"当日"
  const isTodaySelected = startDate === getTodayString() && endDate === getTodayString();
  
  // 判断当前是否选中了"最近一周"
  const isLastWeekSelected = (() => {
    if (!startDate || !endDate) return false;
    const today = getTodayString();
    const weekAgo = formatDateString(subDays(new Date(), 6));
    return startDate === weekAgo && endDate === today;
  })();

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-6 flex-wrap">
        <div className="flex items-center gap-3 theme-accent-bg px-4 py-2 rounded-2xl border theme-border theme-on-accent">
          <Calendar size={16} className="theme-on-accent" />
          <span className="text-[11px] font-black uppercase tracking-widest theme-on-accent">
            时间筛选
          </span>
        </div>
        
        {/* 快捷选项按钮 */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleToday}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              isTodaySelected
                ? 'theme-primary-bg theme-on-primary shadow-md'
                : 'theme-surface border theme-border theme-text theme-accent-text-hover'
            }`}
          >
            当日
          </button>
          <button
            onClick={handleLastWeek}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              isLastWeekSelected
                ? 'theme-primary-bg theme-on-primary shadow-md'
                : 'theme-surface border theme-border theme-text theme-accent-text-hover'
            }`}
          >
            最近一周
          </button>
        </div>
        
        <div className="relative" ref={popoverRef}>
          <button
            onClick={() => setIsOpen(!isOpen)}
            className="flex items-center gap-3 theme-surface border theme-border rounded-2xl px-5 py-3 text-sm font-medium theme-text outline-none transition-all shadow-sm hover:shadow-md cursor-pointer min-w-[280px] theme-accent-text-hover focus:ring-4 focus:ring-[var(--theme-primary)]/20 focus:border-[var(--theme-primary)]"
          >
            <Calendar size={16} className="theme-text-muted" />
            <span className="flex-1 text-left">{displayText}</span>
            {selectedRange && (
              <X 
                size={16} 
                className="text-slate-400 hover:text-red-500 transition-colors"
                onClick={(e) => {
                  e.stopPropagation();
                  const today = getTodayString();
                  onStartDateChange?.(today);
                  onEndDateChange?.(today);
                }}
              />
            )}
          </button>

          {isOpen && (
            <div className="absolute top-full left-0 mt-2 z-50 animate-in fade-in zoom-in-95 duration-200">
              <div className="theme-surface rounded-[1.5rem] shadow-2xl border theme-border p-4 day-picker-container">
                <DayPicker
                  mode="range"
                  selected={selectedRange}
                  onSelect={handleRangeSelect}
                  disabled={{ after: new Date() }}
                  locale={zhCN}
                  numberOfMonths={1}
                  classNames={{
                    root: 'day-picker-custom',
                    months: 'flex gap-4',
                    month: 'space-y-4',
                    month_caption: 'flex justify-center pt-1 relative items-center mb-4',
                    caption_label: 'text-sm font-bold theme-text',
                    nav: 'flex gap-1 absolute right-0',
                    button_previous: 'h-7 w-7 bg-transparent theme-surface-hover rounded-lg transition-colors',
                    button_next: 'h-7 w-7 bg-transparent theme-surface-hover rounded-lg transition-colors',
                    month_grid: 'border-collapse',
                    weekdays: 'flex',
                    weekday: 'theme-text-muted rounded-lg w-9 font-bold text-[10px] uppercase tracking-widest',
                    week: 'flex w-full mt-2',
                    day: 'h-9 w-9 text-center text-sm p-0 relative rounded-lg theme-surface-hover transition-colors',
                    day_button: 'h-9 w-9 p-0 font-medium rounded-lg theme-text transition-all',
                    selected: 'theme-primary-bg theme-on-primary theme-btn-primary font-bold',
                    range_start: 'theme-primary-bg theme-on-primary',
                    range_end: 'theme-primary-bg theme-on-primary',
                    range_middle: 'theme-accent-bg theme-accent-text',
                    today: 'theme-border border font-bold',
                    disabled: 'theme-text-muted opacity-50 cursor-not-allowed hover:bg-transparent',
                    outside: 'theme-text-muted',
                    hidden: 'invisible',
                  }}
                />
              </div>
            </div>
          )}
        </div>
      </div>
      
      {error && (
        <div className="flex items-center gap-2 ml-32 px-4 py-2 bg-red-50 border border-red-100 rounded-xl">
          <span className="text-xs font-bold text-red-600">⚠️ {error}</span>
        </div>
      )}
    </div>
  );
};
