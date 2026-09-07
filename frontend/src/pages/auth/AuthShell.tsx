import type { ReactNode } from 'react';
import { RoomanLogo } from '../../components/common/RoomanLogo';

export interface AuthShellProps {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  /** Links rendered under the card (e.g. "Don't have an account?"). */
  footer?: ReactNode;
  width?: 'sm' | 'md';
}

/** Centred, branded card used by every public auth screen. */
export function AuthShell({ title, subtitle, children, footer, width = 'sm' }: AuthShellProps) {
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center px-4 py-10">
      <div className={width === 'md' ? 'w-full max-w-lg' : 'w-full max-w-md'}>
        <div className="flex justify-center mb-6">
          <RoomanLogo variant="brand" size="lg" showBillingBadge />
        </div>

        <div className="bg-white rounded-2xl border border-slate-200/90 shadow-card px-6 py-7 sm:px-8">
          <div className="mb-6">
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">{title}</h1>
            {subtitle && <p className="mt-1 text-sm text-slate-500 leading-relaxed">{subtitle}</p>}
          </div>
          {children}
        </div>

        {footer && <div className="mt-5 text-center text-sm text-slate-500">{footer}</div>}
      </div>
    </div>
  );
}

/** Inline banner for a top-level (non-field) API error. */
export function FormErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs text-rose-700 font-medium"
    >
      {message}
    </div>
  );
}
