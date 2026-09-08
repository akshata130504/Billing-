import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Upload } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { customerService } from '../../services/customerService';
import { meterService } from '../../services/meterService';
import type { CustomerOut } from '../../types/api';
import type { RecordedUsageEvent, UsageMeterOut } from '../../types/meters';
import { BATCH_CSV_COLUMNS, parseBatchInput } from './usageUtils';

interface BatchImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  meters: UsageMeterOut[];
  knownKeys: ReadonlySet<string>;
  onRecorded: (recorded: RecordedUsageEvent[]) => void;
}

const MAX_BATCH = 1000;

export function BatchImportModal({ isOpen, onClose, meters, knownKeys, onRecorded }: BatchImportModalProps) {
  const { showToast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState('');
  const [fileName, setFileName] = useState<string | null>(null);
  const [customers, setCustomers] = useState<CustomerOut[]>([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setText('');
    setFileName(null);
    let cancelled = false;
    customerService
      .list({ page_size: 100 })
      .then((res) => {
        if (!cancelled) setCustomers(res.items ?? []);
      })
      .catch(() => {
        // Labels only; the import itself does not depend on this lookup.
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const parsed = useMemo(() => parseBatchInput(text), [text]);
  const meterByCode = useMemo(() => new Map(meters.map((m) => [m.code, m])), [meters]);
  const meterById = useMemo(() => new Map(meters.map((m) => [m.id, m])), [meters]);
  const customerById = useMemo(() => new Map(customers.map((c) => [c.id, c])), [customers]);

  const unknownMeters = useMemo(() => {
    const seen = new Set<string>();
    parsed.events.forEach((ev) => {
      const code = ev.meter_code.toLowerCase();
      if (!meterByCode.has(code) && !meterById.has(ev.meter_code)) seen.add(ev.meter_code);
    });
    return [...seen];
  }, [parsed.events, meterByCode, meterById]);

  const tooMany = parsed.events.length > MAX_BATCH;
  const canSubmit =
    parsed.events.length > 0 && parsed.errors.length === 0 && unknownMeters.length === 0 && !tooMany && !submitting;

  const handleFile = (file: File | null) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      setText(typeof reader.result === 'string' ? reader.result : '');
      setFileName(file.name);
    };
    reader.onerror = () => showToast('error', 'Could not read file', file.name);
    reader.readAsText(file);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      setSubmitting(true);
      const sentByKey = new Map(parsed.events.map((ev) => [`${ev.meter_code.toLowerCase()}::${ev.idempotency_key}`, ev]));
      const results = await meterService.recordBatch({
        events: parsed.events.map((ev) => ({ ...ev, meter_code: ev.meter_code.toLowerCase() })),
      });
      const now = new Date().toISOString();
      const recorded: RecordedUsageEvent[] = results.map((event) => {
        const meter = meterById.get(event.meter_id);
        const customer = customerById.get(event.customer_id);
        const sent = meter ? sentByKey.get(`${meter.code}::${event.idempotency_key}`) : undefined;
        const replayed =
          knownKeys.has(event.idempotency_key) ||
          (sent !== undefined && Number(sent.quantity) !== Number(event.quantity));
        return {
          event,
          meter_code: meter?.code ?? event.meter_id,
          meter_name: meter?.name ?? 'Unknown meter',
          unit_name: meter?.unit_name ?? '',
          customer_label: customer ? `${customer.display_name} (${customer.customer_number})` : event.customer_id,
          subscription_label: event.subscription_id ? event.subscription_id.slice(0, 8) : null,
          replayed,
          recorded_at: now,
          source: 'batch',
        };
      });
      onRecorded(recorded);
      const replays = recorded.filter((r) => r.replayed).length;
      showToast(
        'success',
        `Imported ${results.length} usage event${results.length === 1 ? '' : 's'}`,
        replays ? `${replays} matched existing idempotency keys and were returned unchanged.` : undefined
      );
      onClose();
    } catch (err: any) {
      showToast('error', err?.message || 'Batch import failed', 'No events were recorded.');
    } finally {
      setSubmitting(false);
    }
  };

  const sampleCsv = `${BATCH_CSV_COLUMNS.join(',')}\n${meters[0]?.code ?? 'api_requests'},${
    customers[0]?.id ?? '<customer_id>'
  },125.5,evt-0001,,2026-09-08T10:00:00Z,"{""region"":""ap-south-1""}"`;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Batch Import Usage"
      description={`Paste CSV or JSON, or choose a file. Up to ${MAX_BATCH} events per import; the whole batch is accepted or rejected together.`}
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div className="text-xs text-slate-500">
            Columns: <span className="font-mono text-slate-700">{BATCH_CSV_COLUMNS.join(', ')}</span>.{' '}
            <span className="text-slate-400">Missing idempotency keys are generated.</span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.json,text/csv,application/json,text/plain"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              leadingIcon={<Upload className="w-3.5 h-3.5" />}
              onClick={() => fileRef.current?.click()}
            >
              Choose file
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setText(sampleCsv)}>
              Insert sample
            </Button>
          </div>
        </div>

        <textarea
          rows={10}
          spellCheck={false}
          placeholder={sampleCsv}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setFileName(null);
          }}
          className="w-full px-3 py-2 text-xs font-mono bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:outline-none"
        />

        {fileName && (
          <p className="text-xs text-slate-500 -mt-2">
            Loaded from <span className="font-medium text-slate-700">{fileName}</span>
          </p>
        )}

        {parsed.format !== 'empty' && (
          <div
            className={`rounded-lg border px-4 py-3 text-xs space-y-1.5 ${
              parsed.errors.length || unknownMeters.length || tooMany
                ? 'bg-amber-50 border-amber-200 text-amber-900'
                : 'bg-emerald-50 border-emerald-200 text-emerald-900'
            }`}
          >
            <div className="flex items-center gap-2 font-semibold">
              {parsed.errors.length || unknownMeters.length || tooMany ? (
                <AlertTriangle className="w-4 h-4" />
              ) : (
                <CheckCircle2 className="w-4 h-4" />
              )}
              {parsed.events.length} valid event{parsed.events.length === 1 ? '' : 's'} parsed as {parsed.format.toUpperCase()}
              {parsed.errors.length ? ` · ${parsed.errors.length} problem${parsed.errors.length === 1 ? '' : 's'}` : ''}
            </div>
            {tooMany && <div>Only {MAX_BATCH} events can be sent per batch. Split the file and import in parts.</div>}
            {unknownMeters.length > 0 && (
              <div>
                Unknown meter code{unknownMeters.length === 1 ? '' : 's'}:{' '}
                <span className="font-mono">{unknownMeters.join(', ')}</span>. Create the meter first.
              </div>
            )}
            {parsed.errors.length > 0 && (
              <ul className="list-disc pl-4 space-y-0.5 max-h-32 overflow-y-auto">
                {parsed.errors.slice(0, 25).map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
                {parsed.errors.length > 25 && <li>…and {parsed.errors.length - 25} more</li>}
              </ul>
            )}
            {/* Warnings are informational: the rows still import. */}
            {parsed.warnings.length > 0 && (
              <ul className="list-disc pl-4 space-y-0.5 text-amber-700">
                {parsed.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
          <Button variant="ghost" size="sm" type="button" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" type="submit" isLoading={submitting} disabled={!canSubmit}>
            Import {parsed.events.length > 0 ? `${parsed.events.length} event${parsed.events.length === 1 ? '' : 's'}` : 'events'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
