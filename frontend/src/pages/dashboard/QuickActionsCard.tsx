import { useNavigate } from 'react-router-dom';
import { FileText, CreditCard, User, BarChart3 } from 'lucide-react';

export function QuickActionsCard({ title = 'Quick Actions' }: { title?: string } = {}) {
  const navigate = useNavigate();

  const actions = [
    {
      title: 'Create Invoice',
      icon: FileText,
      iconBg: 'bg-[#E8EBFC]',
      iconColor: 'text-[#3F51C9]',
      onClick: () => navigate('/invoices/new'),
    },
    {
      title: 'Record Payment',
      icon: CreditCard,
      iconBg: 'bg-[#F9D9E8]',
      iconColor: 'text-[#E83E8C]',
      onClick: () => navigate('/payments?new=1'),
    },
    {
      title: 'Add Customer',
      icon: User,
      iconBg: 'bg-[#F9D9E8]',
      iconColor: 'text-[#E83E8C]',
      onClick: () => navigate('/customers/new'),
    },
    {
      title: 'View Reports',
      icon: BarChart3,
      iconBg: 'bg-[#E8EBFC]',
      iconColor: 'text-[#3F51C9]',
      onClick: () => navigate('/reports'),
    },
  ];

  return (
    <div className="bg-white p-5 rounded-2xl border border-[#E7E9F2] shadow-sm space-y-3.5">
      <h3 className="text-sm font-bold text-[#11194F] tracking-tight">
        {title}
      </h3>

      <div className="grid grid-cols-2 gap-3">
        {actions.map((action) => {
          const Icon = action.icon;
          return (
            <button
              key={action.title}
              type="button"
              onClick={action.onClick}
              className="min-w-0 p-3 rounded-xl bg-[#F7F8FC]/70 hover:bg-[#F0F2FA] border border-[#E7E9F2] hover:border-[#D0D7F9] transition-all flex items-center gap-3 text-left group cursor-pointer"
            >
              <div
                className={`w-9 h-9 rounded-xl ${action.iconBg} ${action.iconColor} flex items-center justify-center shrink-0 shadow-3xs transition-transform group-hover:scale-105`}
              >
                <Icon className="w-4 h-4 stroke-[2]" />
              </div>
              <span className="min-w-0 text-xs font-semibold text-[#11194F] group-hover:text-[#25247A] leading-snug break-words">
                {action.title}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
