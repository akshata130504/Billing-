import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BookOpen,
  ChevronDown,
  CloudCog,
  CreditCard,
  Database,
  Mail,
  Users,
  Webhook,
} from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { publicService } from '../../services/publicService';
import { toApiError } from '../../services/apiClient';
import { queryKeys } from '../../hooks/queries';
import { cn } from '../../utils/cn';

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

function StatusBadge({ connected }: { connected: boolean }) {
  return (
    <Badge variant={connected ? 'success' : 'neutral'} size="sm" dot>
      {connected ? 'Connected' : 'Not connected'}
    </Badge>
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

/** Card for a real, working integration whose status comes from the API. */
function IntegrationCard({
  icon,
  iconClass,
  name,
  description,
  connected,
  detail,
  envRows,
}: {
  icon: React.ReactNode;
  iconClass: string;
  name: string;
  description: string;
  connected: boolean;
  detail: React.ReactNode;
  envRows: { name: string; description: string }[];
}) {
  const [showConfig, setShowConfig] = useState(false);

  return (
    <div className="bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden">
      <div className="p-4 flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className={cn('p-2.5 rounded-xl border shrink-0', iconClass)}>{icon}</div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-sm text-slate-900">{name}</span>
              <StatusBadge connected={connected} />
            </div>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">{description}</p>
            <div className="text-xs text-slate-500 mt-1.5">{detail}</div>
          </div>
        </div>
      </div>
      <button
        type="button"
        onClick={() => setShowConfig((v) => !v)}
        className="w-full flex items-center justify-between gap-2 px-4 py-2 text-xs font-medium text-slate-600 bg-slate-50/70 border-t border-slate-100 hover:bg-slate-100 transition-colors"
      >
        Show configuration details
        <ChevronDown className={cn('w-3.5 h-3.5 transition-transform', showConfig && 'rotate-180')} />
      </button>
      {showConfig && (
        <div className="p-4 pt-3 border-t border-slate-100 space-y-2">
          <EnvTable rows={envRows} />
        </div>
      )}
    </div>
  );
}

/** Card for a category that has no real backend integration in this app at all. */
function ComingSoonCard({
  icon,
  name,
  description,
}: {
  icon: React.ReactNode;
  name: string;
  description: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200/90 shadow-card p-4 flex items-start justify-between gap-3 opacity-90">
      <div className="flex items-start gap-3 min-w-0">
        <div className="p-2.5 rounded-xl border bg-slate-50 text-slate-400 border-slate-200 shrink-0">{icon}</div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm text-slate-900">{name}</span>
            <StatusBadge connected={false} />
          </div>
          <p className="text-xs text-slate-500 mt-1 leading-relaxed">{description}</p>
        </div>
      </div>
      <div className="shrink-0" title="Coming soon — no provider connected yet">
        <Button variant="outline" size="sm" disabled>
          Configure
        </Button>
      </div>
    </div>
  );
}

function CategoryHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{children}</h3>;
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
    <div className="space-y-6">
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs text-slate-600 leading-relaxed">
        Integrations are configured through environment variables on the API server, not from this
        screen. This page shows what the server currently reports.
      </div>

      <div className="space-y-3">
        <CategoryHeading>Payments</CategoryHeading>
        <IntegrationCard
          icon={<CreditCard className="w-5 h-5" />}
          iconClass="bg-blue-50 text-brand-600 border-blue-100"
          name="Razorpay"
          description="Lets customers pay invoices online from the public payment page and records gateway payments automatically."
          connected={razorpay.enabled}
          detail={
            razorpay.enabled ? (
              <>
                Key id{' '}
                <code className="font-mono bg-slate-100 border border-slate-200 rounded px-1.5 py-0.5">
                  {razorpay.key_id}
                </code>
                . Secrets are never shown here.
              </>
            ) : (
              'The "Pay online" option is hidden on invoice payment pages until the keys are set.'
            )
          }
          envRows={RAZORPAY_VARS}
        />
      </div>

      <div className="space-y-3">
        <CategoryHeading>Email</CategoryHeading>
        <IntegrationCard
          icon={<Mail className="w-5 h-5" />}
          iconClass="bg-amber-50 text-amber-600 border-amber-100"
          name="Email (SMTP)"
          description="Sends invoices, reminders, quote links, team invitations and password resets."
          connected={email.enabled}
          detail={
            email.enabled
              ? 'Emails are sent from the server.'
              : 'Nothing is emailed. Invitation and password-reset links are shown on screen instead so you can share them manually.'
          }
          envRows={SMTP_VARS}
        />
      </div>

      <div className="space-y-3">
        <CategoryHeading>Accounting</CategoryHeading>
        <ComingSoonCard
          icon={<BookOpen className="w-5 h-5" />}
          name="Accounting sync"
          description="Sync invoices and payments with an external accounting ledger."
        />
      </div>

      <div className="space-y-3">
        <CategoryHeading>CRM</CategoryHeading>
        <ComingSoonCard
          icon={<Users className="w-5 h-5" />}
          name="CRM sync"
          description="Keep customer and deal records in sync with a CRM."
        />
      </div>

      <div className="space-y-3">
        <CategoryHeading>Storage</CategoryHeading>
        <ComingSoonCard
          icon={<Database className="w-5 h-5" />}
          name="Cloud storage"
          description="Back up generated documents to an external object store."
        />
      </div>

      <div className="space-y-3">
        <CategoryHeading>Webhooks / API</CategoryHeading>
        <ComingSoonCard
          icon={<Webhook className="w-5 h-5" />}
          name="Outbound webhooks"
          description="Notify external systems when billing events happen in this app."
        />
      </div>

      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs text-slate-500 flex items-start gap-2">
        <CloudCog className="w-3.5 h-3.5 mt-0.5 shrink-0 text-slate-400" />
        Accounting, CRM, storage and webhook connectors are not implemented yet — the cards above are
        placeholders and do not accept any configuration.
      </div>
    </div>
  );
}

export default IntegrationsTab;
