/**
 * An organization's plan in the console: modules and user seats. Every role reads it; only a
 * Platform Administrator changes it (reason + step-up), and only for an active or suspended
 * organization - trials are decided through their subscription request.
 */
import { useCallback, useEffect, useState } from 'react';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { BASE_MODULE_KEYS, OPTIONAL_MODULES, dependents, moduleLabel, withRequirements } from '../../entitlements';
import { consoleApi, type OrganizationEntitlements, type OrgStatus } from '../consoleApi';
import { PlatformApiError } from '../platformApi';
import { ActionDialog } from './ActionDialog';
import { ADMIN, useConsole } from './ConsoleContext';
import { Field, Section, formatDateTime } from './ui';

export function EntitlementsPanel({ organizationId, status }: { organizationId: string; status: OrgStatus }) {
  const { hasRole } = useConsole();
  const [data, setData] = useState<OrganizationEntitlements | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await consoleApi.entitlements(organizationId));
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'Could not load the plan.');
    }
  }, [organizationId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Trials are decided through the organization's subscription request, not edited here.
  const editable = hasRole(ADMIN) && (status === 'active' || status === 'suspended') && data?.module_access !== 'trial';
  const unrestricted = data?.module_access === 'unrestricted';
  const trial = data?.module_access === 'trial';

  return (
    <Section
      title="Plan"
      description="Modules and user seats. The API enforces them."
      actions={editable && data ? <Button size="sm" variant="outline" onClick={() => setEditing(true)}>Change plan</Button> : undefined}
    >
      {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
      {data && (
        <dl className="grid grid-cols-2 gap-3">
          <Field label="Modules">
            {unrestricted
              ? 'All modules (organization predates plans)'
              : trial
                ? data.trial_ends_at
                  ? `Free trial: every module until ${formatDateTime(data.trial_ends_at)}, then a subscription request decides`
                  : 'Free trial starts when the organization is approved'
                : [...BASE_MODULE_KEYS, ...data.modules].map(moduleLabel).join(', ')}
          </Field>
          <Field label="User seats">
            {data.seats_used} in use{data.seat_limit !== null ? ` of ${data.seat_limit}` : ' (no limit)'}
          </Field>
        </dl>
      )}
      {editing && data && (
        <EditPlan organizationId={organizationId} current={data} onClose={() => setEditing(false)} onSaved={(next) => { setData(next); setEditing(false); }} />
      )}
    </Section>
  );
}

function EditPlan({ organizationId, current, onClose, onSaved }: {
  organizationId: string;
  current: OrganizationEntitlements;
  onClose: () => void;
  onSaved: (next: OrganizationEntitlements) => void;
}) {
  const initial = current.module_access === 'unrestricted' ? OPTIONAL_MODULES.map((m) => m.key) : current.modules;
  const [modules, setModules] = useState<string[]>(withRequirements(initial));
  const [seats, setSeats] = useState(current.seat_limit === null ? '' : String(current.seat_limit));
  const [confirming, setConfirming] = useState(false);
  const seatLimit = seats.trim() === '' ? null : Number(seats);
  const seatsValid = seatLimit === null || (Number.isInteger(seatLimit) && seatLimit >= Math.max(1, current.seats_used) && seatLimit <= 10000);

  const toggle = (key: string) =>
    setModules((prev) => {
      if (prev.includes(key)) {
        const drop = new Set([key, ...dependents(key)]);
        return prev.filter((k) => !drop.has(k));
      }
      return withRequirements([...prev, key]);
    });

  return (
    <>
      <Modal isOpen={!confirming} onClose={onClose} title="Change plan" description="Removing a module hides it and refuses its API immediately; no data is deleted." size="lg">
        <div className="space-y-5">
          <fieldset>
            <legend className="text-sm font-semibold text-slate-800">Additional modules</legend>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {OPTIONAL_MODULES.map((m) => (
                <label key={m.key} className="flex items-start gap-2 rounded-lg border border-slate-200 p-2 text-sm">
                  <input type="checkbox" className="mt-0.5" checked={modules.includes(m.key)} onChange={() => toggle(m.key)} />
                  {m.label}
                </label>
              ))}
            </div>
          </fieldset>
          <div>
            <label htmlFor="plan-seats" className="text-sm font-semibold text-slate-800">User seat limit</label>
            <input
              id="plan-seats"
              type="number"
              min={Math.max(1, current.seats_used)}
              max={10000}
              value={seats}
              placeholder="No limit"
              onChange={(e) => setSeats(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm sm:max-w-xs"
            />
            <p className="mt-1 text-xs text-slate-500">{current.seats_used} in use (members and pending invitations). Leave empty for no limit.</p>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
            <Button size="sm" disabled={!seatsValid} onClick={() => setConfirming(true)}>Continue</Button>
          </div>
        </div>
      </Modal>
      <ActionDialog
        isOpen={confirming}
        title="Change plan"
        description="Recorded in the platform audit and the organization's audit log."
        confirmLabel="Save plan"
        notes={[`Modules: ${[...BASE_MODULE_KEYS, ...modules].map(moduleLabel).join(', ')}`, `User seats: ${seatLimit ?? 'no limit'}`]}
        onClose={() => setConfirming(false)}
        onSubmit={(body) => consoleApi.updateEntitlements(organizationId, { modules, seat_limit: seatLimit, reason: body.reason })}
        onDone={onSaved}
      />
    </>
  );
}
