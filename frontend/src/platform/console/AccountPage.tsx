import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../../components/common/Button';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { PageHeader } from '../../components/common/PageHeader';
import { PlatformApiError, PlatformSessionInfo, ROLE_LABELS, platformApi } from '../platformApi';
import { useConsole } from './ConsoleContext';
import { Field, Section, formatDateTime } from './ui';

/** The signed-in staff member's own profile and sessions. */
export function AccountPage() {
  const { me } = useConsole();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<PlatformSessionInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setSessions((await platformApi.sessions()).sessions);
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'Could not load your sessions.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (fn: () => Promise<unknown>, leave = false) => {
    setError(null);
    try {
      await fn();
      if (leave) navigate('/login', { replace: true });
      else await load();
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'That did not work. Please try again.');
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader title="My account" subtitle="Your platform identity and signed-in sessions." />
      <Section title="Profile">
        <dl className="grid gap-4 sm:grid-cols-2">
          <Field label="Name">{me.staff.full_name}</Field>
          <Field label="Email">{me.staff.email}</Field>
          <Field label="Platform role">{ROLE_LABELS[me.staff.role] ?? me.staff.role}</Field>
          <Field label="This session ends">{formatDateTime(me.session_expires_at)}</Field>
        </dl>
      </Section>
      <Section
        title="Your sessions"
        actions={<Button size="sm" variant="danger" onClick={() => void act(() => platformApi.logoutAll(), true)}>Sign out everywhere</Button>}
      >
        {error && <ErrorState message={error} onRetry={() => void load()} />}
        {!sessions && !error && <LoadingState message="Loading sessions..." />}
        {sessions && (
          <ul className="divide-y divide-slate-100">
            {sessions.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
                <div className="min-w-0">
                  <p className="font-medium text-slate-800">{s.user_agent || 'Unknown device'}{s.current ? ' (this session)' : ''}</p>
                  <p className="text-xs text-slate-500">{s.ip_address ?? 'unknown IP'} · started {formatDateTime(s.created_at)} · last used {formatDateTime(s.last_used_at)}</p>
                </div>
                {!s.current && (
                  <Button size="sm" variant="outline" onClick={() => void act(() => platformApi.revokeSession(s.id))}>Revoke</Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
