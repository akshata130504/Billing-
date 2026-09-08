import { useId, useState } from 'react';
import { formatMoney } from '../../../utils/format';

export interface SimpleLineChartPoint {
  period: string;
  value: number;
}

export interface SimpleLineChartProps {
  data: SimpleLineChartPoint[];
  color?: string;
  height?: number;
  /** Formats a value for the tooltip and axis. Defaults to `formatMoney`. */
  formatValue?: (value: number) => string;
  /** Formats a period label for the axis/tooltip. Defaults to the raw period string. */
  formatPeriod?: (period: string) => string;
}

/**
 * A small hand-rolled SVG line/area chart for a single time series. Not a
 * general-purpose charting engine — just enough for revenue/collection trends.
 */
export function SimpleLineChart({
  data,
  color = '#2563EB',
  height = 160,
  formatValue = (v) => formatMoney(v),
  formatPeriod = (p) => p,
}: SimpleLineChartProps) {
  const gradientId = useId();
  const [activeIdx, setActiveIdx] = useState<number | null>(null);

  if (data.length === 0) return null;

  const width = 600;
  const padLeft = 8;
  const padRight = 8;
  const padTop = 16;
  const padBottom = 22;
  const chartWidth = width - padLeft - padRight;
  const chartHeight = height - padTop - padBottom;

  const values = data.map((d) => d.value);
  const maxVal = Math.max(...values, 0);
  const minVal = Math.min(...values, 0);
  const span = maxVal - minVal || 1;

  const points = data.map((d, i) => {
    const x = data.length === 1 ? padLeft + chartWidth / 2 : padLeft + (i / (data.length - 1)) * chartWidth;
    const y = padTop + chartHeight - ((d.value - minVal) / span) * chartHeight;
    return { x, y, ...d };
  });

  const linePath = points.reduce((acc, pt, i, arr) => {
    if (i === 0) return `M ${pt.x},${pt.y}`;
    const prev = arr[i - 1];
    const cx1 = prev.x + (pt.x - prev.x) / 2;
    const cx2 = prev.x + (pt.x - prev.x) / 2;
    return `${acc} C ${cx1},${prev.y} ${cx2},${pt.y} ${pt.x},${pt.y}`;
  }, '');

  const baseline = padTop + chartHeight;
  const areaPath = `${linePath} L ${points[points.length - 1].x},${baseline} L ${points[0].x},${baseline} Z`;

  const active = activeIdx !== null ? points[activeIdx] : null;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full overflow-visible" style={{ height }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.22" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>

        <line x1={padLeft} y1={baseline} x2={width - padRight} y2={baseline} stroke="#F1F5F9" strokeWidth="1" />

        <path d={areaPath} fill={`url(#${gradientId})`} />
        <path d={linePath} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" />

        {points.map((pt, i) => (
          <g key={`${pt.period}-${i}`}>
            <rect
              x={pt.x - (chartWidth / Math.max(points.length, 1)) / 2}
              y={padTop}
              width={chartWidth / Math.max(points.length, 1)}
              height={chartHeight}
              fill="transparent"
              onMouseEnter={() => setActiveIdx(i)}
              onMouseLeave={() => setActiveIdx(null)}
            />
            <circle
              cx={pt.x}
              cy={pt.y}
              r={activeIdx === i ? 4.5 : 2.5}
              className="fill-white transition-all duration-150 pointer-events-none"
              stroke={color}
              strokeWidth="2"
            />
          </g>
        ))}

        <text x={points[0].x} y={height - 4} textAnchor="start" className="text-[10px] fill-slate-400 font-medium">
          {formatPeriod(points[0].period)}
        </text>
        {points.length > 1 && (
          <text
            x={points[points.length - 1].x}
            y={height - 4}
            textAnchor="end"
            className="text-[10px] fill-slate-400 font-medium"
          >
            {formatPeriod(points[points.length - 1].period)}
          </text>
        )}
      </svg>

      {active && (
        <div
          className="absolute -top-2 pointer-events-none -translate-x-1/2 -translate-y-full bg-slate-900 text-white text-[10px] font-semibold px-2 py-1 rounded shadow-md whitespace-nowrap"
          style={{ left: `${(active.x / width) * 100}%` }}
        >
          {formatPeriod(active.period)} &middot; {formatValue(active.value)}
        </div>
      )}
    </div>
  );
}
