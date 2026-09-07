import { useNavigate } from 'react-router-dom';
import { Modal } from './Modal';
import { Receipt, FileText, UserPlus, PackagePlus, CreditCard, Repeat } from 'lucide-react';
import type { MemberRole } from '../../types/api';
import { useAuth } from '../../hooks/useAuth';

export interface QuickCreateModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface QuickCreateOption {
  title: string;
  description: string;
  icon: typeof Receipt;
  color: string;
  path: string;
  /** Minimum role needed to create this entity. */
  minRole: MemberRole;
}

const OPTIONS: QuickCreateOption[] = [
  {
    title: 'Create invoice',
    description: 'Bill a customer for products or services',
    icon: Receipt,
    color: 'bg-emerald-50 text-emerald-600 border-emerald-100',
    path: '/invoices/new',
    minRole: 'finance',
  },
  {
    title: 'Create quote',
    description: 'Draft pricing for a customer to accept',
    icon: FileText,
    color: 'bg-blue-50 text-brand-600 border-blue-100',
    path: '/quotes/new',
    minRole: 'finance',
  },
  {
    title: 'Add customer',
    description: 'Register a new customer account',
    icon: UserPlus,
    color: 'bg-purple-50 text-purple-600 border-purple-100',
    path: '/customers/new',
    minRole: 'finance',
  },
  {
    title: 'Add product',
    description: 'Add a product or plan to the catalog',
    icon: PackagePlus,
    color: 'bg-amber-50 text-amber-600 border-amber-100',
    path: '/catalog?new=product',
    minRole: 'finance',
  },
  {
    title: 'Record payment',
    description: 'Log a bank transfer, UPI, cash or cheque payment',
    icon: CreditCard,
    color: 'bg-teal-50 text-teal-600 border-teal-100',
    path: '/payments?new=1',
    minRole: 'finance',
  },
  {
    title: 'Create subscription',
    description: 'Start recurring billing for a customer',
    icon: Repeat,
    color: 'bg-indigo-50 text-indigo-600 border-indigo-100',
    path: '/subscriptions/new',
    minRole: 'finance',
  },
];

export function QuickCreateModal({ isOpen, onClose }: QuickCreateModalProps) {
  const navigate = useNavigate();
  const { hasRole } = useAuth();
  const canCreate = hasRole('finance');

  const handleSelect = (option: QuickCreateOption) => {
    onClose();
    navigate(option.path);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Quick create"
      description={
        canCreate
          ? 'Choose what you want to create.'
          : 'Your role is read-only in this organization. Ask an admin to grant the Finance role to create records.'
      }
      size="lg"
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 py-1">
        {OPTIONS.map((opt) => {
          const Icon = opt.icon;
          const allowed = hasRole(opt.minRole);
          return (
            <button
              key={opt.title}
              type="button"
              disabled={!allowed}
              onClick={() => handleSelect(opt)}
              className="flex items-start gap-3.5 p-3.5 rounded-xl border border-slate-200/90 hover:border-brand-500 hover:bg-brand-50/30 transition-all text-left group cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:border-slate-200/90 disabled:hover:bg-transparent"
            >
              <div
                className={`p-2.5 rounded-xl border shrink-0 transition-transform group-hover:scale-105 ${opt.color}`}
              >
                <Icon className="w-5 h-5" />
              </div>
              <div className="min-w-0 flex-1">
                <h4 className="text-xs font-bold text-slate-900 group-hover:text-brand-700">
                  {opt.title}
                </h4>
                <p className="text-[11px] text-slate-500 mt-1 leading-snug">{opt.description}</p>
              </div>
            </button>
          );
        })}
      </div>
    </Modal>
  );
}
