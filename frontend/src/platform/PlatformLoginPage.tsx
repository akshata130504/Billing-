import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/common/Button';
import { Input } from '../components/common/Input';
import { PlatformApiError, platformApi } from './platformApi';

/**
 * Rooman platform staff sign-in: email + password.
 * Separate from the tenant /login page; not linked from the tenant app.
 */
export function PlatformLoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await platformApi.login(email.trim(), password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'Sign-in failed. Please try again.');
      setPassword('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900 px-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Rooman Billing</p>
        <h1 className="mt-1 text-xl font-bold text-slate-900">Platform staff sign-in</h1>
        <p className="mt-1 text-sm text-slate-500">For Rooman platform staff only. Customers sign in at the main login page.</p>

        {error && (
          <div role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        <form className="mt-5 space-y-4" onSubmit={submit}>
          <Input label="Email" type="email" autoComplete="username" value={email}
            onChange={(e) => setEmail(e.target.value)} required />
          <Input label="Password" type="password" autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} required />
          <Button type="submit" className="w-full" isLoading={busy}>Sign In</Button>
        </form>
      </div>
    </div>
  );
}

export default PlatformLoginPage;
