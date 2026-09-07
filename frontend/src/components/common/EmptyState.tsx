import React from 'react';
import { cn } from '../../utils/cn';
import { FolderOpen } from 'lucide-react';

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'w-full py-12 px-6 flex flex-col items-center justify-center text-center bg-white rounded-xl border border-dashed border-slate-300',
        className
      )}
    >
      <div className="p-3 rounded-full bg-slate-100 text-slate-500 mb-3.5">
        {icon || <FolderOpen className="w-6 h-6 stroke-1" />}
      </div>
      <h4 className="text-sm font-semibold text-slate-900">{title}</h4>
      <p className="mt-1 text-xs text-slate-500 max-w-sm leading-relaxed">
        {description}
      </p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
