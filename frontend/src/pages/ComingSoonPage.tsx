import { Link, useLocation } from 'react-router-dom';
import { ArrowLeft, Construction } from 'lucide-react';
import { Card, CardContent } from '../components/common/Card';
import { Button } from '../components/common/Button';

interface ModuleInfo {
  title: string;
  description: string;
}

/**
 * Titles/descriptions for routes that are exposed in navigation but have no
 * implementation in this release. Keyed by the first path segment(s).
 */
const MODULES: Record<string, ModuleInfo> = {
  '/cpq': {
    title: 'CPQ',
    description: 'Guided configure-price-quote flows on top of the quotes module.',
  },
  '/plans-pricing': {
    title: 'Plans & Pricing',
    description: 'Plans are managed from the Catalog in this release.',
  },
  '/usage': {
    title: 'Usage / Metering',
    description: 'Usage-based billing on top of subscriptions.',
  },
  '/proration': {
    title: 'Proration',
    description: 'Mid-cycle plan change adjustments for subscriptions.',
  },
  '/dunning': {
    title: 'Dunning',
    description: 'Configurable retry and reminder sequences for unpaid invoices.',
  },
  '/customer-lifecycle': {
    title: 'Customer Lifecycle',
    description: 'Lifecycle stages and health scoring for customer accounts.',
  },
  '/customer-portal': {
    title: 'Customer Portal',
    description: 'A self-service portal for your customers.',
  },
  '/hosted-payment-pages': {
    title: 'Hosted Payment Pages',
    description: 'Configuration for the public invoice payment page.',
  },
  '/expenses': {
    title: 'Expenses',
    description: 'Expense tracking and rebilling.',
  },
  '/projects': {
    title: 'Projects',
    description: 'Project and milestone billing.',
  },
  '/timesheets': {
    title: 'Timesheets',
    description: 'Time tracking that feeds invoices.',
  },
  '/revenue-intelligence': {
    title: 'Revenue Intelligence',
    description: 'Deeper revenue analytics beyond the overview dashboard.',
  },
  '/reports': {
    title: 'Reports & Analytics',
    description: 'Exportable financial and operational reports.',
  },
  '/ai-billing': {
    title: 'AI in Billing',
    description: 'Assisted billing workflows.',
  },
  '/automation': {
    title: 'Automation',
    description: 'Event-driven workflow rules.',
  },
  '/customization': {
    title: 'Customization',
    description: 'Document templates and branding beyond the organization settings.',
  },
  '/integrations': {
    title: 'Integrations',
    description: 'Gateway and email status is shown under Settings → Integrations.',
  },
  '/platforms/mobile': {
    title: 'Mobile',
    description: 'A mobile companion application.',
  },
  '/platforms/desktop': {
    title: 'Desktop',
    description: 'A desktop application.',
  },
};

function lookup(pathname: string): ModuleInfo {
  const exact = MODULES[pathname];
  if (exact) return exact;
  const prefix = Object.keys(MODULES).find((key) => pathname.startsWith(`${key}/`));
  if (prefix) return MODULES[prefix];
  const segment = pathname.split('/').filter(Boolean).pop() ?? 'module';
  const title = segment.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  return { title, description: 'This area of Rooman Billing has no implementation yet.' };
}

export interface ComingSoonPageProps {
  /** Override the route-derived title (used by module stubs). */
  title?: string;
  description?: string;
}

export function ComingSoonPage({ title, description }: ComingSoonPageProps) {
  const { pathname } = useLocation();
  const info = lookup(pathname);
  const resolvedTitle = title ?? info.title;
  const resolvedDescription = description ?? info.description;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">{resolvedTitle}</h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl leading-relaxed">
            {resolvedDescription}
          </p>
        </div>
        <Link to="/dashboard">
          <Button variant="outline" size="sm" leadingIcon={<ArrowLeft className="w-3.5 h-3.5" />}>
            Back to Overview
          </Button>
        </Link>
      </div>

      <Card>
        <CardContent className="p-8 flex flex-col items-center text-center">
          <div className="p-3 rounded-full bg-slate-100 text-slate-500 mb-3.5">
            <Construction className="w-6 h-6 stroke-[1.5]" />
          </div>
          <h2 className="text-sm font-semibold text-slate-900">
            This module is not available in this release
          </h2>
          <p className="mt-1 text-xs text-slate-500 max-w-md leading-relaxed">
            Nothing is shown here because there is no data behind it yet. Use the navigation to
            continue working in the modules that are available.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

export default ComingSoonPage;
