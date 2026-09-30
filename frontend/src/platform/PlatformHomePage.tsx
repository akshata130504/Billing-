import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/common/Button';
import {
  PlatformApiError,
  PlatformMe,
  PlatformSessionInfo,
  ROLE_LABELS,
  platformApi,
} from './platformApi';
import { loadPlatformMe } from './platformSession';

/**
 * Minimal authenticated platform shell (phase 2): proves the platform session works and lets staff
 * see and end their own sessions. No tenant data is shown or reachable from here.
 */
export function PlatformHomePage() {
  const navigate = useNavigate();
  const [me, setMe] = useState<PlatformMe | null>(null);
  const [sessions, setSessions] = useState<PlatformSessionInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      const current = await loadPlatformMe();
      if (!current) {
        navigate('/login', { replace: true });
        return;
      }
      setMe(current);
      setSessions((await platformApi.sessions()).sessions);
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'Could not load your platform session.');
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (fn: () => Promise<unknown>, thenLeave = false) => {
    setError(null);
    try {
      await fn();
      if (thenLeave) navigate('/login', { replace: true });
      else await load();
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'That did not work. Please try again.');
    }
  };

  if (loading) return <div className="p-8 text-sm text-slate-500">Loading platform session…</div>;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="flex items-center justify-between bg-slate-900 px-6 py-3 text-white">
        <span className="font-semibold">Rooman Platform</span>
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" onClick={() => act(() => platformApi.logout(), true)}>Sign out</Button>
        </div>
      </header>
      <main className="mx-auto max-w-3xl space-y-6 p-6">
        {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
        {me && (
          <section className="rounded-xl border border-slate-200 bg-white p-5">
            <h1 className="text-lg font-bold text-slate-900">{me.staff.full_name}</h1>
            <p className="text-sm text-slate-600">{me.staff.email}</p>
            <p className="mt-2 inline-block rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
              {ROLE_LABELS[me.staff.role] ?? me.staff.role}
            </p>
            <p className="mt-3 text-xs text-slate-500">
              Platform administration features arrive in later phases. This console has no access to tenant data.
            </p>
          </section>
        )}
        <section className="rounded-xl border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-slate-900">Your sessions</h2>
            <Button size="sm" variant="danger" onClick={() => act(() => platformApi.logoutAll(), true)}>
              Sign out everywhere
            </Button>
          </div>
          <ul className="mt-3 divide-y divide-slate-100">
            {sessions.map((s) => (
              <li key={s.id} className="flex items-center justify-between py-2 text-sm">
                <div>
                  <div className="text-slate-800">{s.user_agent || 'Unknown device'}{s.current ? ' (this session)' : ''}</div>
                  <div className="text-xs text-slate-500">
                    {s.ip_address || 'unknown IP'} · signed in {new Date(s.created_at).toLocaleString()}
                  </div>
                </div>
                {!s.current && (
                  <Button size="sm" variant="outline" onClick={() => act(() => platformApi.revokeSession(s.id))}>
                    Revoke
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}

export default PlatformHomePage;
