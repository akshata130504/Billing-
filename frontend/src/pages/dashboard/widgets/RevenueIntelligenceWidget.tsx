import { useState } from 'react';
import { TrendingUp, ArrowUpRight } from 'lucide-react';
import type { DashboardRevenue } from '../../../types';
import { formatMoney, formatPercent, parseMoney } from '../../../utils/format';

export interface RevenueIntelligenceWidgetProps {
  revenue: DashboardRevenue;
  currency: string;
}

export function RevenueIntelligenceWidget({ revenue, currency }: RevenueIntelligenceWidgetProps) {
  const [activeIdx, setActiveIdx] = useState<number | null>(null);

  const svgWidth = 560;
  const svgHeight = 170;
  const paddingLeft = 35;
  const paddingRight = 20;
  const paddingTop = 20;
  const paddingBottom = 25;

  const chartWidth = svgWidth - paddingLeft - paddingRight;
  const chartHeight = svgHeight - paddingTop - paddingBottom;

  const trend = revenue.trend.map((t) => ({
    label: t.label,
    revenue: parseMoney(t.revenue) || 0,
    invoiced: parseMoney(t.invoiced) || 0,
  }));
  const maxVal = Math.max(1, ...trend.map((t) => Math.max(t.revenue, t.invoiced)));

  const points = trend.map((d, index) => {
    const x = paddingLeft + (trend.length > 1 ? (index / (trend.length - 1)) * chartWidth : chartWidth / 2);
    const yRevenue = paddingTop + chartHeight - (d.revenue / maxVal) * chartHeight;
    const yInvoiced = paddingTop + chartHeight - (d.invoiced / maxVal) * chartHeight;
    return { x, yRevenue, yInvoiced, ...d };
  });

  const createSpline = (pts: { x: number; y: number }[]) => {
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

  const revenuePath = points.length ? createSpline(points.map((p) => ({ x: p.x, y: p.yRevenue }))) : '';
  const invoicedPath = points.length ? createSpline(points.map((p) => ({ x: p.x, y: p.yInvoiced }))) : '';
  const areaPath =
    points.length > 0
      ? `${revenuePath} L ${points[points.length - 1].x},${paddingTop + chartHeight} L ${points[0].x},${paddingTop + chartHeight} Z`
      : '';

  const mrrChangePct = revenue.mrr_change_pct ? parseMoney(revenue.mrr_change_pct) : null;

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm space-y-4">
      {/* Header & Badges */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">
            Revenue Intelligence
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Realized cash flow vs. amount invoiced, last 12 months
          </p>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-brand-600" />
            <span className="text-slate-600 text-[11px] font-medium">Revenue</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-1 border-t-2 border-dashed border-sky-400" />
            <span className="text-slate-600 text-[11px] font-medium">Invoiced</span>
          </div>
        </div>
      </div>

      {/* KPI Highlight Strip */}
      <div className="grid grid-cols-3 gap-3 bg-slate-50/70 p-3 rounded-xl border border-slate-200/60">
        <div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
            MRR
          </span>
          <span className="text-sm font-bold text-slate-900 tabular-nums block mt-0.5">
            {formatMoney(revenue.mrr, revenue.mrr_currency || currency)}
          </span>
          {mrrChangePct !== null && (
            <span
              className={`text-[10px] font-semibold inline-flex items-center gap-0.5 mt-0.5 ${
                mrrChangePct >= 0 ? 'text-emerald-600' : 'text-rose-600'
              }`}
            >
              <TrendingUp className="w-2.5 h-2.5" />
              {formatPercent(revenue.mrr_change_pct)} MoM
            </span>
          )}
        </div>

        <div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
            ARR
          </span>
          <span className="text-sm font-bold text-slate-900 tabular-nums block mt-0.5">
            {formatMoney(revenue.arr, revenue.mrr_currency || currency)}
          </span>
          <span className="text-[10px] text-slate-500 font-medium block mt-0.5">
            12 &times; current MRR
          </span>
        </div>

        <div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
            Net Growth
          </span>
          <span className="text-sm font-bold text-slate-900 tabular-nums block mt-0.5">
            {mrrChangePct !== null ? formatPercent(revenue.mrr_change_pct) : '—'}
          </span>
          <span className="text-[10px] font-semibold text-slate-400 inline-flex items-center gap-0.5 mt-0.5">
            <ArrowUpRight className="w-2.5 h-2.5" />
            MRR change vs. last period
          </span>
        </div>
      </div>

      {/* Trend Chart */}
      {points.length > 1 ? (
        <div className="relative pt-1">
          <svg
            viewBox={`0 0 ${svgWidth} ${svgHeight}`}
            className="w-full h-40 overflow-visible"
          >
            <defs>
              <linearGradient id="actualGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#2563EB" stopOpacity="0.22" />
                <stop offset="90%" stopColor="#2563EB" stopOpacity="0.01" />
                <stop offset="100%" stopColor="#ffffff" stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {/* Grid lines */}
            {[1, 0.75, 0.5, 0.25, 0].map((frac) => {
              const val = maxVal * frac;
              const y = paddingTop + chartHeight - frac * chartHeight;
              return (
                <g key={frac}>
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
                    {formatMoney(val, currency, { compact: true })}
                  </text>
                </g>
              );
            })}

            <path d={areaPath} fill="url(#actualGradient)" />

            <path
              d={invoicedPath}
              fill="none"
              stroke="#38BDF8"
              strokeWidth="2"
              strokeDasharray="5 4"
              strokeLinecap="round"
            />

            <path
              d={revenuePath}
              fill="none"
              stroke="#2563EB"
              strokeWidth="2.5"
              strokeLinecap="round"
            />

            {points.map((pt, i) => (
              <g key={pt.label}>
                <circle
                  cx={pt.x}
                  cy={pt.yRevenue}
                  r={activeIdx === i ? 4.5 : 2.5}
                  className="fill-white stroke-brand-600 stroke-2 cursor-pointer transition-all duration-150"
                  onMouseEnter={() => setActiveIdx(i)}
                  onMouseLeave={() => setActiveIdx(null)}
                />
                <text
                  x={pt.x}
                  y={svgHeight - 4}
                  textAnchor="middle"
                  className="text-[9.5px] fill-slate-400 font-medium select-none"
                >
                  {pt.label}
                </text>
              </g>
            ))}
          </svg>

          {activeIdx !== null && (
            <div
              className="absolute -top-4 pointer-events-none transform -translate-x-1/2 bg-slate-900 text-white text-[10px] font-semibold px-2 py-1 rounded shadow-md"
              style={{
                left: `${(points[activeIdx].x / svgWidth) * 100}%`,
              }}
            >
              Revenue: {formatMoney(points[activeIdx].revenue, currency, { compact: true })} · Invoiced:{' '}
              {formatMoney(points[activeIdx].invoiced, currency, { compact: true })}
            </div>
          )}
        </div>
      ) : (
        <p className="text-xs text-slate-400 py-8 text-center">
          Not enough billing history yet to draw a trend.
        </p>
      )}
    </div>
  );
}
