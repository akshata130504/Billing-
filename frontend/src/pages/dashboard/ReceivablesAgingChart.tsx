interface AgingBucket {
  label: string;
  value: number; // in thousands (₹k)
  color: string;
}

const buckets: AgingBucket[] = [
  { label: 'Current', value: 7.0, color: '#60A5FA' },
  { label: '1-30 Days', value: 5.1, color: '#93C5FD' },
  { label: '31-60 Days', value: 3.2, color: '#FBBF24' },
  { label: '61-90 Days', value: 1.8, color: '#FB923C' },
  { label: '> 90 Days', value: 2.8, color: '#F87171' },
];

export function ReceivablesAgingChart() {
  const svgWidth = 360;
  const svgHeight = 180;
  const paddingLeft = 35;
  const paddingRight = 15;
  const paddingTop = 15;
  const paddingBottom = 25;

  const chartWidth = svgWidth - paddingLeft - paddingRight;
  const chartHeight = svgHeight - paddingTop - paddingBottom;
  const maxValue = 8; // ₹8k

  const barWidth = 26;
  const slotWidth = chartWidth / buckets.length;

  const yTicks = [
    { label: '₹8k', value: 8 },
    { label: '₹6k', value: 6 },
    { label: '₹4k', value: 4 },
    { label: '₹2k', value: 2 },
    { label: '₹0', value: 0 },
  ];

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm flex flex-col justify-between">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-900 tracking-tight">
          Receivables Aging
        </h3>
      </div>

      {/* SVG Bar Chart */}
      <div className="w-full">
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="w-full h-44 overflow-visible"
        >
          {/* Grid lines & Y-axis labels */}
          {yTicks.map((tick) => {
            const y = paddingTop + chartHeight - (tick.value / maxValue) * chartHeight;
            return (
              <g key={tick.label}>
                <line
                  x1={paddingLeft}
                  y1={y}
                  x2={svgWidth - paddingRight}
                  y2={y}
                  stroke="#F1F5F9"
                  strokeWidth="1"
                  strokeDasharray="2 2"
                />
                <text
                  x={paddingLeft - 8}
                  y={y + 3.5}
                  textAnchor="end"
                  className="text-[10px] fill-slate-400 font-mono"
                >
                  {tick.label}
                </text>
              </g>
            );
          })}

          {/* Bars */}
          {buckets.map((bucket, i) => {
            const h = (bucket.value / maxValue) * chartHeight;
            const x = paddingLeft + i * slotWidth + (slotWidth - barWidth) / 2;
            const y = paddingTop + chartHeight - h;

            return (
              <g key={bucket.label} className="group cursor-pointer">
                <rect
                  x={x}
                  y={y}
                  width={barWidth}
                  height={h}
                  rx="4"
                  fill={bucket.color}
                  className="transition-opacity group-hover:opacity-85"
                />
                {/* X-axis label */}
                <text
                  x={x + barWidth / 2}
                  y={svgHeight - 6}
                  textAnchor="middle"
                  className="text-[9.5px] fill-slate-500 font-medium select-none"
                >
                  {bucket.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
