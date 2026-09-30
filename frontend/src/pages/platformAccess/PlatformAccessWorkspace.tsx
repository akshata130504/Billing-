import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { LogOut, ShieldAlert } from 'lucide-react';
import { API_BASE_URL } from '../../services/apiClient';
import { SCOPE_LABELS } from '../../services/platformAccessService';

/**
 * Read-only workspace for Rooman platform staff under an approved access grant (design section 17).
 *
 * The platform console opens this page and hands over a short-lived grant token with
 * window.postMessage - accepted ONLY from the configured platform origin and only from the window
 * that opened this one. The token lives in memory only (never localStorage, never a URL), is never
 * mixed with a tenant user's own session, and every request is re-validated by the server against
 * the grant (scope, expiry, revocation). A fixed banner shows the organization, scopes, time left
 * and an Exit button that ends the grant token immediately.
 */
export const PLATFORM_ORIGIN: string =
  import.meta.env.VITE_PLATFORM_APP_ORIGIN || (import.meta.env.DEV ? 'http://platform.localhost:5174' : '');

export const GRANT_MESSAGE = 'rooman-platform-grant';
export const READY_MESSAGE = 'rooman-platform-ready';

interface Session {
  grant_id: string;
  organization_name: string;
  staff_name: string;
  scopes: string[];
  areas: string[];
  expires_at: string | null;
  is_emergency: boolean;
  ticket_ref: string;
}

type Column = { key: string; label: string };
interface Area {
  scope: string;
  key: string;
  label: string;
  path: string;
  columns: Column[];
}

const AREAS: Area[] = [
  { scope: 'READ_METADATA', key: 'organization', label: 'Organization', path: '/organization', columns: [
    { key: 'name', label: 'Name' }, { key: 'legal_name', label: 'Legal name' }, { key: 'email', label: 'Email' }, { key: 'country', label: 'Country' }] },
  { scope: 'READ_CUSTOMERS', key: 'customers', label: 'Customers', path: '/customers?page_size=50', columns: [
    { key: 'customer_number', label: 'Number' }, { key: 'display_name', label: 'Name' }, { key: 'email', label: 'Email' }, { key: 'status', label: 'Status' }] },
  { scope: 'READ_QUOTES', key: 'quotes', label: 'Quotes', path: '/quotes?page_size=50', columns: [
    { key: 'quote_number', label: 'Number' }, { key: 'title', label: 'Title' }, { key: 'status', label: 'Status' }, { key: 'total_amount', label: 'Total' }] },
  { scope: 'READ_INVOICES', key: 'invoices', label: 'Invoices', path: '/invoices?page_size=50', columns: [
    { key: 'invoice_number', label: 'Number' }, { key: 'status', label: 'Status' }, { key: 'due_date', label: 'Due' }, { key: 'total_amount', label: 'Total' }] },
  { scope: 'READ_PAYMENTS', key: 'payments', label: 'Payments', path: '/payments?page_size=50', columns: [
    { key: 'payment_number', label: 'Number' }, { key: 'status', label: 'Status' }, { key: 'method', label: 'Method' }, { key: 'amount', label: 'Amount' }] },
  { scope: 'READ_SUBSCRIPTIONS', key: 'subscriptions', label: 'Subscriptions', path: '/subscriptions?page_size=50', columns: [
    { key: 'subscription_number', label: 'Number' }, { key: 'status', label: 'Status' }, { key: 'billing_frequency', label: 'Frequency' }, { key: 'total_amount', label: 'Total' }] },
  { scope: 'READ_AUDIT', key: 'audit', label: 'Audit log', path: '/audit-logs?page_size=50', columns: [
    { key: 'created_at', label: 'When' }, { key: 'actor_label', label: 'Actor' }, { key: 'action', label: 'Action' }, { key: 'entity_label', label: 'Record' }] },
  { scope: 'READ_CONFIG', key: 'templates', label: 'Templates', path: '/templates', columns: [
    { key: 'name', label: 'Name' }, { key: 'document_type', label: 'Type' }, { key: 'layout_type', label: 'Layout' }] },
];

function cell(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'object') return (value as { display_name?: string; name?: string }).display_name ?? (value as { name?: string }).name ?? '...';
  return String(value);
}

function remaining(expiresAt: string | null, now: number): string {
  if (!expiresAt) return '';
  const secs = Math.max(0, Math.floor((new Date(expiresAt).getTime() - now) / 1000));
  return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`;
}

export function PlatformAccessWorkspace() {
  const tokenRef = useRef<string | null>(null); // memory only
  const [session, setSession] = useState<Session | null>(null);
  const [state, setState] = useState<'waiting' | 'active' | 'ended' | 'refused'>('waiting');
  const [message, setMessage] = useState<string | null>(null);
  const [area, setArea] = useState<Area | null>(null);
  const [rows, setRows] = useState<Record<string, unknown>[] | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const call = useCallback(async (path: string, init: RequestInit = {}) => {
    const token = tokenRef.current;
    if (!token) throw new Error('No platform access token');
    const res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: 'omit',
      headers: { Accept: 'application/json', Authorization: `Bearer ${token}`, ...(init.headers || {}) },
    });
    if (res.status === 401) {
      tokenRef.current = null;
      setState('ended');
      setMessage('This platform access has ended or expired. Enter again from the platform console if the grant is still open.');
      throw new Error('ended');
    }
    if (res.status === 204) return null;
    const body = await res.json().catch(() => null);
    if (!res.ok) throw new Error(body?.error?.message || 'Request refused.');
    return body;
  }, []);

  const start = useCallback(async (token: string) => {
    tokenRef.current = token;
    try {
      const info = (await call('/platform-access/session')) as Session;
      setSession(info);
      setState('active');
      const first = AREAS.find((a) => info.scopes.includes(a.scope) && a.scope !== 'READ_METADATA') ?? AREAS[0];
      setArea(first);
    } catch {
      /* call() already moved to "ended" */
    }
  }, [call]);

  useEffect(() => {
    if (!PLATFORM_ORIGIN || !window.opener) {
      setState('refused');
      setMessage('Open this page from the Rooman platform console ("Enter tenant").');
      return;
    }
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== PLATFORM_ORIGIN || event.source !== window.opener) return;
      const data = event.data as { type?: string; token?: string } | null;
      if (data?.type !== GRANT_MESSAGE || typeof data.token !== 'string' || tokenRef.current) return;
      void start(data.token);
    };
    window.addEventListener('message', onMessage);
    window.opener.postMessage({ type: READY_MESSAGE }, PLATFORM_ORIGIN);
    return () => window.removeEventListener('message', onMessage);
  }, [start]);

  useEffect(() => {
    if (state !== 'active') return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [state]);

  useEffect(() => {
    if (state !== 'active' || !area) return;
    setRows(null);
    call(area.path)
      .then((body) => {
        const list = Array.isArray(body) ? body : body && Array.isArray(body.items) ? body.items : body ? [body] : [];
        setRows(list as Record<string, unknown>[]);
      })
      .catch((err: Error) => {
        if (err.message !== 'ended') setRows([]);
        if (err.message !== 'ended') setMessage(err.message);
      });
  }, [area, state, call]);

  const exit = async () => {
    try {
      await call('/platform-access/exit', { method: 'POST' });
    } catch {
      /* already ended */
    }
    tokenRef.current = null;
    setSession(null);
    setState('ended');
    setMessage('You have exited the tenant. The access token is no longer valid.');
  };

  const areas = useMemo(() => AREAS.filter((a) => session?.scopes.includes(a.scope)), [session]);

  if (state !== 'active' || !session) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
        <div className="max-w-md rounded-xl border border-slate-200 bg-white p-6 text-center shadow-sm">
          <ShieldAlert className="mx-auto h-8 w-8 text-rose-600" aria-hidden="true" />
          <h1 className="mt-3 text-lg font-semibold text-slate-900">Rooman platform access</h1>
          <p className="mt-2 text-sm text-slate-600">
            {state === 'waiting' ? 'Waiting for the platform console...' : message}
          </p>
          {state !== 'waiting' && <button type="button" onClick={() => window.close()} className="mt-4 text-sm font-medium text-brand-600 underline">Close this tab</button>}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div role="status" className="sticky top-0 z-40 flex flex-wrap items-center gap-x-4 gap-y-1 bg-rose-700 px-4 py-2 text-sm text-white shadow">
        <ShieldAlert className="h-4 w-4" aria-hidden="true" />
        <strong>{session.is_emergency ? 'EMERGENCY platform access' : 'Platform access'}:</strong>
        <span>{session.organization_name}</span>
        <span className="opacity-90">as {session.staff_name}</span>
        <span className="opacity-90">read-only: {session.areas.join(', ')}</span>
        <span className="font-mono">time left {remaining(session.expires_at, now)}</span>
        <span className="opacity-90">ticket {session.ticket_ref}</span>
        <button type="button" onClick={() => void exit()}
          className="ml-auto inline-flex items-center gap-1 rounded-md bg-white px-3 py-1 font-semibold text-rose-700 hover:bg-rose-50">
          <LogOut className="h-4 w-4" aria-hidden="true" /> Exit tenant
        </button>
      </div>
      <div className="mx-auto max-w-6xl p-4 sm:p-6">
        <nav aria-label="Granted areas" className="flex flex-wrap gap-2">
          {areas.map((a) => (
            <button key={a.key} type="button" onClick={() => setArea(a)} aria-current={area?.key === a.key ? 'page' : undefined}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium ${area?.key === a.key ? 'bg-slate-900 text-white' : 'bg-white text-slate-700 ring-1 ring-slate-200 hover:bg-slate-100'}`}>
              {a.label}
            </button>
          ))}
        </nav>
        <p className="mt-2 text-xs text-slate-500">
          Read-only. Every view is recorded in this organization&apos;s audit log and the Rooman platform audit.
          {' '}{SCOPE_LABELS.READ_PAYMENTS && 'Payment methods show masked details only.'}
        </p>
        {area && (
          <section className="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <h2 className="border-b border-slate-100 px-4 py-3 text-sm font-semibold text-slate-900">{area.label}</h2>
            {rows === null ? (
              <p className="p-4 text-sm text-slate-500">Loading...</p>
            ) : rows.length === 0 ? (
              <p className="p-4 text-sm text-slate-500">Nothing to show.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <tr>{area.columns.map((c) => <th key={c.key} className="px-4 py-2">{c.label}</th>)}</tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {rows.map((row, i) => (
                      <tr key={String(row.id ?? i)}>{area.columns.map((c) => <td key={c.key} className="px-4 py-2 text-slate-700">{cell(row[c.key])}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}

export default PlatformAccessWorkspace;
