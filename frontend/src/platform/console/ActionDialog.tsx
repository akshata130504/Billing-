import { FormEvent, useEffect, useState } from 'react';
import { AlertTriangle, KeyRound } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Modal } from '../../components/common/Modal';
import type { ReasonBody } from '../consoleApi';
import { PlatformApiError, platformApi } from '../platformApi';

export interface ActionDialogProps<T> {
  isOpen: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  danger?: boolean;
  requireTicket?: boolean;
  /** Extra consequences shown to the operator before they confirm. */
  notes?: string[];
  onClose: () => void;
  onSubmit: (body: ReasonBody) => Promise<T>;
  onDone: (result: T) => void;
}

const MIN_REASON = 10;

/**
 * Confirmation for a lifecycle or staff action: reason (always) and ticket (where the design
 * requires one). If the server answers STEP_UP_REQUIRED, the dialog asks for a fresh
 * authenticator code, confirms it with /platform/auth/step-up and retries the same action once.
 */
export function ActionDialog<T>({
  isOpen, title, description, confirmLabel, danger = false, requireTicket = false, notes = [],
  onClose, onSubmit, onDone,
}: ActionDialogProps<T>) {
  const [reason, setReason] = useState('');
  const [ticket, setTicket] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState<'details' | 'code'>('details');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setReason('');
    setTicket('');
    setCode('');
    setStep('details');
    setError(null);
    setBusy(false);
  }, [isOpen]);

  const body = (): ReasonBody => ({ reason: reason.trim(), ...(ticket.trim() ? { ticket_ref: ticket.trim() } : {}) });
  const valid = reason.trim().length >= MIN_REASON && (!requireTicket || ticket.trim().length >= 2);

  const attempt = async () => {
    try {
      onDone(await onSubmit(body()));
    } catch (err) {
      if (err instanceof PlatformApiError && err.code === 'STEP_UP_REQUIRED') {
        setStep('code');
        setError(null);
        return;
      }
      setError(err instanceof PlatformApiError ? err.message : 'That did not work. Please try again.');
    }
  };

  const submitDetails = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError(null);
    await attempt();
    setBusy(false);
  };

  const submitCode = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await platformApi.stepUp(code.trim());
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'The code could not be verified.');
      setCode('');
      setBusy(false);
      return;
    }
    await attempt();
    setBusy(false);
  };

  return (
    <Modal isOpen={isOpen} onClose={() => !busy && onClose()} title={title} description={description} size="md">
      {step === 'details' ? (
        <form onSubmit={submitDetails} className="space-y-4" aria-label={title}>
          {notes.length > 0 && (
            <ul className={`space-y-1 rounded-lg border px-4 py-3 text-sm ${danger ? 'border-rose-200 bg-rose-50 text-rose-800' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
              {notes.map((note) => (
                <li key={note} className="flex gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                  <span>{note}</span>
                </li>
              ))}
            </ul>
          )}
          <div>
            <label htmlFor="action-reason" className="block text-sm font-medium text-slate-700">
              Reason <span className="text-rose-600">*</span>
            </label>
            <textarea
              id="action-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              maxLength={500}
              required
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
              placeholder="Why is this being done? (at least 10 characters)"
            />
          </div>
          <Input
            label={requireTicket ? 'Ticket reference' : 'Ticket reference (optional)'}
            value={ticket}
            onChange={(e) => setTicket(e.target.value)}
            maxLength={100}
            required={requireTicket}
            placeholder="e.g. SUP-1234"
          />
          {error && <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose} disabled={busy}>Cancel</Button>
            <Button type="submit" variant={danger ? 'danger' : 'primary'} size="sm" isLoading={busy} disabled={!valid}>
              {confirmLabel}
            </Button>
          </div>
        </form>
      ) : (
        <form onSubmit={submitCode} className="space-y-4" aria-label="Confirm with authenticator code">
          <div className="flex gap-3 rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-slate-700">
            <KeyRound className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" aria-hidden="true" />
            <span>This is a sensitive action. Enter a fresh code from your authenticator app to continue.</span>
          </div>
          <Input
            label="Authenticator code"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            autoFocus
          />
          {error && <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose} disabled={busy}>Cancel</Button>
            <Button type="submit" variant={danger ? 'danger' : 'primary'} size="sm" isLoading={busy} disabled={code.length !== 6}>
              Verify and {confirmLabel.toLowerCase()}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
