import type { ReactNode } from 'react';
import { Activity, PlusCircle } from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import type { RecordedUsageEvent, UsageAggregateOut, UsageMeterOut } from '../../types/meters';
import { formatDate, formatDateTime, formatMoney, humanize } from '../../utils/format';
import { AGGREGATION_LABELS, formatQuantity, normaliseApiTimestamp } from './usageUtils';

interface MeterDetailModalProps {
  meter: UsageMeterOut | null;
  isOpen: boolean;
  onClose: () => void;
  /** Events recorded from this page during the current session, already filtered to this meter. */
  sessionEvents: RecordedUsageEvent[];
  /** Aggregates finalised from this page during the current session, already filtered to this meter. */
  sessionAggregates: UsageAggregateOut[];
  canRecord: boolean;
  onRecordUsage: (meter: UsageMeterOut) => void;
}

function Field({ label, children, mono = false }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</dt>
      <dd className={`mt-1 text-sm text-slate-900 ${mono ? 'font-mono text-xs break-all' : ''}`}>{children}</dd>
    </div>
  );
}

export function MeterDetailModal({
  meter,
  isOpen,
  onClose,
  sessionEvents,
  sessionAggregates,
  canRecord,
  onRecordUsage,
}: MeterDetailModalProps) {
  if (!meter) return null;
  const agg = AGGREGATION_LABELS[meter.aggregation_type];
  const sessionTotal = sessionEvents.reduce((sum, r) => sum + (Number(r.event.quantity) || 0), 0);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={meter.name}
      description={meter.description || `Meter ${meter.code}`}
      size="lg"
      footer={
        <div className="flex items-center justify-between gap-2 w-full">
          <span className="text-xs text-slate-400">Created {formatDate(normaliseApiTimestamp(meter.created_at))}</span>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              Close
            </Button>
            {canRecord && (
              <Button
                variant="primary"
                size="sm"
                leadingIcon={<PlusCircle className="w-3.5 h-3.5" />}
                onClick={() => onRecordUsage(meter)}
                disabled={!meter.is_active}
              >
                Record Usage
              </Button>
            )}
          </div>
        </div>
      }
    >
      <div className="space-y-6">
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-4 rounded-xl border border-slate-200 bg-slate-50/60 p-4">
          <Field label="Code" mono>
            {meter.code}
          </Field>
          <Field label="Unit">{meter.unit_name}</Field>
          <Field label="Status">
            <Badge variant={meter.is_active ? 'success' : 'neutral'} dot>
              {meter.is_active ? 'Active' : 'Inactive'}
            </Badge>
          </Field>
          <Field label="Aggregation">
            <Badge variant="info">{agg.label}</Badge>
            <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">{agg.hint}</p>
          </Field>
          <Field label="Meter ID" mono>
            {meter.id}
          </Field>
          <Field label="Pricing">
            <span className="text-slate-600 text-xs leading-relaxed">
              Rated at finalisation against the subscription's metered item. No plan is linked at the meter level.
            </span>
          </Field>
        </dl>

        <section>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-slate-900">Rated periods</h4>
            <span className="text-xs text-slate-400">Finalised in this session</span>
          </div>
          {sessionAggregates.length === 0 ? (
            <p className="text-xs text-slate-500 rounded-lg border border-dashed border-slate-300 px-4 py-3">
              The API does not expose stored aggregates per meter. Use <span className="font-medium">Finalize cycle</span>{' '}
              on the Usage page to rate a subscription's billing cycle; results appear here for the rest of your session.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full text-left text-sm text-slate-600">
                <thead className="bg-slate-50/80 text-[11px] font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                  <tr>
                    <th className="px-4 py-2.5">Period</th>
                    <th className="px-4 py-2.5">Subscription</th>
                    <th className="px-4 py-2.5 text-right">Quantity</th>
                    <th className="px-4 py-2.5 text-right">Rated</th>
                    <th className="px-4 py-2.5">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {sessionAggregates.map((a) => (
                    <tr key={a.id}>
                      <td className="px-4 py-2.5 whitespace-nowrap">
                        {formatDate(a.period_start)} – {formatDate(a.period_end)}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs">{a.subscription_id.slice(0, 8)}…</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">
                        {formatQuantity(a.total_quantity)} {meter.unit_name}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums font-medium text-slate-900">
                        {formatMoney(a.rated_amount)}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge variant={a.status === 'finalized' ? 'success' : 'warning'}>{humanize(a.status)}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-slate-900">Usage events</h4>
            <span className="text-xs text-slate-400">
              {sessionEvents.length ? `${sessionEvents.length} recorded this session · ${formatQuantity(sessionTotal)} ${meter.unit_name}` : 'Recorded in this session'}
            </span>
          </div>
          {sessionEvents.length === 0 ? (
            <div className="flex items-start gap-3 rounded-lg border border-dashed border-slate-300 px-4 py-3">
              <Activity className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
              <p className="text-xs text-slate-500 leading-relaxed">
                No events recorded for this meter in your current session. Historical events are stored server-side but the
                API has no listing endpoint yet, so only events you post from this page are shown.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full text-left text-sm text-slate-600">
                <thead className="bg-slate-50/80 text-[11px] font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                  <tr>
                    <th className="px-4 py-2.5">Timestamp</th>
                    <th className="px-4 py-2.5">Customer</th>
                    <th className="px-4 py-2.5 text-right">Quantity</th>
                    <th className="px-4 py-2.5">Key</th>
                    <th className="px-4 py-2.5">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {sessionEvents.map((r) => (
                    <tr key={r.event.id}>
                      <td className="px-4 py-2.5 whitespace-nowrap">{formatDateTime(normaliseApiTimestamp(r.event.timestamp))}</td>
                      <td className="px-4 py-2.5">{r.customer_label}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums font-medium text-slate-900">
                        {formatQuantity(r.event.quantity)}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-slate-500 max-w-[10rem] truncate" title={r.event.idempotency_key}>
                        {r.event.idempotency_key}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge variant={r.replayed ? 'warning' : r.event.status === 'accepted' ? 'success' : 'danger'}>
                          {r.replayed ? 'Duplicate' : humanize(r.event.status)}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </Modal>
  );
}
