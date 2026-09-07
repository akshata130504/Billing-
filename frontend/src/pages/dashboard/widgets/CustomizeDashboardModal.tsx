import { Modal } from '../../../components/common/Modal';
import { Button } from '../../../components/common/Button';
import { WidgetVisibilityState } from '../../../types';
import { Check } from 'lucide-react';

export interface CustomizeDashboardModalProps {
  isOpen: boolean;
  onClose: () => void;
  visibility: WidgetVisibilityState;
  onToggle: (key: keyof WidgetVisibilityState) => void;
  onReset: () => void;
}

const widgetDescriptions: Record<keyof WidgetVisibilityState, { title: string; desc: string }> = {
  revenueIntelligence: {
    title: 'Revenue Intelligence',
    desc: 'MRR, ARR, growth rate, revenue forecast, and spline trend analysis',
  },
  actionCenter: {
    title: 'Action Center',
    desc: 'Actionable queue for overdue invoices, failed payments, expiring trials, and pending quotes',
  },
  billingPipeline: {
    title: 'Billing Pipeline',
    desc: 'Lifecycle stage tracking from Quote to Invoice, Payment, and Paid with counts and monetary value',
  },
  customerHealth: {
    title: 'Customer Health',
    desc: 'Distribution of Healthy, Needs Attention, At-Risk, and Churned accounts',
  },
  paymentRecovery: {
    title: 'Payment Recovery',
    desc: 'Smart dunning metrics: failed payments, retry schedules, and recovered revenues',
  },
  recentTransactions: {
    title: 'Recent Transactions',
    desc: 'Ledger table of recent payment gateway settlements and payment methods',
  },
  activityTimeline: {
    title: 'Recent Activity Timeline',
    desc: 'Categorized stream of billing, customer, payment, and system automation events',
  },
};

export function CustomizeDashboardModal({
  isOpen,
  onClose,
  visibility,
  onToggle,
  onReset,
}: CustomizeDashboardModalProps) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Customize Dashboard Layout"
      description="Show or hide widgets to tailor your Rooman Billing workspace."
      size="md"
      footer={
        <div className="flex items-center justify-between w-full">
          <Button variant="ghost" size="sm" onClick={onReset}>
            Reset to Default
          </Button>
          <Button variant="primary" size="sm" onClick={onClose}>
            Done
          </Button>
        </div>
      }
    >
      <div className="divide-y divide-slate-100 py-1">
        {(Object.keys(visibility) as (keyof WidgetVisibilityState)[]).map((key) => {
          const isEnabled = visibility[key];
          const info = widgetDescriptions[key];

          return (
            <div
              key={key}
              className="py-3 flex items-start justify-between gap-4 cursor-pointer"
              onClick={() => onToggle(key)}
            >
              <div className="min-w-0 flex-1">
                <h4 className="text-xs font-bold text-slate-900">{info.title}</h4>
                <p className="text-[11px] text-slate-500 mt-0.5 leading-snug">
                  {info.desc}
                </p>
              </div>

              {/* Toggle Switch */}
              <button
                type="button"
                role="switch"
                aria-checked={isEnabled}
                onClick={(e) => {
                  e.stopPropagation();
                  onToggle(key);
                }}
                className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  isEnabled ? 'bg-brand-600' : 'bg-slate-200'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
                    isEnabled ? 'translate-x-4' : 'translate-x-0'
                  }`}
                >
                  {isEnabled && <Check className="w-3 h-3 text-brand-600 p-0.5" />}
                </span>
              </button>
            </div>
          );
        })}
      </div>
    </Modal>
  );
}
