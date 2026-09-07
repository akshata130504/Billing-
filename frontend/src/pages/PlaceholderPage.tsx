import { useLocation, Link } from 'react-router-dom';
import { Card, CardContent } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { RoomanLogo } from '../components/common/RoomanLogo';
import {
  Layers,
  ArrowLeft,
  CheckCircle2,
  Shield,
  Monitor,
  Smartphone,
  Sparkles,
  Calendar,
  Lock,
} from 'lucide-react';

interface ModuleMetadata {
  title: string;
  category: string;
  status: string;
  description: string;
  plannedFeatures: string[];
  isAssignedFeature?: boolean;
}

const moduleDirectory: Record<string, ModuleMetadata> = {
  // WORKSPACE
  '/customers': {
    title: 'Customers',
    category: 'WORKSPACE',
    status: 'Planned — Future Phase',
    description: 'Centralized directory of customer accounts, billing profiles, contact persons, tax registration IDs, and lifecycle states.',
    plannedFeatures: [
      'Customer profile & tax identifier registry',
      'Multiple contact persons & billing addresses',
      'Currency & payment terms assignment',
      'Client portal access & invitations',
    ],
  },
  '/catalog': {
    title: 'Catalog',
    category: 'WORKSPACE',
    status: 'Planned — Future Phase',
    description: 'Product catalog defining one-time items, recurring plans, billing cycles, units of measure, and tiered price books.',
    plannedFeatures: [
      'SKU & product hierarchy definition',
      'Multi-currency pricing catalogs',
      'Recurring & one-off item classification',
      'Unit of measurement & add-on linking',
    ],
  },

  // REVENUE
  '/revenue/quotes': {
    title: 'Quotes',
    category: 'REVENUE',
    status: 'Planned — Future Phase',
    description: 'Draft customer estimates, configure deal discounts, track client approval states, and convert accepted quotes directly into invoices.',
    plannedFeatures: [
      'Quote creation & custom term sheets',
      'Approval workflow & expiration tracking',
      'PDF quote rendering & client dispatch',
      '1-click invoice conversion',
    ],
  },
  '/revenue/cpq': {
    title: 'CPQ',
    category: 'REVENUE',
    status: 'Planned — Future Phase',
    description: 'Configure, Price, Quote engine for complex multi-tier pricing bundles, volume-discount matrixes, and contract rule enforcement.',
    plannedFeatures: [
      'Rule-based product bundling logic',
      'Volume, tier, and ramp pricing calculators',
      'Contract tenure & discount threshold guards',
      'Dynamic proposal generation',
    ],
  },
  '/revenue/invoices': {
    title: 'Invoices',
    category: 'REVENUE',
    status: 'Planned — Future Phase',
    description: 'Generate recurring and ad-hoc invoices, line-item tax calculations, credit notes, and automated billing run executions.',
    plannedFeatures: [
      'Draft, Sent, Paid, Void, and Overdue lifecycle',
      'Automated recurring billing batch schedules',
      'Jurisdiction tax calculation rules',
      'Credit notes, refunds, and adjustments',
    ],
  },
  '/revenue/payments': {
    title: 'Payments',
    category: 'REVENUE',
    status: 'Planned — Future Phase',
    description: 'Track payment collections across payment gateways, log manual bank transfers, and reconcile multi-invoice transactions.',
    plannedFeatures: [
      'Multi-invoice payment receipt allocation',
      'Online payment gateway webhooks (Stripe, UPI)',
      'Manual check/wire settlement logging',
      'Refund processing & audit history',
    ],
  },
  '/revenue/collections': {
    title: 'Collections',
    category: 'REVENUE',
    status: 'Planned — Future Phase',
    description: 'Accounts receivable aging analysis, automated payment reminders, escalation tracking, and bad debt management.',
    plannedFeatures: [
      'Aging AR buckets (Current, 1-30, 31-60, 61-90+ days)',
      'Automated reminder cadences & escalation',
      'Dispute logging & customer resolution notes',
      'Write-off & bad-debt classification',
    ],
  },

  // SUBSCRIPTIONS
  '/subscriptions/plans': {
    title: 'Plans & Pricing',
    category: 'SUBSCRIPTIONS',
    status: 'Planned — Future Phase',
    description: 'Define recurring billing models (flat-rate, per-seat, tiered, usage-based), free trial periods, setup fees, and renewal intervals.',
    plannedFeatures: [
      'Flat-rate, per-seat, and tiered pricing schemes',
      'Flexible billing frequencies (monthly, quarterly, annual)',
      'Trial duration & setup fee configurations',
      'Plan versioning & grandfathering',
    ],
  },
  '/subscriptions/all': {
    title: 'Subscriptions',
    category: 'SUBSCRIPTIONS',
    status: 'Planned — Future Phase',
    description: 'Manage active customer subscriptions, contract renewals, upgrades, downgrades, cancellations, and pause states.',
    plannedFeatures: [
      'Full subscription lifecycle state machine',
      'Mid-cycle upgrade & downgrade flows',
      'Scheduled renewals, pause, and resume actions',
      'Cancellation reasons & churn tracking',
    ],
  },
  '/subscriptions/trials': {
    title: 'Trials',
    category: 'SUBSCRIPTIONS',
    status: 'Planned — Future Phase',
    description: 'Monitor active prospect trial periods, feature adoption during trials, automated expiration warnings, and conversion funnels.',
    plannedFeatures: [
      'Trial timeline tracking & expiration schedules',
      'Conversion trigger emails & self-serve upgrade links',
      'Trial duration extension workflows',
      'Conversion & drop-off analytics',
    ],
  },
  '/subscriptions/usage': {
    title: 'Usage / Metering',
    category: 'SUBSCRIPTIONS',
    status: 'Planned — Future Phase',
    description: 'Ingest high-volume metered usage events, evaluate consumption against tier thresholds, and aggregate into billing cycles.',
    plannedFeatures: [
      'High-throughput usage event ingestion API',
      'Aggregation types (sum, max, last, gauge)',
      'Threshold notifications & overage protection',
      'Cycle-end rating & automated invoice line items',
    ],
  },
  '/subscriptions/proration': {
    title: 'Proration',
    category: 'SUBSCRIPTIONS',
    status: 'Planned — Future Phase',
    description: 'Calculate exact day-rate or second-rate proration adjustments for mid-cycle plan changes, seat additions, or tier switches.',
    plannedFeatures: [
      'Calendar-day and exact-second proration engines',
      'Immediate invoice charge vs. next-cycle credit balance',
      'Mid-cycle seat addition & removal calculations',
      'Transparent proration breakdown previews',
    ],
  },
  '/subscriptions/dunning': {
    title: 'Dunning',
    category: 'SUBSCRIPTIONS',
    status: 'Planned — Future Phase',
    description: 'Automated retry schedules for failed recurring payments, smart retry logic, customer payment method update notifications, and account suspension.',
    plannedFeatures: [
      'Smart retry rules with exponential backoff',
      'Payment failure customer notification emails',
      'Self-serve payment method update links',
      'Automated subscription suspension after max retries',
    ],
  },

  // CUSTOMER EXPERIENCE
  '/customer-experience/lifecycle': {
    title: 'Customer Lifecycle',
    category: 'CUSTOMER EXPERIENCE',
    status: 'Planned — Future Phase',
    description: 'Track customer journey from onboarding and trial through active subscription, expansion, renewal, and retention.',
    plannedFeatures: [
      'Customer health score & churn risk indicator',
      'Milestone achievement & onboarding checklists',
      'Account expansion & upsell opportunity flags',
      'Retention workflows & renewal reviews',
    ],
  },
  '/customer-experience/portal': {
    title: 'Customer Portal',
    category: 'CUSTOMER EXPERIENCE',
    status: 'Planned — Future Phase',
    description: 'Branded self-service portal enabling end-customers to view invoices, download receipts, manage payment methods, and adjust subscriptions.',
    plannedFeatures: [
      'Secure passwordless magic-link authentication',
      'Invoice & receipt PDF downloads',
      'Saved card & payment method updates',
      'Self-serve plan upgrades & add-on purchases',
    ],
  },
  '/customer-experience/payment-pages': {
    title: 'Hosted Payment Pages',
    category: 'CUSTOMER EXPERIENCE',
    status: 'Planned — Future Phase',
    description: 'Secure, brandable, PCI-compliant hosted checkout pages for seamless quote acceptance, invoice settlement, and new subscription checkouts.',
    plannedFeatures: [
      'Customizable checkout themes with Rooman branding',
      'Multi-currency & local payment method support',
      'Zero-redirect embedded or standalone payment links',
      'Real-time transaction confirmation & webhook dispatch',
    ],
  },

  // OPERATIONS
  '/operations/expenses': {
    title: 'Expenses',
    category: 'OPERATIONS',
    status: 'Planned — Future Phase',
    description: 'Record company and project expenditures, track receipt attachments, categorize operational overhead, and rebill expenses to clients.',
    plannedFeatures: [
      'Billable vs. non-billable categorization',
      'Receipt upload & tax classification',
      'Client & project expense association',
      'Direct passthrough to client invoice drafts',
    ],
  },
  '/operations/projects': {
    title: 'Projects',
    category: 'OPERATIONS',
    status: 'Planned — Future Phase',
    description: 'Manage client deliverables, billing milestones, fixed vs time-and-materials engagement models, and project budgets.',
    plannedFeatures: [
      'Fixed-fee milestone & deliverable billing',
      'Project budget vs. actual cost tracking',
      'Team member assignment & billing rates',
      'Milestone completion approval to invoice generation',
    ],
  },
  '/operations/timesheets': {
    title: 'Timesheets',
    category: 'OPERATIONS',
    status: 'Planned — Future Phase',
    description: 'Track billable and non-billable service hours, manage weekly manager approvals, and convert logged hours into invoices.',
    plannedFeatures: [
      'Weekly employee time logging grids',
      'Role-based hourly billing rate cards',
      'Manager review & approval workflows',
      'Automated billable hour conversion to invoices',
    ],
  },

  // INSIGHTS
  '/insights/revenue': {
    title: 'Revenue Intelligence',
    category: 'INSIGHTS',
    status: 'Planned — Future Phase',
    description: 'Deep SaaS financial analytics: MRR movements, ARR growth, net revenue retention, churn decomposition, and forward forecasts.',
    plannedFeatures: [
      'MRR waterfall (New, Expansion, Contraction, Churn)',
      'Cohort retention & lifetime value (LTV) models',
      'Customer acquisition cost (CAC) payback curves',
      'Predictive cash flow & renewal forecasting',
    ],
  },
  '/insights/reports': {
    title: 'Reports & Analytics',
    category: 'INSIGHTS',
    status: 'Planned — Future Phase',
    description: 'Standard financial, sales, and tax compliance reports with configurable date filters, aggregations, and export formats.',
    plannedFeatures: [
      'Sales summary & product performance reports',
      'Jurisdictional tax liability schedules',
      'AR aging summaries & collection efficacy',
      'Scheduled recurring report delivery (CSV, PDF)',
    ],
  },
  '/insights/ai': {
    title: 'AI in Billing',
    category: 'INSIGHTS',
    status: 'Planned — Future Phase',
    description: 'Intelligent billing assistant providing churn prediction, automated anomaly detection, payment failure forecasting, and revenue insights.',
    plannedFeatures: [
      'Early churn warning & sentiment indicators',
      'Invoice & billing anomaly detection',
      'Optimal dunning retry time prediction',
      'Natural language queries over billing data',
    ],
  },
  '/insights/activity': {
    title: 'Activity',
    category: 'INSIGHTS',
    status: 'Planned — Future Phase',
    description: 'Immutable audit trail capturing all operational actions, rate modifications, invoice voidings, permission changes, and security events.',
    plannedFeatures: [
      'Complete chronological system audit log',
      'Actor attribution with IP address & timestamps',
      'Field-level before/after modification diffs',
      'Compliance & security report export',
    ],
  },

  // PLATFORMS
  '/platforms/mobile': {
    title: 'Mobile',
    category: 'PLATFORMS',
    status: 'Planned — Future Phase',
    description: 'Native mobile client for on-the-go billing approvals, metric tracking, instant payment notifications, and customer lookup.',
    plannedFeatures: [
      'Biometric login & push notification alerts',
      'Quick quote & invoice approval actions',
      'Mobile camera receipt & expense capture',
      'Real-time MRR & overdue payment dashboard',
    ],
  },
  '/platforms/desktop': {
    title: 'Desktop',
    category: 'PLATFORMS',
    status: 'Planned — Future Phase',
    description: 'Access and manage Rooman Billing through the dedicated desktop experience.',
    isAssignedFeature: true,
    plannedFeatures: [
      'Native workstation client (Windows & macOS)',
      'System tray notifications & background sync',
      'Productivity shortcuts & global command palette',
      'Multi-tenant organization quick switching',
    ],
  },

  // CONTROL CENTER
  '/control-center/action-center': {
    title: 'Action Center',
    category: 'CONTROL CENTER',
    status: 'Planned — Future Phase',
    description: 'Centralized operational cockpit for high-priority billing exceptions, overdue collections, failed payments, and urgent action items.',
    plannedFeatures: [
      'Cross-module exception aggregation',
      'One-click remediation actions (remind, retry, review)',
      'Severity weighting & SLA urgency tags',
      'Automated task resolution audit logging',
    ],
  },
  '/control-center/approvals': {
    title: 'Approval Center',
    category: 'CONTROL CENTER',
    status: 'Planned — Future Phase',
    description: 'Single centralized authorization inbox for financial approvals: high discounts, quote commitments, refund authorizations, and custom pricing overrides.',
    plannedFeatures: [
      'Multi-level authorization hierarchies',
      'Discount & refund policy boundary enforcement',
      'One-click approval/rejection with justification',
      'Full compliance audit trail integration',
    ],
  },
  '/control-center/calendar': {
    title: 'Billing Calendar',
    category: 'CONTROL CENTER',
    status: 'Planned — Future Phase',
    description: 'Chronological horizon for scheduled recurring runs, invoice due dates, subscription renewals, trial expiries, and automated payment retries.',
    plannedFeatures: [
      'Monthly/weekly billing events calendar grid',
      'Category filtering (invoices, renewals, trials, payments)',
      'Scheduled batch run time triggers',
      'Upcoming cashflow & liquidity timeline view',
    ],
  },
  '/control-center/reconciliation': {
    title: 'Reconciliation',
    category: 'CONTROL CENTER',
    status: 'Planned — Future Phase',
    description: 'Automated multi-way matching linking payment receipts, external gateway settlement records, open invoices, and customer accounts.',
    plannedFeatures: [
      'Automated multi-way matching pipeline',
      'Bank statement & gateway UTR reconciliation',
      'Discrepancy variance flagging & exception handling',
      'General ledger settlement confirmation',
    ],
  },
  '/control-center/audit-log': {
    title: 'Audit Log',
    category: 'CONTROL CENTER',
    status: 'Planned — Future Phase',
    description: 'Immutable chronological audit record of critical state transitions, price modifications, invoice adjustments, permission updates, and automated system actions.',
    plannedFeatures: [
      'Immutable cryptographic event ledger',
      'Before & after state change diffing',
      'Actor attribution with IP and device origin',
      'CSV & JSON compliance export capability',
    ],
  },
  '/control-center/migration': {
    title: 'Data Migration',
    category: 'CONTROL CENTER',
    status: 'Planned — Future Phase',
    description: 'Self-serve migration toolchain to bulk ingest historical customers, product price books, open invoices, active subscriptions, and payment ledgers into Rooman Billing.',
    plannedFeatures: [
      'Entity CSV/XLSX staging & validation engine',
      'Tax identifier & currency schema checks',
      'Batch ingestion with real-time error logging',
      'Historical migration run tracking & rollback logs',
    ],
  },

  // SYSTEM
  '/system/automation': {
    title: 'Automation',
    category: 'SYSTEM',
    status: 'Planned — Future Phase',
    description: 'Configure event-driven workflow automation rules, trigger webhooks, automated email alerts, and custom billing lifecycle actions.',
    plannedFeatures: [
      'Visual event trigger & condition builder',
      'Automated email, SMS, and webhook dispatches',
      'Scheduled periodic tasks & maintenance jobs',
      'Workflow execution history & retry logs',
    ],
  },
  '/system/customization': {
    title: 'Customization',
    category: 'SYSTEM',
    status: 'Planned — Future Phase',
    description: 'Tailor invoice templates, define custom fields on billing entities, configure email templates, and manage branding themes.',
    plannedFeatures: [
      'Drag-and-drop invoice & estimate PDF templates',
      'Custom fields on Customers, Invoices, & Subscriptions',
      'Branded notification email layouts & variables',
      'Localization & date/number format preferences',
    ],
  },
  '/system/integrations': {
    title: 'Integrations',
    category: 'SYSTEM',
    status: 'Planned — Future Phase',
    description: 'Connect third-party payment gateways, accounting systems, CRM platforms, and external ERP webhooks.',
    plannedFeatures: [
      'Payment gateways (Stripe, Razorpay, UPI, PayPal)',
      'Accounting sync (QuickBooks, Xero, Tally)',
      'CRM connectivity (Salesforce, HubSpot)',
      'REST API keys & webhook endpoint management',
    ],
  },
  '/system/settings': {
    title: 'Settings',
    category: 'SYSTEM',
    status: 'Planned — Future Phase',
    description: 'Manage organization profile, legal entity details, primary currency, tax identification numbers, team members, and role-based permissions.',
    plannedFeatures: [
      'Legal entity & registered tax identifiers',
      'Multi-currency enablement & exchange rates',
      'Team member management & RBAC role assignment',
      'Security policies, SSO, and audit settings',
    ],
  },
};

export function PlaceholderPage() {
  const location = useLocation();
  const currentPath = location.pathname;

  const meta = moduleDirectory[currentPath] || {
    title: currentPath.split('/').pop()?.replace(/-/g, ' ').toUpperCase() || 'Module',
    category: 'WORKSPACE',
    status: 'Planned — Future Phase',
    description: 'This module is part of the approved Rooman Billing architecture and is scheduled for implementation in its designated phase.',
    plannedFeatures: [
      'Clean domain models & database schemas',
      'FastAPI REST services & repository layer',
      'React UI design system integration',
      'Role-based permission controls',
    ],
  };

  const isDesktop = currentPath === '/platforms/desktop';
  const isMobile = currentPath === '/platforms/mobile';

  return (
    <div className="space-y-6">
      {/* Brand Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-1 border-b border-slate-100">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-white border border-slate-200/90 flex items-center justify-center shadow-2xs">
            <RoomanLogo variant="shield" size="md" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-brand-600">
                Rooman Billing
              </span>
              <span className="text-slate-300">•</span>
              <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">
                {meta.category}
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Enterprise Billing & Revenue Management Platform
            </p>
          </div>
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

      {/* Main Page Title & Metadata Header */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <Badge variant="primary" size="sm">
              {meta.status}
            </Badge>
            {meta.isAssignedFeature && (
              <Badge variant="success" size="sm">
                Assigned Feature
              </Badge>
            )}
            <span className="inline-flex items-center gap-1 text-[11px] text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md">
              <Calendar className="w-3 h-3 text-slate-400" />
              Phase 0 Foundation
            </span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
            {isDesktop && <Monitor className="w-6 h-6 text-brand-600 shrink-0" />}
            {isMobile && <Smartphone className="w-6 h-6 text-brand-600 shrink-0" />}
            <span>{meta.title}</span>
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 mt-1.5 max-w-2xl leading-relaxed">
            {meta.description}
          </p>
        </div>
      </div>

      {/* Assigned Feature Banner for Desktop */}
      {isDesktop && (
        <div className="p-4 rounded-xl bg-gradient-to-r from-blue-50 to-indigo-50/60 border border-blue-200/80">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-white border border-blue-200 text-brand-600 shadow-2xs shrink-0">
              <Monitor className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-xs font-bold text-brand-900 uppercase tracking-wider">
                  Dedicated Desktop Feature Route
                </h3>
                <span className="text-[10px] bg-brand-600 text-white font-semibold px-2 py-0.5 rounded-full">
                  Primary Assigned Module
                </span>
              </div>
              <p className="text-xs text-brand-800 mt-1 leading-relaxed">
                This dedicated route establishes the official navigation, layout shell, and architecture placeholder for the Rooman Billing Desktop experience. Real desktop application runtimes (Electron/Tauri) and local OS integrations will be implemented in subsequent development phases per project milestones.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Scope Details Card */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-xl bg-brand-50 text-brand-600 border border-brand-100 shrink-0">
              {isDesktop ? (
                <Monitor className="w-6 h-6" />
              ) : isMobile ? (
                <Smartphone className="w-6 h-6" />
              ) : (
                <Layers className="w-6 h-6" />
              )}
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-sm font-semibold text-slate-900">
                  Planned Module Scope & Architecture
                </h3>
                <span className="text-xs text-slate-400 font-normal">
                  (Strict Phase 0 Boundary — Placeholder State)
                </span>
              </div>
              <p className="text-xs text-slate-600 mt-1.5 leading-relaxed">
                The navigation item, route mapping, and design token integration for{' '}
                <strong className="text-slate-800">{meta.title}</strong> are now established in Rooman Billing. Business logic, database tables, and API integrations remain strictly deferred to subsequent phases.
              </p>

              {/* Key Capabilities */}
              <div className="mt-5 border-t border-slate-100 pt-4">
                <h4 className="text-xs font-semibold text-slate-800 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-brand-600" />
                  <span>Planned Core Capabilities:</span>
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {meta.plannedFeatures.map((feat, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2.5 text-xs text-slate-700 bg-slate-50 p-2.5 rounded-lg border border-slate-200/60"
                    >
                      <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span>{feat}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Architecture Guarantee */}
              <div className="mt-5 p-3 rounded-lg bg-slate-50 border border-slate-200/80 text-xs text-slate-600 flex items-start gap-2.5">
                <Shield className="w-4 h-4 text-brand-600 shrink-0 mt-0.5" />
                <div className="leading-snug">
                  <strong className="text-slate-800">Phase 0 Architectural Guarantee:</strong>
                  <span className="ml-1">
                    No mock business logic, mock database records, or temporary forms are hardcoded in this view. When development begins for this module, it will bind cleanly to production FastAPI endpoints and PostgreSQL repositories.
                  </span>
                </div>
              </div>

              {/* Security & Access Notice */}
              <div className="mt-3 flex items-center gap-2 text-[11px] text-slate-400">
                <Lock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                <span>Status: {meta.status} • Rooman Billing Design System v1.0 Approved</span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
