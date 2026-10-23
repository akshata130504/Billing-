import { Fragment, useState, useEffect, useRef, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Sparkles,
  Layers,
  Check,
  Menu,
  X,
  ChevronDown,
  ArrowUpRight,
  Play,
  Pause,
  Info,
} from 'lucide-react';
import { RoomanLogo } from '../../components/common/RoomanLogo';
import { Button } from '../../components/common/Button';
import { iconFor, toneFor } from './landing/icons';
import { buildBreakdown, calculatePrice } from './landing/pricing';
import type { CapabilityAnimation, LandingContent, SectionKey } from './landing/types';

/**
 * The public landing page, rendered from platform-managed content (see ./landing/types.ts).
 * Pure presentation: the tenant route (LandingPage.tsx) passes the PUBLISHED content, the platform
 * console passes a draft for preview. Markup and styling are those of the original page.
 */

/** Internal paths use the router; validated external https links open in a new tab. */
function SmartLink({ to, className, children, onClick, onMouseEnter, onMouseLeave }: {
  to: string;
  className?: string;
  children: ReactNode;
  onClick?: () => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}) {
  if (to.startsWith('/')) {
    return (
      <Link to={to} className={className} onClick={onClick} onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
        {children}
      </Link>
    );
  }
  return (
    <a href={to} target="_blank" rel="noopener noreferrer" className={className} onClick={onClick}
      onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
      {children}
    </a>
  );
}

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

function renderMicro(animation: CapabilityAnimation, active: boolean, success: boolean) {
  switch (animation) {
    case 'catalog':
      return <CatalogMicroAnimation isActive={active} />;
    case 'pricing':
      return <PricingMicroAnimation isActive={active} />;
    case 'cpq':
      return <CpqMicroAnimation isActive={active} />;
    case 'quotes':
      return <QuotesMicroAnimation isActive={active} />;
    case 'invoices':
      return <InvoicesMicroAnimation isActive={active} />;
    case 'payments':
      return <PaymentsMicroAnimation isActive={active} isSuccess={success} />;
    default:
      return null;
  }
}

type CapabilityCard = LandingContent['capabilities']['cards'][number];

function LivingRevenuePipeline({ cards }: { cards: CapabilityCard[] }) {
  const last = Math.max(cards.length - 1, 0);
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
        if (prev === last - 1) {
          successTimer = setTimeout(() => {
            setPaymentSuccess(true);
          }, 900);
          return last;
        } else if (prev >= last) {
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
  }, [prefersReducedMotion, last]);

  const effectiveStage = hoveredStage !== null ? hoveredStage : activeStage;

  return (
    <div className="relative">
      {/* Living Revenue Pipeline Visual Connection Track (Desktop) */}
      <div className="hidden lg:block mb-5 px-4" aria-hidden="true">
        <div className="relative flex items-center justify-between">
          <div className="absolute left-[7%] right-[7%] top-1/2 -translate-y-1/2 h-[2px] bg-slate-200/70 overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-[#3F51C9] via-[#6C2BD9] via-[#E83E8C] to-[#10B981] transition-all duration-700 ease-out"
              style={{ width: `${(effectiveStage / Math.max(last, 1)) * 100}%` }}
            />
          </div>

          {cards.map((cap, idx) => {
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
        {cards.map((card, idx) => {
          const IconComponent = iconFor(card.icon);
          const isActive = effectiveStage === idx;
          const isHovered = hoveredStage === idx;
          const isPaymentCard = idx === last;
          const showSuccess = isPaymentCard && (paymentSuccess || (isHovered && activeStage === last));

          return (
            <div key={card.title} className="relative group">
              <SmartLink
                to={card.link}
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
                        ? `${card.badge_bg} text-[${card.accent}] scale-105 shadow-3xs`
                        : 'bg-[#E8EBFC] text-[#3F51C9]'
                    }`}
                    style={{
                      backgroundColor: (isHovered || isActive) && !showSuccess ? card.badge_bg : undefined,
                      color: (isHovered || isActive) && !showSuccess ? card.accent : undefined,
                    }}
                  >
                    <IconComponent className="w-5 h-5 transition-transform duration-300" />
                  </div>

                  {renderMicro(card.animation, isActive || isHovered, showSuccess)}
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
              </SmartLink>

              {idx < last && (
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
export interface LandingViewProps {
  content: LandingContent;
  isAuthenticated: boolean;
}

export function LandingView({ content, isAuthenticated }: LandingViewProps) {
  const navigate = useNavigate();
  const visible = <T extends { visible?: boolean }>(items: T[]) => items.filter((item) => item.visible !== false);
  const hero = content.hero;
  const wf = content.workflow;
  const pr = content.pricing;
  const capabilityCards = visible(content.capabilities.cards);

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
  const [videoLoaded, setVideoLoaded] = useState<boolean>(false);
  const [videoFailed, setVideoFailed] = useState<boolean>(false);

  const navItems = visible(content.header.nav);

  // Auto cycle workflow steps with fine-grained animated progress bar (4.2 seconds per step)
  const TOUR_DURATION = 4200;
  const UPDATE_INTERVAL = 50;
  const workflowSteps = visible(wf.steps);
  const workflowCount = Math.max(workflowSteps.length, 1);

  useEffect(() => {
    if (!isAutoPlayingWorkflow || isHoveringTour) return;

    const timer = setInterval(() => {
      setTourProgress((prev) => {
        const next = prev + (UPDATE_INTERVAL / TOUR_DURATION) * 100;
        if (next >= 100) {
          setActiveWorkflowTab((cur) => (cur + 1) % workflowCount);
          return 0;
        }
        return next;
      });
    }, UPDATE_INTERVAL);

    return () => clearInterval(timer);
  }, [isAutoPlayingWorkflow, isHoveringTour, workflowCount]);

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

  // Pricing models (illustrative marketing examples) with live dynamic preview
  const pricingModels = visible(pr.models);
  const selectedModel = pricingModels[Math.min(selectedPricingModel, Math.max(pricingModels.length - 1, 0))];
  const priceFor = (qty: number) => (selectedModel ? calculatePrice(selectedModel, qty) : 0);

  // Scroll-triggered initial count-up for Pricing Models (0 -> actual calculated price once on enter)
  useEffect(() => {
    const el = pricingSectionRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && !hasTriggeredPricingRef.current) {
            hasTriggeredPricingRef.current = true;
            const target = priceFor(simulatorQuantity);
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
  }, [selectedPricingModel, simulatorQuantity, selectedModel]);

  // Subsequent transition when selecting other pricing models or changing quantity
  useEffect(() => {
    if (!hasTriggeredPricingRef.current) return;

    const target = priceFor(simulatorQuantity);
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
  }, [selectedPricingModel, simulatorQuantity, selectedModel]);

  const currentBreakdown = selectedModel ? buildBreakdown(selectedModel, simulatorQuantity) : null;

  const targetAudiences = visible(content.audiences.items);
  const howItWorksSteps = visible(content.how_it_works.steps);
  const faqs = visible(content.faq.items);
  const activeStep = workflowSteps[Math.min(activeWorkflowTab, workflowSteps.length - 1)];
  const nextStep = workflowSteps[(Math.min(activeWorkflowTab, workflowSteps.length - 1) + 1) % workflowCount];

  const SECTIONS: Record<SectionKey, () => ReactNode> = {
    capabilities: () => (
      <>
        {/* =========================================================================
            3. VALUE STRIP: CORE CAPABILITIES
        ========================================================================== */}
        <section id="features" className="py-12 bg-[#F2F3FB] border-y border-[#E2E5F5]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 mb-8">
              <div className="shrink-0 text-center lg:text-left">
                <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9]">{content.capabilities.eyebrow}</span>
                <h2 className="text-xl sm:text-2xl font-bold text-[#11194F] mt-0.5">
                  {content.capabilities.heading}
                </h2>
              </div>
              <p className="text-xs sm:text-sm text-slate-500 max-w-lg">
                {content.capabilities.description}
              </p>
            </div>

            <LivingRevenuePipeline cards={capabilityCards} />
          </div>
        </section>
      </>
    ),
    how_it_works: () => (
      <>
        {/* =========================================================================
            4. HOW IT WORKS
        ========================================================================== */}
        <section id="how-it-works" className="py-20 bg-[#F8F9FD]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center max-w-3xl mx-auto mb-10">
              <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3.5 py-1 rounded-full border border-[#D0D7F9]">
                {content.how_it_works.badge}
              </span>
              <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
                {content.how_it_works.heading}
              </h2>
              <p className="mt-3 text-base text-slate-600">
                {content.how_it_works.description}
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
                {content.how_it_works.video_sources.map((src) => (
                  <source key={src} src={src} type="video/mp4" />
                ))}
              </video>
            </div>

            {/* Three Cards Placed A Little After Video - Dynamic & Colourful */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8">
              {howItWorksSteps.map((stepItem, idx) => {
                const IconComp = iconFor(stepItem.icon);
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
                            {stepItem.stage_label}
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
      </>
    ),
    workflow: () => (
      <>
        {/* =========================================================================
            5. UPGRADED 9-STAGE QUOTE-TO-CASH AUTO-TOUR
        ========================================================================== */}
        <section id="workflow" className="py-20 bg-[#F2F3FB] border-t border-[#E2E5F5]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center max-w-3xl mx-auto mb-12">
              <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3 py-1 rounded-full border border-[#D0D7F9]">
                {wf.badge}
              </span>
              <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
                {wf.heading}
              </h2>
              <p className="mt-3 text-base text-slate-600">
                {wf.description}
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
                      <Pause className="w-3.5 h-3.5" /> {wf.pause_label}
                    </>
                  ) : (
                    <>
                      <Play className="w-3.5 h-3.5" /> {wf.resume_label}
                    </>
                  )}
                </button>
                <span className="text-slate-300">|</span>
                <span className="text-[11px] text-slate-500">Stage {Math.min(activeWorkflowTab, workflowCount - 1) + 1} of {workflowSteps.length}</span>
              </div>
            </div>

            {/* Stepped Interactive Bar with Active Progress Fill */}
            <div className="bg-slate-50 p-3 sm:p-4 rounded-2xl border border-slate-200 mb-8 overflow-x-auto scrollbar-none shadow-3xs">
              <div className="flex items-center justify-between min-w-[800px] gap-2">
                {workflowSteps.map((step, idx) => {
                  const isActive = activeWorkflowTab === idx;
                  return (
                    <button
                      key={step.key}
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
            {activeStep && (
            <div
              onMouseEnter={() => setIsHoveringTour(true)}
              onMouseLeave={() => setIsHoveringTour(false)}
              className="bg-[#0B0F28] text-white rounded-3xl p-6 sm:p-10 shadow-2xl border border-white/10 transition-all relative overflow-hidden"
            >
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center relative z-10">
                <div className="lg:col-span-7 space-y-4">
                  <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 text-[#8EA5FF] text-xs font-semibold border border-white/15">
                    <span>Stage {activeStep.step} of {String(workflowSteps.length).padStart(2, '0')}</span>
                    <span>&bull;</span>
                    <span>{activeStep.badge}</span>
                  </div>
                  <h3 className="text-2xl sm:text-3xl font-extrabold text-white">
                    {activeStep.title}
                  </h3>
                  <p className="text-slate-300 text-sm sm:text-base leading-relaxed">
                    {activeStep.desc}
                  </p>

                  {/* Key Feature Pills */}
                  <div className="flex flex-wrap gap-2 pt-2">
                    {activeStep.details.map((detail, dIdx) => (
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
                    <SmartLink to={activeStep.link}>
                      <Button
                        variant="primary"
                        size="md"
                        trailingIcon={<ArrowRight className="w-4 h-4" />}
                        className="bg-gradient-to-r from-[#3F51C9] to-[#E83E8C] text-white font-semibold shadow-sm active:scale-[0.98]"
                      >
                        {wf.open_label.replace('{label}', activeStep.label)}
                      </Button>
                    </SmartLink>
                    <span className="text-xs text-slate-400">
                      {wf.footnote}
                    </span>
                  </div>
                </div>

                {/* Stage Real-time Preview Panel */}
                <div className="lg:col-span-5 bg-white/5 backdrop-blur-md rounded-2xl p-5 border border-white/10 text-xs font-mono space-y-3">
                  <div className="flex justify-between items-center pb-2 border-b border-white/10 text-slate-400">
                    <span>{wf.panel_title}</span>
                    <span className="text-emerald-400 flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                      {wf.panel_status}
                    </span>
                  </div>
                  <div className="space-y-2.5 text-slate-200">
                    <div className="flex justify-between">
                      <span className="text-slate-400">{wf.panel_active_label}</span>
                      <span className="font-bold text-white">{activeStep.label}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">{wf.panel_next_label}</span>
                      <span className="text-[#FF75A0]">
                        {nextStep.label} &rarr;
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">{wf.panel_metric_label}</span>
                      <span className="text-emerald-300 font-bold">{activeStep.kpi}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">{wf.panel_validation_label}</span>
                      <span className="text-slate-300">{wf.panel_validation_value}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            )}
          </div>
        </section>
      </>
    ),
    pricing: () => (
      <>
        {/* =========================================================================
            6. PRICING MODELS (INTERACTIVE SIMULATOR)
        ========================================================================== */}
        <section id="pricing-models" ref={pricingSectionRef} className="py-24 sm:py-32 bg-[#F8F9FD] border-t border-[#E2E5F5]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            {/* Header */}
            <div className="text-center max-w-3xl mx-auto mb-14">
              <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3.5 py-1 rounded-full border border-[#D0D7F9] inline-flex items-center gap-1.5">
                {pr.badge}
              </span>
              <h2 className="mt-4 text-3xl sm:text-5xl font-extrabold text-[#11194F] tracking-tight">
                {pr.heading}
              </h2>
              <p className="mt-4 text-base sm:text-lg text-slate-600 leading-relaxed">
                {pr.description}
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
            {selectedModel && currentBreakdown && (
            <div className="mt-12 bg-white rounded-3xl p-6 sm:p-10 border border-[#E2E5F5] shadow-lg shadow-indigo-500/5 max-w-5xl mx-auto">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 pb-6 border-b border-slate-100">
                {/* Live Badge */}
                <div className="space-y-1.5">
                  <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200/80 text-[11px] font-bold tracking-wider uppercase">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    {pr.live_badge}
                  </div>
                  <div className="text-xs text-slate-500">
                    {pr.live_caption} <span className="font-semibold text-[#11194F]">{selectedModel.title}</span>
                  </div>
                </div>

                {/* Slider for models with unit quantity */}
                {selectedModel.kind !== 'flat' ? (
                  <div className="flex-1 max-w-sm bg-slate-50 p-3.5 rounded-xl border border-slate-200/80">
                    <div className="flex justify-between items-center text-xs font-medium text-slate-700 mb-1.5">
                      <span>{pr.simulate_label}</span>
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
                    <span>{pr.flat_note}</span>
                  </div>
                )}
              </div>

              {/* Big Final Price Display */}
              <div className="py-8 text-center sm:text-left flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-4">
                <div>
                  <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                    {pr.calculated_label}
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
                      {pr.verified_label}
                    </span>
                    <span className="text-xs text-slate-400">•</span>
                    <span className="text-xs text-slate-500">{pr.audit_label}</span>
                  </div>
                </div>

                <div className="sm:text-right text-xs text-slate-500">
                  <div className="font-mono text-[#3F51C9] font-bold text-sm">
                    {selectedModel.type}
                  </div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    {pr.isolation_label}
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
                    <span>{pr.steps_title}</span>
                    <span className="text-slate-300">•</span>
                    <span className="text-slate-400 font-normal">{pr.steps_subtitle}</span>
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
                    <span className="font-bold text-[#11194F] text-sm">{pr.why_title}</span>
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
            )}

            {/* CTAs */}
            <div className="mt-12 text-center flex flex-col sm:flex-row items-center justify-center gap-4">
              <SmartLink to={pr.primary_cta_link}>
                <Button
                  variant="primary"
                  size="lg"
                  trailingIcon={<ArrowRight className="w-4 h-4" />}
                  className="bg-[#25247A] text-white font-semibold shadow-sm active:scale-[0.98]"
                >
                  {pr.primary_cta_label}
                </Button>
              </SmartLink>
              <SmartLink to={pr.secondary_cta_link}>
                <Button
                  variant="outline"
                  size="lg"
                  trailingIcon={<ArrowUpRight className="w-4 h-4" />}
                  className="font-medium text-[#25247A]"
                >
                  {pr.secondary_cta_label}
                </Button>
              </SmartLink>
            </div>
          </div>
        </section>
      </>
    ),
    why: () => (
      <>
        {/* =========================================================================
            7. WHY ROOMAN: CONNECTED REVENUE ENGINE
        ========================================================================== */}
        <section id="why-rooman" className="py-20 bg-[#F2F3FB] border-t border-[#E2E5F5]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center max-w-3xl mx-auto mb-16">
              <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3 py-1 rounded-full border border-[#D0D7F9]">
                {content.why.badge}
              </span>
              <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
                {content.why.heading}
              </h2>
              <p className="mt-3 text-base text-slate-600">
                {content.why.description}
              </p>
            </div>

            {/* Connected Flow Diagram Visual */}
            <div className="mb-14 p-6 sm:p-8 rounded-3xl bg-[#0B0F28] text-white border border-white/10 shadow-xl overflow-x-auto">
              <div className="text-center text-xs text-[#8EA5FF] uppercase font-bold tracking-wider mb-6">
                {content.why.pipeline_title}
              </div>
              <div className="flex items-center justify-between min-w-[720px] text-center gap-2">
                {content.why.pipeline.map((node, nIdx, arr) => {
                  const IconComp = iconFor(node.icon);
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
              {visible(content.why.cards).map((card, cIdx) => {
                const IconComp = iconFor(card.icon);
                return (
                  <div key={cIdx} className="bg-white p-6 rounded-2xl border border-[#E7E9F2] shadow-xs hover:shadow-card transition-all">
                    <div className={`w-10 h-10 rounded-xl ${toneFor(card.tone)} flex items-center justify-center mb-4`}>
                      <IconComp className="w-5 h-5" />
                    </div>
                    <h3 className="text-base font-bold text-slate-900">{card.title}</h3>
                    <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                      {card.desc}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      </>
    ),
    audiences: () => (
      <>
        {/* =========================================================================
            8. WHO ROOMAN IS FOR
        ========================================================================== */}
        <section className="py-20 bg-[#F8F9FD] border-t border-[#E2E5F5]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center max-w-3xl mx-auto mb-16">
              <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3 py-1 rounded-full border border-[#D0D7F9]">
                {content.audiences.badge}
              </span>
              <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
                {content.audiences.heading}
              </h2>
              <p className="mt-3 text-base text-slate-600">
                {content.audiences.description}
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {targetAudiences.map((audience, aIdx) => {
                const IconComp = iconFor(audience.icon);
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
      </>
    ),
    customer_experience: () => (
      <>
        {/* =========================================================================
            9. CUSTOMER EXPERIENCE (TRUTHFUL ARCHITECTURE)
        ========================================================================== */}
        <section className="py-20 bg-[#F2F3FB] border-t border-[#E2E5F5]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center max-w-3xl mx-auto mb-14">
              <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3 py-1 rounded-full border border-[#D0D7F9]">
                {content.customer_experience.badge}
              </span>
              <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
                {content.customer_experience.heading}
              </h2>
              <p className="mt-3 text-base text-slate-600">
                {content.customer_experience.description}
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8">
              {visible(content.customer_experience.cards).map((card, cIdx) => {
                const IconComp = iconFor(card.icon);
                const wrapperExtra = cIdx === 0 ? ' relative overflow-hidden' : cIdx === 1 ? ' relative' : '';
                return (
                  <div key={cIdx} className={`bg-slate-50/70 rounded-2xl p-6 sm:p-7 border border-slate-200 shadow-xs flex flex-col justify-between${wrapperExtra}`}>
                    <div>
                      <div className="flex items-center justify-between mb-4">
                        <div className={`w-10 h-10 rounded-xl ${toneFor(card.tone)} flex items-center justify-center`}>
                          <IconComp className="w-5 h-5" />
                        </div>
                        <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-[#DDF4EA] text-[#107548] border border-[#BCEBD6]">
                          {card.status_badge}
                        </span>
                      </div>
                      <h3 className="text-xl font-bold text-slate-900">{card.title}</h3>
                      <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                        {card.desc}
                      </p>
                    </div>
                    {card.footer_link ? (
                      <div className="mt-6 pt-4 border-t border-slate-200 text-xs text-[#3F51C9] font-semibold">
                        <SmartLink to={card.footer_link} className="hover:underline flex items-center gap-1">
                          <span>{card.footer_text}</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </SmartLink>
                      </div>
                    ) : (
                      <div className="mt-6 pt-4 border-t border-slate-200 text-xs text-slate-500 font-medium">
                        {card.footer_text}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      </>
    ),
    operations: () => (
      <>
        {/* =========================================================================
            10. OPERATIONS & GOVERNANCE
        ========================================================================== */}
        <section className="py-20 bg-[#F8F9FD] border-t border-[#E2E5F5]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center max-w-3xl mx-auto mb-14">
              <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3 py-1 rounded-full border border-[#D0D7F9]">
                {content.operations.badge}
              </span>
              <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
                {content.operations.heading}
              </h2>
              <p className="mt-3 text-base text-slate-600">
                {content.operations.description}
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {visible(content.operations.cards).map((card, cIdx) => {
                const IconComp = iconFor(card.icon);
                return (
                  <SmartLink
                    key={cIdx}
                    to={card.link}
                    className="bg-white p-6 rounded-2xl border border-[#E7E9F2] shadow-xs hover:shadow-card hover:-translate-y-1 transition-all group"
                  >
                    <div className={`w-10 h-10 rounded-xl ${toneFor(card.tone)} flex items-center justify-center mb-4`}>
                      <IconComp className="w-5 h-5" />
                    </div>
                    <h3 className="text-base font-bold text-slate-900 group-hover:text-[#25247A]">{card.title}</h3>
                    <p className="mt-2 text-xs text-slate-600 leading-relaxed">
                      {card.desc}
                    </p>
                  </SmartLink>
                );
              })}
            </div>
          </div>
        </section>
      </>
    ),
    faq: () => (
      <>
        {/* =========================================================================
            11. FREQUENTLY ASKED QUESTIONS
        ========================================================================== */}
        <section id="faq" className="py-20 bg-[#F2F3FB] border-t border-[#E2E5F5]">
          <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center mb-14">
              <span className="text-xs font-bold uppercase tracking-wider text-[#3F51C9] bg-[#E8EBFC] px-3 py-1 rounded-full border border-[#D0D7F9]">
                {content.faq.badge}
              </span>
              <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold text-[#11194F] tracking-tight">
                {content.faq.heading}
              </h2>
              <p className="mt-3 text-base text-slate-600">
                {content.faq.description}
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
      </>
    ),
    final_cta: () => (
      <>
        {/* =========================================================================
            12. FINAL CTA
        ========================================================================== */}
        <section className="py-20 bg-gradient-to-br from-[#11194F] via-[#171B63] to-[#0B0F33] text-white relative overflow-hidden">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[350px] bg-gradient-to-r from-[#3F51C9]/30 to-[#E83E8C]/25 blur-3xl -z-10 rounded-full pointer-events-none" />

          <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 text-slate-200 text-xs font-semibold mb-6 backdrop-blur-xs">
              <Sparkles className="w-3.5 h-3.5 text-[#FF75A0]" />
              <span>{content.final_cta.badge}</span>
            </div>

            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-white tracking-tight">
              {content.final_cta.heading}
            </h2>
            <p className="mt-4 text-base sm:text-lg text-slate-300 max-w-2xl mx-auto leading-relaxed">
              {content.final_cta.description}
            </p>

            <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link to={isAuthenticated ? '/dashboard' : '/signup'} className="w-full sm:w-auto">
                <Button
                  variant="primary"
                  size="lg"
                  trailingIcon={<ArrowRight className="w-4 h-4" />}
                  className="w-full sm:w-auto font-semibold px-8 py-3.5 text-base bg-gradient-to-r from-[#3F51C9] to-[#E83E8C] text-white hover:opacity-95 shadow-elevated active:scale-[0.98]"
                >
                  {content.final_cta.primary_cta_label}
                </Button>
              </Link>
              <button
                type="button"
                onClick={() => scrollToSection('workflow')}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-7 py-3.5 rounded-lg border border-white/20 bg-white/10 text-white font-medium hover:bg-white/20 transition-all cursor-pointer text-base backdrop-blur-sm active:scale-[0.98]"
              >
                <Layers className="w-4 h-4 text-slate-300 shrink-0" />
                <span>{content.final_cta.secondary_cta_label}</span>
              </button>
            </div>
          </div>
        </section>
      </>
    ),
  };
  const sectionOrder = content.section_order.filter((key, i, all) => key in SECTIONS && all.indexOf(key) === i);

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
              const isActive = activeNavSection === item.target;
              return (
                <button
                  key={item.target}
                  type="button"
                  onClick={() => scrollToSection(item.target)}
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
              <Button
                variant="primary"
                size="md"
                onClick={() => navigate('/dashboard')}
                trailingIcon={<ArrowRight className="w-4 h-4" />}
                className="bg-[#25247A] hover:bg-[#1C1B63] text-white shadow-sm font-semibold active:scale-[0.98] transition-transform"
              >
                {content.header.dashboard_label}
              </Button>
            ) : (
              <>
                <Link to="/login">
                  <Button variant="ghost" size="md" className="text-slate-700 hover:text-slate-900 font-medium">
                    {content.header.sign_in_label}
                  </Button>
                </Link>
                <Link to="/signup">
                  <Button
                    variant="primary"
                    size="md"
                    className="bg-gradient-to-r from-[#25247A] via-[#3F51C9] to-[#E83E8C] hover:opacity-95 text-white shadow-sm font-semibold active:scale-[0.98] transition-all"
                  >
                    {content.header.get_started_label}
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
              const isActive = activeNavSection === item.target;
              return (
                <button
                  key={item.target}
                  type="button"
                  onClick={() => scrollToSection(item.target)}
                  className={`block w-full text-left py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? 'text-[#E83E8C] font-semibold'
                      : 'text-slate-700 hover:text-[#E83E8C]'
                  }`}
                >
                  {item.mobile_label}
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
                  {content.header.mobile_dashboard_label}
                </Button>
              ) : (
                <>
                  <Link to="/login" className="w-full" onClick={() => setMobileMenuOpen(false)}>
                    <Button variant="outline" size="md" className="w-full justify-center">
                      {content.header.sign_in_label}
                    </Button>
                  </Link>
                  <Link to="/signup" className="w-full" onClick={() => setMobileMenuOpen(false)}>
                    <Button
                      variant="primary"
                      size="md"
                      className="w-full justify-center font-semibold bg-gradient-to-r from-[#25247A] to-[#E83E8C] text-white"
                    >
                      {content.header.get_started_label}
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
      {hero.visible && (
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
              <source src={hero.video_src} type="video/mp4" />
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
              <span>{hero.badge}</span>
            </div>

            {/* Headline */}
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-white tracking-tight leading-[1.12]">
              {hero.headline}{' '}
              <span className="bg-clip-text text-transparent bg-gradient-to-r from-[#8EA5FF] via-[#E9E8FA] to-[#FF75A0]">
                {hero.headline_highlight}
              </span>
            </h1>

            {/* Supporting Text */}
            <p className="mt-5 text-lg sm:text-xl font-medium text-slate-300 leading-relaxed max-w-2xl mx-auto">
              {hero.subheading}
            </p>

            {/* CTA Buttons */}
            <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link to={isAuthenticated ? '/dashboard' : '/signup'} className="w-full sm:w-auto">
                <Button
                  variant="primary"
                  size="lg"
                  trailingIcon={<ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />}
                  className="w-full sm:w-auto font-semibold px-8 py-3.5 text-base bg-gradient-to-r from-[#25247A] via-[#3F51C9] to-[#E83E8C] text-white shadow-elevated group active:scale-[0.98] transition-all hover:brightness-110"
                >
                  {hero.primary_cta_label}
                </Button>
              </Link>
              <button
                type="button"
                onClick={() => scrollToSection('workflow')}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-7 py-3.5 rounded-lg border border-white/20 bg-white/10 text-white font-medium hover:bg-white/20 shadow-xs transition-all active:scale-[0.98] cursor-pointer text-sm sm:text-base backdrop-blur-sm"
              >
                <Layers className="w-4 h-4 text-slate-300 shrink-0" />
                <span>{hero.secondary_cta_label}</span>
              </button>
            </div>
          </div>
        </div>
      </section>
      )}

      {sectionOrder.map((key) => (
        <Fragment key={key}>{content[key].visible ? SECTIONS[key]() : null}</Fragment>
      ))}

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
                {content.footer.tagline}
              </p>
              <div className="mt-4 text-xs text-slate-400">
                &copy; {new Date().getFullYear()} {content.footer.copyright_holder}. All rights reserved.
              </div>
            </div>

            {content.footer.columns.map((column, colIdx) => (
              <div key={colIdx}>
                <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3">{column.title}</h4>
                <ul className="space-y-2 text-xs text-slate-600">
                  {column.links.map((link, linkIdx) => (
                    <li key={linkIdx}>
                      <SmartLink to={link.link} className="hover:text-[#3F51C9] transition-colors">{link.label}</SmartLink>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="pt-8 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-400">
            <div>{content.footer.bottom_text}</div>
            <div className="flex items-center gap-6">
              {content.footer.bottom_badges.map((badge, bIdx) => (
                <Fragment key={bIdx}>
                  {bIdx > 0 && <span>&bull;</span>}
                  <span className="text-slate-500 font-medium">{badge}</span>
                </Fragment>
              ))}
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
