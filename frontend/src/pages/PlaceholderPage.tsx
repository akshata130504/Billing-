import { useLocation, Link } from 'react-router-dom';
import { Card, CardContent } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import {
  Layers,
  ArrowLeft,
  CheckCircle2,
  Shield,
  Monitor,
  Smartphone,
} from 'lucide-react';

interface ModuleMetadata {
  title: string;
  category: string;
  phase: string;
  coreFeatureIndex?: number;
  coreFeatureName?: string;
  description: string;
  plannedFeatures: string[];
  isAssignedFeature?: boolean;
}

const moduleDirectory: Record<string, ModuleMetadata> = {
  // 1. Quotes
  '/quotes': {
    title: 'Quotes & Proposals',
    category: 'REVENUE',
    phase: 'Phase 2',
    coreFeatureIndex: 1,
    coreFeatureName: 'Quotes',
    description: 'Draft customer pricing estimates, configure custom deal terms, track client approval states, and convert accepted quotes into invoices.',
    plannedFeatures: [
      'Interactive quote builder & customized term sheets',
      'Client e-signature approval & expiration tracking',
      'PDF quote rendering & email dispatch with tracking',
      '1-click conversion to finalized invoice',
    ],
  },

  // 2. Billing / Invoices
  '/invoices': {
    title: 'Billing & Invoices Lifecycle',
    category: 'REVENUE',
    phase: 'Phase 2',
    coreFeatureIndex: 2,
    coreFeatureName: 'Billing / Invoices',
    description: 'Recurring and manual invoice issuance, line-item tax calculations, automated billing runs, credit notes, and invoice lifecycle states.',
    plannedFeatures: [
      'Draft, Sent, Paid, Void, and Overdue state machine',
      'Automated recurring batch billing schedules',
      'Multi-jurisdiction GST/VAT tax calculation rules',
      'Credit notes, balance adjustments, and ledger sync',
    ],
  },

  // 3. Expenses
  '/expenses': {
    title: 'Expense Management & Billing',
    category: 'OPERATIONS',
    phase: 'Phase 6',
    coreFeatureIndex: 3,
    coreFeatureName: 'Expenses',
    description: 'Record operating and project expenses, capture receipts, categorize tax deductions, and pass billable costs onto client invoices.',
    plannedFeatures: [
      'Billable vs. non-billable expense categorization',
      'Client and project cost-center allocation',
      'Multi-currency receipt uploads & OCR parsing',
      'One-click rebilling onto client invoices',
    ],
  },

  // 4. Projects
  '/projects': {
    title: 'Projects & Engagements',
    category: 'OPERATIONS',
    phase: 'Phase 6',
    coreFeatureIndex: 4,
    coreFeatureName: 'Projects',
    description: 'Manage client deliverables, milestone-based billing, engagement budgets, task assignments, and progress tracking.',
    plannedFeatures: [
      'Milestone-based and retainer project billing models',
      'Fixed-price vs. Time & Materials (T&M) tracking',
      'Budget vs. actual expenditure variance analytics',
      'Role-based task assignments and delivery schedules',
    ],
  },

  // 5. Payments
  '/payments': {
    title: 'Payments & Gateway Processing',
    category: 'REVENUE',
    phase: 'Phase 3',
    coreFeatureIndex: 5,
    coreFeatureName: 'Payments',
    description: 'Process online gateway transactions, log offline wire/bank transfers, and allocate single payments across multiple open invoices.',
    plannedFeatures: [
      'Multi-invoice payment receipt allocation engine',
      'Payment gateway integrations (Razorpay, Stripe, UPI)',
      'Offline bank wire / check settlement recording',
      'Refund management & transactional ledger audit trail',
    ],
  },

  // 6. Product Catalog
  '/catalog': {
    title: 'Product Catalog & Plans',
    category: 'WORKSPACE',
    phase: 'Phase 1',
    coreFeatureIndex: 6,
    coreFeatureName: 'Product Catalog',
    description: 'Central registry of recurring plans, one-time add-ons, pricing models (flat, per-unit, tiered, usage), and currencies.',
    plannedFeatures: [
      'SKU hierarchy & product categorization',
      'Multi-tier and volume pricing configuration',
      'Recurring interval rules & add-on dependencies',
      'Multi-currency price lists & catalog versioning',
    ],
  },

  // 7. CPQ
  '/cpq': {
    title: 'Configure, Price, Quote (CPQ)',
    category: 'REVENUE',
    phase: 'Phase 2',
    coreFeatureIndex: 7,
    coreFeatureName: 'CPQ',
    description: 'Advanced CPQ engine for complex multi-tier pricing bundles, volume discount matrices, and contract rule enforcement.',
    plannedFeatures: [
      'Rule-based product bundling logic',
      'Volume, tier, and ramp pricing calculators',
      'Contract tenure & discount threshold guards',
      'Dynamic proposal generation and approval routing',
    ],
  },

  // 8. Trial Management
  '/trials': {
    title: 'Trial Management & Funnels',
    category: 'SUBSCRIPTIONS',
    phase: 'Phase 4',
    coreFeatureIndex: 8,
    coreFeatureName: 'Trial Management',
    description: 'Track prospect trial expiration dates, monitor product usage during evaluation, and execute automated conversion campaigns.',
    plannedFeatures: [
      'Configurable free trial durations (with/without card)',
      'Automated trial expiration warnings & alerts',
      'One-click conversion checkout links',
      'Trial extension approvals and funnel conversion analytics',
    ],
  },

  // 9. Customer Lifecycle
  '/customer-lifecycle': {
    title: 'Customer Lifecycle Management',
    category: 'CUSTOMER EXPERIENCE',
    phase: 'Phase 5',
    coreFeatureIndex: 9,
    coreFeatureName: 'Customer Lifecycle',
    description: 'Orchestrate customer journeys from prospect trial, onboarding, expansion, renewal, and retention through automated stage triggers.',
    plannedFeatures: [
      'Account health scoring & churn propensity triggers',
      'Onboarding milestone checkpoints & automated nudges',
      'Expansion and upsell propensity signaling',
      'Retention playbooks & automated cancellation flows',
    ],
  },

  // 10. Customer Portal
  '/customer-portal': {
    title: 'Self-Service Customer Portal',
    category: 'CUSTOMER EXPERIENCE',
    phase: 'Phase 5',
    coreFeatureIndex: 10,
    coreFeatureName: 'Customer Portal',
    description: 'Branded self-service portal empowering customers to view historical invoices, manage payment methods, and upgrade subscriptions.',
    plannedFeatures: [
      'White-label branded portal subdomain',
      'Invoice PDF download & online payment links',
      'Saved payment method management (Cards & UPI)',
      'Self-service plan upgrades, add-ons, and renewals',
    ],
  },

  // 11. Proration
  '/proration': {
    title: 'Proration Engine',
    category: 'SUBSCRIPTIONS',
    phase: 'Phase 4',
    coreFeatureIndex: 11,
    coreFeatureName: 'Proration',
    description: 'Mathematical proration engine calculating mid-cycle subscription upgrades, downgrades, cancellations, and credit adjustments.',
    plannedFeatures: [
      'Second-precision proration calculation models',
      'Immediate invoice vs. next-cycle credit settlement',
      'Mid-cycle seat additions and plan swaps',
      'Transparent proration line items on customer statements',
    ],
  },

  // 12. Metered Billing
  '/usage': {
    title: 'Metered & Usage-Based Billing',
    category: 'SUBSCRIPTIONS',
    phase: 'Phase 4',
    coreFeatureIndex: 12,
    coreFeatureName: 'Metered Billing',
    description: 'High-frequency usage telemetry ingestion, rating events according to tier thresholds, and appending to cycle billing runs.',
    plannedFeatures: [
      'High-throughput usage telemetry ingestion API',
      'Sum, Max, Last, and Unique Count aggregation modes',
      'Graduated and volume pricing brackets',
      'Usage threshold alerts and automated cap protections',
    ],
  },

  // 13. Hosted Payment Pages
  '/hosted-payment-pages': {
    title: 'Hosted Payment Pages',
    category: 'CUSTOMER EXPERIENCE',
    phase: 'Phase 5',
    coreFeatureIndex: 13,
    coreFeatureName: 'Hosted Payment Pages',
    description: 'PCI-compliant hosted checkout pages with dynamic localization, responsive mobile layouts, and instant webhook confirmations.',
    plannedFeatures: [
      'PCI-DSS compliant zero-redirect checkout embeds',
      'Optimized 1-click checkout with UPI & international cards',
      'Custom branding, vanity domains, and theme styling',
      'Instant webhook acknowledgment & subscription activation',
    ],
  },

  // 14. Dunning Management
  '/dunning': {
    title: 'Dunning & Payment Recovery',
    category: 'SUBSCRIPTIONS',
    phase: 'Phase 4',
    coreFeatureIndex: 14,
    coreFeatureName: 'Dunning Management',
    description: 'Automated failed payment recovery sequences, smart retry schedules, email escalation notices, and subscription auto-pause.',
    plannedFeatures: [
      'Customizable retry cadences (Smart Retries)',
      'Escalating email notices with self-service update links',
      'Configurable subscription suspension / cancel rules',
      'Payment recovery funnel analytics and recovered MRR metrics',
    ],
  },

  // 15. Pricing Models
  '/plans-pricing': {
    title: 'Pricing Models & Rate Cards',
    category: 'SUBSCRIPTIONS',
    phase: 'Phase 1',
    coreFeatureIndex: 15,
    coreFeatureName: 'Pricing Models',
    description: 'Configure flexible pricing structures: Flat-fee, Per-seat, Tiered, Volume, Stairstep, and hybrid recurring + usage models.',
    plannedFeatures: [
      'Multi-model pricing builders (Flat, Per Unit, Tiered, Volume)',
      'Monthly, quarterly, semi-annual, and annual intervals',
      'Multi-currency rate cards & foreign exchange conversions',
      'Price versioning and grandfathering policies',
    ],
  },

  // 16. AI in Billing
  '/ai-billing': {
    title: 'AI in Billing & Intelligence',
    category: 'INSIGHTS',
    phase: 'Phase 7',
    coreFeatureIndex: 16,
    coreFeatureName: 'AI in Billing',
    description: 'Machine learning models predicting customer churn, detecting invoice anomalies, optimizing smart dunning retries, and cash forecasting.',
    plannedFeatures: [
      'Predictive churn warning signals & proactive intervention',
      'Smart payment retry optimization based on transaction historical success',
      'Automated invoice anomaly & fraudulent transaction detection',
      'AI-powered cash flow and revenue trajectory forecasting',
    ],
  },

  // 17. Customization and Automation
  '/automation': {
    title: 'Customization & Workflow Automation',
    category: 'SYSTEM',
    phase: 'Phase 7',
    coreFeatureIndex: 17,
    coreFeatureName: 'Customization and Automation',
    description: 'Event-driven triggers, custom fields, webhooks, and automated actions powering hands-off billing workflows.',
    plannedFeatures: [
      'Event-trigger workflow builder (IF invoice overdue THEN notify)',
      'Custom metadata fields on accounts, invoices, and subscriptions',
      'Outbound webhooks with signature verification & replay',
      'Automated task assignments and Slack/Email integrations',
    ],
  },
  '/customization': {
    title: 'Organization Customization & Themes',
    category: 'SYSTEM',
    phase: 'Phase 7',
    coreFeatureIndex: 17,
    coreFeatureName: 'Customization and Automation',
    description: 'Brand customization, invoice email templates, custom numbering schemes, and workspace preference management.',
    plannedFeatures: [
      'Invoice template customizer (HTML/CSS editor)',
      'Custom invoice & quote numbering sequences',
      'White-label portal branding & email sender domains',
      'Localization, tax formats, and currency presentation',
    ],
  },

  // 18. Reporting and Analytics
  '/reports': {
    title: 'Reporting & Analytics Suite',
    category: 'INSIGHTS',
    phase: 'Phase 7',
    coreFeatureIndex: 18,
    coreFeatureName: 'Reporting and Analytics',
    description: 'Executive dashboards, financial accounting schedules, revenue recognition, tax summaries, and aging AR reports.',
    plannedFeatures: [
      'SaaS financial metrics: MRR, ARR, Net Churn, LTV, CAC',
      'Accounts Receivable Aging reports (1-30, 31-60, 61-90+ days)',
      'Tax liability schedules by jurisdiction (GST/VAT)',
      'Automated scheduled report delivery (PDF & CSV exports)',
    ],
  },
  '/revenue-intelligence': {
    title: 'Revenue Intelligence & MRR Waterfall',
    category: 'INSIGHTS',
    phase: 'Phase 7',
    coreFeatureIndex: 18,
    coreFeatureName: 'Reporting and Analytics',
    description: 'Deep revenue decomposition: New MRR, Expansion, Contraction, Churn, Reactivation, and cohort retention matrices.',
    plannedFeatures: [
      'Interactive MRR movement waterfall chart',
      'Cohort-based customer retention matrices',
      'Expansion vs. contraction revenue driver breakdown',
      'Real-time cash flow & projected pipeline value',
    ],
  },

  // 19. Mobile
  '/platforms/mobile': {
    title: 'Rooman Mobile Companion',
    category: 'PLATFORMS',
    phase: 'Phase 8',
    coreFeatureIndex: 19,
    coreFeatureName: 'Mobile',
    description: 'Native mobile companion apps for iOS and Android providing on-the-go billing oversight, approvals, and instant notifications.',
    plannedFeatures: [
      'Native iOS and Android responsive design',
      'Push notifications for critical billing exceptions & approvals',
      '1-tap quote and discount approval workflows',
      'Mobile camera receipt capture for expense claims',
    ],
  },

  // 20. Desktop (ASSIGNED FEATURE)
  '/platforms/desktop': {
    title: 'Rooman Desktop Application',
    category: 'PLATFORMS',
    phase: 'Phase 8',
    coreFeatureIndex: 20,
    coreFeatureName: 'Desktop',
    isAssignedFeature: true,
    description: 'Dedicated high-performance desktop workstation experience for finance teams with native OS integration and offline resilience.',
    plannedFeatures: [
      'Native workstation client (Windows & macOS via Tauri/Electron)',
      'System tray notifications & background real-time synchronization',
      'Global productivity shortcuts & rapid command palette',
      'Multi-tenant workspace quick-switching with isolated local cache',
      'Offline invoice drafting with background queue reconciliation',
      'Multi-window support for simultaneous ledger and customer review',
    ],
  },

  // Additional Supporting Navigation
  '/customers': {
    title: 'Customers Directory & 360',
    category: 'WORKSPACE',
    phase: 'Phase 1',
    description: 'Comprehensive directory of customer accounts, contact details, payment terms, and lifecycle state management.',
    plannedFeatures: [
      'Customer profile & tax IDs',
      'Contact persons & multiple addresses',
      'Billing currency assignment',
      'Portal access invitation',
    ],
  },
  '/collections': {
    title: 'Collections & Aging AR',
    category: 'REVENUE',
    phase: 'Phase 3',
    description: 'Accounts receivable aging schedules, automated overdue follow-ups, and bad debt management.',
    plannedFeatures: [
      'Aging AR buckets (1-30, 31-60, 61-90+ days)',
      'Escalated reminder sequences',
      'Dispute tracking',
      'Collection notes & payment promise tracking',
    ],
  },
  '/subscriptions': {
    title: 'Active Subscriptions Management',
    category: 'SUBSCRIPTIONS',
    phase: 'Phase 4',
    description: 'Manage active recurring customer subscriptions, mid-cycle plan upgrades, pause/resume, and renewal tracking.',
    plannedFeatures: [
      'Subscription state machine (Active, Trial, Paused, Canceled)',
      'Mid-cycle upgrades/downgrades with automatic proration',
      'Pause, resume, and cancellation workflows',
      'Automated renewal billing triggers',
    ],
  },
  '/timesheets': {
    title: 'Timesheets & Billable Hours',
    category: 'OPERATIONS',
    phase: 'Phase 6',
    description: 'Log consulting and service hours by project task, approve employee timesheets, and generate time-based billing.',
    plannedFeatures: [
      'Weekly timesheet entry grids',
      'Billable vs. non-billable hourly rates',
      'Manager approval workflow',
      'Time-to-invoice automated billing conversion',
    ],
  },
  '/activity': {
    title: 'Activity & Audit Log Feed',
    category: 'INSIGHTS',
    phase: 'Phase 7',
    description: 'Full immutable compliance audit trail of all financial actions, rate modifications, invoice voidings, and system events.',
    plannedFeatures: [
      'Live activity stream across all modules',
      'Filter by actor, subsystem, and severity',
      'Before/after state diff inspections',
      'Compliance export support',
    ],
  },
  '/integrations': {
    title: 'Payment Gateways & Integrations',
    category: 'SYSTEM',
    phase: 'Phase 3',
    description: 'Connect payment processors (Razorpay, Stripe, UPI), accounting software, and external ERP webhooks.',
    plannedFeatures: [
      'Razorpay & Stripe gateway credentials management',
      'Webhook endpoints & cryptographic secret verification',
      'Hosted checkout appearance settings',
      'Accounting & ERP data synchronization',
    ],
  },
  '/system/settings': {
    title: 'Organization & Workspace Settings',
    category: 'SYSTEM',
    phase: 'Phase 0 / Settings',
    description: 'Manage legal entity details, primary currency, tax identification numbers, team members, and role-based permissions.',
    plannedFeatures: [
      'Company details & tax identifiers (GSTIN/PAN)',
      'Multi-currency enablement & exchange rate feeds',
      'Team member invites & RBAC role permissions',
      'Default payment terms and invoice numbering schemes',
    ],
  },
};

export function PlaceholderPage() {
  const location = useLocation();
  const currentPath = location.pathname;

  const meta = moduleDirectory[currentPath] || {
    title: currentPath.split('/').pop()?.replace(/-/g, ' ').toUpperCase() || 'Module',
    category: 'WORKSPACE',
    phase: 'Planned Phase',
    description: 'This module is part of the approved Rooman Billing platform roadmap and is scheduled for implementation in its designated phase.',
    plannedFeatures: [
      'Clean domain models & repository patterns',
      'FastAPI REST endpoints',
      'PostgreSQL multi-tenant tables',
      'React UI design system integration',
    ],
  };

  const isDesktop = meta.isAssignedFeature || currentPath === '/platforms/desktop';
  const isMobile = currentPath === '/platforms/mobile';

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
            {meta.coreFeatureIndex && (
              <>
                <span className="text-slate-300">•</span>
                <span className="text-[11px] font-bold text-slate-500">
                  Feature #{meta.coreFeatureIndex} of 20
                </span>
              </>
            )}
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
            {isDesktop && <Monitor className="w-6 h-6 text-brand-600 shrink-0" />}
            {isMobile && <Smartphone className="w-6 h-6 text-brand-600 shrink-0" />}
            <span>{meta.title}</span>
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl leading-relaxed">
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

      {/* Assigned Feature Hero Banner for Desktop (Primary Assigned Module) */}
      {isDesktop && (
        <div className="p-4 sm:p-5 rounded-2xl bg-gradient-to-r from-blue-50 via-indigo-50/50 to-blue-50 border border-blue-200/80 shadow-xs">
          <div className="flex items-start gap-3.5">
            <div className="p-2.5 rounded-xl bg-white border border-blue-200 text-brand-600 shadow-2xs shrink-0">
              <Monitor className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-xs font-bold text-brand-900 uppercase tracking-wider">
                  Assigned Feature Specification
                </h3>
                <span className="text-[10px] bg-brand-600 text-white font-bold px-2 py-0.5 rounded-full">
                  Primary Assigned Module #20
                </span>
                <span className="text-[11px] font-mono text-brand-700 bg-white/80 border border-blue-200 px-2 py-0.5 rounded">
                  /platforms/desktop
                </span>
              </div>
              <p className="text-xs text-brand-800 leading-relaxed max-w-3xl">
                This dedicated route establishes the official navigation, layout shell, and architecture placeholder for the <strong>Rooman Billing Desktop</strong> experience. Native desktop workstation runtimes (Tauri / Electron), local OS keybindings, system tray background workers, and offline cash-flow ledgers are designated for this module per the architectural roadmap.
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
                  (Strict Phase Boundary — Roadmap Specification)
                </span>
              </div>
              <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                Per the approved project roadmap, business logic and database models for this module will be introduced in {meta.phase}. The navigation shell, routing foundation, and design system integration are fully wired and prepared.
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
                  <strong>Architecture Guarantee:</strong> No fake business logic is hardcoded. When {meta.phase} is deployed, this view will connect directly to production FastAPI endpoints and PostgreSQL repositories.
                </span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
