import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { cn } from '../../utils/cn';

export interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Small uppercase label rendered above the title (e.g. section name). */
  eyebrow?: ReactNode;
  /** Right-hand slot for buttons. */
  actions?: ReactNode;
  /** Optional back link rendered above the title. */
  backTo?: { to: string; label: string };
  className?: string;
}

export function PageHeader({ title, subtitle, eyebrow, actions, backTo, className }: PageHeaderProps) {
  return (
    <div className={cn('flex flex-col sm:flex-row sm:items-start justify-between gap-4', className)}>
      <div className="min-w-0">
        {backTo && (
          <Link
            to={backTo.to}
            className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-brand-600 mb-2 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            {backTo.label}
          </Link>
        )}
        {eyebrow && (
          <p className="text-[11px] font-semibold uppercase tracking-wider text-brand-600 mb-1">{eyebrow}</p>
        )}
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight truncate">{title}</h1>
        {subtitle && (
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl leading-relaxed">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0 flex-wrap">{actions}</div>}
    </div>
  );
}
