import { useState, useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  CheckCircle2,
  Shield,
  Layers,
  FileText,
  CreditCard,
  BarChart3,
  Sliders,
  Sparkles,
  Lock,
  Database,
  Calculator,
  Receipt,
  Check,
  Building2,
  Calendar,
  Eye,
  Menu,
  X,
  Cpu,
  ChevronDown,
  ArrowUpRight,
  Briefcase,
  Play,
  Pause,
  Server,
  ArrowLeftRight,
} from 'lucide-react';
import { RoomanLogo } from '../../components/common/RoomanLogo';
import { Button } from '../../components/common/Button';
import { useAuth } from '../../hooks/useAuth';

// ---------------------------------------------------------------------------
// Background Fintech Grid Animation Canvas (Graceful Video Fallback)
// ---------------------------------------------------------------------------
function FintechBackgroundCanvas() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = canvas.offsetWidth);
    let height = (canvas.height = canvas.offsetHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = canvas.offsetWidth;
      height = canvas.height = canvas.offsetHeight;
    };
    window.addEventListener('resize', handleResize);

    // Subtle, slow-moving atmospheric particles (zero text labels, zero dense network lines)
    const nodes: Array<{
      x: number;
      y: number;
      vx: number;
      vy: number;
      radius: number;
      alpha: number;
      color: string;
    }> = [];

    const colors = ['#8EA5FF', '#A7B5F2', '#6366F1', '#E83E8C'];
    const nodeCount = Math.min(Math.floor((width * height) / 38000), 16);

    for (let i = 0; i < nodeCount; i++) {
      nodes.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.18,
        vy: (Math.random() - 0.5) * 0.18,
        radius: Math.random() * 2 + 1,
        alpha: Math.random() * 0.25 + 0.1,
        color: colors[Math.floor(Math.random() * colors.length)],
      });
    }

    const render = () => {
      ctx.clearRect(0, 0, width, height);

      // Draw subtle ambient particles only (clean, uncluttered)
      for (const node of nodes) {
        node.x += node.vx;
        node.y += node.vy;

        if (node.x < 0) node.x = width;
        if (node.x > width) node.x = 0;
        if (node.y < 0) node.y = height;
        if (node.y > height) node.y = 0;

        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
        ctx.fillStyle = node.color;
        ctx.globalAlpha = node.alpha;
        ctx.fill();
      }

      ctx.globalAlpha = 1.0;
      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none opacity-60" />;
}

// ---------------------------------------------------------------------------
// Main Landing Page Component
// ---------------------------------------------------------------------------
export function LandingPage() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  // Navigation & UI States
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [activeWorkflowTab, setActiveWorkflowTab] = useState<number>(0);
  const [isAutoPlayingWorkflow, setIsAutoPlayingWorkflow] = useState<boolean>(true);
  const [tourProgress, setTourProgress] = useState<number>(0);
  const [isHoveringTour, setIsHoveringTour] = useState<boolean>(false);
  const [selectedPricingModel, setSelectedPricingModel] = useState<number>(0);
  const [simulatorQuantity, setSimulatorQuantity] = useState<number>(150);
  const [openFaqIndex, setOpenFaqIndex] = useState<number | null>(0);
  const [activeAudienceIndex, setActiveAudienceIndex] = useState<number>(0);
  const [videoLoaded, setVideoLoaded] = useState<boolean>(false);
  const [videoFailed, setVideoFailed] = useState<boolean>(false);

  // Auto cycle workflow steps with fine-grained animated progress bar (4.2 seconds per step)
  const TOUR_DURATION = 4200;
  const UPDATE_INTERVAL = 50;

  useEffect(() => {
    if (!isAutoPlayingWorkflow || isHoveringTour) return;

    const timer = setInterval(() => {
      setTourProgress((prev) => {
        const next = prev + (UPDATE_INTERVAL / TOUR_DURATION) * 100;
        if (next >= 100) {
          setActiveWorkflowTab((cur) => (cur + 1) % 9);
          return 0;
        }
        return next;
      });
    }, UPDATE_INTERVAL);

    return () => clearInterval(timer);
  }, [isAutoPlayingWorkflow, isHoveringTour]);

  // Reset progress bar on manual stage click
  const handleStageSelect = (idx: number) => {
    setActiveWorkflowTab(idx);
    setTourProgress(0);
  };

  const scrollToSection = (id: string) => {
    setMobileMenuOpen(false);
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  // 9 Quote-to-Cash Workflow Stages
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
      kpi: '81 Active Offerings',
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
      kpi: '5 Deterministic Models',
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
      kpi: 'Real-time Margin Check',
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
      kpi: 'Public Acceptance Link',
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
      kpi: 'Zero Unapproved Discounts',
    },
    {
      id: 'invoice',
      label: 'Invoice',
      step: '06',
      title: 'One-Click Invoice Conversion',
      desc: 'Instantly convert accepted quotes into tax-compliant invoices with automatic sequence numbering and due dates.',
      badge: 'Billing Ops',
      route: '/invoices',
      details: ['Sequential numbering', 'Tax & line item preservation', 'CGST/SGST/IGST breakdown'],
      kpi: 'GST Tax-Compliant',
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
      kpi: 'Matched Settlement',
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
      kpi: '100% Audit Reconciled',
    },
    {
      id: 'reporting',
      label: 'Reporting',
      step: '09',
      title: 'Revenue Analytics & Reporting',
      desc: 'Gain 360-degree visibility over MRR, ARR, invoice aging, collections efficiency, and churn velocity.',
      badge: 'Intelligence',
      route: '/reports',
      details: ['Real-time MRR/ARR indicators', 'Aging receivables buckets', 'Cohort & retention insights'],
      kpi: 'Real-time Cash Visibility',
    },
  ];

  // 5 Pricing Models with live dynamic preview
  const pricingModels = [
    {
      title: 'Flat Fee',
      type: 'Fixed Rate',
      desc: 'Predictable, static recurring billing on regular intervals (e.g. $299/month).',
      example: 'Enterprise Platform Access',
      calculate: () => 299,
      calcDisplay: 'Fixed $299.00 / month regardless of seats',
      features: ['Fixed monthly or annual billing', 'Simple invoice generation', 'Ideal for base platform tiers'],
    },
    {
      title: 'Per Unit',
      type: 'Seat / License',
      desc: 'Linear pricing calculated by multiplying unit price by active user count or license seats.',
      example: '$15 / active user / month',
      calculate: (qty: number) => qty * 15,
      calcDisplay: (qty: number) => `${qty} units × $15.00 = $${(qty * 15).toLocaleString()}.00 / mo`,
      features: ['Dynamic quantity recalculation', 'Mid-cycle seat adjustments', 'Ideal for SaaS team plans'],
    },
    {
      title: 'Volume',
      type: 'All-Unit Discount',
      desc: 'Total volume purchased qualifies all units for a discounted tier price.',
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
      title: 'B2B SaaS Companies',
      desc: 'Handle hybrid seat + usage pricing, automated subscription renewals, trial conversions, and self-serve upgrades with zero billing leakage.',
      icon: Layers,
      benefit: 'Automate recurring SaaS tiers & mid-cycle seat expansions',
      example: 'Vertex Global: Scaled from 20 to 180 seats with automated monthly proration',
    },
    {
      title: 'IT & Managed Services',
      desc: 'Combine fixed monthly retainer agreements, billable consulting timesheets, hardware one-time sales, and milestone invoicing in one ledger.',
      icon: Briefcase,
      benefit: 'Unify time & material logs with recurring retainer invoices',
      example: 'CloudTech Systems: Consolidated 50+ client retainer contracts & project milestones',
    },
    {
      title: 'Usage & API Platforms',
      desc: 'Ingest high-frequency meter events, aggregate billable units, calculate tier discounts, and bill overages accurately at period end.',
      icon: Cpu,
      benefit: 'Deterministic meter event ingestion with idempotency keys',
      example: 'Nova Stream: Ingests 100k+ API billing events daily with paisa-level precision',
    },
    {
      title: 'Sales-Assisted Enterprise',
      desc: 'Empower sales reps with guided CPQ configuration, custom discount approval limits, professional quote previews, and one-click invoice creation.',
      icon: Building2,
      benefit: 'Guard margins with multi-tier managerial approval thresholds',
      example: 'Apex Global: Reduced sales quote-to-cash turnaround from 5 days to 20 minutes',
    },
  ];

  // How It Works Steps
  const howItWorksSteps = [
    {
      step: '01',
      title: 'Configure Products & Plans',
      desc: 'Define standard offerings, recurring plans, add-ons, and pricing models in your unified product catalog.',
      icon: PackageIcon,
    },
    {
      step: '02',
      title: 'Configure Deals & Quotes',
      desc: 'Generate branded quotes via CPQ, apply guided discount limits, and share instant public review links.',
      icon: FileText,
    },
    {
      step: '03',
      title: 'Collect Payments & Reconcile',
      desc: 'Convert accepted quotes into tax invoices, accept online or bank payments, and reconcile every rupee in real time.',
      icon: CreditCard,
    },
  ];

  function PackageIcon(props: { className?: string }) {
    return <Layers {...props} />;
  }

  // FAQs
  const faqs = [
    {
      q: 'How does Rooman Billing ensure calculation accuracy?',
      a: 'Rooman Billing uses deterministic Decimal/NUMERIC arithmetic across all database layers and domain services. We strictly avoid floating-point shortcuts, guaranteeing exact penny and paisa totals across volume tiers, graduated brackets, and GST splits (CGST, SGST, IGST).',
    },
    {
      q: 'Can we convert quotes directly into invoices and collect payments?',
      a: 'Yes. Accepted quotes convert into fully compliant tax invoices with one click. Invoices immediately receive a secure, tokenized public link where clients can review itemized line items and complete payment seamlessly.',
    },
    {
      q: 'How does multi-tenant security and data isolation work?',
      a: 'Every single record in Rooman Billing is scoped strictly to your Organization ID. Cross-tenant access is prohibited at both the database query layer and application service tier, verified by rigorous IDOR security audits.',
    },
    {
      q: 'Does Rooman Billing handle complex CPQ and approval rules?',
      a: 'Yes. Our built-in CPQ engine validates product bundle compatibility and flags discount thresholds that exceed policy, automatically submitting deals to designated managers before quotes can be released.',
    },
    {
      q: 'Can we track billable project hours and invoice them directly?',
      a: 'Yes. Rooman Billing features integrated project tracking and employee timesheets. Billable hours undergo supervisor review and can be converted directly into itemized invoice line items.',
    },
  ];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 selection:bg-[#E83E8C] selection:text-white font-sans">
      {/* =========================================================================
          1. TOP NAVIGATION (STICKY WITH BACKDROP BLUR)
      ========================================================================== */}
      <header className="sticky top-0 z-50 bg-white/85 backdrop-blur-md border-b border-slate-200/80 transition-all shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Brand Logo */}
          <Link to="/" className="flex items-center gap-3 group">
            <RoomanLogo variant="brand" size="md" showBillingBadge />
          </Link>

          {/* Center Navigation Links */}
          <nav className="hidden lg:flex items-center gap-7 text-sm font-medium text-slate-600">
            <button
              type="button"
              onClick={() => scrollToSection('features')}
              className="hover:text-[#25247A] transition-colors cursor-pointer"
            >
              Product
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('how-it-works')}
              className="hover:text-[#25247A] transition-colors cursor-pointer"
            >
              How It Works
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('workflow')}
              className="hover:text-[#25247A] transition-colors cursor-pointer"
            >
              Workflow
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('pricing-models')}
              className="hover:text-[#25247A] transition-colors cursor-pointer"
            >
              Pricing Models
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('why-rooman')}
              className="hover:text-[#25247A] transition-colors cursor-pointer"
            >
              Why Rooman
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('faq')}
              className="hover:text-[#25247A] transition-colors cursor-pointer"
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
                className="bg-[#25247A] hover:bg-[#1C1B63] text-white shadow-sm font-semibold active:scale-[0.98] transition-transform"
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
                  <Button
                    variant="primary"
                    size="md"
                    className="bg-gradient-to-r from-[#25247A] via-[#3F51C9] to-[#E83E8C] hover:opacity-95 text-white shadow-sm font-semibold active:scale-[0.98] transition-all"
                  >
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
            className="lg:hidden p-2 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors focus:outline-none"
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
              className="block w-full text-left py-2 text-sm font-medium text-slate-700 hover:text-[#25247A]"
            >
              Product & Features
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('how-it-works')}
              className="block w-full text-left py-2 text-sm font-medium text-slate-700 hover:text-[#25247A]"
            >
              How It Works
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('workflow')}
              className="block w-full text-left py-2 text-sm font-medium text-slate-700 hover:text-[#25247A]"
            >
              End-to-End Workflow
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('pricing-models')}
              className="block w-full text-left py-2 text-sm font-medium text-slate-700 hover:text-[#25247A]"
            >
              Pricing Models
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('why-rooman')}
              className="block w-full text-left py-2 text-sm font-medium text-slate-700 hover:text-[#25247A]"
            >
              Why Rooman
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('faq')}
              className="block w-full text-left py-2 text-sm font-medium text-slate-700 hover:text-[#25247A]"
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
                  className="w-full justify-center bg-[#25247A] text-white"
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
                    <Button
                      variant="primary"
                      size="md"
                      className="w-full justify-center font-semibold bg-gradient-to-r from-[#25247A] to-[#E83E8C] text-white"
                    >
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
          2. HERO — COMPLETE VISUAL TRANSFORMATION
      ========================================================================== */}
      <section className="relative min-h-[calc(100vh-4.5rem)] flex items-center justify-center py-20 md:py-32 overflow-hidden bg-[#0A0D1A] text-white">
        {/* Background Looping Video with Graceful Fallback */}
        <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
          {!videoFailed && (
            <video
              autoPlay
              muted
              loop
              playsInline
              preload="auto"
              onLoadedData={() => setVideoLoaded(true)}
              onError={() => setVideoFailed(true)}
              className={`w-full h-full object-cover object-center transition-opacity duration-1000 ${
                videoLoaded ? 'opacity-40' : 'opacity-0'
              }`}
            >
              <source src="/videos/rooman-billing.mp4" type="video/mp4" />
            </video>
          )}

          {/* Animated Fintech Data Nodes Grid (Renders smoothly as primary or fallback layer) */}
          <FintechBackgroundCanvas />

          {/* Glowing Ambient Mesh Gradients in Deep Indigo & Rooman Pink */}
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[850px] h-[450px] bg-gradient-to-tr from-[#3F51C9]/35 via-[#6C2BD9]/25 to-[#E83E8C]/20 blur-[120px] rounded-full" />
          <div className="absolute bottom-0 inset-x-0 h-40 bg-gradient-to-t from-[#0A0D1A] to-transparent" />
        </div>

        <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full">
          <div className="text-center max-w-3xl mx-auto">
            {/* Eyebrow Badge */}
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/10 border border-white/15 text-slate-200 text-xs font-semibold uppercase tracking-wider mb-6 shadow-sm backdrop-blur-md">
              <Sparkles className="w-3.5 h-3.5 text-[#FF75A0]" />
              <span>ROOMAN BILLING &bull; ENTERPRISE REVENUE ENGINE</span>
            </div>

            {/* Headline */}
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-white tracking-tight leading-[1.12]">
              Powerful billing.{' '}
              <span className="bg-clip-text text-transparent bg-gradient-to-r from-[#8EA5FF] via-[#E9E8FA] to-[#FF75A0]">
                Smarter business.
              </span>
            </h1>

            {/* Supporting Text */}
            <p className="mt-5 text-lg sm:text-xl font-medium text-slate-300 leading-relaxed max-w-2xl mx-auto">
              One connected platform for products, pricing, quotes, invoices, payments, subscriptions and revenue operations.
            </p>

            {/* CTA Buttons */}
            <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link to={isAuthenticated ? '/dashboard' : '/signup'} className="w-full sm:w-auto">
                <Button
                  variant="primary"
                  size="lg"
                  className="w-full sm:w-auto font-semibold px-8 py-3.5 text-base bg-gradient-to-r from-[#25247A] via-[#3F51C9] to-[#E83E8C] text-white shadow-elevated group active:scale-[0.98] transition-all hover:brightness-110"
                >
                  Get Started
                  <ArrowRight className="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" />
                </Button>
              </Link>
              <button
                type="button"
                onClick={() => scrollToSection('workflow')}
                className="w-full sm:w-auto inline-flex items-center justify-center px-7 py-3.5 rounded-lg border border-white/20 bg-white/10 text-white font-medium hover:bg-white/20 shadow-xs transition-all active:scale-[0.98] cursor-pointer text-sm sm:text-base backdrop-blur-sm"
              >
                Explore Platform
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          3. VALUE STRIP: CORE CAPABILITIES
      ========================================================================== */}
      <section id="features" className="py-12 bg-white border-y border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 mb-8">
            <div className="shrink-0 text-center lg:text-left">
              <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9]">Core Capabilities</span>
              <h2 className="text-xl sm:text-2xl font-bold text-[#11194F] mt-0.5">
                Everything you need to orchestrate revenue
              </h2>
            </div>
            <p className="text-xs sm:text-sm text-slate-500 max-w-lg">
              Click any module to jump directly into the live workspace and manage active records.
            </p>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4">
            <Link
              to="/catalog"
              className="flex flex-col justify-between p-4 rounded-2xl bg-slate-50/80 hover:bg-white border border-[#E7E9F2] hover:border-[#3F51C9] hover:shadow-card hover:-translate-y-1 transition-all duration-200 group"
            >
              <div className="w-9 h-9 rounded-xl bg-[#E8EBFC] text-[#3F51C9] flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                <Layers className="w-5 h-5" />
              </div>
              <div>
                <span className="text-xs font-bold text-slate-900 group-hover:text-[#25247A]">Product Catalog</span>
                <p className="text-[10px] text-slate-400 mt-0.5">SKUs & offerings</p>
              </div>
            </Link>

            <Link
              to="/plans-pricing"
              className="flex flex-col justify-between p-4 rounded-2xl bg-slate-50/80 hover:bg-white border border-[#E7E9F2] hover:border-[#3F51C9] hover:shadow-card hover:-translate-y-1 transition-all duration-200 group"
            >
              <div className="w-9 h-9 rounded-xl bg-[#E8EBFC] text-[#3F51C9] flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                <Sliders className="w-5 h-5" />
              </div>
              <div>
                <span className="text-xs font-bold text-slate-900 group-hover:text-[#25247A]">Flexible Pricing</span>
                <p className="text-[10px] text-slate-400 mt-0.5">5 fee structures</p>
              </div>
            </Link>

            <Link
              to="/cpq"
              className="flex flex-col justify-between p-4 rounded-2xl bg-slate-50/80 hover:bg-white border border-[#E7E9F2] hover:border-[#3F51C9] hover:shadow-card hover:-translate-y-1 transition-all duration-200 group"
            >
              <div className="w-9 h-9 rounded-xl bg-[#E8EBFC] text-[#3F51C9] flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                <Cpu className="w-5 h-5" />
              </div>
              <div>
                <span className="text-xs font-bold text-slate-900 group-hover:text-[#25247A]">CPQ Deals</span>
                <p className="text-[10px] text-slate-400 mt-0.5">Guided configuration</p>
              </div>
            </Link>

            <Link
              to="/quotes"
              className="flex flex-col justify-between p-4 rounded-2xl bg-slate-50/80 hover:bg-white border border-[#E7E9F2] hover:border-[#3F51C9] hover:shadow-card hover:-translate-y-1 transition-all duration-200 group"
            >
              <div className="w-9 h-9 rounded-xl bg-[#E8EBFC] text-[#3F51C9] flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                <FileText className="w-5 h-5" />
              </div>
              <div>
                <span className="text-xs font-bold text-slate-900 group-hover:text-[#25247A]">Quotes</span>
                <p className="text-[10px] text-slate-400 mt-0.5">Acceptance links</p>
              </div>
            </Link>

            <Link
              to="/invoices"
              className="flex flex-col justify-between p-4 rounded-2xl bg-slate-50/80 hover:bg-white border border-[#E7E9F2] hover:border-[#3F51C9] hover:shadow-card hover:-translate-y-1 transition-all duration-200 group"
            >
              <div className="w-9 h-9 rounded-xl bg-[#E8EBFC] text-[#3F51C9] flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                <Receipt className="w-5 h-5" />
              </div>
              <div>
                <span className="text-xs font-bold text-slate-900 group-hover:text-[#25247A]">Invoices</span>
                <p className="text-[10px] text-slate-400 mt-0.5">GST tax compliant</p>
              </div>
            </Link>

            <Link
              to="/payments"
              className="flex flex-col justify-between p-4 rounded-2xl bg-slate-50/80 hover:bg-white border border-[#E7E9F2] hover:border-[#3F51C9] hover:shadow-card hover:-translate-y-1 transition-all duration-200 group"
            >
              <div className="w-9 h-9 rounded-xl bg-[#E8EBFC] text-[#3F51C9] flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                <CreditCard className="w-5 h-5" />
              </div>
              <div>
                <span className="text-xs font-bold text-slate-900 group-hover:text-[#25247A]">Payments</span>
                <p className="text-[10px] text-slate-400 mt-0.5">Allocations & refunds</p>
              </div>
            </Link>
          </div>
        </div>
      </section>

      {/* =========================================================================
          4. HOW IT WORKS
      ========================================================================== */}
      <section id="how-it-works" className="py-20 bg-slate-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-14">
            <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3 py-1 rounded-full border border-[#D0D7F9]">
              Simple 3-Step Flow
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
              How Rooman Billing Works
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Go from catalog definition to active invoice collection in three straightforward stages.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8">
            {howItWorksSteps.map((stepItem, idx) => {
              const IconComp = stepItem.icon;
              return (
                <div
                  key={idx}
                  className="bg-white rounded-2xl p-7 border border-[#E7E9F2] shadow-card hover:shadow-elevated transition-all flex flex-col justify-between relative group"
                >
                  <div>
                    <div className="flex items-center justify-between mb-5">
                      <div className="w-12 h-12 rounded-2xl bg-[#E8EBFC] text-[#3F51C9] flex items-center justify-center font-bold text-lg group-hover:scale-110 transition-transform">
                        <IconComp className="w-6 h-6" />
                      </div>
                      <span className="text-2xl font-black font-mono text-slate-200 group-hover:text-[#8EA5FF] transition-colors">
                        {stepItem.step}
                      </span>
                    </div>
                    <h3 className="text-lg font-bold text-[#11194F]">{stepItem.title}</h3>
                    <p className="mt-2 text-sm text-slate-600 leading-relaxed">{stepItem.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* =========================================================================
          5. UPGRADED 9-STAGE QUOTE-TO-CASH AUTO-TOUR
      ========================================================================== */}
      <section id="workflow" className="py-20 bg-white border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-12">
            <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3 py-1 rounded-full border border-[#D0D7F9]">
              Unified Revenue Architecture
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
              From quote to cash &mdash; one connected workflow
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Watch how Rooman Billing connects every phase of the revenue lifecycle. No broken handoffs, zero data re-entry.
            </p>

            {/* Play / Pause Interactive Toggle */}
            <div className="mt-4 inline-flex items-center gap-3 text-xs text-slate-600 bg-slate-100 px-4 py-1.5 rounded-full border border-slate-200 shadow-3xs">
              <button
                type="button"
                onClick={() => setIsAutoPlayingWorkflow(!isAutoPlayingWorkflow)}
                className="inline-flex items-center gap-1.5 font-bold text-[#25247A] hover:text-[#3F51C9] cursor-pointer"
              >
                {isAutoPlayingWorkflow ? (
                  <>
                    <Pause className="w-3.5 h-3.5" /> Pause Auto-Tour
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5" /> Resume Auto-Tour
                  </>
                )}
              </button>
              <span className="text-slate-300">|</span>
              <span className="text-[11px] text-slate-500">Stage {activeWorkflowTab + 1} of 9</span>
            </div>
          </div>

          {/* Stepped Interactive Bar with Active Progress Fill */}
          <div className="bg-slate-50 p-3 sm:p-4 rounded-2xl border border-slate-200 mb-8 overflow-x-auto scrollbar-none shadow-3xs">
            <div className="flex items-center justify-between min-w-[800px] gap-2">
              {workflowSteps.map((step, idx) => {
                const isActive = activeWorkflowTab === idx;
                return (
                  <button
                    key={step.id}
                    onClick={() => handleStageSelect(idx)}
                    className={`relative flex-1 py-3 px-3 rounded-xl text-center transition-all cursor-pointer overflow-hidden ${
                      isActive
                        ? 'bg-[#25247A] text-white shadow-md scale-[1.02]'
                        : 'bg-white text-slate-700 hover:bg-slate-100 border border-slate-200/80'
                    }`}
                  >
                    {/* Animated Progress Indicator on Active Stage */}
                    {isActive && (
                      <div
                        style={{ width: `${tourProgress}%` }}
                        className="absolute bottom-0 inset-x-0 h-1 bg-gradient-to-r from-[#8EA5FF] to-[#E83E8C] transition-all duration-75"
                      />
                    )}
                    <div className={`text-[10px] font-mono font-bold ${isActive ? 'text-[#8EA5FF]' : 'text-slate-400'}`}>
                      {step.step}
                    </div>
                    <div className="text-xs font-bold mt-0.5 whitespace-nowrap">{step.label}</div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Selected Stage Detail Card */}
          <div
            onMouseEnter={() => setIsHoveringTour(true)}
            onMouseLeave={() => setIsHoveringTour(false)}
            className="bg-[#0B0F28] text-white rounded-3xl p-6 sm:p-10 shadow-2xl border border-white/10 transition-all relative overflow-hidden"
          >
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center relative z-10">
              <div className="lg:col-span-7 space-y-4">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 text-[#8EA5FF] text-xs font-semibold border border-white/15">
                  <span>Stage {workflowSteps[activeWorkflowTab].step} of 09</span>
                  <span>&bull;</span>
                  <span>{workflowSteps[activeWorkflowTab].badge}</span>
                </div>
                <h3 className="text-2xl sm:text-3xl font-extrabold text-white">
                  {workflowSteps[activeWorkflowTab].title}
                </h3>
                <p className="text-slate-300 text-sm sm:text-base leading-relaxed">
                  {workflowSteps[activeWorkflowTab].desc}
                </p>

                {/* Key Feature Pills */}
                <div className="flex flex-wrap gap-2 pt-2">
                  {workflowSteps[activeWorkflowTab].details.map((detail, dIdx) => (
                    <span
                      key={dIdx}
                      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-white/5 text-slate-300 text-xs border border-white/10"
                    >
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                      {detail}
                    </span>
                  ))}
                </div>

                <div className="pt-4 flex flex-wrap items-center gap-4">
                  <Link to={workflowSteps[activeWorkflowTab].route}>
                    <Button
                      variant="primary"
                      size="md"
                      className="bg-gradient-to-r from-[#3F51C9] to-[#E83E8C] text-white font-semibold shadow-sm active:scale-[0.98]"
                    >
                      Open {workflowSteps[activeWorkflowTab].label} in App
                      <ArrowRight className="w-4 h-4 ml-1.5" />
                    </Button>
                  </Link>
                  <span className="text-xs text-slate-400">
                    Deterministic transition with tenant audit isolation
                  </span>
                </div>
              </div>

              {/* Stage Real-time Preview Panel */}
              <div className="lg:col-span-5 bg-white/5 backdrop-blur-md rounded-2xl p-5 border border-white/10 text-xs font-mono space-y-3">
                <div className="flex justify-between items-center pb-2 border-b border-white/10 text-slate-400">
                  <span>Pipeline Stage Node</span>
                  <span className="text-emerald-400 flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                    Connected
                  </span>
                </div>
                <div className="space-y-2.5 text-slate-200">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Active Node:</span>
                    <span className="font-bold text-white">{workflowSteps[activeWorkflowTab].label}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Next Destination:</span>
                    <span className="text-[#FF75A0]">
                      {workflowSteps[(activeWorkflowTab + 1) % workflowSteps.length].label} &rarr;
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Guaranteed Metric:</span>
                    <span className="text-emerald-300 font-bold">{workflowSteps[activeWorkflowTab].kpi}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Tenant Validation:</span>
                    <span className="text-slate-300">Strict Org ID Scoped</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          6. PRICING MODELS (INTERACTIVE SIMULATOR)
      ========================================================================== */}
      <section id="pricing-models" className="py-20 bg-slate-50 border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-14">
            <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3 py-1 rounded-full border border-[#D0D7F9]">
              Monetization Flexibility
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
              Pricing that adapts to your business
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Rooman Billing natively accommodates five distinct monetization models with zero custom coding.
            </p>
          </div>

          {/* 5 Model Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-5">
            {pricingModels.map((model, idx) => (
              <div
                key={model.title}
                onClick={() => setSelectedPricingModel(idx)}
                className={`rounded-2xl p-5 border transition-all cursor-pointer flex flex-col justify-between ${
                  selectedPricingModel === idx
                    ? 'bg-white border-[#3F51C9] ring-2 ring-[#3F51C9]/20 shadow-elevated scale-[1.02]'
                    : 'bg-white border-[#E7E9F2] shadow-xs hover:border-slate-300 hover:shadow-subtle'
                }`}
              >
                <div>
                  <div className="inline-block px-2 py-0.5 rounded text-[11px] font-bold bg-[#E8EBFC] text-[#3F51C9] mb-3">
                    {model.type}
                  </div>
                  <h3 className="text-lg font-bold text-slate-900">{model.title}</h3>
                  <p className="mt-2 text-xs text-slate-600 leading-relaxed min-h-[48px]">{model.desc}</p>

                  <div className="mt-4 p-2.5 rounded-xl bg-slate-50 border border-slate-200/70 text-[11px] font-mono text-slate-700">
                    <span className="text-slate-400 block text-[10px]">Structure:</span>
                    {model.example}
                  </div>

                  <ul className="mt-4 space-y-1.5 text-[11px] text-slate-500">
                    {model.features.map((feat, fIdx) => (
                      <li key={fIdx} className="flex items-center gap-1.5">
                        <Check className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                        <span>{feat}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="mt-5 pt-3 border-t border-slate-100 text-center">
                  <span className={`text-xs font-semibold ${selectedPricingModel === idx ? 'text-[#3F51C9]' : 'text-slate-400'}`}>
                    {selectedPricingModel === idx ? 'Active Simulation' : 'Click to Simulate'}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Interactive Pricing Range Slider */}
          <div className="mt-10 bg-white rounded-2xl p-6 sm:p-7 border border-[#E7E9F2] shadow-sm max-w-4xl mx-auto">
            <div className="flex flex-col sm:flex-row items-center justify-between gap-6">
              <div className="w-full sm:w-1/2">
                <div className="flex justify-between items-center text-xs font-medium text-slate-700 mb-2">
                  <span>Simulate Units / Seats:</span>
                  <span className="font-bold font-mono text-[#3F51C9] text-base">{simulatorQuantity} units</span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="500"
                  value={simulatorQuantity}
                  onChange={(e) => setSimulatorQuantity(Number(e.target.value))}
                  className="w-full accent-[#3F51C9] h-2 bg-slate-200 rounded-lg cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-400 mt-1.5">
                  <span>1 unit</span>
                  <span>250 units</span>
                  <span>500 units</span>
                </div>
              </div>

              <div className="w-full sm:w-1/2 bg-[#F7F8FC] p-4 rounded-xl border border-[#E7E9F2]">
                <div className="text-xs text-slate-500 font-medium">
                  {pricingModels[selectedPricingModel].title} Calculation:
                </div>
                <div className="text-sm font-mono font-bold text-[#11194F] mt-1.5">
                  {typeof pricingModels[selectedPricingModel].calcDisplay === 'function'
                    ? pricingModels[selectedPricingModel].calcDisplay(simulatorQuantity)
                    : pricingModels[selectedPricingModel].calcDisplay}
                </div>
              </div>
            </div>
          </div>

          {/* CTAs */}
          <div className="mt-10 text-center flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link to="/plans-pricing">
              <Button variant="primary" size="lg" className="bg-[#25247A] text-white font-semibold shadow-sm">
                Explore Plans & Pricing
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </Link>
            <Link to="/plans-pricing/simulator">
              <Button variant="outline" size="lg" className="font-medium text-[#25247A]">
                Open Full Pricing Simulator
                <ArrowUpRight className="w-4 h-4 ml-1.5" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* =========================================================================
          7. WHY ROOMAN: CONNECTED REVENUE ENGINE
      ========================================================================== */}
      <section id="why-rooman" className="py-20 bg-white border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3 py-1 rounded-full border border-[#D0D7F9]">
              Architectural Difference
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
              Why Choose Rooman Billing?
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Built from the ground up as a unified revenue engine, eliminating fragmented point solutions and error-prone manual spreadsheets.
            </p>
          </div>

          {/* Connected Flow Diagram Visual */}
          <div className="mb-14 p-6 sm:p-8 rounded-3xl bg-[#0B0F28] text-white border border-white/10 shadow-xl overflow-x-auto">
            <div className="text-center text-xs text-[#8EA5FF] uppercase font-bold tracking-wider mb-6">
              Deterministic Pipeline Architecture
            </div>
            <div className="flex items-center justify-between min-w-[720px] text-center gap-2">
              {[
                { name: 'Catalog', icon: Layers },
                { name: 'Pricing', icon: Sliders },
                { name: 'CPQ', icon: Cpu },
                { name: 'Quote', icon: FileText },
                { name: 'Approval', icon: Shield },
                { name: 'Invoice', icon: Receipt },
                { name: 'Payment', icon: CreditCard },
                { name: 'Reconcile', icon: ArrowLeftRight },
                { name: 'Reporting', icon: BarChart3 },
              ].map((node, nIdx, arr) => {
                const IconComp = node.icon;
                return (
                  <div key={nIdx} className="flex items-center gap-2 flex-1">
                    <div className="flex-1 flex flex-col items-center">
                      <div className="w-10 h-10 rounded-xl bg-white/10 text-white flex items-center justify-center border border-white/20 mb-2">
                        <IconComp className="w-4 h-4 text-[#8EA5FF]" />
                      </div>
                      <span className="text-xs font-bold text-white">{node.name}</span>
                    </div>
                    {nIdx < arr.length - 1 && (
                      <span className="text-[#FF75A0] font-bold text-xs shrink-0">&rarr;</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="bg-white p-6 rounded-2xl border border-[#E7E9F2] shadow-xs hover:shadow-card transition-all">
              <div className="w-10 h-10 rounded-xl bg-[#E8EBFC] text-[#3F51C9] flex items-center justify-center mb-4">
                <Server className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">One Unified System</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Catalog, pricing rules, quotes, invoices, payments, and bank reconciliation live in one shared relational ledger.
              </p>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-[#E7E9F2] shadow-xs hover:shadow-card transition-all">
              <div className="w-10 h-10 rounded-xl bg-[#DDF4EA] text-[#107548] flex items-center justify-center mb-4">
                <Calculator className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">Zero-Loss Accuracy</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Deterministic calculation logic preserves exact pennies and discounts across complex graduated brackets and partial terms.
              </p>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-[#E7E9F2] shadow-xs hover:shadow-card transition-all">
              <div className="w-10 h-10 rounded-xl bg-[#F9D9E8] text-[#D81B60] flex items-center justify-center mb-4">
                <Shield className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">Built-In Governance</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Sales discount limits and managerial approval workflows prevent unauthorized pricing commitments before quote generation.
              </p>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-[#E7E9F2] shadow-xs hover:shadow-card transition-all">
              <div className="w-10 h-10 rounded-xl bg-[#FCEBD9] text-[#C05621] flex items-center justify-center mb-4">
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
          8. WHO ROOMAN IS FOR
      ========================================================================== */}
      <section className="py-20 bg-slate-50 border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3 py-1 rounded-full border border-[#D0D7F9]">
              Built for Modern Commerce
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
              Who Is Rooman Billing For?
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Engineered to support modern business models from high-velocity SaaS to complex contract billing.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {targetAudiences.map((audience, aIdx) => {
              const IconComp = audience.icon;
              const isSelected = activeAudienceIndex === aIdx;
              return (
                <div
                  key={aIdx}
                  onClick={() => setActiveAudienceIndex(aIdx)}
                  className={`rounded-2xl p-6 border transition-all cursor-pointer flex flex-col justify-between ${
                    isSelected
                      ? 'bg-white border-[#3F51C9] shadow-elevated scale-[1.02]'
                      : 'bg-white/80 border-[#E7E9F2] shadow-xs hover:bg-white hover:shadow-card'
                  }`}
                >
                  <div>
                    <div className="w-10 h-10 rounded-xl bg-[#E8EBFC] text-[#3F51C9] flex items-center justify-center mb-4">
                      <IconComp className="w-5 h-5" />
                    </div>
                    <h3 className="text-lg font-bold text-slate-900">{audience.title}</h3>
                    <p className="mt-2 text-xs text-slate-600 leading-relaxed">{audience.desc}</p>
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-100 text-[11px] text-[#3F51C9] font-medium">
                    {audience.benefit}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* =========================================================================
          9. CUSTOMER EXPERIENCE (TRUTHFUL ARCHITECTURE)
      ========================================================================== */}
      <section className="py-20 bg-white border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-14">
            <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3 py-1 rounded-full border border-[#D0D7F9]">
              Buyer Centricity
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
              A better experience for your customers
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Deliver transparent, frictionless invoicing and payment experiences that build customer confidence.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8">
            {/* Card 1: Customer Portal */}
            <div className="bg-slate-50/70 rounded-2xl p-6 sm:p-7 border border-slate-200 shadow-xs flex flex-col justify-between relative overflow-hidden">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="w-10 h-10 rounded-xl bg-[#E8EBFC] text-[#3F51C9] flex items-center justify-center">
                    <Building2 className="w-5 h-5" />
                  </div>
                  <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-[#DDF4EA] text-[#107548] border border-[#BCEBD6]">
                    Self-Service Portal
                  </span>
                </div>
                <h3 className="text-xl font-bold text-slate-900">Customer Portal</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                  Dedicated self-service interface for your clients to view statements, download PDFs, and inspect payment receipts.
                </p>
              </div>
              <div className="mt-6 pt-4 border-t border-slate-200 text-xs text-[#3F51C9] font-semibold">
                <Link to="/portal/login" className="hover:underline flex items-center gap-1">
                  <span>Open Customer Portal</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>

            {/* Card 2: Hosted Payment Pages */}
            <div className="bg-slate-50/70 rounded-2xl p-6 sm:p-7 border border-slate-200 shadow-xs flex flex-col justify-between relative">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="w-10 h-10 rounded-xl bg-[#DDF4EA] text-[#107548] flex items-center justify-center">
                    <CreditCard className="w-5 h-5" />
                  </div>
                  <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-[#DDF4EA] text-[#107548] border border-[#BCEBD6]">
                    Active
                  </span>
                </div>
                <h3 className="text-xl font-bold text-slate-900">Hosted Payment Pages</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                  Direct, tokenized links for customers to view and pay specific invoices instantly without logging into an account.
                </p>
              </div>
              <div className="mt-6 pt-4 border-t border-slate-200 text-xs text-slate-500 font-medium">
                Integrated with invoice share links
              </div>
            </div>

            {/* Card 3: Simple Billing Experience */}
            <div className="bg-slate-50/70 rounded-2xl p-6 sm:p-7 border border-slate-200 shadow-xs flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="w-10 h-10 rounded-xl bg-[#F9D9E8] text-[#D81B60] flex items-center justify-center">
                    <Sparkles className="w-5 h-5" />
                  </div>
                  <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-[#DDF4EA] text-[#107548] border border-[#BCEBD6]">
                    Active
                  </span>
                </div>
                <h3 className="text-xl font-bold text-slate-900">Simple Billing Experience</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                  Crystal-clear itemized quotes, transparent line breakdown, tax identification, and payment confirmation receipts.
                </p>
              </div>
              <div className="mt-6 pt-4 border-t border-slate-200 text-xs text-slate-500 font-medium">
                Professional branding & PDF exports
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          10. OPERATIONS & GOVERNANCE
      ========================================================================== */}
      <section className="py-20 bg-slate-50 border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-14">
            <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3 py-1 rounded-full border border-[#D0D7F9]">
              Operations & Control
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
              Control Center for Finance Teams
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Centralized tools to track approvals, audit trails, and reconciliation without manual spreadsheets.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <Link
              to="/control-center/action-center"
              className="bg-white p-6 rounded-2xl border border-[#E7E9F2] shadow-xs hover:shadow-card hover:-translate-y-1 transition-all group"
            >
              <div className="w-10 h-10 rounded-xl bg-[#E8EBFC] text-[#3F51C9] flex items-center justify-center mb-4">
                <CheckCircle2 className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900 group-hover:text-[#25247A]">Action Center</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Centralized inbox for pending invoices, overdue reminders, and urgent billing tasks.
              </p>
            </Link>

            <Link
              to="/control-center/approvals"
              className="bg-white p-6 rounded-2xl border border-[#E7E9F2] shadow-xs hover:shadow-card hover:-translate-y-1 transition-all group"
            >
              <div className="w-10 h-10 rounded-xl bg-[#F9D9E8] text-[#D81B60] flex items-center justify-center mb-4">
                <Shield className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900 group-hover:text-[#25247A]">Approval Center</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Multi-level discount approval workflows and policy threshold checkpoints.
              </p>
            </Link>

            <Link
              to="/control-center/reconciliation"
              className="bg-white p-6 rounded-2xl border border-[#E7E9F2] shadow-xs hover:shadow-card hover:-translate-y-1 transition-all group"
            >
              <div className="w-10 h-10 rounded-xl bg-[#DDF4EA] text-[#107548] flex items-center justify-center mb-4">
                <ArrowLeftRight className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900 group-hover:text-[#25247A]">Reconciliation</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Match bank statements and gateway transaction logs to customer invoices.
              </p>
            </Link>

            <Link
              to="/control-center/audit-log"
              className="bg-white p-6 rounded-2xl border border-[#E7E9F2] shadow-xs hover:shadow-card hover:-translate-y-1 transition-all group"
            >
              <div className="w-10 h-10 rounded-xl bg-[#E9E8FA] text-[#25247A] flex items-center justify-center mb-4">
                <Eye className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900 group-hover:text-[#25247A]">Audit Log</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Granular, timestamped audit trail of all pricing adjustments and invoice status changes.
              </p>
            </Link>

            <Link
              to="/control-center/calendar"
              className="bg-white p-6 rounded-2xl border border-[#E7E9F2] shadow-xs hover:shadow-card hover:-translate-y-1 transition-all group"
            >
              <div className="w-10 h-10 rounded-xl bg-[#FCEBD9] text-[#C05621] flex items-center justify-center mb-4">
                <Calendar className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900 group-hover:text-[#25247A]">Billing Calendar</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Schedule upcoming renewal cycles, invoice issue dates, and tax filing milestones.
              </p>
            </Link>

            <Link
              to="/control-center/migration"
              className="bg-white p-6 rounded-2xl border border-[#E7E9F2] shadow-xs hover:shadow-card hover:-translate-y-1 transition-all group"
            >
              <div className="w-10 h-10 rounded-xl bg-[#E8EBFC] text-[#3F51C9] flex items-center justify-center mb-4">
                <Database className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900 group-hover:text-[#25247A]">Data Migration</h3>
              <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                Bulk import customers, legacy invoices, and historical ledger balances safely.
              </p>
            </Link>
          </div>
        </div>
      </section>

      {/* =========================================================================
          11. FREQUENTLY ASKED QUESTIONS
      ========================================================================== */}
      <section id="faq" className="py-20 bg-white border-t border-slate-200">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14">
            <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3 py-1 rounded-full border border-[#D0D7F9]">
              Got Questions?
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
              Frequently Asked Questions
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Clear answers to common questions about Rooman Billing&apos;s architecture, models, and operations.
            </p>
          </div>

          <div className="space-y-4">
            {faqs.map((faq, fIdx) => {
              const isOpen = openFaqIndex === fIdx;
              return (
                <div key={fIdx} className="rounded-2xl border border-[#E7E9F2] overflow-hidden transition-all bg-white">
                  <button
                    type="button"
                    onClick={() => setOpenFaqIndex(isOpen ? null : fIdx)}
                    className="w-full text-left px-6 py-5 flex items-center justify-between gap-4 font-semibold text-slate-900 hover:bg-slate-50/70 transition-colors cursor-pointer"
                    aria-expanded={isOpen}
                  >
                    <span className="text-base">{faq.q}</span>
                    <ChevronDown
                      className={`w-5 h-5 text-slate-400 shrink-0 transition-transform duration-200 ${
                        isOpen ? 'rotate-180 text-[#3F51C9]' : ''
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
        </div>
      </section>

      {/* =========================================================================
          12. FINAL CTA
      ========================================================================== */}
      <section className="py-20 bg-gradient-to-br from-[#11194F] via-[#171B63] to-[#0B0F33] text-white relative overflow-hidden">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[350px] bg-gradient-to-r from-[#3F51C9]/30 to-[#E83E8C]/25 blur-3xl -z-10 rounded-full pointer-events-none" />

        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 text-slate-200 text-xs font-semibold mb-6 backdrop-blur-xs">
            <Sparkles className="w-3.5 h-3.5 text-[#FF75A0]" />
            <span>Ready for unified revenue management</span>
          </div>

          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-white tracking-tight">
            Ready to simplify your billing?
          </h2>
          <p className="mt-4 text-base sm:text-lg text-slate-300 max-w-2xl mx-auto leading-relaxed">
            Bring your catalog, pricing, customers, invoices and payments together with Rooman Billing.
          </p>

          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link to={isAuthenticated ? '/dashboard' : '/signup'} className="w-full sm:w-auto">
              <Button
                variant="primary"
                size="lg"
                className="w-full sm:w-auto font-semibold px-8 py-3.5 text-base bg-gradient-to-r from-[#3F51C9] to-[#E83E8C] text-white hover:opacity-95 shadow-elevated active:scale-[0.98]"
              >
                Get Started
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </Link>
            <button
              type="button"
              onClick={() => scrollToSection('workflow')}
              className="w-full sm:w-auto inline-flex items-center justify-center px-7 py-3.5 rounded-lg border border-white/20 bg-white/10 text-white font-medium hover:bg-white/20 transition-all cursor-pointer text-base backdrop-blur-sm active:scale-[0.98]"
            >
              Explore Platform
            </button>
          </div>
        </div>
      </section>

      {/* =========================================================================
          13. FOOTER
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
                Rooman Billing is an enterprise revenue engine engineered for modern SaaS, commerce, and service businesses.
              </p>
              <div className="mt-4 text-xs text-slate-400">
                &copy; {new Date().getFullYear()} Rooman Technologies. All rights reserved.
              </div>
            </div>

            {/* Product Column */}
            <div>
              <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3">Product</h4>
              <ul className="space-y-2 text-xs text-slate-600">
                <li>
                  <Link to="/catalog" className="hover:text-[#3F51C9] transition-colors">Catalog</Link>
                </li>
                <li>
                  <Link to="/cpq" className="hover:text-[#3F51C9] transition-colors">CPQ</Link>
                </li>
                <li>
                  <Link to="/plans-pricing" className="hover:text-[#3F51C9] transition-colors">Plans & Pricing</Link>
                </li>
                <li>
                  <Link to="/quotes" className="hover:text-[#3F51C9] transition-colors">Quotes</Link>
                </li>
                <li>
                  <Link to="/invoices" className="hover:text-[#3F51C9] transition-colors">Invoices</Link>
                </li>
                <li>
                  <Link to="/payments" className="hover:text-[#3F51C9] transition-colors">Payments</Link>
                </li>
              </ul>
            </div>

            {/* Operations Column */}
            <div>
              <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3">Operations</h4>
              <ul className="space-y-2 text-xs text-slate-600">
                <li>
                  <Link to="/dashboard" className="hover:text-[#3F51C9] transition-colors">Dashboard</Link>
                </li>
                <li>
                  <Link to="/customers" className="hover:text-[#3F51C9] transition-colors">Customers</Link>
                </li>
                <li>
                  <Link to="/control-center/action-center" className="hover:text-[#3F51C9] transition-colors">Action Center</Link>
                </li>
                <li>
                  <Link to="/control-center/approvals" className="hover:text-[#3F51C9] transition-colors">Approvals</Link>
                </li>
                <li>
                  <Link to="/control-center/reconciliation" className="hover:text-[#3F51C9] transition-colors">Reconciliation</Link>
                </li>
                <li>
                  <Link to="/reports" className="hover:text-[#3F51C9] transition-colors">Reports</Link>
                </li>
              </ul>
            </div>

            {/* Account & Auth */}
            <div>
              <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3">Account</h4>
              <ul className="space-y-2 text-xs text-slate-600">
                <li>
                  <Link to="/login" className="hover:text-[#3F51C9] transition-colors">Sign In</Link>
                </li>
                <li>
                  <Link to="/signup" className="hover:text-[#3F51C9] transition-colors">Get Started</Link>
                </li>
                <li>
                  <Link to="/portal/login" className="hover:text-[#3F51C9] transition-colors">Customer Portal</Link>
                </li>
                <li>
                  <Link to="/settings" className="hover:text-[#3F51C9] transition-colors">Settings</Link>
                </li>
              </ul>
            </div>
          </div>

          <div className="pt-8 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-400">
            <div>Rooman Billing Platform &bull; Built for business-critical billing operations.</div>
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
