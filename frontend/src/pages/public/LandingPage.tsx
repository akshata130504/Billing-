import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  Shield,
  Layers,
  FileText,
  CreditCard,
  Users,
  BarChart3,
  Sliders,
  Sparkles,
  Zap,
  Lock,
  Database,
  Calculator,
  Receipt,
  RotateCcw,
  Check,
  Building2,
  Calendar,
  Eye,
  Menu,
  X,
  TrendingUp,
  Cpu,
  ChevronDown,
  ArrowUpRight,
  Briefcase,
  Play,
  Pause,
  Server,
  Workflow,
} from 'lucide-react';
import { RoomanLogo } from '../../components/common/RoomanLogo';
import { Button } from '../../components/common/Button';
import { useAuth } from '../../hooks/useAuth';

export function LandingPage() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  // Navigation & UI States
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [activeWorkflowTab, setActiveWorkflowTab] = useState<number>(0);
  const [isAutoPlayingWorkflow, setIsAutoPlayingWorkflow] = useState<boolean>(true);
  const [selectedPricingModel, setSelectedPricingModel] = useState<number>(0);
  const [simulatorQuantity, setSimulatorQuantity] = useState<number>(150);
  const [openFaqIndex, setOpenFaqIndex] = useState<number | null>(0);
  const [activeTabVisual, setActiveTabVisual] = useState<'transactions' | 'cpq'>('transactions');

  // Auto cycle workflow steps
  useEffect(() => {
    if (!isAutoPlayingWorkflow) return;
    const timer = setInterval(() => {
      setActiveWorkflowTab((prev) => (prev + 1) % 9);
    }, 4200);
    return () => clearInterval(timer);
  }, [isAutoPlayingWorkflow]);

  const scrollToSection = (id: string) => {
    setMobileMenuOpen(false);
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  // 9 Workflow Stages
  const workflowSteps = [
    {
      id: 'catalog',
      label: 'Catalog',
      step: '01',
      title: 'Product & Service Catalog',
      desc: 'Define standard products, recurring subscriptions, usage rates, and modular add-ons in a single consolidated repository.',
      badge: 'Foundation',
      route: '/catalog',
      details: ['Multi-currency support', 'Subscription plans & one-time items', 'Add-ons & usage tiers'],
    },
    {
      id: 'pricing',
      label: 'Pricing',
      step: '02',
      title: 'Flexible Pricing Engine',
      desc: 'Configure flat, tiered, volume, per-unit, or graduated fee structures with customizable billing frequencies and schedules.',
      badge: 'Configuration',
      route: '/plans-pricing',
      details: ['5 native monetization models', 'Billing frequencies (monthly/annual)', 'Proration rules'],
    },
    {
      id: 'cpq',
      label: 'CPQ',
      step: '03',
      title: 'Configure, Price, Quote (CPQ)',
      desc: 'Interactive sales configuration rules ensuring valid product combinations, required add-ons, and margin-protected pricing.',
      badge: 'Sales Ops',
      route: '/cpq',
      details: ['Bundle compatibility rules', 'Discount threshold alerts', 'Margin protection checks'],
    },
    {
      id: 'quote',
      label: 'Quote',
      step: '04',
      title: 'Professional Quote Generation',
      desc: 'Produce branded quotes with custom payment terms, itemized line tables, and shareable public links.',
      badge: 'Client Facing',
      route: '/quotes',
      details: ['One-click PDF preview', 'Shareable client links', 'Real-time expiry tracking'],
    },
    {
      id: 'approval',
      label: 'Approval',
      step: '05',
      title: 'Automated Multi-Tier Approvals',
      desc: 'Enforce governance with discount thresholds and manager approval checkpoints before quotes are finalized.',
      badge: 'Governance',
      route: '/control-center/approvals',
      details: ['Role-based threshold signoffs', 'Instant approval notifications', 'Audit log tracing'],
    },
    {
      id: 'invoice',
      label: 'Invoice',
      step: '06',
      title: 'One-Click Invoice Conversion',
      desc: 'Instantly convert accepted quotes into tax-compliant invoices with automatic sequence numbering and due dates.',
      badge: 'Billing Ops',
      route: '/invoices',
      details: ['Sequential numbering', 'Tax & line item preservation', 'Custom payment terms'],
    },
    {
      id: 'payment',
      label: 'Payment',
      step: '07',
      title: 'Payment Processing & Allocation',
      desc: 'Record and track payments, allocations to open invoices, refunds, and real-time outstanding ledger balances.',
      badge: 'Cash Flow',
      route: '/payments',
      details: ['Multi-invoice allocations', 'Partial payment handling', 'Comprehensive refund ledger'],
    },
    {
      id: 'reconciliation',
      label: 'Reconciliation',
      step: '08',
      title: 'Financial Reconciliation',
      desc: 'Match bank statements and gateway transaction logs directly to internal customer ledger entries.',
      badge: 'Accounting',
      route: '/control-center/reconciliation',
      details: ['Disbursement matching', 'Settlement variance detection', 'Zero-discrepancy ledger'],
    },
    {
      id: 'reporting',
      label: 'Reporting',
      step: '09',
      title: 'Revenue Analytics & Reporting',
      desc: 'Gain 360-degree visibility over MRR, ARR, invoice aging, collections efficiency, and churn velocity.',
      badge: 'Intelligence',
      route: '/dashboard',
      details: ['Real-time MRR/ARR indicators', 'Aging receivables buckets', 'Cohort & retention insights'],
    },
  ];

  // 5 Pricing Models with live dynamic preview
  const pricingModels = [
    {
      title: 'Flat Fee',
      type: 'Fixed Rate',
      desc: 'Predictable, static recurring billing recurring on regular intervals (e.g. $199/month).',
      example: 'Enterprise Platform Access',
      calculate: () => 299,
      calcDisplay: 'Fixed $299.00 / month regardless of seats',
      features: ['Fixed monthly or annual billing', 'Simple invoice generation', 'Ideal for base platform tiers'],
    },
    {
      title: 'Per Unit',
      type: 'Seat / License',
      desc: 'Linear pricing calculated by multiplying the unit price by active user count or license seats.',
      example: '$15 / active user / month',
      calculate: (qty: number) => qty * 15,
      calcDisplay: (qty: number) => `${qty} units × $15.00 = $${(qty * 15).toLocaleString()}.00 / mo`,
      features: ['Dynamic quantity recalculation', 'Mid-cycle seat adjustments', 'Ideal for SaaS team plans'],
    },
    {
      title: 'Volume',
      type: 'All-Unit Discount',
      desc: 'The total volume purchased qualifies all units for a discounted tier price.',
      example: '1-50 units: $20/ea | 51-200 units: $14/ea | 201+: $10/ea',
      calculate: (qty: number) => {
        const rate = qty > 200 ? 10 : qty > 50 ? 14 : 20;
        return qty * rate;
      },
      calcDisplay: (qty: number) => {
        const rate = qty > 200 ? 10 : qty > 50 ? 14 : 20;
        return `${qty} units @ Volume Tier ($${rate}/ea) = $${(qty * rate).toLocaleString()}.00 / mo`;
      },
      features: ['High-volume incentive structures', 'Automatic tier threshold triggers', 'B2B bulk order support'],
    },
    {
      title: 'Tiered / Graduated',
      type: 'Bracketed',
      desc: 'Units are priced progressively within discrete range brackets as volume expands.',
      example: 'First 50 @ $20, Next 100 @ $12, Beyond @ $8',
      calculate: (qty: number) => {
        let total = 0;
        const t1 = Math.min(qty, 50);
        total += t1 * 20;
        if (qty > 50) {
          const t2 = Math.min(qty - 50, 100);
          total += t2 * 12;
        }
        if (qty > 150) {
          total += (qty - 150) * 8;
        }
        return total;
      },
      calcDisplay: (qty: number) => {
        let total = 0;
        const t1 = Math.min(qty, 50);
        total += t1 * 20;
        if (qty > 50) {
          const t2 = Math.min(qty - 50, 100);
          total += t2 * 12;
        }
        if (qty > 150) {
          total += (qty - 150) * 8;
        }
        return `${qty} units split across 3 graduated brackets = $${total.toLocaleString()}.00 / mo`;
      },
      features: ['Precise margin control', 'Transparent bracketed line items', 'Fair pricing for scaling usage'],
    },
    {
      title: 'Package',
      type: 'Bundled Allotment',
      desc: 'Predefined blocks of units with fixed bundled pricing and overage support.',
      example: 'Block of 50 units @ $450/bundle',
      calculate: (qty: number) => {
        const bundles = Math.ceil(qty / 50);
        return bundles * 450;
      },
      calcDisplay: (qty: number) => {
        const bundles = Math.ceil(qty / 50);
        return `${bundles} package bundle(s) required for ${qty} units = $${(bundles * 450).toLocaleString()}.00 / mo`;
      },
      features: ['Base unit allotments', 'Predictable commitment billing', 'Overage addon compatibility'],
    },
  ];

  // Target Audiences
  const targetAudiences = [
    {
      icon: Briefcase,
      title: 'B2B SaaS Companies',
      desc: 'Automate recurring subscriptions, multi-tier seat licensing, mid-month proration, and instant invoice deliveries.',
    },
    {
      icon: Building2,
      title: 'IT & Managed Services',
      desc: 'Bill complex project milestones, professional service retainers, and hardware/software bundles in unified client statements.',
    },
    {
      icon: Cpu,
      title: 'Usage & API Platforms',
      desc: 'Monetize high-volume transactions, graduated usage brackets, base allotments, and automated overage billing.',
    },
    {
      icon: Users,
      title: 'Sales-Assisted Enterprise',
      desc: 'Empower sales reps with margin-checked CPQ configurations, automated manager approvals, and client quote links.',
    },
  ];

  // How It Works Steps
  const howItWorksSteps = [
    {
      step: '01',
      title: 'Define Products & Pricing',
      desc: 'Set up your catalog items, subscription frequencies, tier rules, and currency preferences in minutes.',
      link: '/catalog',
      linkText: 'Explore Catalog',
    },
    {
      step: '02',
      title: 'Configure Quotes with CPQ',
      desc: 'Generate accurate, margin-guaranteed quotes with discount approval limits and shareable client view links.',
      link: '/cpq',
      linkText: 'Explore CPQ',
    },
    {
      step: '03',
      title: 'Automate Invoicing & Collections',
      desc: 'Convert approved quotes into itemized invoices with 1 click, track payments, and reconcile bank settlements.',
      link: '/invoices',
      linkText: 'Explore Invoicing',
    },
  ];

  // Frequently Asked Questions
  const faqs = [
    {
      q: 'How does Rooman Billing handle custom pricing models?',
      a: 'Rooman Billing supports 5 native pricing models: Flat Fee, Per Unit (seat-based), Volume Discounting, Tiered / Graduated brackets, and Package allotments. You can combine recurring subscriptions with one-time setup fees and usage add-ons inside a single customer agreement.',
    },
    {
      q: 'Can quotes be converted directly into invoices without re-typing data?',
      a: 'Yes. Once a quote is approved or accepted by a client, you can convert it to an invoice with a single click. All line items, tiered calculations, discount allocations, and tax rates transfer automatically with zero data entry errors.',
    },
    {
      q: 'How do discount thresholds and manager approvals work?',
      a: 'In the Control Center, you can set approval policies based on discount percentage or total quote value. When a sales rep creates a quote exceeding the threshold, it is automatically routed to the Approval Center for managerial sign-off before being finalized.',
    },
    {
      q: 'Can we track multi-invoice payment allocations and partial payments?',
      a: 'Absolutely. The Payments module records client remittances, tracks partial disbursements across multiple open invoices, maintains an unallocated balance ledger, and provides an auditable refund log.',
    },
    {
      q: 'Is our organization data strictly separated from other organizations?',
      a: 'Yes. Rooman Billing enforces multi-tenant organization isolation. All customer records, catalog pricing, quotes, invoices, and audit logs are partitioned at the organization layer with granular role-based access control (Admin, Member, Viewer).',
    },
    {
      q: 'Can we import existing customer lists and product catalogs?',
      a: 'Yes. The Data Migration center inside the Control Center provides structured import and export capabilities for customer directories, catalog items, and historical billing transactions.',
    },
  ];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 selection:bg-brand-500 selection:text-white antialiased flex flex-col overflow-x-hidden">
      {/* =========================================================================
          1. NAVBAR
      ========================================================================== */}
      <header className="sticky top-0 z-50 bg-white/95 backdrop-blur-md border-b border-slate-200/80 transition-all shadow-3xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 sm:h-20 flex items-center justify-between">
          {/* Logo */}
          <Link
            to="/"
            className="flex items-center gap-2.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 rounded-lg group"
            aria-label="Rooman Billing Home"
          >
            <RoomanLogo variant="brand" size="md" showBillingBadge />
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden lg:flex items-center gap-7 text-sm font-medium text-slate-600">
            <button
              type="button"
              onClick={() => scrollToSection('features')}
              className="hover:text-brand-600 transition-colors cursor-pointer"
            >
              Product
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('how-it-works')}
              className="hover:text-brand-600 transition-colors cursor-pointer"
            >
              How It Works
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('workflow')}
              className="hover:text-brand-600 transition-colors cursor-pointer"
            >
              Workflow
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('pricing-models')}
              className="hover:text-brand-600 transition-colors cursor-pointer"
            >
              Pricing Models
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('why-rooman')}
              className="hover:text-brand-600 transition-colors cursor-pointer"
            >
              Why Rooman
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('faq')}
              className="hover:text-brand-600 transition-colors cursor-pointer"
            >
              FAQ
            </button>
          </nav>

          {/* Auth CTA Buttons */}
          <div className="hidden sm:flex items-center gap-3">
            {isAuthenticated ? (
              <Button
                variant="primary"
                size="md"
                onClick={() => navigate('/dashboard')}
                className="shadow-sm font-semibold active:scale-[0.98] transition-transform"
              >
                Dashboard
                <ArrowRight className="w-4 h-4 ml-1.5" />
              </Button>
            ) : (
              <>
                <Link to="/login">
                  <Button variant="ghost" size="md" className="text-slate-700 hover:text-slate-900 font-medium">
                    Sign In
                  </Button>
                </Link>
                <Link to="/signup">
                  <Button variant="primary" size="md" className="shadow-sm font-semibold active:scale-[0.98] transition-transform">
                    Get Started
                  </Button>
                </Link>
              </>
            )}
          </div>

          {/* Mobile Menu Button */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="lg:hidden p-2 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            aria-label="Toggle Navigation Menu"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>

        {/* Mobile Dropdown Menu Drawer */}
        {mobileMenuOpen && (
          <div className="lg:hidden border-b border-slate-200 bg-white px-4 pt-3 pb-6 space-y-3 shadow-xl animate-in slide-in-from-top-2 duration-150">
            <button
              type="button"
              onClick={() => scrollToSection('features')}
              className="block w-full text-left py-2 text-sm font-medium text-slate-700 hover:text-brand-600"
            >
              Product & Features
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('how-it-works')}
              className="block w-full text-left py-2 text-sm font-medium text-slate-700 hover:text-brand-600"
            >
              How It Works
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('workflow')}
              className="block w-full text-left py-2 text-sm font-medium text-slate-700 hover:text-brand-600"
            >
              End-to-End Workflow
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('pricing-models')}
              className="block w-full text-left py-2 text-sm font-medium text-slate-700 hover:text-brand-600"
            >
              Pricing Models
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('why-rooman')}
              className="block w-full text-left py-2 text-sm font-medium text-slate-700 hover:text-brand-600"
            >
              Why Rooman
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('faq')}
              className="block w-full text-left py-2 text-sm font-medium text-slate-700 hover:text-brand-600"
            >
              FAQ
            </button>

            <div className="pt-3 border-t border-slate-100 flex flex-col gap-2.5">
              {isAuthenticated ? (
                <Button
                  variant="primary"
                  size="md"
                  onClick={() => {
                    setMobileMenuOpen(false);
                    navigate('/dashboard');
                  }}
                  className="w-full justify-center"
                >
                  Go to Dashboard
                </Button>
              ) : (
                <>
                  <Link to="/login" className="w-full" onClick={() => setMobileMenuOpen(false)}>
                    <Button variant="outline" size="md" className="w-full justify-center">
                      Sign In
                    </Button>
                  </Link>
                  <Link to="/signup" className="w-full" onClick={() => setMobileMenuOpen(false)}>
                    <Button variant="primary" size="md" className="w-full justify-center font-semibold">
                      Get Started
                    </Button>
                  </Link>
                </>
              )}
            </div>
          </div>
        )}
      </header>

      {/* =========================================================================
          2. HERO SECTION
      ========================================================================== */}
      <section className="relative pt-12 pb-16 md:pt-20 md:pb-28 overflow-hidden bg-gradient-to-b from-white via-slate-50 to-slate-50">
        {/* Subtle decorative background gradient circles */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[350px] bg-gradient-to-tr from-brand-100/60 via-blue-50/40 to-emerald-50/30 blur-3xl -z-10 pointer-events-none rounded-full" />

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto">
            {/* Pill Tag */}
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-blue-50 border border-blue-200/70 text-brand-700 text-xs font-semibold uppercase tracking-wider mb-6 shadow-3xs hover:bg-blue-100/80 transition-colors">
              <Sparkles className="w-3.5 h-3.5 text-brand-600" />
              <span>ROOMAN BILLING &bull; ENTERPRISE REVENUE ENGINE</span>
            </div>

            {/* Headline */}
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-slate-900 tracking-tight leading-[1.12]">
              Powerful billing.{' '}
              <span className="bg-clip-text text-transparent bg-gradient-to-r from-brand-600 via-brand-700 to-blue-900">
                Smarter business.
              </span>
            </h1>

            {/* Supporting text */}
            <p className="mt-5 text-lg sm:text-xl font-medium text-slate-700 leading-relaxed">
              Complete billing and subscription management built for modern businesses.
            </p>

            {/* Description */}
            <p className="mt-3 text-sm sm:text-base text-slate-500 max-w-2xl mx-auto leading-relaxed">
              Manage products, pricing, quotes, invoices, payments, subscriptions, customers and revenue — all from one intelligent billing platform.
            </p>

            {/* CTA Buttons */}
            <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3.5">
              <Link to={isAuthenticated ? '/dashboard' : '/signup'} className="w-full sm:w-auto">
                <Button
                  variant="primary"
                  size="lg"
                  className="w-full sm:w-auto font-semibold px-8 py-3.5 text-base shadow-elevated group active:scale-[0.98] transition-all"
                >
                  Get Started
                  <ArrowRight className="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" />
                </Button>
              </Link>
              <button
                type="button"
                onClick={() => scrollToSection('features')}
                className="w-full sm:w-auto inline-flex items-center justify-center px-6 py-3.5 rounded-lg border border-slate-300/80 bg-white text-slate-700 font-medium hover:bg-slate-50 hover:text-slate-900 shadow-xs transition-all active:scale-[0.98] cursor-pointer text-sm sm:text-base"
              >
                Explore Platform
              </button>
            </div>

            {/* Trust Micro-Badges */}
            <div className="mt-7 flex flex-wrap items-center justify-center gap-6 text-xs text-slate-500 font-medium">
              <span className="inline-flex items-center gap-1.5">
                <Check className="w-4 h-4 text-emerald-600" />
                Zero setup friction
              </span>
              <span className="inline-flex items-center gap-1.5">
                <Check className="w-4 h-4 text-emerald-600" />
                5 native pricing models
              </span>
              <span className="inline-flex items-center gap-1.5">
                <Check className="w-4 h-4 text-emerald-600" />
                Automated quote-to-cash
              </span>
            </div>
          </div>

          {/* =========================================================================
              HERO VISUAL: Interactive Rooman Billing Product UI Dashboard Mockup
          ========================================================================== */}
          <div className="mt-14 max-w-5xl mx-auto">
            <div className="rounded-2xl bg-white border border-slate-200/90 shadow-2xl overflow-hidden ring-1 ring-slate-900/5 transition-all">
              {/* Browser / Application Top Chrome */}
              <div className="bg-slate-100/90 border-b border-slate-200 px-4 py-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-rose-400" />
                  <div className="w-3 h-3 rounded-full bg-amber-400" />
                  <div className="w-3 h-3 rounded-full bg-emerald-400" />
                  <span className="ml-3 text-xs font-mono text-slate-400 hidden sm:inline-block">
                    https://billing.rooman.com/dashboard
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {/* Interactive toggle between views */}
                  <div className="inline-flex rounded-lg p-0.5 bg-slate-200/70 text-[11px] font-medium text-slate-700">
                    <button
                      type="button"
                      onClick={() => setActiveTabVisual('transactions')}
                      className={`px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                        activeTabVisual === 'transactions' ? 'bg-white text-brand-700 shadow-3xs font-semibold' : 'hover:text-slate-900'
                      }`}
                    >
                      Live Transactions
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTabVisual('cpq')}
                      className={`px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                        activeTabVisual === 'cpq' ? 'bg-white text-brand-700 shadow-3xs font-semibold' : 'hover:text-slate-900'
                      }`}
                    >
                      CPQ Pricing Engine
                    </button>
                  </div>
                  <div className="hidden sm:flex items-center gap-1.5 text-xs font-medium text-slate-600 bg-white px-2.5 py-1 rounded-md border border-slate-200 shadow-3xs">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    <span>Live Operations</span>
                  </div>
                </div>
              </div>

              {/* Inside Dashboard Mockup View */}
              <div className="p-4 sm:p-6 lg:p-8 bg-slate-50 space-y-6">
                {/* Metric Summary Ribbon with subtle animated values */}
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                  <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-3xs hover:border-slate-300 transition-colors">
                    <div className="flex items-center justify-between text-xs text-slate-500 font-medium">
                      <span>Monthly Recurring (MRR)</span>
                      <TrendingUp className="w-3.5 h-3.5 text-emerald-600" />
                    </div>
                    <div className="mt-1.5 text-xl sm:text-2xl font-bold text-slate-900 tabular-nums">
                      $128,450
                    </div>
                    <div className="mt-1 flex items-center gap-1 text-[11px] text-emerald-600 font-semibold">
                      <span>+14.2%</span>
                      <span className="text-slate-400 font-normal">vs last month</span>
                    </div>
                  </div>

                  <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-3xs hover:border-slate-300 transition-colors">
                    <div className="flex items-center justify-between text-xs text-slate-500 font-medium">
                      <span>Active Subscriptions</span>
                      <Users className="w-3.5 h-3.5 text-brand-600" />
                    </div>
                    <div className="mt-1.5 text-xl sm:text-2xl font-bold text-slate-900 tabular-nums">
                      1,420
                    </div>
                    <div className="mt-1 flex items-center gap-1 text-[11px] text-brand-600 font-semibold">
                      <span>99.2%</span>
                      <span className="text-slate-400 font-normal">retention rate</span>
                    </div>
                  </div>

                  <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-3xs hover:border-slate-300 transition-colors">
                    <div className="flex items-center justify-between text-xs text-slate-500 font-medium">
                      <span>Invoiced This Month</span>
                      <Receipt className="w-3.5 h-3.5 text-purple-600" />
                    </div>
                    <div className="mt-1.5 text-xl sm:text-2xl font-bold text-slate-900 tabular-nums">
                      $489,200
                    </div>
                    <div className="mt-1 flex items-center gap-1 text-[11px] text-slate-500">
                      <span className="font-semibold text-slate-700">184</span>
                      <span>invoices generated</span>
                    </div>
                  </div>

                  <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-3xs hover:border-slate-300 transition-colors">
                    <div className="flex items-center justify-between text-xs text-slate-500 font-medium">
                      <span>Collection Rate</span>
                      <CreditCard className="w-3.5 h-3.5 text-emerald-600" />
                    </div>
                    <div className="mt-1.5 text-xl sm:text-2xl font-bold text-slate-900 tabular-nums">
                      98.4%
                    </div>
                    <div className="mt-1 flex items-center gap-1 text-[11px] text-emerald-600 font-semibold">
                      <span>&lt; 3.2 days</span>
                      <span className="text-slate-400 font-normal">avg settlement</span>
                    </div>
                  </div>
                </div>

                {/* Switchable Interactive Dashboard View */}
                {activeTabVisual === 'transactions' ? (
                  <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 animate-in fade-in duration-200">
                    {/* Left Column: Recent Pipeline Activity */}
                    <div className="lg:col-span-7 bg-white p-4 sm:p-5 rounded-xl border border-slate-200/80 shadow-3xs">
                      <div className="flex items-center justify-between mb-4">
                        <div>
                          <h4 className="text-sm font-bold text-slate-900">Recent Revenue Transactions</h4>
                          <p className="text-xs text-slate-500">Real-time quote, invoice & payment tracking</p>
                        </div>
                        <span className="text-[11px] font-semibold text-brand-600 bg-brand-50 px-2 py-0.5 rounded border border-brand-100">
                          Live Ledger
                        </span>
                      </div>

                      <div className="divide-y divide-slate-100 text-xs">
                        <div className="py-2.5 flex items-center justify-between hover:bg-slate-50/80 px-1.5 rounded-lg transition-colors">
                          <div className="flex items-center gap-3">
                            <div className="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center font-bold text-[10px]">
                              INV
                            </div>
                            <div>
                              <div className="font-semibold text-slate-900">Acme Cloud Corp</div>
                              <div className="text-[11px] text-slate-400">INV-2026-0891 &bull; Tiered Enterprise Plan</div>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="font-bold text-slate-900 tabular-nums">$14,500.00</div>
                            <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                              Paid
                            </span>
                          </div>
                        </div>

                        <div className="py-2.5 flex items-center justify-between hover:bg-slate-50/80 px-1.5 rounded-lg transition-colors">
                          <div className="flex items-center gap-3">
                            <div className="w-7 h-7 rounded-lg bg-blue-50 text-brand-700 flex items-center justify-center font-bold text-[10px]">
                              QTE
                            </div>
                            <div>
                              <div className="font-semibold text-slate-900">TechNova Systems</div>
                              <div className="text-[11px] text-slate-400">QT-2026-0412 &bull; CPQ Configured Bundle</div>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="font-bold text-slate-900 tabular-nums">$28,900.00</div>
                            <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                              Pending Approval
                            </span>
                          </div>
                        </div>

                        <div className="py-2.5 flex items-center justify-between hover:bg-slate-50/80 px-1.5 rounded-lg transition-colors">
                          <div className="flex items-center gap-3">
                            <div className="w-7 h-7 rounded-lg bg-purple-50 text-purple-700 flex items-center justify-center font-bold text-[10px]">
                              SUB
                            </div>
                            <div>
                              <div className="font-semibold text-slate-900">Vertex Global Logistics</div>
                              <div className="text-[11px] text-slate-400">SUB-9021 &bull; Per-Unit Volume License</div>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="font-bold text-slate-900 tabular-nums">$6,450.00 / mo</div>
                            <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[10px] font-bold bg-blue-50 text-brand-700 border border-blue-200">
                              Active
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Right Column: Mini Revenue Stream Overview */}
                    <div className="lg:col-span-5 bg-gradient-to-br from-slate-900 to-slate-800 text-white p-4 sm:p-5 rounded-xl shadow-3xs flex flex-col justify-between">
                      <div>
                        <div className="flex items-center justify-between mb-3">
                          <span className="text-xs font-semibold text-brand-300 uppercase tracking-wider flex items-center gap-1.5">
                            <Workflow className="w-3.5 h-3.5 text-amber-400" />
                            Connected Lifecycle
                          </span>
                          <span className="text-[10px] bg-slate-700/80 px-2 py-0.5 rounded text-slate-300">
                            Automated
                          </span>
                        </div>
                        <div className="text-sm font-semibold text-slate-100">
                          Deterministic Quote-to-Cash
                        </div>
                        <p className="text-xs text-slate-400 mt-1">
                          Catalog items flow directly into CPQ quotes, converting to invoices and reconciled settlements without manual data entry.
                        </p>

                        <div className="mt-4 bg-slate-800/80 rounded-lg p-3 border border-slate-700/80 text-xs space-y-2 font-mono">
                          <div className="flex justify-between text-slate-300">
                            <span>Base Seats (120 qty)</span>
                            <span className="font-bold">$3,600.00</span>
                          </div>
                          <div className="flex justify-between text-slate-300">
                            <span>Usage Tier (Bracket 2)</span>
                            <span className="font-bold">$850.00</span>
                          </div>
                          <div className="flex justify-between text-emerald-400 border-t border-slate-700 pt-1 font-bold">
                            <span>Calculated Total</span>
                            <span>$4,450.00 / mo</span>
                          </div>
                        </div>
                      </div>

                      <div className="mt-4 pt-3 border-t border-slate-700/70 flex items-center justify-between text-[11px] text-slate-400">
                        <span>✓ Margin Protected</span>
                        <span>✓ Audit Verified</span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-3xs animate-in fade-in duration-200">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
                      <div>
                        <h4 className="text-sm font-bold text-slate-900">CPQ Live Calculation Sandbox</h4>
                        <p className="text-xs text-slate-500">Configure bundles and test automated discount rules in real-time</p>
                      </div>
                      <Link to="/cpq">
                        <Button variant="outline" size="sm" className="font-semibold text-xs">
                          Open Full CPQ
                          <ArrowRight className="w-3.5 h-3.5 ml-1" />
                        </Button>
                      </Link>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4 text-xs">
                      <div className="p-3 bg-slate-50 rounded-lg border border-slate-200/70">
                        <span className="text-slate-500 font-medium">Selected Product</span>
                        <div className="font-bold text-slate-900 mt-1">Enterprise Platform Tier</div>
                        <span className="text-[11px] text-brand-600 font-semibold">$1,200.00 base / mo</span>
                      </div>
                      <div className="p-3 bg-slate-50 rounded-lg border border-slate-200/70">
                        <span className="text-slate-500 font-medium">Seat Allotment (50 Users)</span>
                        <div className="font-bold text-slate-900 mt-1">Volume Discount Applied (15%)</div>
                        <span className="text-[11px] text-emerald-600 font-semibold">$637.50 / mo (Saved $112.50)</span>
                      </div>
                      <div className="p-3 bg-slate-50 rounded-lg border border-slate-200/70">
                        <span className="text-slate-500 font-medium">Governance Check</span>
                        <div className="font-bold text-emerald-700 mt-1">Auto-Approved</div>
                        <span className="text-[11px] text-slate-500">Margin: 68.4% &ge; 50.0% min</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          3. VALUE STRIP
      ========================================================================== */}
      <section className="py-8 bg-white border-y border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
            <div className="shrink-0 text-center lg:text-left">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Core Capabilities
              </span>
              <h2 className="text-base sm:text-lg font-bold text-slate-900">
                Everything you need to manage your revenue
              </h2>
            </div>

            {/* 6 Value Pillars linking directly to respective routes */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4">
              <Link to="/catalog" className="flex items-center gap-2.5 p-2.5 rounded-lg bg-slate-50 hover:bg-blue-50/60 border border-slate-200/80 hover:border-brand-300 transition-all group">
                <Layers className="w-4 h-4 text-brand-600 shrink-0 group-hover:scale-110 transition-transform" />
                <span className="text-xs font-semibold text-slate-800 group-hover:text-brand-700">Product Catalog</span>
              </Link>
              <Link to="/plans-pricing" className="flex items-center gap-2.5 p-2.5 rounded-lg bg-slate-50 hover:bg-blue-50/60 border border-slate-200/80 hover:border-brand-300 transition-all group">
                <Sliders className="w-4 h-4 text-brand-600 shrink-0 group-hover:scale-110 transition-transform" />
                <span className="text-xs font-semibold text-slate-800 group-hover:text-brand-700">Flexible Pricing</span>
              </Link>
              <Link to="/cpq" className="flex items-center gap-2.5 p-2.5 rounded-lg bg-slate-50 hover:bg-blue-50/60 border border-slate-200/80 hover:border-brand-300 transition-all group">
                <Cpu className="w-4 h-4 text-brand-600 shrink-0 group-hover:scale-110 transition-transform" />
                <span className="text-xs font-semibold text-slate-800 group-hover:text-brand-700">CPQ</span>
              </Link>
              <Link to="/quotes" className="flex items-center gap-2.5 p-2.5 rounded-lg bg-slate-50 hover:bg-blue-50/60 border border-slate-200/80 hover:border-brand-300 transition-all group">
                <FileText className="w-4 h-4 text-brand-600 shrink-0 group-hover:scale-110 transition-transform" />
                <span className="text-xs font-semibold text-slate-800 group-hover:text-brand-700">Quotes</span>
              </Link>
              <Link to="/invoices" className="flex items-center gap-2.5 p-2.5 rounded-lg bg-slate-50 hover:bg-blue-50/60 border border-slate-200/80 hover:border-brand-300 transition-all group">
                <Receipt className="w-4 h-4 text-brand-600 shrink-0 group-hover:scale-110 transition-transform" />
                <span className="text-xs font-semibold text-slate-800 group-hover:text-brand-700">Invoices</span>
              </Link>
              <Link to="/payments" className="flex items-center gap-2.5 p-2.5 rounded-lg bg-slate-50 hover:bg-blue-50/60 border border-slate-200/80 hover:border-brand-300 transition-all group">
                <CreditCard className="w-4 h-4 text-brand-600 shrink-0 group-hover:scale-110 transition-transform" />
                <span className="text-xs font-semibold text-slate-800 group-hover:text-brand-700">Payments</span>
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          4. HOW IT WORKS
      ========================================================================== */}
      <section id="how-it-works" className="py-20 bg-slate-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="text-xs font-bold uppercase tracking-wider text-brand-600 bg-brand-50 px-3 py-1 rounded-full border border-brand-200">
              Simple 3-Step Setup
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
              How Rooman Billing Works
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Go from catalog definition to active invoice collection in three straightforward stages.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {howItWorksSteps.map((stepItem) => (
              <div
                key={stepItem.step}
                className="bg-white rounded-2xl p-7 border border-slate-200/90 shadow-card hover:shadow-elevated transition-all flex flex-col justify-between relative group"
              >
                <div>
                  <div className="w-12 h-12 rounded-xl bg-brand-50 text-brand-600 font-extrabold text-lg flex items-center justify-center mb-5 border border-brand-100 group-hover:bg-brand-600 group-hover:text-white transition-colors">
                    {stepItem.step}
                  </div>
                  <h3 className="text-xl font-bold text-slate-900">{stepItem.title}</h3>
                  <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                    {stepItem.desc}
                  </p>
                </div>
                <div className="mt-6 pt-4 border-t border-slate-100">
                  <Link to={stepItem.link}>
                    <Button variant="ghost" size="sm" className="w-full justify-between text-brand-600 hover:text-brand-700 font-semibold">
                      <span>{stepItem.linkText}</span>
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* =========================================================================
          5. FEATURE SHOWCASE
      ========================================================================== */}
      <section id="features" className="py-20 bg-white border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="text-xs font-bold uppercase tracking-wider text-brand-600 bg-brand-50 px-3 py-1 rounded-full border border-brand-200">
              Complete Feature Suite
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
              Everything your billing team needs.
            </h2>
            <p className="mt-3 text-base text-slate-600">
              End-to-end tools designed to handle every facet of modern recurring billing, contract configuration, and financial control.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8">
            {/* 1. Product & Pricing */}
            <div className="bg-slate-50/50 rounded-2xl p-6 sm:p-7 border border-slate-200/90 shadow-card hover:shadow-elevated transition-all flex flex-col justify-between hover:bg-white">
              <div>
                <div className="w-11 h-11 rounded-xl bg-blue-50 text-brand-600 flex items-center justify-center mb-5 border border-blue-100">
                  <Layers className="w-6 h-6" />
                </div>
                <h3 className="text-xl font-bold text-slate-900">Product & Pricing</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                  Build products, services, plans and bundles with flexible pricing models.
                </p>
                <ul className="mt-4 space-y-2 text-xs text-slate-600">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Tiered, graduated, per-unit & volume pricing
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Multi-currency & billing frequency support
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Add-ons, one-time fees and custom plan rules
                  </li>
                </ul>
              </div>
              <div className="mt-6 pt-5 border-t border-slate-200/70">
                <Link to="/catalog">
                  <Button variant="ghost" size="sm" className="w-full justify-between text-brand-600 hover:text-brand-700">
                    <span>Explore Catalog</span>
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </Link>
              </div>
            </div>

            {/* 2. Quotes & Invoicing */}
            <div className="bg-slate-50/50 rounded-2xl p-6 sm:p-7 border border-slate-200/90 shadow-card hover:shadow-elevated transition-all flex flex-col justify-between hover:bg-white">
              <div>
                <div className="w-11 h-11 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center mb-5 border border-purple-100">
                  <Receipt className="w-6 h-6" />
                </div>
                <h3 className="text-xl font-bold text-slate-900">Quotes & Invoicing</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                  Create professional quotes and invoices and manage the complete billing lifecycle.
                </p>
                <ul className="mt-4 space-y-2 text-xs text-slate-600">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    1-click quote-to-invoice automated conversion
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Sequential auto-numbering & custom payment terms
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Shareable public payment and quote links
                  </li>
                </ul>
              </div>
              <div className="mt-6 pt-5 border-t border-slate-200/70">
                <Link to="/invoices">
                  <Button variant="ghost" size="sm" className="w-full justify-between text-brand-600 hover:text-brand-700">
                    <span>Manage Invoices</span>
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </Link>
              </div>
            </div>

            {/* 3. Payments */}
            <div className="bg-slate-50/50 rounded-2xl p-6 sm:p-7 border border-slate-200/90 shadow-card hover:shadow-elevated transition-all flex flex-col justify-between hover:bg-white">
              <div>
                <div className="w-11 h-11 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center mb-5 border border-emerald-100">
                  <CreditCard className="w-6 h-6" />
                </div>
                <h3 className="text-xl font-bold text-slate-900">Payments</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                  Track payments, allocations, refunds and outstanding balances.
                </p>
                <ul className="mt-4 space-y-2 text-xs text-slate-600">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Multi-invoice payment allocations & partial payouts
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Comprehensive refund ledger and tracking
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Real-time customer outstanding balances
                  </li>
                </ul>
              </div>
              <div className="mt-6 pt-5 border-t border-slate-200/70">
                <Link to="/payments">
                  <Button variant="ghost" size="sm" className="w-full justify-between text-brand-600 hover:text-brand-700">
                    <span>View Payments</span>
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </Link>
              </div>
            </div>

            {/* 4. Customer Management */}
            <div className="bg-slate-50/50 rounded-2xl p-6 sm:p-7 border border-slate-200/90 shadow-card hover:shadow-elevated transition-all flex flex-col justify-between hover:bg-white">
              <div>
                <div className="w-11 h-11 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center mb-5 border border-amber-100">
                  <Users className="w-6 h-6" />
                </div>
                <h3 className="text-xl font-bold text-slate-900">Customer Management</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                  Manage customer accounts, billing information and transactions.
                </p>
                <ul className="mt-4 space-y-2 text-xs text-slate-600">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Unified customer billing profiles and contacts
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Complete historical invoices, quotes & payment audit
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Configurable credit limits & currency defaults
                  </li>
                </ul>
              </div>
              <div className="mt-6 pt-5 border-t border-slate-200/70">
                <Link to="/customers">
                  <Button variant="ghost" size="sm" className="w-full justify-between text-brand-600 hover:text-brand-700">
                    <span>Manage Customers</span>
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </Link>
              </div>
            </div>

            {/* 5. Business Intelligence */}
            <div className="bg-slate-50/50 rounded-2xl p-6 sm:p-7 border border-slate-200/90 shadow-card hover:shadow-elevated transition-all flex flex-col justify-between hover:bg-white">
              <div>
                <div className="w-11 h-11 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center mb-5 border border-indigo-100">
                  <BarChart3 className="w-6 h-6" />
                </div>
                <h3 className="text-xl font-bold text-slate-900">Business Intelligence</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                  Understand revenue, receivables and billing performance.
                </p>
                <ul className="mt-4 space-y-2 text-xs text-slate-600">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Real-time MRR, ARR & revenue growth indicators
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Aging receivables and collection velocity reports
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Subscription retention and churn analytics
                  </li>
                </ul>
              </div>
              <div className="mt-6 pt-5 border-t border-slate-200/70">
                <Link to="/dashboard">
                  <Button variant="ghost" size="sm" className="w-full justify-between text-brand-600 hover:text-brand-700">
                    <span>Overview Dashboard</span>
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </Link>
              </div>
            </div>

            {/* 6. Automation & Control */}
            <div className="bg-slate-50/50 rounded-2xl p-6 sm:p-7 border border-slate-200/90 shadow-card hover:shadow-elevated transition-all flex flex-col justify-between hover:bg-white">
              <div>
                <div className="w-11 h-11 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center mb-5 border border-rose-100">
                  <Shield className="w-6 h-6" />
                </div>
                <h3 className="text-xl font-bold text-slate-900">Automation & Control</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                  Manage approvals, reconciliation, audit trails and billing operations.
                </p>
                <ul className="mt-4 space-y-2 text-xs text-slate-600">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Centralized Action Center for pending finance tasks
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Multi-level discount approval workflows
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    Granular, timestamped audit log of all adjustments
                  </li>
                </ul>
              </div>
              <div className="mt-6 pt-5 border-t border-slate-200/70">
                <Link to="/control-center/action-center">
                  <Button variant="ghost" size="sm" className="w-full justify-between text-brand-600 hover:text-brand-700">
                    <span>Control Center</span>
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          6. END-TO-END BILLING FLOW (ANIMATED / INTERACTIVE)
      ========================================================================== */}
      <section id="workflow" className="py-20 bg-slate-50 border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-14">
            <span className="text-xs font-bold uppercase tracking-wider text-brand-600 bg-brand-50 px-3 py-1 rounded-full border border-brand-200">
              Unified Revenue Architecture
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
              From quote to cash — one connected workflow
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Rooman Billing connects every phase of the revenue lifecycle. No broken handoffs, no manual re-keying.
            </p>

            {/* Play / Pause Toggle */}
            <div className="mt-4 inline-flex items-center gap-2 text-xs text-slate-500 bg-white px-3 py-1 rounded-full border border-slate-200 shadow-3xs">
              <button
                type="button"
                onClick={() => setIsAutoPlayingWorkflow(!isAutoPlayingWorkflow)}
                className="inline-flex items-center gap-1 font-semibold text-brand-600 hover:text-brand-700 cursor-pointer"
              >
                {isAutoPlayingWorkflow ? (
                  <>
                    <Pause className="w-3.5 h-3.5" /> Pause Auto-Tour
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5" /> Play Auto-Tour
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Stepped interactive visual bar with active state indicator */}
          <div className="bg-white p-3 sm:p-4 rounded-2xl border border-slate-200 mb-8 overflow-x-auto scrollbar-none shadow-3xs">
            <div className="flex items-center justify-between min-w-[760px] gap-2">
              {workflowSteps.map((step, idx) => {
                const isActive = activeWorkflowTab === idx;
                return (
                  <button
                    key={step.id}
                    onClick={() => {
                      setIsAutoPlayingWorkflow(false);
                      setActiveWorkflowTab(idx);
                    }}
                    className={`flex-1 py-3 px-3 rounded-xl text-center transition-all cursor-pointer ${
                      isActive
                        ? 'bg-brand-600 text-white shadow-md scale-[1.02]'
                        : 'bg-slate-50 text-slate-700 hover:bg-slate-100 border border-slate-200/80'
                    }`}
                  >
                    <div className={`text-[10px] font-mono font-bold ${isActive ? 'text-brand-200' : 'text-slate-400'}`}>
                      {step.step}
                    </div>
                    <div className="text-xs font-bold mt-0.5 whitespace-nowrap">{step.label}</div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Selected Step Detailed Card */}
          <div className="bg-slate-900 text-white rounded-2xl p-6 sm:p-10 shadow-xl border border-slate-800 transition-all">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
              <div className="lg:col-span-7">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-500/20 text-brand-300 text-xs font-semibold border border-brand-500/30 mb-4">
                  <span>Stage {workflowSteps[activeWorkflowTab].step} of 09</span>
                  <span>&bull;</span>
                  <span>{workflowSteps[activeWorkflowTab].badge}</span>
                </div>
                <h3 className="text-2xl sm:text-3xl font-bold text-white">
                  {workflowSteps[activeWorkflowTab].title}
                </h3>
                <p className="mt-3 text-slate-300 text-base leading-relaxed">
                  {workflowSteps[activeWorkflowTab].desc}
                </p>

                {/* Key feature pills for this step */}
                <div className="mt-4 flex flex-wrap gap-2">
                  {workflowSteps[activeWorkflowTab].details.map((detail, dIdx) => (
                    <span key={dIdx} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-800 text-slate-300 text-xs border border-slate-700">
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                      {detail}
                    </span>
                  ))}
                </div>

                <div className="mt-6 flex items-center gap-4">
                  <Link to={workflowSteps[activeWorkflowTab].route}>
                    <Button variant="primary" size="md" className="font-semibold shadow-sm active:scale-[0.98]">
                      Open {workflowSteps[activeWorkflowTab].label} in App
                      <ArrowRight className="w-4 h-4 ml-1.5" />
                    </Button>
                  </Link>
                  <span className="text-xs text-slate-400 hidden sm:inline">
                    Automatic data flow without duplicate entry
                  </span>
                </div>
              </div>

              <div className="lg:col-span-5 bg-slate-800/90 rounded-xl p-5 border border-slate-700 text-xs font-mono space-y-3">
                <div className="flex justify-between items-center pb-2 border-b border-slate-700 text-slate-400">
                  <span>Lifecycle Pipeline Status</span>
                  <span className="text-emerald-400 flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                    Connected
                  </span>
                </div>
                <div className="text-slate-200 space-y-2">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Current Node:</span>
                    <span className="font-bold text-white">{workflowSteps[activeWorkflowTab].label}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Next Destination:</span>
                    <span className="text-brand-300">
                      {workflowSteps[(activeWorkflowTab + 1) % workflowSteps.length].label} &rarr;
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Schema Validation:</span>
                    <span className="text-emerald-400">Strict Multi-Tenant Check</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Audit Status:</span>
                    <span className="text-slate-300">Timestamped Event Logged</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          7. PRICING MODELS (INTERACTIVE SIMULATOR)
      ========================================================================== */}
      <section id="pricing-models" className="py-20 bg-white border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-14">
            <span className="text-xs font-bold uppercase tracking-wider text-brand-600 bg-brand-50 px-3 py-1 rounded-full border border-brand-200">
              Monetization Flexibility
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
              Pricing that adapts to your business
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Rooman Billing natively accommodates five distinct monetization models without custom engineering.
            </p>
          </div>

          {/* 5 Pricing Model Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-5">
            {pricingModels.map((model, idx) => (
              <div
                key={model.title}
                onClick={() => setSelectedPricingModel(idx)}
                className={`rounded-2xl p-5 border transition-all cursor-pointer flex flex-col justify-between ${
                  selectedPricingModel === idx
                    ? 'bg-blue-50/40 border-brand-500 ring-2 ring-brand-500/20 shadow-elevated scale-[1.02]'
                    : 'bg-white border-slate-200/90 shadow-card hover:border-slate-300 hover:shadow-subtle'
                }`}
              >
                <div>
                  <div className="inline-block px-2 py-0.5 rounded text-[11px] font-bold bg-slate-100 text-slate-700 mb-3">
                    {model.type}
                  </div>
                  <h3 className="text-lg font-bold text-slate-900">{model.title}</h3>
                  <p className="mt-2 text-xs text-slate-600 leading-relaxed min-h-[48px]">
                    {model.desc}
                  </p>

                  <div className="mt-4 p-2.5 rounded-lg bg-white border border-slate-200/70 text-[11px] font-mono text-slate-700">
                    <span className="text-slate-400 block text-[10px]">Model Structure:</span>
                    {model.example}
                  </div>

                  <ul className="mt-4 space-y-1.5 text-[11px] text-slate-500">
                    {model.features.map((feat, fIdx) => (
                      <li key={fIdx} className="flex items-center gap-1.5">
                        <Check className="w-3.5 h-3.5 text-brand-600 shrink-0" />
                        <span>{feat}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="mt-5 pt-3 border-t border-slate-200/60 text-center">
                  <span className={`text-xs font-semibold ${selectedPricingModel === idx ? 'text-brand-700' : 'text-slate-500'}`}>
                    {selectedPricingModel === idx ? 'Active Simulation' : 'Click to Simulate'}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Interactive Pricing Model Live Simulator Ribbon */}
          <div className="mt-10 bg-slate-50 rounded-2xl p-6 border border-slate-200 shadow-3xs max-w-4xl mx-auto">
            <div className="flex flex-col sm:flex-row items-center justify-between gap-6">
              <div className="w-full sm:w-1/2">
                <div className="flex justify-between items-center text-xs font-medium text-slate-700 mb-2">
                  <span>Simulate Units / License Seats:</span>
                  <span className="font-bold font-mono text-brand-700 text-sm">{simulatorQuantity} units</span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="500"
                  value={simulatorQuantity}
                  onChange={(e) => setSimulatorQuantity(Number(e.target.value))}
                  className="w-full accent-brand-600 h-2 bg-slate-200 rounded-lg cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                  <span>1 unit</span>
                  <span>250 units</span>
                  <span>500 units</span>
                </div>
              </div>

              <div className="w-full sm:w-1/2 bg-white p-4 rounded-xl border border-slate-200 shadow-3xs">
                <div className="text-xs text-slate-500 font-medium">
                  {pricingModels[selectedPricingModel].title} Calculation:
                </div>
                <div className="text-sm font-mono font-bold text-slate-900 mt-1">
                  {typeof pricingModels[selectedPricingModel].calcDisplay === 'function'
                    ? pricingModels[selectedPricingModel].calcDisplay(simulatorQuantity)
                    : pricingModels[selectedPricingModel].calcDisplay}
                </div>
              </div>
            </div>
          </div>

          {/* Pricing CTA */}
          <div className="mt-10 text-center flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link to="/plans-pricing">
              <Button variant="primary" size="lg" className="font-semibold shadow-sm active:scale-[0.98]">
                Explore Plans & Pricing
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </Link>
            <Link to="/plans-pricing/simulator">
              <Button variant="outline" size="lg" className="font-medium">
                Open Full Pricing Simulator
                <ArrowUpRight className="w-4 h-4 ml-1.5" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* =========================================================================
          8. WHY ROOMAN BILLING?
      ========================================================================== */}
      <section id="why-rooman" className="py-20 bg-slate-50 border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="text-xs font-bold uppercase tracking-wider text-brand-600 bg-brand-50 px-3 py-1 rounded-full border border-brand-200">
              Architectural Difference
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
              Why Choose Rooman Billing?
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Built from the ground up as a unified revenue engine, replacing fragmented point solutions and error-prone manual spreadsheets.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-card hover:shadow-elevated transition-all">
              <div className="w-10 h-10 rounded-xl bg-blue-50 text-brand-600 flex items-center justify-center mb-4">
                <Server className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">One Unified System</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Catalog, pricing rules, quotes, invoices, payments, and bank reconciliation live in one shared relational ledger.
              </p>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-card hover:shadow-elevated transition-all">
              <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center mb-4">
                <Calculator className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">Zero-Loss Accuracy</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Deterministic calculation logic preserves exact pennies and discounts across complex graduated brackets and partial terms.
              </p>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-card hover:shadow-elevated transition-all">
              <div className="w-10 h-10 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center mb-4">
                <Shield className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">Built-In Governance</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Sales discount limits and managerial approval workflows prevent unauthorized pricing commitments before quote generation.
              </p>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-card hover:shadow-elevated transition-all">
              <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center mb-4">
                <Lock className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">Enterprise Isolation</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Strict organization-level data segregation ensures your business pricing and customer profiles remain completely private.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          9. WHO IT'S BUILT FOR
      ========================================================================== */}
      <section className="py-20 bg-white border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="text-xs font-bold uppercase tracking-wider text-brand-600 bg-brand-50 px-3 py-1 rounded-full border border-brand-200">
              Built for Modern Commerce
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
              Who Is Rooman Billing For?
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Engineered to support modern business models from self-serve SaaS to complex, high-touch contract billing.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {targetAudiences.map((audience, aIdx) => {
              const IconComp = audience.icon;
              return (
                <div
                  key={aIdx}
                  className="bg-slate-50/70 rounded-2xl p-6 border border-slate-200/90 shadow-3xs hover:bg-white hover:shadow-card transition-all flex flex-col justify-between"
                >
                  <div>
                    <div className="w-10 h-10 rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center mb-4">
                      <IconComp className="w-5 h-5" />
                    </div>
                    <h3 className="text-lg font-bold text-slate-900">{audience.title}</h3>
                    <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                      {audience.desc}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* =========================================================================
          10. CUSTOMER EXPERIENCE
      ========================================================================== */}
      <section className="py-20 bg-slate-50 border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-14">
            <span className="text-xs font-bold uppercase tracking-wider text-brand-600 bg-brand-50 px-3 py-1 rounded-full border border-brand-200">
              Buyer Centricity
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
              A better experience for your customers
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Deliver transparent, frictionless invoicing and payment experiences that build customer confidence and reduce payment delays.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8">
            {/* Card 1: Customer Portal */}
            <div className="bg-white rounded-2xl p-6 sm:p-7 border border-slate-200 shadow-3xs flex flex-col justify-between relative overflow-hidden">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="w-10 h-10 rounded-xl bg-blue-100 text-brand-700 flex items-center justify-center">
                    <Building2 className="w-5 h-5" />
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
                    Coming Soon
                  </span>
                </div>
                <h3 className="text-xl font-bold text-slate-900">Customer Portal</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                  Dedicated self-service interface for your clients to view statements, download PDFs, and update payment methods.
                </p>
              </div>
              <div className="mt-6 pt-4 border-t border-slate-100 text-xs text-slate-500 font-medium">
                Self-service billing & subscription control
              </div>
            </div>

            {/* Card 2: Hosted Payment Pages */}
            <div className="bg-white rounded-2xl p-6 sm:p-7 border border-brand-200 shadow-card flex flex-col justify-between relative">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center">
                    <CreditCard className="w-5 h-5" />
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                    Active
                  </span>
                </div>
                <h3 className="text-xl font-bold text-slate-900">Hosted Payment Pages</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                  Direct, tokenized links for customers to view and pay specific invoices instantly without logging into an account.
                </p>
              </div>
              <div className="mt-6 pt-4 border-t border-slate-100 text-xs text-brand-600 font-semibold flex items-center gap-1">
                <span>Integrated with invoice share links</span>
                <Check className="w-3.5 h-3.5" />
              </div>
            </div>

            {/* Card 3: Simple Billing & Payment Experience */}
            <div className="bg-white rounded-2xl p-6 sm:p-7 border border-slate-200 shadow-3xs flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="w-10 h-10 rounded-xl bg-purple-100 text-purple-700 flex items-center justify-center">
                    <Sparkles className="w-5 h-5" />
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                    Active
                  </span>
                </div>
                <h3 className="text-xl font-bold text-slate-900">Simple Billing Experience</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                  Crystal-clear itemized quotes, transparent line breakdown, tax identification, and payment confirmation receipts.
                </p>
              </div>
              <div className="mt-6 pt-4 border-t border-slate-100 text-xs text-slate-500 font-medium">
                Professional branding & PDF exports
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          11. CONTROL CENTER
      ========================================================================== */}
      <section className="py-20 bg-slate-900 text-white border-t border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-14">
            <span className="text-xs font-bold uppercase tracking-wider text-brand-400 bg-brand-900/50 px-3 py-1 rounded-full border border-brand-700/50">
              Operations & Governance
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
              Stay in control of every billing operation
            </h2>
            <p className="mt-3 text-base text-slate-400">
              Mission control for finance leads, billing operations, and administrators to orchestrate company-wide financial events.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* 1. Action Center */}
            <div className="bg-slate-800/90 rounded-xl p-6 border border-slate-700 flex flex-col justify-between hover:border-slate-600 transition-colors">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="w-9 h-9 rounded-lg bg-brand-500/20 text-brand-400 flex items-center justify-center">
                    <Zap className="w-5 h-5" />
                  </div>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    Live
                  </span>
                </div>
                <h3 className="text-lg font-bold text-white">Action Center</h3>
                <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                  Real-time operational alerts for pending invoice actions, overdue collections, and approval queues.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-slate-700/70">
                <Link to="/control-center/action-center" className="text-xs text-brand-400 hover:text-brand-300 font-semibold inline-flex items-center gap-1">
                  Open Action Center <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>

            {/* 2. Approval Center */}
            <div className="bg-slate-800/90 rounded-xl p-6 border border-slate-700 flex flex-col justify-between hover:border-slate-600 transition-colors">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="w-9 h-9 rounded-lg bg-purple-500/20 text-purple-400 flex items-center justify-center">
                    <Shield className="w-5 h-5" />
                  </div>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    Live
                  </span>
                </div>
                <h3 className="text-lg font-bold text-white">Approval Center</h3>
                <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                  Manage required managerial approvals for high-value quotes, custom discounts, and credit notes.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-slate-700/70">
                <Link to="/control-center/approvals" className="text-xs text-brand-400 hover:text-brand-300 font-semibold inline-flex items-center gap-1">
                  Open Approvals <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>

            {/* 3. Billing Calendar */}
            <div className="bg-slate-800/90 rounded-xl p-6 border border-slate-700 flex flex-col justify-between hover:border-slate-600 transition-colors">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="w-9 h-9 rounded-lg bg-amber-500/20 text-amber-400 flex items-center justify-center">
                    <Calendar className="w-5 h-5" />
                  </div>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    Live
                  </span>
                </div>
                <h3 className="text-lg font-bold text-white">Billing Calendar</h3>
                <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                  Visual calendar of upcoming subscription renewal dates, scheduled invoice dispatches, and due payments.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-slate-700/70">
                <Link to="/control-center/calendar" className="text-xs text-brand-400 hover:text-brand-300 font-semibold inline-flex items-center gap-1">
                  Open Calendar <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>

            {/* 4. Reconciliation */}
            <div className="bg-slate-800/90 rounded-xl p-6 border border-slate-700 flex flex-col justify-between hover:border-slate-600 transition-colors">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="w-9 h-9 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center">
                    <RotateCcw className="w-5 h-5" />
                  </div>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    Live
                  </span>
                </div>
                <h3 className="text-lg font-bold text-white">Reconciliation</h3>
                <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                  Systematic matching of payment gateway settlements with open invoices and internal ledger accounts.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-slate-700/70">
                <Link to="/control-center/reconciliation" className="text-xs text-brand-400 hover:text-brand-300 font-semibold inline-flex items-center gap-1">
                  Open Reconciliation <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>

            {/* 5. Audit Log */}
            <div className="bg-slate-800/90 rounded-xl p-6 border border-slate-700 flex flex-col justify-between hover:border-slate-600 transition-colors">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="w-9 h-9 rounded-lg bg-rose-500/20 text-rose-400 flex items-center justify-center">
                    <Eye className="w-5 h-5" />
                  </div>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    Live
                  </span>
                </div>
                <h3 className="text-lg font-bold text-white">Audit Log</h3>
                <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                  Immutable chronological records of all user actions, price alterations, status changes, and data edits.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-slate-700/70">
                <Link to="/control-center/audit-log" className="text-xs text-brand-400 hover:text-brand-300 font-semibold inline-flex items-center gap-1">
                  Open Audit Log <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>

            {/* 6. Data Migration */}
            <div className="bg-slate-800/90 rounded-xl p-6 border border-slate-700 flex flex-col justify-between hover:border-slate-600 transition-colors">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="w-9 h-9 rounded-lg bg-blue-500/20 text-blue-400 flex items-center justify-center">
                    <Database className="w-5 h-5" />
                  </div>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    Live
                  </span>
                </div>
                <h3 className="text-lg font-bold text-white">Data Migration</h3>
                <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                  Import and export customer lists, catalogs, historical invoices, and ledger records safely.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-slate-700/70">
                <Link to="/control-center/migration" className="text-xs text-brand-400 hover:text-brand-300 font-semibold inline-flex items-center gap-1">
                  Open Migration <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          12. ENTERPRISE / TRUST
      ========================================================================== */}
      <section id="enterprise" className="py-20 bg-slate-50 border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-14">
            <span className="text-xs font-bold uppercase tracking-wider text-brand-600 bg-brand-50 px-3 py-1 rounded-full border border-brand-200">
              Enterprise Grade
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
              Built for business-critical billing
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Architected with data integrity, deterministic pricing calculations, and role governance at its core.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* 1. Role-Based Access */}
            <div className="bg-white p-6 rounded-2xl border border-slate-200/90 shadow-card">
              <div className="w-10 h-10 rounded-xl bg-blue-50 text-brand-600 flex items-center justify-center mb-4">
                <Lock className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">Role-Based Access</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Granular permission levels for Owner, Admin, Member, and Viewer with strictly bounded capabilities.
              </p>
            </div>

            {/* 2. Organization-Level Data Isolation */}
            <div className="bg-white p-6 rounded-2xl border border-slate-200/90 shadow-card">
              <div className="w-10 h-10 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center mb-4">
                <Database className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">Organization Data Isolation</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Multi-tenant isolation ensures data belonging to your organization is strictly separated and guarded.
              </p>
            </div>

            {/* 3. Audit Trail */}
            <div className="bg-white p-6 rounded-2xl border border-slate-200/90 shadow-card">
              <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center mb-4">
                <Eye className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">Comprehensive Audit Trail</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Every quote modification, price adjustment, invoice issue, and approval is logged with user timestamps.
              </p>
            </div>

            {/* 4. Persistent Financial Records */}
            <div className="bg-white p-6 rounded-2xl border border-slate-200/90 shadow-card">
              <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center mb-4">
                <Receipt className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">Persistent Financial Records</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Immutable invoice snapshots preserve agreed line items and tax calculations for historical consistency.
              </p>
            </div>

            {/* 5. Billing Accuracy */}
            <div className="bg-white p-6 rounded-2xl border border-slate-200/90 shadow-card">
              <div className="w-10 h-10 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center mb-4">
                <Calculator className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">Billing Accuracy</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Deterministic calculation logic prevents rounding discrepancies across complex tiered and discount structures.
              </p>
            </div>

            {/* 6. Operational Visibility */}
            <div className="bg-white p-6 rounded-2xl border border-slate-200/90 shadow-card">
              <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center mb-4">
                <BarChart3 className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">Operational Visibility</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Direct view into overdue collections, approval bottlenecks, and active subscription trends across your business.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          13. FREQUENTLY ASKED QUESTIONS
      ========================================================================== */}
      <section id="faq" className="py-20 bg-white border-t border-slate-200">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14">
            <span className="text-xs font-bold uppercase tracking-wider text-brand-600 bg-brand-50 px-3 py-1 rounded-full border border-brand-200">
              Got Questions?
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
              Frequently Asked Questions
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Clear answers to common questions about Rooman Billing's architecture, models, and operations.
            </p>
          </div>

          <div className="space-y-4">
            {faqs.map((faq, fIdx) => {
              const isOpen = openFaqIndex === fIdx;
              return (
                <div
                  key={fIdx}
                  className="rounded-2xl border border-slate-200/90 overflow-hidden transition-all bg-white"
                >
                  <button
                    type="button"
                    onClick={() => setOpenFaqIndex(isOpen ? null : fIdx)}
                    className="w-full text-left px-6 py-5 flex items-center justify-between gap-4 font-semibold text-slate-900 hover:bg-slate-50/70 transition-colors cursor-pointer"
                    aria-expanded={isOpen}
                  >
                    <span className="text-base">{faq.q}</span>
                    <ChevronDown
                      className={`w-5 h-5 text-slate-400 shrink-0 transition-transform duration-200 ${
                        isOpen ? 'rotate-180 text-brand-600' : ''
                      }`}
                    />
                  </button>
                  {isOpen && (
                    <div className="px-6 pb-5 pt-1 text-sm text-slate-600 leading-relaxed border-t border-slate-100 bg-slate-50/40">
                      {faq.a}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="mt-10 text-center p-6 rounded-2xl bg-blue-50/50 border border-blue-100">
            <h4 className="text-sm font-bold text-slate-900">Have a custom billing requirement?</h4>
            <p className="text-xs text-slate-600 mt-1">
              Our engineering team supports customized catalog configurations, enterprise migrations, and tailored workflows.
            </p>
            <div className="mt-4">
              <Link to="/signup">
                <Button variant="outline" size="sm" className="font-semibold text-brand-700 bg-white">
                  Get Started Free
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          14. FINAL CTA
      ========================================================================== */}
      <section className="py-20 bg-gradient-to-br from-brand-900 via-brand-800 to-slate-950 text-white relative overflow-hidden">
        {/* Subtle glow circle */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[300px] bg-brand-500/20 blur-3xl -z-10 rounded-full pointer-events-none" />

        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 text-brand-200 text-xs font-semibold mb-6 backdrop-blur-xs">
            <Sparkles className="w-3.5 h-3.5 text-brand-300" />
            <span>Ready for unified revenue management</span>
          </div>

          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-white tracking-tight">
            Ready to simplify your billing?
          </h2>
          <p className="mt-4 text-base sm:text-lg text-brand-100 max-w-2xl mx-auto leading-relaxed">
            Bring your catalog, pricing, customers, invoices and payments together with Rooman Billing.
          </p>

          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3.5">
            <Link to={isAuthenticated ? '/dashboard' : '/signup'} className="w-full sm:w-auto">
              <Button
                variant="primary"
                size="lg"
                className="w-full sm:w-auto font-semibold px-8 py-3.5 text-base bg-white text-brand-900 hover:bg-slate-100 shadow-elevated active:scale-[0.98]"
              >
                Get Started
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </Link>
            <button
              type="button"
              onClick={() => scrollToSection('features')}
              className="w-full sm:w-auto inline-flex items-center justify-center px-7 py-3.5 rounded-lg border border-white/20 bg-white/10 text-white font-medium hover:bg-white/20 transition-all cursor-pointer text-base backdrop-blur-sm active:scale-[0.98]"
            >
              Explore the Platform
            </button>
          </div>
        </div>
      </section>

      {/* =========================================================================
          15. FOOTER
      ========================================================================== */}
      <footer className="bg-white border-t border-slate-200 pt-14 pb-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-8 mb-12">
            {/* Brand column */}
            <div className="col-span-2 lg:col-span-2">
              <Link to="/" className="inline-block">
                <RoomanLogo variant="brand" size="md" showBillingBadge />
              </Link>
              <p className="mt-4 text-xs text-slate-500 max-w-sm leading-relaxed">
                Rooman Billing is an enterprise-grade billing and subscription platform engineered for high-growth businesses.
              </p>
              <div className="mt-4 text-xs text-slate-400">
                &copy; {new Date().getFullYear()} Rooman Technologies. All rights reserved.
              </div>
            </div>

            {/* Product Column */}
            <div>
              <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3">Product</h4>
              <ul className="space-y-2 text-xs text-slate-600">
                <li><Link to="/catalog" className="hover:text-brand-600 transition-colors">Catalog</Link></li>
                <li><Link to="/cpq" className="hover:text-brand-600 transition-colors">CPQ</Link></li>
                <li><Link to="/plans-pricing" className="hover:text-brand-600 transition-colors">Plans & Pricing</Link></li>
                <li><Link to="/quotes" className="hover:text-brand-600 transition-colors">Quotes</Link></li>
                <li><Link to="/invoices" className="hover:text-brand-600 transition-colors">Invoices</Link></li>
                <li><Link to="/payments" className="hover:text-brand-600 transition-colors">Payments</Link></li>
              </ul>
            </div>

            {/* Operations Column */}
            <div>
              <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3">Operations</h4>
              <ul className="space-y-2 text-xs text-slate-600">
                <li><Link to="/dashboard" className="hover:text-brand-600 transition-colors">Dashboard</Link></li>
                <li><Link to="/customers" className="hover:text-brand-600 transition-colors">Customers</Link></li>
                <li><Link to="/collections" className="hover:text-brand-600 transition-colors">Collections</Link></li>
                <li><Link to="/control-center/action-center" className="hover:text-brand-600 transition-colors">Action Center</Link></li>
                <li><Link to="/control-center/approvals" className="hover:text-brand-600 transition-colors">Approvals</Link></li>
                <li><Link to="/control-center/reconciliation" className="hover:text-brand-600 transition-colors">Reconciliation</Link></li>
              </ul>
            </div>

            {/* Account & Auth */}
            <div>
              <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3">Account</h4>
              <ul className="space-y-2 text-xs text-slate-600">
                <li><Link to="/login" className="hover:text-brand-600 transition-colors">Sign In</Link></li>
                <li><Link to="/signup" className="hover:text-brand-600 transition-colors">Get Started</Link></li>
                <li><Link to="/forgot-password" className="hover:text-brand-600 transition-colors">Forgot Password</Link></li>
                <li><Link to="/settings" className="hover:text-brand-600 transition-colors">Organization Settings</Link></li>
              </ul>
            </div>
          </div>

          <div className="pt-8 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-400">
            <div>
              Rooman Billing Platform &bull; Built for business-critical billing operations.
            </div>
            <div className="flex items-center gap-6">
              <span className="text-slate-500 font-medium">Enterprise Ready</span>
              <span>&bull;</span>
              <span className="text-slate-500 font-medium">Role Governance</span>
              <span>&bull;</span>
              <span className="text-slate-500 font-medium">Deterministic Billing</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
