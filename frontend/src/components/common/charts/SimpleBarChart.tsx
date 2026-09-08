import { useState } from 'react';
import { formatMoney } from '../../../utils/format';

export interface SimpleBarChartDatum {
  label: string;
  value: number;
}

export interface SimpleBarChartProps {
  data: SimpleBarChartDatum[];
  color?: string;
  height?: number;
  /** Ranked list with the bar growing rightward (aging buckets, top customers, methods). Default true. */
  horizontal?: boolean;
  /** Formats a value for the bar label/tooltip. Defaults to `formatMoney`. */
  formatValue?: (value: number) => string;
}

/**
 * A small hand-rolled SVG bar chart. `horizontal` (the default) renders a
 * ranked list of bars — good for aging buckets, payment methods, top
 * customers. Set `horizontal={false}` for a vertical column chart.
 */
export function SimpleBarChart({
  data,
  color = '#2563EB',
  height,
  horizontal = true,
  formatValue = (v) => formatMoney(v),
}: SimpleBarChartProps) {
  const [activeIdx, setActiveIdx] = useState<number | null>(null);

  if (data.length === 0) return null;

  const maxVal = Math.max(...data.map((d) => d.value), 0) || 1;

  if (horizontal) {
    const rowHeight = 28;
    const width = 600;
    const labelWidth = 140;
    const chartWidth = width - labelWidth - 70;
    const svgHeight = data.length * rowHeight;

    return (
      <svg viewBox={`0 0 ${width} ${svgHeight}`} className="w-full" style={{ height: height ?? svgHeight }}>
        {data.map((d, i) => {
          const barWidth = Math.max((d.value / maxVal) * chartWidth, d.value > 0 ? 3 : 0);
          const y = i * rowHeight;
          const active = activeIdx === i;
          return (
            <g
              key={`${d.label}-${i}`}
              onMouseEnter={() => setActiveIdx(i)}
              onMouseLeave={() => setActiveIdx(null)}
              className="cursor-default"
            >
              <text
                x={labelWidth - 8}
                y={y + rowHeight / 2 + 4}
                textAnchor="end"
                className="text-[11px] fill-slate-600 font-medium"
              >
                {d.label.length > 22 ? `${d.label.slice(0, 21)}…` : d.label}
              </text>
              <rect x={labelWidth} y={y + 5} width={chartWidth} height={rowHeight - 12} rx={3} fill="#F1F5F9" />
              <rect
                x={labelWidth}
                y={y + 5}
                width={barWidth}
                height={rowHeight - 12}
                rx={3}
                fill={color}
                opacity={active ? 1 : 0.85}
              />
              <text
                x={labelWidth + chartWidth + 8}
                y={y + rowHeight / 2 + 4}
                className="text-[11px] fill-slate-900 font-semibold tabular-nums"
              >
                {formatValue(d.value)}
              </text>
            </g>
          );
        })}
      </svg>
    );
  }

  // Vertical column chart.
  const width = 600;
  const chartHeight = (height ?? 200) - 28;
  const padLeft = 8;
  const padRight = 8;
  const chartWidth = width - padLeft - padRight;
  const barGap = 10;
  const barWidth = Math.max((chartWidth - barGap * (data.length - 1)) / data.length, 4);

  return (
    <svg viewBox={`0 0 ${width} ${height ?? 200}`} className="w-full" style={{ height: height ?? 200 }}>
      <line x1={padLeft} y1={chartHeight} x2={width - padRight} y2={chartHeight} stroke="#F1F5F9" strokeWidth="1" />
      {data.map((d, i) => {
        const barHeight = Math.max((d.value / maxVal) * (chartHeight - 8), d.value > 0 ? 2 : 0);
        const x = padLeft + i * (barWidth + barGap);
        const y = chartHeight - barHeight;
        const active = activeIdx === i;
        return (
          <g
            key={`${d.label}-${i}`}
            onMouseEnter={() => setActiveIdx(i)}
            onMouseLeave={() => setActiveIdx(null)}
            className="cursor-default"
          >
            <rect x={x} y={y} width={barWidth} height={barHeight} rx={3} fill={color} opacity={active ? 1 : 0.85} />
            {active && (
              <text x={x + barWidth / 2} y={y - 6} textAnchor="middle" className="text-[10px] fill-slate-900 font-bold">
                {formatValue(d.value)}
              </text>
            )}
            <text
              x={x + barWidth / 2}
              y={chartHeight + 16}
              textAnchor="middle"
              className="text-[10px] fill-slate-400 font-medium"
            >
              {d.label.length > 10 ? `${d.label.slice(0, 9)}…` : d.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
