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
<<<<<<< HEAD
  Info,
=======
  TrendingUp,
  Users,
  Workflow,
>>>>>>> origin/main
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
// Living Revenue Pipeline & Micro-Interactions for Core Capabilities
// ---------------------------------------------------------------------------

function CatalogMicroAnimation({ isActive }: { isActive: boolean }) {
  return (
    <div className="w-5 h-5 grid grid-cols-2 gap-0.5 items-center justify-center pointer-events-none" aria-hidden="true">
      <span
        className={`w-2 h-2 rounded-[1.5px] bg-[#3F51C9] transition-all duration-500 ${
          isActive ? 'scale-105 opacity-100 shadow-3xs' : 'opacity-60 scale-90'
        }`}
      />
      <span
        className={`w-2 h-2 rounded-[1.5px] bg-[#6C2BD9] transition-all duration-500 delay-75 ${
          isActive ? 'scale-105 opacity-100 shadow-3xs' : 'opacity-40 scale-90'
        }`}
      />
      <span
        className={`w-2 h-2 rounded-[1.5px] bg-[#8EA5FF] transition-all duration-500 delay-100 ${
          isActive ? 'scale-105 opacity-100 shadow-3xs' : 'opacity-40 scale-90'
        }`}
      />
      <span
        className={`w-2 h-2 rounded-[1.5px] bg-[#E83E8C] transition-all duration-500 delay-150 ${
          isActive ? 'scale-105 opacity-100 shadow-3xs' : 'opacity-60 scale-90'
        }`}
      />
    </div>
  );
}

function PricingMicroAnimation({ isActive }: { isActive: boolean }) {
  return (
    <div className="w-5 h-5 flex items-end justify-center gap-1 pb-0.5 pointer-events-none" aria-hidden="true">
      <span
        className={`w-1 rounded-t-[1px] bg-[#6C2BD9] transition-all duration-500 ${
          isActive ? 'h-2.5 opacity-100' : 'h-1.5 opacity-40'
        }`}
      />
      <span
        className={`w-1 rounded-t-[1px] bg-[#3F51C9] transition-all duration-500 delay-75 ${
          isActive ? 'h-3.5 opacity-100' : 'h-2.5 opacity-60'
        }`}
      />
      <span
        className={`w-1 rounded-t-[1px] bg-[#E83E8C] transition-all duration-500 delay-150 ${
          isActive ? 'h-4.5 opacity-100' : 'h-3.5 opacity-70'
        }`}
      />
    </div>
  );
}

function CpqMicroAnimation({ isActive }: { isActive: boolean }) {
  return (
    <div className="w-5 h-5 flex items-center justify-center gap-0.5 pointer-events-none" aria-hidden="true">
      <span
        className={`w-2 h-3.5 border-2 border-r-0 border-[#25247A] rounded-l-[2px] transition-all duration-500 ${
          isActive ? 'translate-x-0.5 border-[#3F51C9]' : '-translate-x-0.5 opacity-50'
        }`}
      />
      <span
        className={`w-1 h-1 rounded-full bg-[#8EA5FF] transition-all duration-300 ${
          isActive ? 'scale-125 opacity-100' : 'scale-75 opacity-30'
        }`}
      />
      <span
        className={`w-2 h-3.5 border-2 border-l-0 border-[#25247A] rounded-r-[2px] transition-all duration-500 ${
          isActive ? '-translate-x-0.5 border-[#3F51C9]' : 'translate-x-0.5 opacity-50'
        }`}
      />
    </div>
  );
}

function QuotesMicroAnimation({ isActive }: { isActive: boolean }) {
  return (
    <div className="w-5 h-5 flex items-center justify-center pointer-events-none" aria-hidden="true">
      <div className="w-3.5 h-4.5 rounded-[1.5px] border border-slate-300 bg-white p-0.5 flex flex-col justify-between shadow-3xs">
        <span
          className={`h-0.5 rounded-full bg-[#3F51C9] transition-all duration-500 ${
            isActive ? 'w-full opacity-100' : 'w-2/3 opacity-40'
          }`}
        />
        <span
          className={`h-0.5 rounded-full bg-[#6C2BD9] transition-all duration-500 delay-75 ${
            isActive ? 'w-3/4 opacity-100' : 'w-1/2 opacity-30'
          }`}
        />
        <span
          className={`h-0.5 rounded-full bg-[#E83E8C] transition-all duration-500 delay-150 ${
            isActive ? 'w-full opacity-100' : 'w-1/3 opacity-30'
          }`}
        />
      </div>
    </div>
  );
}

function InvoicesMicroAnimation({ isActive }: { isActive: boolean }) {
  return (
    <div className="w-5 h-5 flex items-center justify-center pointer-events-none" aria-hidden="true">
      <div className="w-4 h-4.5 rounded-[1.5px] border border-slate-300 bg-white p-0.5 flex flex-col justify-between shadow-3xs relative">
        <div className="flex justify-between items-center">
          <span className="w-1.5 h-0.5 bg-[#3F51C9] rounded-full" />
          <span
            className={`w-1.5 h-1.5 rounded-full flex items-center justify-center text-[7px] font-bold text-white transition-all duration-500 ${
              isActive ? 'bg-[#107548] scale-100' : 'bg-slate-200 scale-75'
            }`}
          >
            ✓
          </span>
        </div>
        <span className="w-full h-0.5 bg-slate-200 rounded-full" />
        <span className="w-2/3 h-0.5 bg-slate-200 rounded-full" />
      </div>
    </div>
  );
}

function PaymentsMicroAnimation({ isActive, isSuccess }: { isActive: boolean; isSuccess: boolean }) {
  return (
    <div className="w-5 h-5 flex items-center justify-center relative pointer-events-none" aria-hidden="true">
      {isSuccess && (
        <span className="absolute inset-0 rounded-full bg-emerald-400/30 animate-ping" />
      )}
      <div
        className={`w-4.5 h-3.5 rounded-[1.5px] border flex items-center justify-between px-0.5 transition-all duration-500 ${
          isSuccess
            ? 'bg-[#DDF4EA] border-[#107548] text-[#107548] shadow-[0_0_8px_rgba(16,117,72,0.3)]'
            : isActive
            ? 'bg-emerald-50 border-emerald-300 text-emerald-600'
            : 'bg-white border-slate-300 text-slate-400'
        }`}
      >
        <span className="w-1 h-0.5 rounded-[0.5px] bg-current opacity-70" />
        <span className="text-[7.5px] font-bold leading-none">{isSuccess ? '✓' : '₹'}</span>
      </div>
    </div>
  );
}

const CORE_CAPABILITIES = [
  {
    to: '/catalog',
    title: 'Product Catalog',
    desc: 'SKUs & offerings',
    icon: Layers,
    accent: '#3F51C9',
    badgeBg: '#E8EBFC',
    renderMicro: (active: boolean, _success: boolean) => <CatalogMicroAnimation isActive={active} />,
  },
  {
    to: '/plans-pricing',
    title: 'Flexible Pricing',
    desc: '5 fee structures',
    icon: Sliders,
    accent: '#6C2BD9',
    badgeBg: '#EDE9FE',
    renderMicro: (active: boolean, _success: boolean) => <PricingMicroAnimation isActive={active} />,
  },
  {
    to: '/cpq',
    title: 'CPQ Deals',
    desc: 'Guided configuration',
    icon: Cpu,
    accent: '#25247A',
    badgeBg: '#E0E7FF',
    renderMicro: (active: boolean, _success: boolean) => <CpqMicroAnimation isActive={active} />,
  },
  {
    to: '/quotes',
    title: 'Quotes',
    desc: 'Acceptance links',
    icon: FileText,
    accent: '#E83E8C',
    badgeBg: '#FCE7F3',
    renderMicro: (active: boolean, _success: boolean) => <QuotesMicroAnimation isActive={active} />,
  },
  {
    to: '/invoices',
    title: 'Invoices',
    desc: 'GST tax compliant',
    icon: Receipt,
    accent: '#3F51C9',
    badgeBg: '#E8EBFC',
    renderMicro: (active: boolean, _success: boolean) => <InvoicesMicroAnimation isActive={active} />,
  },
  {
    to: '/payments',
    title: 'Payments',
    desc: 'Allocations & refunds',
    icon: CreditCard,
    accent: '#107548',
    badgeBg: '#DDF4EA',
    renderMicro: (active: boolean, success: boolean) => <PaymentsMicroAnimation isActive={active} isSuccess={success} />,
  },
];

function LivingRevenuePipeline() {
  const [activeStage, setActiveStage] = useState<number>(0);
  const [hoveredStage, setHoveredStage] = useState<number | null>(null);
  const [paymentSuccess, setPaymentSuccess] = useState<boolean>(false);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState<boolean>(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPrefersReducedMotion(mediaQuery.matches);
    const handler = (e: MediaQueryListEvent) => setPrefersReducedMotion(e.matches);
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, []);

  useEffect(() => {
    if (prefersReducedMotion) return;

    let successTimer: ReturnType<typeof setTimeout> | null = null;

    const interval = setInterval(() => {
      setActiveStage((prev) => {
        if (prev === 4) {
          successTimer = setTimeout(() => {
            setPaymentSuccess(true);
          }, 900);
          return 5;
        } else if (prev === 5) {
          setPaymentSuccess(false);
          return 0;
        } else {
          setPaymentSuccess(false);
          return prev + 1;
        }
      });
    }, 2000);

    return () => {
      clearInterval(interval);
      if (successTimer) clearTimeout(successTimer);
    };
  }, [prefersReducedMotion]);

  const effectiveStage = hoveredStage !== null ? hoveredStage : activeStage;

  return (
    <div className="relative">
      {/* Living Revenue Pipeline Visual Connection Track (Desktop) */}
      <div className="hidden lg:block mb-5 px-4" aria-hidden="true">
        <div className="relative flex items-center justify-between">
          <div className="absolute left-[7%] right-[7%] top-1/2 -translate-y-1/2 h-[2px] bg-slate-200/70 overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-[#3F51C9] via-[#6C2BD9] via-[#E83E8C] to-[#10B981] transition-all duration-700 ease-out"
              style={{ width: `${(effectiveStage / 5) * 100}%` }}
            />
          </div>

          {CORE_CAPABILITIES.map((cap, idx) => {
            const isCurrent = effectiveStage === idx;
            const isCompleted = effectiveStage > idx;
            return (
              <div key={cap.title} className="relative z-10 flex flex-col items-center">
                <div
                  className={`w-3 h-3 rounded-full border-2 transition-all duration-500 ${
                    isCurrent
                      ? 'border-[#3F51C9] bg-white scale-125 shadow-[0_0_8px_rgba(63,81,201,0.5)] ring-2 ring-[#3F51C9]/20'
                      : isCompleted
                      ? 'border-[#107548] bg-[#107548]'
                      : 'border-slate-300 bg-white'
                  }`}
                />
              </div>
            );
          })}
        </div>
      </div>

      {/* Six-Card Horizontal Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4 relative">
        {CORE_CAPABILITIES.map((card, idx) => {
          const IconComponent = card.icon;
          const isActive = effectiveStage === idx;
          const isHovered = hoveredStage === idx;
          const isPaymentCard = idx === 5;
          const showSuccess = isPaymentCard && (paymentSuccess || (isHovered && activeStage === 5));

          return (
            <div key={card.title} className="relative group">
              <Link
                to={card.to}
                onMouseEnter={() => setHoveredStage(idx)}
                onMouseLeave={() => setHoveredStage(null)}
                className={`flex flex-col justify-between p-4 rounded-2xl border transition-all duration-300 h-full select-none ${
                  showSuccess
                    ? 'bg-[#F0FBF6] border-[#107548] shadow-[0_8px_24px_rgba(16,117,72,0.14)] -translate-y-1'
                    : isHovered
                    ? 'bg-white border-[#3F51C9] shadow-[0_10px_25px_-5px_rgba(63,81,201,0.15)] -translate-y-1.5'
                    : isActive
                    ? 'bg-white border-[#3F51C9]/80 shadow-[0_6px_20px_rgba(63,81,201,0.10)] ring-1 ring-[#3F51C9]/20 -translate-y-0.5'
                    : 'bg-slate-50/80 hover:bg-white border-[#E7E9F2] hover:border-[#3F51C9] hover:shadow-card hover:-translate-y-1'
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <div
                    className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-300 ${
                      showSuccess
                        ? 'bg-[#DDF4EA] text-[#107548] scale-105 shadow-[0_0_10px_rgba(16,117,72,0.25)]'
                        : isHovered || isActive
                        ? `${card.badgeBg} text-[${card.accent}] scale-105 shadow-3xs`
                        : 'bg-[#E8EBFC] text-[#3F51C9]'
                    }`}
                    style={{
                      backgroundColor: (isHovered || isActive) && !showSuccess ? card.badgeBg : undefined,
                      color: (isHovered || isActive) && !showSuccess ? card.accent : undefined,
                    }}
                  >
                    <IconComponent className="w-5 h-5 transition-transform duration-300" />
                  </div>

                  {card.renderMicro(isActive || isHovered, showSuccess)}
                </div>

                <div>
                  <div className="flex items-center justify-between">
                    <span
                      className={`text-xs font-bold transition-colors duration-200 ${
                        showSuccess
                          ? 'text-[#107548]'
                          : isHovered || isActive
                          ? 'text-[#25247A]'
                          : 'text-slate-900 group-hover:text-[#25247A]'
                      }`}
                    >
                      {card.title}
                    </span>
                    {showSuccess && (
                      <span className="text-[10px] font-bold text-[#107548] bg-[#DDF4EA] px-1.5 py-0.2 rounded-full animate-pulse">
                        ✓
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] text-slate-400 mt-0.5">{card.desc}</p>
                </div>
              </Link>

              {idx < 5 && (
                <div
                  className="hidden lg:flex items-center justify-center absolute -right-2 sm:-right-2.5 top-1/2 -translate-y-1/2 z-20 pointer-events-none"
                  aria-hidden="true"
                >
                  <div
                    className={`w-4 h-4 rounded-full flex items-center justify-center transition-all duration-500 ${
                      effectiveStage === idx
                        ? 'bg-gradient-to-r from-[#3F51C9] to-[#6C2BD9] text-white scale-110 shadow-xs ring-2 ring-[#3F51C9]/20'
                        : 'bg-white/90 border border-slate-200 text-slate-300'
                    }`}
                  >
                    <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path d="M9 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Landing Page Component
// ---------------------------------------------------------------------------
export function LandingPage() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  // Navigation & UI States
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [activeNavSection, setActiveNavSection] = useState<string>('');
  const [activeWorkflowTab, setActiveWorkflowTab] = useState<number>(0);
  const [isAutoPlayingWorkflow, setIsAutoPlayingWorkflow] = useState<boolean>(true);
  const [tourProgress, setTourProgress] = useState<number>(0);
  const [isHoveringTour, setIsHoveringTour] = useState<boolean>(false);
  const [selectedPricingModel, setSelectedPricingModel] = useState<number>(0);
  const [simulatorQuantity, setSimulatorQuantity] = useState<number>(150);
  const pricingSectionRef = useRef<HTMLElement | null>(null);
  const hasTriggeredPricingRef = useRef<boolean>(false);
  const [displayPrice, setDisplayPrice] = useState<number>(0);
  const [showPricingBreakdown, setShowPricingBreakdown] = useState<boolean>(false);
  const [isPricingCounting, setIsPricingCounting] = useState<boolean>(false);
  const activePricingAnimRef = useRef<number | null>(null);
  const currentCalculatedPriceRef = useRef<number>(0);
  const [openFaqIndex, setOpenFaqIndex] = useState<number | null>(0);
  const [activeAudienceIndex, setActiveAudienceIndex] = useState<number>(0);
  const [activeTabVisual, setActiveTabVisual] = useState<'transactions' | 'cpq'>('transactions');
  const [videoLoaded, setVideoLoaded] = useState<boolean>(false);
  const [videoFailed, setVideoFailed] = useState<boolean>(false);

  const navItems = [
    { id: 'features', label: 'Product', mobileLabel: 'Product & Features' },
    { id: 'how-it-works', label: 'How It Works', mobileLabel: 'How It Works' },
    { id: 'workflow', label: 'Workflow', mobileLabel: 'End-to-End Workflow' },
    { id: 'pricing-models', label: 'Pricing Models', mobileLabel: 'Pricing Models' },
    { id: 'why-rooman', label: 'Why Rooman', mobileLabel: 'Why Rooman' },
    { id: 'faq', label: 'FAQ', mobileLabel: 'FAQ' },
  ];

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
    setActiveNavSection(id);
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
      desc: 'Predictable, static recurring billing on regular intervals (e.g. ₹299/month).',
      example: 'Enterprise Platform Access',
      calculate: () => 299,
      calcDisplay: 'Fixed ₹299.00 / month regardless of seats',
      features: ['Fixed monthly or annual billing', 'Simple invoice generation', 'Ideal for base platform tiers'],
    },
    {
      title: 'Per Unit',
      type: 'Seat / License',
      desc: 'Linear pricing calculated by multiplying unit price by active user count or license seats.',
      example: '₹15 / active user / month',
      calculate: (qty: number) => qty * 15,
      calcDisplay: (qty: number) => `${qty} units × ₹15.00 = ₹${(qty * 15).toLocaleString('en-IN')}.00 / mo`,
      features: ['Dynamic quantity recalculation', 'Mid-cycle seat adjustments', 'Ideal for SaaS team plans'],
    },
    {
      title: 'Volume',
      type: 'All-Unit Discount',
      desc: 'Total volume purchased qualifies all units for a discounted tier price.',
      example: '1-50 units: ₹20/ea | 51-200 units: ₹14/ea | 201+: ₹10/ea',
      calculate: (qty: number) => {
        const rate = qty > 200 ? 10 : qty > 50 ? 14 : 20;
        return qty * rate;
      },
      calcDisplay: (qty: number) => {
        const rate = qty > 200 ? 10 : qty > 50 ? 14 : 20;
        return `${qty} units @ Volume Tier (₹${rate}/ea) = ₹${(qty * rate).toLocaleString('en-IN')}.00 / mo`;
      },
      features: ['High-volume incentive structures', 'Automatic tier threshold triggers', 'B2B bulk order support'],
    },
    {
      title: 'Tiered / Graduated',
      type: 'Bracketed',
      desc: 'Units are priced progressively within discrete range brackets as volume expands.',
      example: 'First 50 @ ₹20, Next 100 @ ₹12, Beyond @ ₹8',
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
        return `${qty} units split across 3 graduated brackets = ₹${total.toLocaleString('en-IN')}.00 / mo`;
      },
      features: ['Precise margin control', 'Transparent bracketed line items', 'Fair pricing for scaling usage'],
    },
    {
      title: 'Package',
      type: 'Bundled Allotment',
      desc: 'Predefined blocks of units with fixed bundled pricing and overage support.',
      example: 'Block of 50 units @ ₹450/bundle',
      calculate: (qty: number) => {
        const bundles = Math.ceil(qty / 50);
        return bundles * 450;
      },
      calcDisplay: (qty: number) => {
        const bundles = Math.ceil(qty / 50);
        return `${bundles} package bundle(s) required for ${qty} units = ₹${(bundles * 450).toLocaleString('en-IN')}.00 / mo`;
      },
      features: ['Base unit allotments', 'Predictable commitment billing', 'Overage addon compatibility'],
    },
  ];

  // Scroll-triggered initial count-up for Pricing Models (0 -> actual calculated price once on enter)
  useEffect(() => {
    const el = pricingSectionRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && !hasTriggeredPricingRef.current) {
            hasTriggeredPricingRef.current = true;
            const target = pricingModels[selectedPricingModel].calculate(simulatorQuantity);
            const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

            if (prefersReducedMotion) {
              currentCalculatedPriceRef.current = target;
              setDisplayPrice(target);
              setShowPricingBreakdown(true);
              return;
            }

            // Animate smoothly from 0 to target (e.g. 0 -> 75 -> 150 -> 225 -> 299)
            setIsPricingCounting(true);
            const duration = 1200;
            const startTime = performance.now();
            const startVal = 0;

            const step = (now: number) => {
              const elapsed = now - startTime;
              const progress = Math.min(elapsed / duration, 1);
              const ease = 1 - Math.pow(1 - progress, 3);
              const current = Math.round(startVal + (target - startVal) * ease);
              setDisplayPrice(current);
              currentCalculatedPriceRef.current = current;

              if (progress < 1) {
                activePricingAnimRef.current = requestAnimationFrame(step);
              } else {
                setDisplayPrice(target);
                currentCalculatedPriceRef.current = target;
                setIsPricingCounting(false);
                setShowPricingBreakdown(true);
              }
            };

            activePricingAnimRef.current = requestAnimationFrame(step);
          }
        });
      },
      { threshold: 0.25 }
    );

    observer.observe(el);
    return () => {
      observer.disconnect();
      if (activePricingAnimRef.current) cancelAnimationFrame(activePricingAnimRef.current);
    };
  }, [selectedPricingModel, simulatorQuantity]);

  // Subsequent transition when selecting other pricing models or changing quantity
  useEffect(() => {
    if (!hasTriggeredPricingRef.current) return;

    const target = pricingModels[selectedPricingModel].calculate(simulatorQuantity);
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (prefersReducedMotion) {
      currentCalculatedPriceRef.current = target;
      setDisplayPrice(target);
      return;
    }

    if (activePricingAnimRef.current) {
      cancelAnimationFrame(activePricingAnimRef.current);
    }

    const startVal = currentCalculatedPriceRef.current;
    if (startVal === target) return;

    setIsPricingCounting(true);
    const duration = 500;
    const startTime = performance.now();

    const step = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3);
      const current = Math.round(startVal + (target - startVal) * ease);
      setDisplayPrice(current);
      currentCalculatedPriceRef.current = current;

      if (progress < 1) {
        activePricingAnimRef.current = requestAnimationFrame(step);
      } else {
        setDisplayPrice(target);
        currentCalculatedPriceRef.current = target;
        setIsPricingCounting(false);
      }
    };

    activePricingAnimRef.current = requestAnimationFrame(step);
  }, [selectedPricingModel, simulatorQuantity]);

  const currentBreakdown = (() => {
    const qty = simulatorQuantity;
    switch (selectedPricingModel) {
      case 0: // Flat Fee
        return {
          basePrice: '₹299.00',
          basePriceNote: 'Flat recurring fee',
          quantity: 'Fixed',
          quantityNote: 'Unlimited access',
          discount: '₹0.00',
          discountNote: 'Standard platform rate',
          tax: '₹0.00',
          taxNote: 'Net B2B / Excl.',
          finalPrice: 299,
          formula: 'Fixed Platform Rate = ₹299.00 / month',
          explanation: 'Predictable, static recurring billing of ₹299.00/month regardless of usage spikes or seat count, providing stable overhead forecasting.',
        };
      case 1: // Per Unit
        return {
          basePrice: '₹15.00 / unit',
          basePriceNote: 'Per active seat license',
          quantity: `${qty} units`,
          quantityNote: `${qty} active seats`,
          discount: '₹0.00',
          discountNote: 'Linear unit scale',
          tax: '₹0.00',
          taxNote: 'Net B2B / Excl.',
          finalPrice: qty * 15,
          formula: `${qty} units × ₹15.00/unit = ₹${(qty * 15).toLocaleString('en-IN')}.00`,
          explanation: `Linear pricing calculates monthly billing directly by multiplying ${qty} active provisioned seats by ₹15.00/unit with automated mid-cycle proration.`,
        };
      case 2: { // Volume
        const rate = qty > 200 ? 10 : qty > 50 ? 14 : 20;
        const total = qty * rate;
        const savings = (20 - rate) * qty;
        const tierName = qty > 200 ? 'Tier 3 (201+ units @ ₹10)' : qty > 50 ? 'Tier 2 (51-200 units @ ₹14)' : 'Tier 1 (1-50 units @ ₹20)';
        return {
          basePrice: '₹20.00 / unit',
          basePriceNote: 'Baseline Tier 1 rate',
          quantity: `${qty} units`,
          quantityNote: `Qualifies for ${tierName}`,
          discount: rate < 20 ? `-₹${savings.toLocaleString('en-IN')}.00` : '₹0.00',
          discountNote: rate < 20 ? `${Math.round(((20 - rate) / 20) * 100)}% volume savings` : 'Baseline rate (1-50)',
          tax: '₹0.00',
          taxNote: 'Net B2B / Excl.',
          finalPrice: total,
          formula: `${qty} units × ₹${rate}.00/unit (${tierName}) = ₹${total.toLocaleString('en-IN')}.00`,
          explanation: `All ${qty} units qualify for the discounted ${tierName} threshold, generating ₹${savings.toLocaleString('en-IN')} in total volume savings over base rate.`,
        };
      }
      case 3: { // Tiered / Graduated
        let total = 0;
        const t1 = Math.min(qty, 50);
        total += t1 * 20;
        const t2 = qty > 50 ? Math.min(qty - 50, 100) : 0;
        total += t2 * 12;
        const t3 = qty > 150 ? qty - 150 : 0;
        total += t3 * 8;
        const savings = (qty * 20) - total;
        return {
          basePrice: '₹20.00 / unit',
          basePriceNote: 'Bracket 1 initial rate',
          quantity: `${qty} units`,
          quantityNote: 'Distributed in brackets',
          discount: savings > 0 ? `-₹${savings.toLocaleString('en-IN')}.00` : '₹0.00',
          discountNote: savings > 0 ? 'Bracket graduation savings' : 'First bracket only',
          tax: '₹0.00',
          taxNote: 'Net B2B / Excl.',
          finalPrice: total,
          formula: `${t1} @ ₹20${t2 > 0 ? ` + ${t2} @ ₹12` : ''}${t3 > 0 ? ` + ${t3} @ ₹8` : ''} = ₹${total.toLocaleString('en-IN')}.00`,
          explanation: `Units are dynamically bucketed into progressive graduated brackets (first 50 @ ₹20, next 100 @ ₹12, beyond @ ₹8), guaranteeing margin control and transparent line items.`,
        };
      }
      case 4: { // Package
        const bundles = Math.ceil(qty / 50);
        const total = bundles * 450;
        return {
          basePrice: '₹450.00 / bundle',
          basePriceNote: 'Block of 50 units',
          quantity: `${bundles} bundle${bundles > 1 ? 's' : ''}`,
          quantityNote: `Covers ${qty} units (${bundles * 50} capacity)`,
          discount: '₹0.00',
          discountNote: 'Bundled wholesale rate',
          tax: '₹0.00',
          taxNote: 'Net B2B / Excl.',
          finalPrice: total,
          formula: `${bundles} bundle(s) × ₹450.00/bundle = ₹${total.toLocaleString('en-IN')}.00`,
          explanation: `Predefined commitment allotments group units into blocks of 50 at ₹450.00 per bundle, providing predictable volume commitments with zero billing drift.`,
        };
      }
      default:
        return {
          basePrice: '₹299.00',
          basePriceNote: 'Flat monthly base',
          quantity: 'Fixed',
          quantityNote: 'Unlimited access',
          discount: '₹0.00',
          discountNote: 'Standard platform rate',
          tax: '₹0.00',
          taxNote: 'Net B2B / Excl.',
          finalPrice: 299,
          formula: 'Fixed Platform Rate = ₹299.00 / month',
          explanation: 'Predictable recurring billing.',
        };
    }
  })();

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
    <div className="min-h-screen bg-[#F8F9FD] text-slate-900 selection:bg-[#E83E8C] selection:text-white font-sans">
      {/* =========================================================================
          1. TOP NAVIGATION (STICKY WITH BACKDROP BLUR)
      ========================================================================== */}
      <header className="sticky top-0 z-50 bg-[#F8F9FD]/90 backdrop-blur-md border-b border-[#E2E5F5] transition-all shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Brand Logo */}
          <Link to="/" className="flex items-center gap-3 group">
            <RoomanLogo variant="brand" size="md" showBillingBadge />
          </Link>

          {/* Center Navigation Links */}
          <nav className="hidden lg:flex items-center gap-7 text-sm font-medium">
            {navItems.map((item) => {
              const isActive = activeNavSection === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => scrollToSection(item.id)}
                  className={`relative py-1 transition-all cursor-pointer ${
                    isActive
                      ? 'text-[#E83E8C] font-semibold'
                      : 'text-slate-600 hover:text-[#E83E8C]'
                  }`}
                >
                  {item.label}
                  {isActive && (
                    <span className="absolute -bottom-1 left-0 right-0 h-0.5 bg-[#E83E8C] rounded-full transition-all" />
                  )}
                </button>
              );
            })}
          </nav>

          {/* Auth CTA Buttons */}
          <div className="hidden sm:flex items-center gap-3">
            {isAuthenticated ? (
<<<<<<< HEAD
              <>
                <Link to="/login">
                  <Button variant="ghost" size="md" className="text-slate-700 hover:text-slate-900 font-medium">
                    Sign In
                  </Button>
                </Link>
                <Button
                  variant="primary"
                  size="md"
                  onClick={() => navigate('/dashboard')}
                  leadingIcon={<ArrowRight className="w-4 h-4" />}
                  className="bg-[#25247A] hover:bg-[#1C1B63] text-white shadow-sm font-semibold active:scale-[0.98] transition-transform"
                >
                  Dashboard
                </Button>
              </>
=======
              <Button
                variant="primary"
                size="md"
                onClick={() => navigate('/dashboard')}
                trailingIcon={<ArrowRight className="w-4 h-4" />}
                className="bg-[#25247A] hover:bg-[#1C1B63] text-white shadow-sm font-semibold active:scale-[0.98] transition-transform"
              >
                Dashboard
              </Button>
>>>>>>> origin/main
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
          <div className="lg:hidden border-b border-[#E2E5F5] bg-[#F8F9FD] px-4 pt-3 pb-6 space-y-3 shadow-xl animate-in slide-in-from-top-2 duration-150">
            {navItems.map((item) => {
              const isActive = activeNavSection === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => scrollToSection(item.id)}
                  className={`block w-full text-left py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? 'text-[#E83E8C] font-semibold'
                      : 'text-slate-700 hover:text-[#E83E8C]'
                  }`}
                >
                  {item.mobileLabel}
                </button>
              );
            })}

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
<<<<<<< HEAD
                  leadingIcon={<ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />}
=======
                  trailingIcon={<ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />}
>>>>>>> origin/main
                  className="w-full sm:w-auto font-semibold px-8 py-3.5 text-base bg-gradient-to-r from-[#25247A] via-[#3F51C9] to-[#E83E8C] text-white shadow-elevated group active:scale-[0.98] transition-all hover:brightness-110"
                >
                  Get Started
                </Button>
              </Link>
              <button
                type="button"
                onClick={() => scrollToSection('workflow')}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-7 py-3.5 rounded-lg border border-white/20 bg-white/10 text-white font-medium hover:bg-white/20 shadow-xs transition-all active:scale-[0.98] cursor-pointer text-sm sm:text-base backdrop-blur-sm"
              >
                <Layers className="w-4 h-4 text-slate-300" />
                <span>Explore Platform</span>
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
                        <Button
                          variant="outline"
                          size="sm"
                          trailingIcon={<ArrowRight className="w-3.5 h-3.5" />}
                          className="font-semibold text-xs"
                        >
                          Open Full CPQ
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
          3. VALUE STRIP: CORE CAPABILITIES
      ========================================================================== */}
      <section id="features" className="py-12 bg-[#F2F3FB] border-y border-[#E2E5F5]">
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

          <LivingRevenuePipeline />
        </div>
      </section>

      {/* =========================================================================
          4. HOW IT WORKS
      ========================================================================== */}
      <section id="how-it-works" className="py-20 bg-[#F8F9FD]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-10">
            <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3.5 py-1 rounded-full border border-[#D0D7F9]">
              Simple 3-Step Flow
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
              How Rooman Billing Works
            </h2>
            <p className="mt-3 text-base text-slate-600">
              Go from catalog definition to active invoice collection in three straightforward stages.
            </p>
          </div>

          {/* Payment Video Showcase (Fully Visible) */}
          <div className="max-w-4xl mx-auto mb-12 rounded-2xl sm:rounded-3xl overflow-hidden shadow-2xl border border-[#E2E6FB] bg-slate-900 aspect-video relative group">
            <video
              autoPlay
              loop
              muted
              playsInline
              className="w-full h-full object-cover"
            >
              <source src="/videos/Payment.mp4" type="video/mp4" />
              <source src="/videos/payment.mp4" type="video/mp4" />
            </video>
          </div>

          {/* Three Cards Placed A Little After Video - Dynamic & Colourful */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8">
            {howItWorksSteps.map((stepItem, idx) => {
              const IconComp = stepItem.icon;
              const cardThemes = [
                {
                  cardBg: 'bg-gradient-to-br from-indigo-50/90 via-white to-blue-50/60',
                  border: 'border-indigo-100 hover:border-indigo-400',
                  glowShadow: 'hover:shadow-xl hover:shadow-indigo-500/15',
                  topBar: 'bg-gradient-to-r from-blue-600 via-indigo-600 to-cyan-500',
                  iconBg: 'bg-gradient-to-tr from-blue-600 to-indigo-600 text-white shadow-md shadow-blue-500/30',
                  stepColor: 'text-indigo-200 group-hover:text-indigo-600',
                  titleHover: 'group-hover:text-indigo-700',
                  accentBadge: 'bg-blue-100/90 text-blue-700 border-blue-200/80',
                  stageLabel: 'Step 1 • Setup',
                },
                {
                  cardBg: 'bg-gradient-to-br from-purple-50/90 via-white to-fuchsia-50/60',
                  border: 'border-purple-100 hover:border-purple-400',
                  glowShadow: 'hover:shadow-xl hover:shadow-purple-500/15',
                  topBar: 'bg-gradient-to-r from-purple-600 via-fuchsia-600 to-pink-500',
                  iconBg: 'bg-gradient-to-tr from-purple-600 to-pink-600 text-white shadow-md shadow-purple-500/30',
                  stepColor: 'text-purple-200 group-hover:text-purple-600',
                  titleHover: 'group-hover:text-purple-700',
                  accentBadge: 'bg-purple-100/90 text-purple-700 border-purple-200/80',
                  stageLabel: 'Step 2 • CPQ & Quotes',
                },
                {
                  cardBg: 'bg-gradient-to-br from-emerald-50/90 via-white to-teal-50/60',
                  border: 'border-emerald-100 hover:border-emerald-400',
                  glowShadow: 'hover:shadow-xl hover:shadow-emerald-500/15',
                  topBar: 'bg-gradient-to-r from-emerald-600 via-teal-600 to-cyan-500',
                  iconBg: 'bg-gradient-to-tr from-emerald-600 to-teal-600 text-white shadow-md shadow-emerald-500/30',
                  stepColor: 'text-emerald-200 group-hover:text-emerald-600',
                  titleHover: 'group-hover:text-emerald-700',
                  accentBadge: 'bg-emerald-100/90 text-emerald-700 border-emerald-200/80',
                  stageLabel: 'Step 3 • Revenue',
                },
              ];
              const theme = cardThemes[idx % cardThemes.length];

              return (
                <div
                  key={idx}
                  className={`rounded-2xl p-7 border ${theme.border} ${theme.cardBg} ${theme.glowShadow} shadow-md transition-all duration-300 flex flex-col justify-between relative group overflow-hidden hover:-translate-y-2`}
                >
                  {/* Top Dynamic Colorful Accent Bar */}
                  <div className={`absolute top-0 left-0 right-0 h-1.5 ${theme.topBar} transition-all`} />

                  <div>
                    <div className="flex items-center justify-between mb-5 pt-1">
                      <div className={`w-12 h-12 rounded-2xl ${theme.iconBg} flex items-center justify-center font-bold text-lg group-hover:scale-110 group-hover:rotate-3 transition-transform duration-300`}>
                        <IconComp className="w-6 h-6" />
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border ${theme.accentBadge}`}>
                          {theme.stageLabel}
                        </span>
                        <span className={`text-3xl font-black font-mono ${theme.stepColor} transition-colors select-none`}>
                          {stepItem.step}
                        </span>
                      </div>
                    </div>
                    <h3 className={`text-lg font-bold text-[#11194F] ${theme.titleHover} transition-colors`}>
                      {stepItem.title}
                    </h3>
                    <p className="mt-2.5 text-sm text-slate-600 leading-relaxed">
                      {stepItem.desc}
                    </p>
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
      <section id="workflow" className="py-20 bg-[#F2F3FB] border-t border-[#E2E5F5]">
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
                      trailingIcon={<ArrowRight className="w-4 h-4" />}
                      className="bg-gradient-to-r from-[#3F51C9] to-[#E83E8C] text-white font-semibold shadow-sm active:scale-[0.98]"
                    >
                      Open {workflowSteps[activeWorkflowTab].label} in App
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
      <section id="pricing-models" ref={pricingSectionRef} className="py-24 sm:py-32 bg-[#F8F9FD] border-t border-[#E2E5F5]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Header */}
          <div className="text-center max-w-3xl mx-auto mb-14">
            <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3.5 py-1 rounded-full border border-[#D0D7F9] inline-flex items-center gap-1.5">
              Monetization Flexibility
            </span>
            <h2 className="mt-4 text-3xl sm:text-5xl font-extrabold text-[#11194F] tracking-tight">
              Pricing that adapts to your business
            </h2>
            <p className="mt-4 text-base sm:text-lg text-slate-600 leading-relaxed">
              Rooman Billing natively accommodates five distinct monetization models with zero custom coding and deterministic calculation accuracy.
            </p>
          </div>

          {/* 5 Model Selection Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            {pricingModels.map((model, idx) => {
              const isSelected = selectedPricingModel === idx;
              return (
                <div
                  key={model.title}
                  onClick={() => setSelectedPricingModel(idx)}
                  className={`rounded-2xl p-5 border transition-all cursor-pointer flex flex-col justify-between ${
                    isSelected
                      ? 'bg-white border-[#3F51C9] ring-2 ring-[#3F51C9]/20 shadow-md scale-[1.01]'
                      : 'bg-slate-50/70 hover:bg-white border-slate-200 hover:border-slate-300 shadow-2xs hover:shadow-xs'
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[11px] font-bold ${
                          isSelected ? 'bg-[#3F51C9] text-white' : 'bg-[#E8EBFC] text-[#3F51C9]'
                        }`}
                      >
                        {model.type}
                      </span>
                      {isSelected && (
                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" title="Active Model" />
                      )}
                    </div>
                    <h3 className="text-base font-bold text-[#11194F]">{model.title}</h3>
                    <p className="mt-2 text-xs text-slate-600 leading-relaxed min-h-[48px]">{model.desc}</p>

                    <div className="mt-3 p-2.5 rounded-xl bg-slate-100/70 border border-slate-200/70 text-[11px] font-mono text-slate-700">
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
                    <span className={`text-xs font-semibold ${isSelected ? 'text-[#3F51C9]' : 'text-slate-400'}`}>
                      {isSelected ? '✓ Active Model' : 'Select Model'}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Live Price Calculation Display (The Main Visual Feature) */}
          <div className="mt-12 bg-white rounded-3xl p-6 sm:p-10 border border-[#E2E5F5] shadow-lg shadow-indigo-500/5 max-w-5xl mx-auto">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 pb-6 border-b border-slate-100">
              {/* Live Badge */}
              <div className="space-y-1.5">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200/80 text-[11px] font-bold tracking-wider uppercase">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  LIVE PRICE CALCULATION
                </div>
                <div className="text-xs text-slate-500">
                  Real-time billing engine output for <span className="font-semibold text-[#11194F]">{pricingModels[selectedPricingModel].title}</span>
                </div>
              </div>

              {/* Slider for models with unit quantity */}
              {selectedPricingModel > 0 ? (
                <div className="flex-1 max-w-sm bg-slate-50 p-3.5 rounded-xl border border-slate-200/80">
                  <div className="flex justify-between items-center text-xs font-medium text-slate-700 mb-1.5">
                    <span>Simulate Units / Seats:</span>
                    <span className="font-bold font-mono text-[#3F51C9] text-sm bg-white px-2 py-0.5 rounded border border-[#3F51C9]/20 shadow-2xs">
                      {simulatorQuantity} units
                    </span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="500"
                    value={simulatorQuantity}
                    onChange={(e) => setSimulatorQuantity(Number(e.target.value))}
                    className="w-full accent-[#3F51C9] h-2 bg-slate-200 rounded-lg cursor-pointer"
                  />
                  <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                    <span>1</span>
                    <span>250</span>
                    <span>500 units</span>
                  </div>
                </div>
              ) : (
                <div className="px-4 py-2 rounded-xl bg-slate-50 border border-slate-200/80 text-xs text-slate-500 flex items-center gap-2">
                  <Check className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>Flat platform rate covers all included usage & seats</span>
                </div>
              )}
            </div>

            {/* Big Final Price Display */}
            <div className="py-8 text-center sm:text-left flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-4">
              <div>
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                  Calculated Monthly Price
                </div>
                <div className="flex items-baseline justify-center sm:justify-start gap-1">
                  <span className="text-3xl sm:text-5xl font-semibold text-slate-500">₹</span>
                  <span className="text-5xl sm:text-7xl font-extrabold text-[#11194F] tracking-tight font-mono tabular-nums">
                    {displayPrice.toLocaleString('en-IN')}
                  </span>
                  <span className="text-lg sm:text-xl font-medium text-slate-500 ml-1">/ month</span>
                  {isPricingCounting && (
                    <span className="ml-2 inline-flex items-center text-xs font-semibold text-[#3F51C9] animate-pulse">
                      calculating...
                    </span>
                  )}
                </div>
                <div className="mt-2 flex items-center justify-center sm:justify-start gap-2">
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-xs font-medium border border-emerald-200">
                    <Check className="w-3 h-3 text-emerald-600" />
                    Verified Deterministic Result
                  </span>
                  <span className="text-xs text-slate-400">•</span>
                  <span className="text-xs text-slate-500">B2B Audit Ready</span>
                </div>
              </div>

              <div className="sm:text-right text-xs text-slate-500">
                <div className="font-mono text-[#3F51C9] font-bold text-sm">
                  {pricingModels[selectedPricingModel].type}
                </div>
                <div className="text-[11px] text-slate-400 mt-0.5">
                  Tenant Isolation Verified
                </div>
              </div>
            </div>

            {/* Step-by-Step Calculation: Base Price → Quantity → Discount → Tax → Final Price */}
            <div
              className={`mt-2 pt-6 border-t border-slate-100 transition-all duration-700 ${
                showPricingBreakdown ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3'
              }`}
            >
              <div className="flex items-center justify-between mb-4">
                <div className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-2">
                  <span>Calculation Steps</span>
                  <span className="text-slate-300">•</span>
                  <span className="text-slate-400 font-normal">Base Price &rarr; Quantity &rarr; Discount &rarr; Tax &rarr; Final Price</span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
                {/* Step 1: Base Price */}
                <div className="p-4 rounded-xl bg-slate-50/80 border border-slate-200/70 flex flex-col justify-between">
                  <div>
                    <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Step 1</div>
                    <div className="text-xs font-semibold text-[#11194F] mt-0.5">Base Price</div>
                  </div>
                  <div className="my-2 text-base font-bold text-[#11194F] font-mono">{currentBreakdown.basePrice}</div>
                  <div className="text-[11px] text-slate-500">{currentBreakdown.basePriceNote}</div>
                </div>

                {/* Step 2: Quantity */}
                <div className="p-4 rounded-xl bg-slate-50/80 border border-slate-200/70 flex flex-col justify-between">
                  <div>
                    <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Step 2</div>
                    <div className="text-xs font-semibold text-[#11194F] mt-0.5">Quantity</div>
                  </div>
                  <div className="my-2 text-base font-bold text-[#3F51C9] font-mono">{currentBreakdown.quantity}</div>
                  <div className="text-[11px] text-slate-500">{currentBreakdown.quantityNote}</div>
                </div>

                {/* Step 3: Discount */}
                <div className="p-4 rounded-xl bg-slate-50/80 border border-slate-200/70 flex flex-col justify-between">
                  <div>
                    <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Step 3</div>
                    <div className="text-xs font-semibold text-[#11194F] mt-0.5">Discount</div>
                  </div>
                  <div
                    className={`my-2 text-base font-bold font-mono ${
                      currentBreakdown.discount.startsWith('-') ? 'text-emerald-600' : 'text-slate-700'
                    }`}
                  >
                    {currentBreakdown.discount}
                  </div>
                  <div className="text-[11px] text-slate-500">{currentBreakdown.discountNote}</div>
                </div>

                {/* Step 4: Tax */}
                <div className="p-4 rounded-xl bg-slate-50/80 border border-slate-200/70 flex flex-col justify-between">
                  <div>
                    <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Step 4</div>
                    <div className="text-xs font-semibold text-[#11194F] mt-0.5">Tax (GST)</div>
                  </div>
                  <div className="my-2 text-base font-bold text-slate-700 font-mono">{currentBreakdown.tax}</div>
                  <div className="text-[11px] text-slate-500">{currentBreakdown.taxNote}</div>
                </div>

                {/* Step 5: Final Price */}
                <div className="p-4 rounded-xl bg-gradient-to-br from-[#E8EBFC] to-white border border-[#3F51C9]/30 ring-1 ring-[#3F51C9]/20 flex flex-col justify-between">
                  <div>
                    <div className="text-[10px] font-bold text-[#3F51C9] uppercase tracking-wider">Step 5</div>
                    <div className="text-xs font-bold text-[#11194F] mt-0.5">Final Price</div>
                  </div>
                  <div className="my-2 text-lg font-extrabold text-[#11194F] font-mono">
                    ₹{displayPrice.toLocaleString('en-IN')}
                  </div>
                  <div className="text-[11px] text-emerald-600 font-semibold flex items-center gap-1">
                    <Check className="w-3 h-3 text-emerald-500" />
                    <span>Calculated Total</span>
                  </div>
                </div>
              </div>
            </div>

            {/* "Why this price?" */}
            <div className="mt-6 p-4 rounded-2xl bg-[#F7F8FC] border border-[#E7E9F2] text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2 pb-2 border-b border-slate-200/60">
                <div className="flex items-center gap-2">
                  <Info className="w-4 h-4 text-[#3F51C9]" />
                  <span className="font-bold text-[#11194F] text-sm">Why this price?</span>
                </div>
                <span className="text-xs font-mono text-[#3F51C9] bg-[#E8EBFC] px-2.5 py-0.5 rounded-md font-semibold border border-[#D0D7F9]">
                  {currentBreakdown.formula}
                </span>
              </div>
              <p className="text-slate-600 leading-relaxed">
                {currentBreakdown.explanation}
              </p>
            </div>
          </div>

          {/* CTAs */}
          <div className="mt-12 text-center flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link to="/plans-pricing">
              <Button
                variant="primary"
                size="lg"
                trailingIcon={<ArrowRight className="w-4 h-4" />}
                className="bg-[#25247A] text-white font-semibold shadow-sm active:scale-[0.98]"
              >
                Explore Plans & Pricing
              </Button>
            </Link>
            <Link to="/plans-pricing/simulator">
              <Button
                variant="outline"
                size="lg"
                trailingIcon={<ArrowUpRight className="w-4 h-4" />}
                className="font-medium text-[#25247A]"
              >
                Open Full Pricing Simulator
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* =========================================================================
          7. WHY ROOMAN: CONNECTED REVENUE ENGINE
      ========================================================================== */}
      <section id="why-rooman" className="py-20 bg-[#F2F3FB] border-t border-[#E2E5F5]">
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
      <section className="py-20 bg-[#F8F9FD] border-t border-[#E2E5F5]">
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
      <section className="py-20 bg-[#F2F3FB] border-t border-[#E2E5F5]">
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
      <section className="py-20 bg-[#F8F9FD] border-t border-[#E2E5F5]">
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
      <section id="faq" className="py-20 bg-[#F2F3FB] border-t border-[#E2E5F5]">
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
                trailingIcon={<ArrowRight className="w-4 h-4" />}
                className="w-full sm:w-auto font-semibold px-8 py-3.5 text-base bg-gradient-to-r from-[#3F51C9] to-[#E83E8C] text-white hover:opacity-95 shadow-elevated active:scale-[0.98]"
              >
                Get Started
              </Button>
            </Link>
            <button
              type="button"
              onClick={() => scrollToSection('workflow')}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-7 py-3.5 rounded-lg border border-white/20 bg-white/10 text-white font-medium hover:bg-white/20 transition-all cursor-pointer text-base backdrop-blur-sm active:scale-[0.98]"
            >
              <Layers className="w-4 h-4 text-slate-300" />
              <span>Explore Platform</span>
            </button>
          </div>
        </div>
      </section>

      {/* =========================================================================
          13. FOOTER
      ========================================================================== */}
      <footer className="bg-[#EDEFF8] border-t border-[#DCE0F0] pt-14 pb-10">
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
