import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Lock } from 'lucide-react';
import { cn } from '../../../utils/cn';
import { toApiError } from '../../../services/apiClient';

// ---------------------------------------------------------------------------
// Data-loading hook shared by every tab
// ---------------------------------------------------------------------------

export interface Resource<T> {
  items: T[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
  /** Optimistically replace one item in place (used after edit / retry). */
  replace: (item: T, match: (a: T, b: T) => boolean) => void;
}

export function useResource<T>(fetcher: () => Promise<T[]>): Resource<T> {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetcher();
      if (mounted.current) setItems(data);
    } catch (err: any) {
      if (mounted.current) setError(toApiError(err).message || 'Failed to load data');
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [fetcher]);

  useEffect(() => {
    mounted.current = true;
    void reload();
    return () => {
      mounted.current = false;
    };
  }, [reload]);

  const replace = useCallback((item: T, match: (a: T, b: T) => boolean) => {
    setItems((prev) => prev.map((existing) => (match(existing, item) ? item : existing)));
  }, []);

  return { items, loading, error, reload, replace };
}

// ---------------------------------------------------------------------------
// Small form primitives that the common library does not provide
// ---------------------------------------------------------------------------

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  helperText?: string;
  error?: string;
  /** Monospace "code" styling for CSS / markup. */
  code?: boolean;
}

export function Textarea({ label, helperText, error, code, className, id: customId, ...props }: TextareaProps) {
  const generatedId = useId();
  const id = customId || generatedId;
  return (
    <div className="w-full">
      {label && (
        <label htmlFor={id} className="block text-xs font-medium text-slate-700 mb-1.5">
          {label}
          {props.required && <span className="text-rose-500 ml-0.5">*</span>}
        </label>
      )}
      <textarea
        id={id}
        className={cn(
          'block w-full rounded-lg border bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 transition-colors shadow-subtle',
          'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500',
          'disabled:bg-slate-50 disabled:text-slate-400 disabled:cursor-not-allowed',
          error ? 'border-rose-300 focus:ring-rose-500 focus:border-rose-500' : 'border-slate-300 hover:border-slate-400',
          code && 'font-mono text-xs leading-relaxed bg-slate-50 text-slate-800',
          className
        )}
        {...props}
      />
      {error ? (
        <p className="mt-1 text-xs text-rose-600 font-medium">{error}</p>
      ) : helperText ? (
        <p className="mt-1 text-xs text-slate-500">{helperText}</p>
      ) : null}
    </div>
  );
}

export function Toggle({
  label,
  description,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label
      className={cn(
        'flex items-start justify-between gap-4 rounded-lg border border-slate-200 px-3.5 py-2.5 cursor-pointer select-none',
        disabled && 'opacity-60 cursor-not-allowed'
      )}
    >
      <span className="min-w-0">
        <span className="block text-sm font-medium text-slate-800">{label}</span>
        {description && <span className="block text-xs text-slate-500 mt-0.5">{description}</span>}
      </span>
      <span className="relative inline-flex shrink-0 mt-0.5">
        <input
          type="checkbox"
          className="peer sr-only"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="w-9 h-5 rounded-full bg-slate-300 peer-checked:bg-brand-600 transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-brand-500 peer-focus-visible:ring-offset-2" />
        <span className="absolute left-0.5 top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform peer-checked:translate-x-4" />
      </span>
    </label>
  );
}

export function ColorField({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
}) {
  const id = useId();
  const isHex = /^#[0-9a-fA-F]{6}$/.test(value);
  return (
    <div className="w-full">
      <label htmlFor={id} className="block text-xs font-medium text-slate-700 mb-1.5">
        {label}
      </label>
      <div className="flex items-center gap-2">
        <span
          className="relative w-9 h-9 rounded-lg border border-slate-300 overflow-hidden shrink-0 shadow-subtle"
          style={{ backgroundColor: isHex ? value : '#e2e8f0' }}
        >
          <input
            type="color"
            aria-label={`${label} picker`}
            value={isHex ? value : '#000000'}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value.toUpperCase())}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
          />
        </span>
        <input
          id={id}
          type="text"
          value={value}
          disabled={disabled}
          maxLength={20}
          onChange={(e) => onChange(e.target.value)}
          className={cn(
            'block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-mono uppercase text-slate-900 shadow-subtle',
            'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500',
            'disabled:bg-slate-50 disabled:text-slate-400 disabled:cursor-not-allowed'
          )}
        />
      </div>
    </div>
  );
}

/** Read-only notice shown to users whose role cannot change a resource. */
export function ReadOnlyNotice({ what }: { what: string }) {
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs text-slate-600">
      <Lock className="w-3.5 h-3.5 mt-0.5 shrink-0 text-slate-400" />
      <span>
        Your role can view but not change {what}. Ask an owner or admin of this organization to make changes.
      </span>
    </div>
  );
}

/** Section title + description + optional right-hand actions, used at the top of every tab. */
export function TabHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-base font-semibold text-slate-900">{title}</h2>
        <p className="text-xs sm:text-sm text-slate-500 mt-0.5 max-w-2xl leading-relaxed">{description}</p>
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0 flex-wrap">{actions}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Value helpers
// ---------------------------------------------------------------------------

export const str = (value: string | null | undefined): string => value ?? '';
export const nullable = (value: string): string | null => (value.trim() === '' ? null : value.trim());

/** Mirrors backend resolve_number_tokens: {YYYY}, {MM}, {DD} → today's date. */
export function resolveNumberTokens(value: string | null | undefined, now: Date = new Date()): string {
  if (!value) return '';
  const yyyy = String(now.getFullYear());
  const mm = String(now.getMonth() + 1).padStart(2, '0');
  const dd = String(now.getDate()).padStart(2, '0');
  return value
    .replace(/\{YYYY\}/g, yyyy)
    .replace(/\{MM\}/g, mm)
    .replace(/\{DD\}/g, dd);
}

export function formatSeriesNumber(prefix: string, number: number, padding: number, suffix?: string | null): string {
  return `${resolveNumberTokens(prefix)}${String(number).padStart(padding, '0')}${resolveNumberTokens(suffix)}`;
}
