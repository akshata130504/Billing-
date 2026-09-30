import { FormEvent, useEffect, useState } from 'react';
import { KeyRound } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Modal } from '../../components/common/Modal';
import { PlatformApiError, platformApi } from '../platformApi';

/** Asks for a fresh authenticator code (step-up) and calls onVerified once it is accepted. */
export function StepUpDialog({ isOpen, title, onClose, onVerified }: {
  isOpen: boolean;
  title: string;
  onClose: () => void;
  onVerified: () => void | Promise<void>;
}) {
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setCode('');
      setError(null);
    }
  }, [isOpen]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await platformApi.stepUp(code.trim());
      await onVerified();
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'The code could not be verified.');
      setCode('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={() => !busy && onClose()} title={title} size="sm">
      <form onSubmit={submit} className="space-y-4" aria-label="Confirm with authenticator code">
        <div className="flex gap-3 rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-slate-700">
          <KeyRound className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" aria-hidden="true" />
          <span>Enter a fresh code from your authenticator app to continue.</span>
        </div>
        <Input label="Authenticator code" value={code} inputMode="numeric" autoComplete="one-time-code" autoFocus required
          onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} />
        {error && <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" size="sm" isLoading={busy} disabled={code.length !== 6}>Verify</Button>
        </div>
      </form>
    </Modal>
  );
}
