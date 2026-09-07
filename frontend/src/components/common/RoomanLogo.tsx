export interface RoomanLogoProps {
  variant?: 'shield' | 'full' | 'brand' | 'combined';
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  showBillingBadge?: boolean;
}

export function RoomanLogo({
  variant = 'brand',
  className = '',
  size = 'md',
  showBillingBadge = true,
}: RoomanLogoProps) {
  // Shield emblem icon only (for avatars, favicons, compact badges)
  if (variant === 'shield') {
    const dimensionClass =
      size === 'sm' ? 'w-6 h-6' : size === 'lg' ? 'w-10 h-10' : 'w-7 h-7';
    return (
      <img
        src="/logos/rooman-shield-logo.png"
        alt="Rooman Shield Logo"
        className={`${dimensionClass} object-contain shrink-0 ${className}`}
      />
    );
  }

  // Full image without badge
  if (variant === 'full') {
    const heightClass =
      size === 'sm' ? 'h-6' : size === 'lg' ? 'h-10' : 'h-8';
    return (
      <img
        src="/logos/rooman-full-logo.png"
        alt="Rooman Technologies"
        className={`${heightClass} w-auto object-contain ${className}`}
      />
    );
  }

  // Brand / Combined: Official company logo graphic (Shield + Rooman + Tagline) + Billing badge
  const heightClass =
    size === 'sm' ? 'h-6' : size === 'lg' ? 'h-9' : 'h-7 sm:h-8';

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <img
        src="/logos/rooman-full-logo.png"
        alt="Rooman Technologies"
        className={`${heightClass} w-auto object-contain shrink-0 drop-shadow-2xs`}
      />
      {showBillingBadge && (
        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-blue-50 text-brand-700 border border-blue-200/80 leading-none shadow-3xs tracking-tight shrink-0 self-center">
          Billing
        </span>
      )}
    </div>
  );
}
