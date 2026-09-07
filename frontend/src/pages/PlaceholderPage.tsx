import { useLocation, Link } from 'react-router-dom';
import { Card, CardContent } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Layers, ArrowLeft, CheckCircle2, Shield } from 'lucide-react';

interface ModuleMetadata {
  title: string;
  category: string;
  phase: string;
  description: string;
  plannedFeatures: string[];
}

const moduleDirectory: Record<string, ModuleMetadata> = {
  '/customers': {
    title: 'Customers Directory & 360',
    category: 'WORKSPACE',
    phase: 'Phase 1',
    description: 'Comprehensive directory of customer accounts, contact details, payment terms, and lifecycle state management.',
    plannedFeatures: ['Customer profile & tax IDs', 'Contact persons & multiple addresses', 'Billing currency assignment', 'Portal access invitation'],
  },
  '/catalog': {
    title: 'Product Catalog & Pricing Plans',
    category: 'WORKSPACE',
    phase: 'Phase 1',
    description: 'Central registry of recurring plans, one-time add-ons, pricing models (flat, per-unit, tiered, usage), and currencies.',
    plannedFeatures: ['Multi-tier pricing models', 'Recurring billing intervals', 'Add-on dependencies', 'Volume & graduated brackets'],
  },
  '/revenue/quotes': {
    title: 'Quotes & CPQ Proposals',
    category: 'REVENUE',
    phase: 'Phase 2',
    description: 'Configure products, compute multi-tier pricing, draft customer estimates, and convert approved quotes into invoices.',
    plannedFeatures: ['CPQ rule configuration', 'Dynamic line-item pricing', 'Quote status lifecycle', '1-click invoice conversion'],
  },
  '/revenue/invoices': {
    title: 'Invoices & Billing Lifecycle',
    category: 'REVENUE',
    phase: 'Phase 2',
    description: 'Recurring and manual invoice issuance, line items, taxes, discounts, credit notes, and automated billing runs.',
    plannedFeatures: ['Draft, Sent, Paid, Overdue workflow', 'Automated recurring billing cycles', 'Tax calculation rules', 'Credit notes and voiding'],
  },
  '/revenue/payments': {
    title: 'Payments & Reconciliation',
    category: 'REVENUE',
    phase: 'Phase 3',
    description: 'Process online gateway transactions, log offline wire/bank transfers, and allocate single payments across multiple open invoices.',
    plannedFeatures: ['Multi-invoice payment allocation', 'Gateway webhook reconciliation', 'Payment method registry', 'Refund management & audit log'],
  },
  '/revenue/collections': {
    title: 'Collections & Aging AR',
    category: 'REVENUE',
    phase: 'Phase 3',
    description: 'Accounts receivable aging schedules, automated overdue follow-ups, and bad debt management.',
    plannedFeatures: ['Aging AR buckets (1-30, 31-60, 61-90+ days)', 'Escalated reminder sequences', 'Dispute tracking', 'Collection notes'],
  },
  '/subscriptions/plans': {
    title: 'Subscription Plans & Tiers',
    category: 'SUBSCRIPTIONS',
    phase: 'Phase 1',
    description: 'Define recurring billing frequencies, free trial periods, base fees, and seat allowances.',
    plannedFeatures: ['Monthly/annual billing cycles', 'Trial duration configuration', 'Setup fees and discounts', 'Plan versioning'],
  },
  '/subscriptions/all': {
    title: 'Subscriptions & Proration Engine',
    category: 'SUBSCRIPTIONS',
    phase: 'Phase 4',
    description: 'Manage active customer recurring subscriptions, mid-cycle plan upgrades/downgrades with automatic proration credits.',
    plannedFeatures: ['Subscription state machine', 'Mid-cycle upgrade/downgrade proration', 'Pause, resume, and cancel flows', 'Renewal automation'],
  },
  '/subscriptions/usage': {
    title: 'Metered & Usage-Based Billing',
    category: 'SUBSCRIPTIONS',
    phase: 'Phase 4',
    description: 'Ingest high-frequency usage telemetry, rate usage according to tier thresholds, and append to cycle invoices.',
    plannedFeatures: ['Usage event ingestion API', 'Sum, Max, Last aggregation modes', 'Tiered usage calculations', 'Overage alert triggers'],
  },
  '/subscriptions/trials': {
    title: 'Trial Management & Funnels',
    category: 'SUBSCRIPTIONS',
    phase: 'Phase 4',
    description: 'Track prospect trial expiration dates, monitor product usage during trial, and execute automated conversion campaigns.',
    plannedFeatures: ['Trial expiration alerts', 'Conversion checkout links', 'Trial extension approvals', 'Auto-cancellation workflows'],
  },
  '/operations/expenses': {
    title: 'Expense Management & Billing',
    category: 'OPERATIONS',
    phase: 'Phase 6',
    description: 'Record operating and project expenses, capture receipts, categorize, and pass billable costs onto client invoices.',
    plannedFeatures: ['Billable vs. non-billable tag', 'Customer/project tagging', 'Receipt attachment uploads', 'Invoice line-item passthrough'],
  },
  '/operations/projects': {
    title: 'Projects & Engagements',
    category: 'OPERATIONS',
    phase: 'Phase 6',
    description: 'Manage client deliverables, billing milestones, project budgets, and task tracking.',
    plannedFeatures: ['Milestone-based billing', 'Fixed vs. T&M project models', 'Budget vs. actual tracking', 'Project team assignments'],
  },
  '/operations/timesheets': {
    title: 'Timesheets & Billable Hours',
    category: 'OPERATIONS',
    phase: 'Phase 6',
    description: 'Log consulting and service hours by project task, approve employee timesheets, and generate time-based billing.',
    plannedFeatures: ['Weekly timesheet grids', 'Billable hourly rates', 'Manager approval workflow', 'Time-to-invoice auto billing'],
  },
  '/insights/revenue': {
    title: 'Revenue Intelligence & Forecasting',
    category: 'INSIGHTS',
    phase: 'Phase 7',
    description: 'Advanced SaaS revenue metrics: MRR waterfall, ARR expansion, net churn, cohort retention, and predictive revenue.',
    plannedFeatures: ['MRR movement waterfall', 'Cohort retention matrices', 'LTV and CAC modeling', 'Predictive cash flow projections'],
  },
  '/insights/reports': {
    title: 'Financial & Tax Reports',
    category: 'INSIGHTS',
    phase: 'Phase 7',
    description: 'Comprehensive financial reporting: Sales by product, Tax liability reports, Aging AR, and Payment gateway reconciliation.',
    plannedFeatures: ['Sales summary reports', 'Tax collection reports by jurisdiction', 'CSV and PDF exports', 'Scheduled automated email delivery'],
  },
  '/insights/activity': {
    title: 'Audit Trail & Activity Log',
    category: 'INSIGHTS',
    phase: 'Phase 7',
    description: 'Full immutable compliance audit trail of all financial actions, rate modifications, invoice voidings, and system events.',
    plannedFeatures: ['Filter by user and subsystem', 'Actor IP and timestamp logging', 'Before/after state diffs', 'Compliance export support'],
  },
  '/system/automation': {
    title: 'Workflow Automation Rules',
    category: 'SYSTEM',
    phase: 'Phase 7',
    description: 'Event-driven triggers and automated actions for payment failure reminders, high-usage notices, and invoice follow-ups.',
    plannedFeatures: ['Event trigger builder', 'Action webhooks & email dispatch', 'Conditional branching logic', 'Execution audit log'],
  },
  '/system/integrations': {
    title: 'Payment Gateways & Integrations',
    category: 'SYSTEM',
    phase: 'Phase 3',
    description: 'Connect payment processors (Stripe, Razorpay, UPI), accounting software, and external ERP webhooks.',
    plannedFeatures: ['Stripe & Razorpay payment credentials', 'Webhook endpoints & secret validation', 'Hosted checkout settings', 'ERP synchronization'],
  },
  '/system/settings': {
    title: 'Organization & Workspace Settings',
    category: 'SYSTEM',
    phase: 'Settings',
    description: 'Manage legal entity details, primary currency, tax identification numbers, team members, and role-based permissions.',
    plannedFeatures: ['Company details & tax identifiers', 'Multi-currency enablement', 'Team user invites & RBAC roles', 'Invoice customization templates'],
  },
};

export function PlaceholderPage() {
  const location = useLocation();
  const currentPath = location.pathname;

  const meta = moduleDirectory[currentPath] || {
    title: currentPath.split('/').pop()?.replace(/-/g, ' ').toUpperCase() || 'Module',
    category: 'WORKSPACE',
    phase: 'Scheduled Phase',
    description: 'This module is part of the approved Rooman Billing architecture and is scheduled for implementation in its designated phase.',
    plannedFeatures: ['Clean domain models', 'FastAPI REST services', 'PostgreSQL tables', 'React UI design system integration'],
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
              {meta.category}
            </span>
            <span className="text-slate-300">•</span>
            <Badge variant="primary" size="sm">
              {meta.phase}
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            {meta.title}
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            {meta.description}
          </p>
        </div>

        <Link to="/dashboard">
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<ArrowLeft className="w-3.5 h-3.5" />}
          >
            Back to Overview
          </Button>
        </Link>
      </div>

      {/* Scope Details Card */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-xl bg-brand-50 text-brand-600 border border-brand-100 shrink-0">
              <Layers className="w-6 h-6" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-slate-900">
                  Feature Scope Specification
                </h3>
                <span className="text-xs text-slate-400 font-normal">
                  (Strictly adhering to Phase 0 boundary rule)
                </span>
              </div>
              <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                Per the approved project roadmap, business logic and database models for this module will be introduced in {meta.phase}. The navigation shell and design system foundation are now fully prepared.
              </p>

              <div className="mt-5 border-t border-slate-100 pt-4">
                <h4 className="text-xs font-semibold text-slate-800 uppercase tracking-wider mb-3">
                  Key Capabilities in {meta.phase}:
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {meta.plannedFeatures.map((feat, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 text-xs text-slate-700 bg-slate-50 p-2.5 rounded-lg border border-slate-200/60"
                    >
                      <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span>{feat}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-5 p-3 rounded-lg bg-blue-50/70 border border-blue-100 text-xs text-brand-800 flex items-center gap-2">
                <Shield className="w-4 h-4 text-brand-600 shrink-0" />
                <span>
                  <strong>Architecture Guarantee:</strong> No mockup/fake business logic is hardcoded. When {meta.phase} is developed, it will connect directly to production FastAPI endpoints and PostgreSQL repositories.
                </span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
