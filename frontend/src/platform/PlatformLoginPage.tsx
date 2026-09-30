import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/common/Button';
import { Input } from '../components/common/Input';
import { PlatformApiError, platformApi } from './platformApi';

/**
 * Rooman platform staff sign-in: email + password, then a mandatory authenticator code.
 * Separate from the tenant /login page; not linked from the tenant app.
 */
export function PlatformLoginPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<'password' | 'code'>('password');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [challenge, setChallenge] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submitPassword = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = await platformApi.login(email.trim(), password);
      setChallenge(result.challenge_token);
      setPassword('');
      setStep('code');
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'Sign-in failed. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const submitCode = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await platformApi.verifyTwoFactor(challenge, code.trim());
      navigate('/platform', { replace: true });
    } catch (err) {
      const message = err instanceof PlatformApiError ? err.message : 'Verification failed. Please try again.';
      setError(message);
      setCode('');
      if (err instanceof PlatformApiError && /expired|invalid or has expired/i.test(message)) {
        setStep('password');
        setChallenge('');
      }
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

        {step === 'password' ? (
          <form className="mt-5 space-y-4" onSubmit={submitPassword}>
            <Input label="Email" type="email" autoComplete="username" value={email}
              onChange={(e) => setEmail(e.target.value)} required />
            <Input label="Password" type="password" autoComplete="current-password" value={password}
              onChange={(e) => setPassword(e.target.value)} required />
            <Button type="submit" className="w-full" isLoading={busy}>Continue</Button>
          </form>
        ) : (
          <form className="mt-5 space-y-4" onSubmit={submitCode}>
            <Input label="Authenticator code" inputMode="numeric" autoComplete="one-time-code" maxLength={10}
              value={code} onChange={(e) => setCode(e.target.value)} required autoFocus />
            <Button type="submit" className="w-full" isLoading={busy}>Verify and sign in</Button>
            <button type="button" className="w-full text-sm text-slate-500 hover:text-slate-700"
              onClick={() => { setStep('password'); setChallenge(''); setCode(''); }}>
              Start over
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

export default PlatformLoginPage;
