/**
 * "Create Admin": a Platform Administrator provisions an organization's tenant Admin after its
 * subscription is approved. The organization and the role are fixed (read-only); the server creates a
 * tenant user (never platform staff) and emails them a set-password invitation. No password or
 * invitation link is ever shown here. Asks for the current password when the server wants a step-up.
 */
import { FormEvent, useEffect, useState } from 'react';
import { CheckCircle2, MailWarning } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Modal } from '../../components/common/Modal';
import { consoleApi, type ProvisionedAdmin } from '../consoleApi';
import { PlatformApiError } from '../platformApi';
import { StepUpDialog } from './StepUpDialog';
import { formatDateTime } from './ui';

export function ProvisionAdminDialog({ isOpen, organizationId, organizationName, onClose, onProvisioned }: {
  isOpen: boolean;
  organizationId: string;
  organizationName: string;
  onClose: () => void;
  onProvisioned?: (admin: ProvisionedAdmin) => void;
}) {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [stepUp, setStepUp] = useState(false);
  const [result, setResult] = useState<ProvisionedAdmin | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setFullName('');
    setEmail('');
    setError(null);
    setBusy(false);
    setStepUp(false);
    setResult(null);
  }, [isOpen]);

  const attempt = async () => {
    try {
      const created = await consoleApi.provisionTenantAdmin(organizationId, { full_name: fullName.trim(), email: email.trim() });
      setResult(created);
      setStepUp(false);
      onProvisioned?.(created);
    } catch (err) {
      if (err instanceof PlatformApiError && err.code === 'STEP_UP_REQUIRED') {
        setStepUp(true);
        return;
      }
      setStepUp(false);
      setError(err instanceof PlatformApiError ? err.message : 'The Admin could not be created. Please try again.');
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    await attempt();
    setBusy(false);
  };

  return (
    <>
      <Modal isOpen={isOpen && !stepUp} onClose={() => !busy && onClose()} title="Create Admin"
        description="The Admin is a user of this organization's billing workspace, not Rooman platform staff." size="md">
        {result ? (
          <div className="space-y-4" role="status">
            <div className="flex gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <div>
                <p className="font-semibold">Admin created for {result.organization_name}</p>
                <p>{result.full_name} ({result.email}) · Role: Admin · Status: Invited</p>
                <p>Invitation valid until {formatDateTime(result.invite_expires_at)}.</p>
              </div>
            </div>
            {result.email_delivered ? (
              <p className="text-sm text-slate-600">The invitation email was sent. They set their own password from the link.</p>
            ) : (
              <p className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                <MailWarning className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                The invitation email could not be delivered. Create the Admin again with the same email to resend it.
              </p>
            )}
            <div className="flex justify-end">
              <Button size="sm" onClick={onClose}>Done</Button>
            </div>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4" aria-label="Create Admin">
            <Input label="Admin name" value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={200} required autoFocus />
            <Input label="Admin email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={255} required />
            <Input label="Organization" value={organizationName} readOnly disabled />
            <Input label="Role" value="Admin" readOnly disabled />
            <p className="text-xs text-slate-500">
              They receive an email invitation and set their own password. No password is created or shown here.
            </p>
            {error && <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={onClose} disabled={busy}>Cancel</Button>
              <Button type="submit" size="sm" isLoading={busy} disabled={!fullName.trim() || !email.trim()}>Create Admin</Button>
            </div>
          </form>
        )}
      </Modal>
      <StepUpDialog
        isOpen={isOpen && stepUp}
        title="Confirm to create the Admin"
        onClose={() => setStepUp(false)}
        onVerified={attempt}
      />
    </>
  );
}
