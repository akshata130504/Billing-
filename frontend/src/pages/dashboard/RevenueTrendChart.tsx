import { useState } from 'react';
import { Calendar, ChevronDown } from 'lucide-react';

interface DataPoint {
  month: string;
  value: number; // in thousands (e.g. 2 for 2k)
}

const data: DataPoint[] = [
  { month: 'Jan', value: 2.0 },
  { month: 'Feb', value: 3.0 },
  { month: 'Mar', value: 2.8 },
  { month: 'Apr', value: 3.5 },
  { month: 'May', value: 4.8 },
  { month: 'Jun', value: 5.0 },
  { month: 'Jul', value: 4.4 },
  { month: 'Aug', value: 5.2 },
  { month: 'Sep', value: 5.8 },
  { month: 'Oct', value: 5.4 },
  { month: 'Nov', value: 6.8 },
  { month: 'Dec', value: 8.0 },
];

export function RevenueTrendChart() {
  const [activePoint, setActivePoint] = useState<number | null>(null);

  // SVG Chart Dimensions
  const svgWidth = 500;
  const svgHeight = 180;
  const paddingLeft = 35;
  const paddingRight = 15;
  const paddingTop = 15;
  const paddingBottom = 25;

  const chartWidth = svgWidth - paddingLeft - paddingRight;
  const chartHeight = svgHeight - paddingTop - paddingBottom;
  const maxValue = 8; // ₹8k

  const points = data.map((d, index) => {
    const x = paddingLeft + (index / (data.length - 1)) * chartWidth;
    const y = paddingTop + chartHeight - (d.value / maxValue) * chartHeight;
    return { x, y, ...d };
  });

  // Generate cubic spline SVG path
  const createSmoothPath = (pts: { x: number; y: number }[]) => {
    return pts.reduce((acc, pt, i, arr) => {
      if (i === 0) return `M ${pt.x},${pt.y}`;
      const prev = arr[i - 1];
      const cx1 = prev.x + (pt.x - prev.x) / 2;
      const cy1 = prev.y;
      const cx2 = prev.x + (pt.x - prev.x) / 2;
      const cy2 = pt.y;
      return `${acc} C ${cx1},${cy1} ${cx2},${cy2} ${pt.x},${pt.y}`;
    }, '');
  };

  const linePath = createSmoothPath(points);
  const areaPath = `${linePath} L ${points[points.length - 1].x},${paddingTop + chartHeight} L ${points[0].x},${paddingTop + chartHeight} Z`;

  const yTicks = [
    { label: '₹8k', value: 8 },
    { label: '₹6k', value: 6 },
    { label: '₹4k', value: 4 },
    { label: '₹2k', value: 2 },
    { label: '₹0', value: 0 },
  ];

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm flex flex-col justify-between">
      {/* Card Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-900 tracking-tight">
          Revenue Trend
        </h3>
        <button
          type="button"
          className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-slate-600 bg-slate-50 border border-slate-200 rounded-lg hover:bg-slate-100 transition-colors"
        >
          <Calendar className="w-3.5 h-3.5 text-slate-400" />
          <span>Last 12 months</span>
          <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
        </button>
      </div>

      {/* SVG Chart */}
      <div className="w-full relative">
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="w-full h-44 overflow-visible"
        >
          <defs>
            <linearGradient id="revenueGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2563EB" stopOpacity="0.28" />
              <stop offset="85%" stopColor="#3B82F6" stopOpacity="0.04" />
              <stop offset="100%" stopColor="#ffffff" stopOpacity="0.0" />
            </linearGradient>
          </defs>

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

          {/* Area under curve */}
          <path d={areaPath} fill="url(#revenueGradient)" />

          {/* Spline curve line */}
          <path
            d={linePath}
            fill="none"
            stroke="#2563EB"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Dots on points */}
          {points.map((pt, i) => (
            <g key={pt.month}>
              <circle
                cx={pt.x}
                cy={pt.y}
                r={activePoint === i ? 4.5 : 3}
                className="fill-white stroke-brand-600 stroke-2 cursor-pointer transition-all duration-150"
                onMouseEnter={() => setActivePoint(i)}
                onMouseLeave={() => setActivePoint(null)}
              />
              {/* X-axis Month Label */}
              <text
                x={pt.x}
                y={svgHeight - 4}
                textAnchor="middle"
                className="text-[10px] fill-slate-400 font-medium select-none"
              >
                {pt.month}
              </text>
            </g>
          ))}
        </svg>

        {/* Hover Tooltip */}
        {activePoint !== null && (
          <div
            className="absolute -top-3 pointer-events-none transform -translate-x-1/2 bg-slate-900 text-white text-[11px] font-semibold px-2 py-1 rounded shadow-md"
            style={{
              left: `${(points[activePoint].x / svgWidth) * 100}%`,
            }}
          >
            ₹{data[activePoint].value * 1000}
          </div>
        )}
      </div>
    </div>
  );
}
