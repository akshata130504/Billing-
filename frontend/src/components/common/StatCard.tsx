import React from 'react';
import { cn } from '../../utils/cn';
import { TrendingUp, TrendingDown } from 'lucide-react';

export interface StatCardProps {
  title: string;
  value: string | number;
  change?: string;
  isPositive?: boolean;
  comparisonText?: string;
  icon?: React.ReactNode;
  className?: string;
}

export function StatCard({
  title,
  value,
  change,
  isPositive = true,
  comparisonText,
  icon,
  className,
}: StatCardProps) {
  return (
    <div
      className={cn(
        'bg-white p-5 rounded-xl border border-slate-200/90 shadow-card hover:shadow-elevated transition-all flex flex-col justify-between',
        className
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium text-slate-500 tracking-wide uppercase">
          {title}
        </span>
        {icon && (
          <div className="p-2 rounded-lg bg-blue-50/80 text-brand-600 border border-blue-100">
            {icon}
          </div>
        )}
      </div>

      <div className="mt-3">
        <div className="text-2xl font-bold text-slate-900 tracking-tight tabular-nums">
          {value}
        </div>

        {(change || comparisonText) && (
          <div className="mt-2 flex items-center gap-1.5 text-xs">
            {change && (
              <span
                className={cn(
                  'inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md font-semibold text-[11px]',
                  isPositive
                    ? 'bg-emerald-50 text-emerald-700'
                    : 'bg-rose-50 text-rose-700'
                )}
              >
                {isPositive ? (
                  <TrendingUp className="w-3 h-3" />
                ) : (
                  <TrendingDown className="w-3 h-3" />
                )}
                {change}
              </span>
            )}
            {comparisonText && (
              <span className="text-slate-500 text-[11px] truncate">
                {comparisonText}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
