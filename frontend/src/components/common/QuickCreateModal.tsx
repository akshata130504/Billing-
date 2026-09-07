import { useNavigate } from 'react-router-dom';
import { Modal } from './Modal';
import { Receipt, FileText, UserPlus, PackagePlus, CreditCard, Repeat } from 'lucide-react';
import { useToast } from './Toast';

export interface QuickCreateModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function QuickCreateModal({ isOpen, onClose }: QuickCreateModalProps) {
  const navigate = useNavigate();
  const { showToast } = useToast();

  const options = [
    {
      title: 'Create Invoice',
      description: 'Issue a one-off or recurring invoice to an account',
      icon: Receipt,
      color: 'bg-emerald-50 text-emerald-600 border-emerald-100',
      path: '/revenue/invoices',
      phase: 'Phase 2',
    },
    {
      title: 'Create Quote',
      description: 'Draft pricing terms, discounts, and line-item estimates',
      icon: FileText,
      color: 'bg-blue-50 text-brand-600 border-blue-100',
      path: '/revenue/quotes',
      phase: 'Phase 2',
    },
    {
      title: 'Add Customer',
      description: 'Onboard a new client organization or contact',
      icon: UserPlus,
      color: 'bg-purple-50 text-purple-600 border-purple-100',
      path: '/customers',
      phase: 'Phase 1',
    },
    {
      title: 'Add Product',
      description: 'Register a plan, one-time item, or metered add-on',
      icon: PackagePlus,
      color: 'bg-amber-50 text-amber-600 border-amber-100',
      path: '/catalog',
      phase: 'Phase 1',
    },
    {
      title: 'Record Payment',
      description: 'Log manual, bank wire, or offline payment reconciliation',
      icon: CreditCard,
      color: 'bg-teal-50 text-teal-600 border-teal-100',
      path: '/revenue/payments',
      phase: 'Phase 3',
    },
    {
      title: 'Create Subscription',
      description: 'Enroll customer in recurring billing cycle with trial terms',
      icon: Repeat,
      color: 'bg-indigo-50 text-indigo-600 border-indigo-100',
      path: '/subscriptions/all',
      phase: 'Phase 4',
    },
  ];

  const handleSelect = (item: (typeof options)[0]) => {
    onClose();
    showToast('info', item.title, `Feature workflow scheduled in ${item.phase}.`);
    navigate(item.path);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Quick Create"
      description="Select an entity to initiate a new record or billing action."
      size="lg"
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 py-1">
        {options.map((opt) => {
          const Icon = opt.icon;
          return (
            <button
              key={opt.title}
              type="button"
              onClick={() => handleSelect(opt)}
              className="flex items-start gap-3.5 p-3.5 rounded-xl border border-slate-200/90 hover:border-brand-500 hover:bg-brand-50/30 transition-all text-left group cursor-pointer"
            >
              <div
                className={`p-2.5 rounded-xl border shrink-0 transition-transform group-hover:scale-105 ${opt.color}`}
              >
                <Icon className="w-5 h-5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-slate-900 group-hover:text-brand-700">
                    {opt.title}
                  </h4>
                  <span className="text-[10px] text-slate-400 font-medium">
                    {opt.phase}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 mt-1 leading-snug">
                  {opt.description}
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </Modal>
  );
}
