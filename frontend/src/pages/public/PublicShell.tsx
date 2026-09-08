import type { ReactNode } from 'react';
import { RoomanLogo } from '../../components/common/RoomanLogo';
import { LoadingState } from '../../components/common/LoadingState';
import { cn } from '../../utils/cn';

interface PublicShellProps {
  children: ReactNode;
  /** `lg` for full documents (invoice/quote), `md` for message-only states. */
  width?: 'md' | 'lg';
}

/** Centred, branded page frame shared by the hosted (no-auth) pages. */
export function PublicShell({ children, width = 'lg' }: PublicShellProps) {
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center px-4 py-8 sm:py-12">
      <div className={cn('w-full flex-1 flex flex-col', width === 'lg' ? 'max-w-3xl' : 'max-w-md')}>
        {children}
        <footer className="mt-8 flex flex-col items-center gap-2 text-xs text-slate-400">
          <div className="flex items-center gap-1.5">
            <span>Powered by</span>
            <RoomanLogo variant="brand" size="sm" showBillingBadge />
          </div>
        </footer>
      </div>
    </div>
  );
}

/** White card used for the document body. */
export function PublicCard({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn('bg-white rounded-2xl border border-slate-200/90 shadow-card', className)}>
      {children}
    </div>
  );
}

/** Full-page loading state (logo + spinner). */
export function PublicLoading({ message }: { message: string }) {
  return (
    <PublicShell width="md">
      <div className="flex justify-center mb-6">
        <RoomanLogo variant="brand" size="lg" showBillingBadge />
      </div>
      <PublicCard className="px-6 py-10">
        <LoadingState message={message} />
      </PublicCard>
    </PublicShell>
  );
}

interface PublicMessageProps {
  icon: ReactNode;
  title: string;
  message: ReactNode;
  action?: ReactNode;
  tone?: 'neutral' | 'danger';
}

/** Full-page message (invalid link, unexpected error). */
export function PublicMessage({ icon, title, message, action, tone = 'neutral' }: PublicMessageProps) {
  return (
    <PublicShell width="md">
      <div className="flex justify-center mb-6">
        <RoomanLogo variant="brand" size="lg" showBillingBadge />
      </div>
      <PublicCard className="px-6 py-8 sm:px-8 text-center">
        <div
          className={cn(
            'mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full',
            tone === 'danger' ? 'bg-rose-50 text-rose-600' : 'bg-slate-100 text-slate-500'
          )}
        >
          {icon}
        </div>
        <h1 className="text-lg font-bold text-slate-900 tracking-tight">{title}</h1>
        <div className="mt-2 text-sm text-slate-500 leading-relaxed">{message}</div>
        {action && <div className="mt-6 flex justify-center">{action}</div>}
      </PublicCard>
    </PublicShell>
  );
}
