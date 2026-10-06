import { ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export function BillingPromoCard({ title = 'Streamline Your Billing' }: { title?: string } = {}) {
  const navigate = useNavigate();

  return (
    <div className="relative overflow-hidden bg-white p-5 rounded-2xl border border-[#E7E9F2] shadow-sm flex flex-col justify-between min-h-[140px] group">
      {/* Decorative Wave Graphics in Bottom-Right */}
      <div className="absolute right-0 bottom-0 w-48 h-28 pointer-events-none opacity-90">
        <svg
          viewBox="0 0 200 120"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="w-full h-full object-cover"
          preserveAspectRatio="none"
        >
          <path
            d="M20 120 C 60 70, 100 110, 160 50 C 180 35, 200 60, 200 60 L 200 120 Z"
            fill="url(#promoGradient1)"
            opacity="0.4"
          />
          <path
            d="M50 120 C 90 85, 120 115, 170 70 C 185 55, 200 75, 200 75 L 200 120 Z"
            fill="url(#promoGradient2)"
            opacity="0.75"
          />
          <path
            d="M90 120 C 130 95, 150 115, 190 85 C 195 80, 200 90, 200 90 L 200 120 Z"
            fill="url(#promoGradient3)"
            opacity="0.9"
          />
          <defs>
            <linearGradient id="promoGradient1" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#FCEBD9" />
              <stop offset="100%" stopColor="#F9D9E8" />
            </linearGradient>
            <linearGradient id="promoGradient2" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#F9D9E8" />
              <stop offset="100%" stopColor="#E83E8C" />
            </linearGradient>
            <linearGradient id="promoGradient3" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#E83E8C" />
              <stop offset="100%" stopColor="#25247A" />
            </linearGradient>
          </defs>
        </svg>
      </div>

      {/* Card Typography Content */}
      <div className="relative z-10 space-y-1">
        <h4 className="text-sm font-bold text-[#11194F] tracking-tight leading-snug">
          {title}
        </h4>
        <h4 className="text-sm font-bold text-[#11194F] tracking-tight leading-snug">
          Empower Your Growth
        </h4>
        <p className="text-[11px] font-medium text-[#7B829A] pt-1">
          Rooman Billing
        </p>
      </div>

      {/* Action Arrow Button */}
      <div className="relative z-10 flex justify-end mt-4">
        <button
          type="button"
          onClick={() => navigate('/automation')}
          aria-label="Explore billing features"
          className="w-8 h-8 rounded-full bg-[#25247A] hover:bg-[#171B63] text-white flex items-center justify-center shadow-xs transition-transform group-hover:scale-110 cursor-pointer"
        >
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
