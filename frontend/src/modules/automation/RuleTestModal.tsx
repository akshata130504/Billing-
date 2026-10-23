import React, { useEffect, useState } from 'react';
import { CheckCircle2, XCircle, FlaskConical } from 'lucide-react';
import { Modal } from '../../components/common/Modal';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { useToast } from '../../components/common/Toast';
import { automationService } from '../../services/automationService';
import type { AutomationRule, AutomationRuleTestResult } from '../../types/automation';
import { describeConditions, sampleEventFromConditions, TRIGGER_EVENT_LABELS } from './constants';

export interface RuleTestModalProps {
  isOpen: boolean;
  onClose: () => void;
  rule: AutomationRule | null;
}

export function RuleTestModal({ isOpen, onClose, rule }: RuleTestModalProps) {
  const { showToast } = useToast();
  const [payload, setPayload] = useState('{}');
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<AutomationRuleTestResult | null>(null);

  useEffect(() => {
    if (!isOpen || !rule) return;
    setResult(null);
    setJsonError(null);
    setPayload(JSON.stringify(sampleEventFromConditions(rule.conditions), null, 2));
  }, [isOpen, rule]);

  const handleRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rule) return;
    let eventData: Record<string, unknown>;
    try {
      const parsed: unknown = JSON.parse(payload || '{}');
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        throw new Error('Payload must be a JSON object.');
      }
      eventData = parsed as Record<string, unknown>;
      setJsonError(null);
    } catch (err: any) {
      setJsonError(err?.message || 'Invalid JSON.');
      return;
    }
    setRunning(true);
    try {
      const res = await automationService.testRule(rule.id, { event_data: eventData });
      setResult(res);
      showToast(
        res.matches ? 'success' : 'info',
        res.matches ? 'Conditions matched' : 'Conditions did not match',
        res.matches
          ? `${res.would_execute_actions.length} action(s) would run.`
          : 'No actions would run for this payload.'
      );
    } catch (err: any) {
      showToast('error', 'Test failed', err?.message);
    } finally {
      setRunning(false);
    }
  };

  const conditionSummary = rule ? describeConditions(rule.conditions) : [];

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={rule ? `Test rule: ${rule.name}` : 'Test rule'}
      description="Dry-runs the rule's conditions against a sample event. No actions are executed."
      size="lg"
    >
      {rule && (
        <form onSubmit={handleRun} className="space-y-5">
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-600 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-slate-700">Trigger:</span>
              <Badge variant="info" size="sm">
                {rule.module}
              </Badge>
              <span>{TRIGGER_EVENT_LABELS[rule.trigger_event]}</span>
            </div>
            <div className="flex flex-wrap items-start gap-2">
              <span className="font-semibold text-slate-700">Conditions:</span>
              {conditionSummary.length === 0 ? (
                <span className="italic text-slate-500">none — matches every event</span>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {conditionSummary.map((c) => (
                    <code key={c} className="rounded bg-white border border-slate-200 px-1.5 py-0.5 font-mono text-[11px]">
                      {c}
                    </code>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1.5">Sample event payload (JSON)</label>
            <textarea
              rows={8}
              value={payload}
              onChange={(e) => setPayload(e.target.value)}
              spellCheck={false}
              className={`block w-full rounded-lg border bg-white px-3 py-2 font-mono text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 ${
                jsonError ? 'border-rose-400 focus:border-rose-400' : 'border-slate-300 focus:border-brand-500'
              }`}
            />
            {jsonError ? (
              <p className="mt-1 text-xs text-rose-600">{jsonError}</p>
            ) : (
              <p className="mt-1 text-xs text-slate-400">
                Keys should mirror the fields your conditions reference (pre-filled from the rule).
              </p>
            )}
          </div>

          {result && (
            <div
              className={`rounded-xl border px-4 py-3 ${
                result.matches ? 'border-emerald-200 bg-emerald-50' : 'border-slate-200 bg-slate-50'
              }`}
            >
              <div className="flex items-center gap-2">
                {result.matches ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                ) : (
                  <XCircle className="w-5 h-5 text-slate-400" />
                )}
                <span className={`text-sm font-semibold ${result.matches ? 'text-emerald-800' : 'text-slate-700'}`}>
                  {result.matches ? 'Rule matches this payload' : 'Rule does not match this payload'}
                </span>
              </div>
              <div className="mt-2 text-xs text-slate-600">
                {result.matches ? (
                  result.would_execute_actions.length === 0 ? (
                    <span className="italic">The rule has no actions to execute.</span>
                  ) : (
                    <>
                      <span className="font-medium text-slate-700">Would execute, in order:</span>
                      <ol className="mt-1 list-decimal list-inside space-y-0.5">
                        {result.would_execute_actions.map((a, i) => (
                          <li key={`${a}-${i}`}>{a}</li>
                        ))}
                      </ol>
                    </>
                  )
                ) : (
                  <span>Adjust the payload or the rule's conditions and run the test again.</span>
                )}
              </div>
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
            <Button type="button" variant="ghost" size="sm" onClick={onClose}>
              Close
            </Button>
            <Button type="submit" variant="primary" size="sm" isLoading={running} leadingIcon={<FlaskConical className="w-4 h-4" />}>
              Run test
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
