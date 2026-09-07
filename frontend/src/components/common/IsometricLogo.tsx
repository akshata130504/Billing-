export function IsometricLogo({ className = 'w-8 h-8' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 36 36"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      {/* Top Diamond Facet */}
      <path
        d="M18 3L31 10.5L18 18L5 10.5L18 3Z"
        fill="#3B82F6"
        stroke="#60A5FA"
        strokeWidth="1"
        strokeLinejoin="round"
      />
      {/* Left Facet */}
      <path
        d="M5 10.5L18 18V33L5 25.5V10.5Z"
        fill="#1D4ED8"
        stroke="#2563EB"
        strokeWidth="1"
        strokeLinejoin="round"
      />
      {/* Right Facet */}
      <path
        d="M18 18L31 10.5V25.5L18 33V18Z"
        fill="#2563EB"
        stroke="#3B82F6"
        strokeWidth="1"
        strokeLinejoin="round"
      />
      {/* Internal Corner highlight */}
      <path
        d="M18 18V33M18 18L5 10.5M18 18L31 10.5"
        stroke="#93C5FD"
        strokeWidth="1"
        strokeLinecap="round"
      />
    </svg>
  );
}
