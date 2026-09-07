import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, CreditCard, Mail, XCircle } from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { publicService } from '../../services/publicService';
import { toApiError } from '../../services/apiClient';
import { queryKeys } from '../../hooks/queries';
import { SettingsSection } from './settingsShared';

const RAZORPAY_VARS = [
  { name: 'RAZORPAY_KEY_ID', description: 'Public key id. Shown to the browser on the payment page.' },
  { name: 'RAZORPAY_KEY_SECRET', description: 'Secret key used server-side to create orders, verify signatures and issue refunds.' },
  { name: 'RAZORPAY_WEBHOOK_SECRET', description: 'Used to verify the X-Razorpay-Signature header on incoming webhooks.' },
];

const SMTP_VARS = [
  { name: 'SMTP_HOST', description: 'Mail server host name.' },
  { name: 'SMTP_PORT', description: 'Mail server port (usually 587 for STARTTLS or 465 for TLS).' },
  { name: 'SMTP_USERNAME', description: 'Login user for the mail server.' },
  { name: 'SMTP_PASSWORD', description: 'Login password or app password.' },
  { name: 'SMTP_FROM_EMAIL', description: 'Sender address for invoices, reminders, invitations and password resets.' },
];

function StatusPill({ enabled }: { enabled: boolean }) {
  return (
    <Badge variant={enabled ? 'success' : 'neutral'} size="sm" dot>
      {enabled ? 'Configured' : 'Not configured'}
    </Badge>
  );
}

export function IntegrationsTab() {
  const integrations = useQuery({
    queryKey: queryKeys.meta.integrations(),
    queryFn: publicService.integrations,
  });

  if (integrations.isPending) return <LoadingState message="Checking integrations..." />;
  if (integrations.isError) {
    return (
      <ErrorState
        message={toApiError(integrations.error).message}
        onRetry={() => void integrations.refetch()}
      />
    );
  }

  const { razorpay, email } = integrations.data;

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs text-slate-600 leading-relaxed">
        Integrations are configured through environment variables on the API server, not from this
        screen. This page shows what the server currently reports.
      </div>

      <SettingsSection
        title="Razorpay"
        description="Lets customers pay invoices online from the public payment page and records gateway payments automatically."
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="p-2.5 rounded-xl bg-blue-50 text-brand-600 border border-blue-100 shrink-0">
              <CreditCard className="w-5 h-5" />
            </div>
            <div className="text-sm">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-900">Online payments</span>
                <StatusPill enabled={razorpay.enabled} />
              </div>
              <p className="text-xs text-slate-500 mt-1">
                {razorpay.enabled ? (
                  <>
                    Key id{' '}
                    <code className="font-mono bg-slate-100 border border-slate-200 rounded px-1.5 py-0.5">
                      {razorpay.key_id}
                    </code>
                  </>
                ) : (
                  'The "Pay online" option is hidden on invoice payment pages until the keys are set.'
                )}
              </p>
            </div>
          </div>
          {razorpay.enabled ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0" />
          ) : (
            <XCircle className="w-5 h-5 text-slate-300 shrink-0" />
          )}
        </div>
        <EnvTable rows={RAZORPAY_VARS} />
        <p className="text-xs text-slate-500">
          Webhook endpoint:{' '}
          <code className="font-mono bg-slate-100 border border-slate-200 rounded px-1.5 py-0.5">
            POST /api/v1/webhooks/razorpay
          </code>
        </p>
      </SettingsSection>

      <SettingsSection
        title="Email (SMTP)"
        description="Sends invoices, reminders, quote links, team invitations and password resets."
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="p-2.5 rounded-xl bg-amber-50 text-amber-600 border border-amber-100 shrink-0">
              <Mail className="w-5 h-5" />
            </div>
            <div className="text-sm">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-900">Outgoing email</span>
                <StatusPill enabled={email.enabled} />
              </div>
              <p className="text-xs text-slate-500 mt-1">
                {email.enabled
                  ? 'Emails are sent from the server.'
                  : 'Nothing is emailed. Invitation and password-reset links are shown on screen instead so you can share them manually.'}
              </p>
            </div>
          </div>
          {email.enabled ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0" />
          ) : (
            <XCircle className="w-5 h-5 text-slate-300 shrink-0" />
          )}
        </div>
        <EnvTable rows={SMTP_VARS} />
      </SettingsSection>
    </div>
  );
}

function EnvTable({ rows }: { rows: { name: string; description: string }[] }) {
  return (
    <div className="rounded-lg border border-slate-200 overflow-hidden">
      <table className="w-full text-xs">
        <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider text-[10px] font-semibold">
          <tr>
            <th className="text-left px-3 py-2">Environment variable</th>
            <th className="text-left px-3 py-2">Purpose</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => (
            <tr key={row.name}>
              <td className="px-3 py-2 font-mono text-slate-800 whitespace-nowrap">{row.name}</td>
              <td className="px-3 py-2 text-slate-600">{row.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
