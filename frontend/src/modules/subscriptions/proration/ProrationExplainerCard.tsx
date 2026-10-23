import { CalendarRange, Calculator, ReceiptText, Clock } from 'lucide-react';
import { usePageSpec } from '../../../appUi/usePageSpec';

const STEPS = [
  {
    icon: CalendarRange,
    title: 'Calendar days',
    body: 'The current billing period is measured in calendar days. The change date is clamped to that period, so days remaining = period end − change date.',
  },
  {
    icon: Calculator,
    title: 'Credit and charge',
    body: 'Unused credit = old rate × days remaining ÷ total days. Remaining charge = new rate × days remaining ÷ total days. Rate is unit price × quantity, rounded to the paise.',
  },
  {
    icon: ReceiptText,
    title: 'Net adjustment',
    body: 'Net = charge − credit. A positive net raises a prorated invoice; the credit is issued as a credit note and automatically offset against that invoice.',
  },
  {
    icon: Clock,
    title: 'End of term',
    body: 'Changes scheduled for end of term are recorded now and applied on the period end date with no mid-cycle proration. They can be cancelled until then.',
  },
];

export function ProrationExplainerCard() {
  const ui = usePageSpec('proration');
  return (
    <div className="bg-white rounded-xl border border-slate-200/90 shadow-card p-5">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div {...ui.edit('explainer')}>
          <h2 className="text-sm font-semibold text-slate-900 tracking-tight">{ui.text('explainer', 'title')}</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {ui.text('explainer', 'description')}
          </p>
        </div>
        <code className="hidden md:block shrink-0 text-[11px] font-mono text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5">
          net = (new − old) × days remaining ÷ total days
        </code>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {STEPS.map((step) => {
          const Icon = step.icon;
          return (
            <div key={step.title} className="flex gap-3">
              <div className="p-2 rounded-lg bg-blue-50/80 text-brand-600 border border-blue-100 h-fit shrink-0">
                <Icon className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <div className="text-xs font-semibold text-slate-800">{step.title}</div>
                <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{step.body}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
