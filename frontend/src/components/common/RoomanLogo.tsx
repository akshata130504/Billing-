export interface RoomanLogoProps {
  variant?: 'shield' | 'full' | 'combined';
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  showTagline?: boolean;
}

export function RoomanLogo({
  variant = 'combined',
  className = '',
  size = 'md',
  showTagline = false,
}: RoomanLogoProps) {
  if (variant === 'full') {
    const heightClass =
      size === 'sm' ? 'h-6' : size === 'lg' ? 'h-10' : 'h-8';
    return (
      <img
        src="/logos/rooman-full-logo.png"
        alt="Rooman Technologies"
        className={`${heightClass} object-contain ${className}`}
      />
    );
  }

  if (variant === 'shield') {
    const dimensionClass =
      size === 'sm' ? 'w-6 h-6' : size === 'lg' ? 'w-10 h-10' : 'w-8 h-8';
    return (
      <img
        src="/logos/rooman-shield-logo.png"
        alt="Rooman Shield Logo"
        className={`${dimensionClass} object-contain shrink-0 ${className}`}
      />
    );
  }

  // Combined: Shield emblem + Rooman Typography + Billing Badge
  const shieldDim =
    size === 'sm' ? 'w-6 h-6' : size === 'lg' ? 'w-9 h-9' : 'w-7 h-7';
  const titleText =
    size === 'sm' ? 'text-xs' : size === 'lg' ? 'text-base' : 'text-sm';

  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <img
        src="/logos/rooman-shield-logo.png"
        alt="Rooman Logo"
        className={`${shieldDim} object-contain shrink-0 drop-shadow-2xs`}
      />
      <div className="flex flex-col leading-tight min-w-0">
        <div className="flex items-center gap-1.5">
          <span
            className={`${titleText} font-extrabold text-[#1B365D] tracking-tight uppercase`}
          >
            Rooman
          </span>
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-blue-50 text-brand-700 border border-blue-200/80 leading-none">
            Billing
          </span>
        </div>
        {showTagline && (
          <span className="text-[8.5px] font-semibold text-slate-400 tracking-wider uppercase mt-0.5">
            Innovate • Integrate • Empower
          </span>
        )}
      </div>
    </div>
  );
}
