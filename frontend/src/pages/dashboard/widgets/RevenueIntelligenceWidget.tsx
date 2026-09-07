import { useState } from 'react';
import { TrendingUp, ArrowUpRight, Sparkles } from 'lucide-react';
import { mockRevenueIntelligence } from '../mockDashboardData';

export function RevenueIntelligenceWidget() {
  const [activeIdx, setActiveIdx] = useState<number | null>(null);
  const data = mockRevenueIntelligence;

  const svgWidth = 560;
  const svgHeight = 170;
  const paddingLeft = 35;
  const paddingRight = 20;
  const paddingTop = 20;
  const paddingBottom = 25;

  const chartWidth = svgWidth - paddingLeft - paddingRight;
  const chartHeight = svgHeight - paddingTop - paddingBottom;
  const maxVal = 140;

  const points = data.trend.map((d, index) => {
    const x = paddingLeft + (index / (data.trend.length - 1)) * chartWidth;
    const yActual = paddingTop + chartHeight - (d.actual / maxVal) * chartHeight;
    const yForecast = paddingTop + chartHeight - (d.forecast / maxVal) * chartHeight;
    return { x, yActual, yForecast, ...d };
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

  const actualPath = createSpline(points.map((p) => ({ x: p.x, y: p.yActual })));
  const forecastPath = createSpline(points.map((p) => ({ x: p.x, y: p.yForecast })));
  const areaPath = `${actualPath} L ${points[points.length - 1].x},${paddingTop + chartHeight} L ${points[0].x},${paddingTop + chartHeight} Z`;

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm space-y-4">
      {/* Header & Badges */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-slate-900 tracking-tight">
              Revenue Intelligence
            </h3>
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-blue-50 text-brand-600 border border-blue-100">
              <Sparkles className="w-2.5 h-2.5" />
              AI Predictive
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Realized cash flow, recurring trajectory & quarterly forecast
          </p>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-brand-600" />
            <span className="text-slate-600 text-[11px] font-medium">Actual</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-1 border-t-2 border-dashed border-sky-400" />
            <span className="text-slate-600 text-[11px] font-medium">Forecast</span>
          </div>
        </div>
      </div>

      {/* KPI Highlight Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-50/70 p-3 rounded-xl border border-slate-200/60">
        <div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
            MRR
          </span>
          <span className="text-sm font-bold text-slate-900 tabular-nums block mt-0.5">
            {data.mrr}
          </span>
          <span className="text-[10px] font-semibold text-emerald-600 inline-flex items-center gap-0.5 mt-0.5">
            <TrendingUp className="w-2.5 h-2.5" />
            {data.mrrChange}
          </span>
        </div>

        <div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
            ARR
          </span>
          <span className="text-sm font-bold text-slate-900 tabular-nums block mt-0.5">
            {data.arr}
          </span>
          <span className="text-[10px] text-slate-500 font-medium block mt-0.5">
            {data.arrChange}
          </span>
        </div>

        <div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
            Net Growth
          </span>
          <span className="text-sm font-bold text-slate-900 tabular-nums block mt-0.5">
            {data.growthRate}
          </span>
          <span className="text-[10px] font-semibold text-emerald-600 inline-flex items-center gap-0.5 mt-0.5">
            <ArrowUpRight className="w-2.5 h-2.5" />
            YoY velocity
          </span>
        </div>

        <div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
            Forecast Q4
          </span>
          <span className="text-sm font-bold text-brand-600 tabular-nums block mt-0.5">
            {data.forecastedRevenue}
          </span>
          <span className="text-[10px] text-slate-400 font-medium block mt-0.5">
            94% model confidence
          </span>
        </div>
      </div>

      {/* Interactive Spline Trend Chart */}
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
          {[120, 80, 40, 0].map((val) => {
            const y = paddingTop + chartHeight - (val / maxVal) * chartHeight;
            return (
              <g key={val}>
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
                  ₹{val}k
                </text>
              </g>
            );
          })}

          {/* Area under actual */}
          <path d={areaPath} fill="url(#actualGradient)" />

          {/* Forecast line (dashed) */}
          <path
            d={forecastPath}
            fill="none"
            stroke="#38BDF8"
            strokeWidth="2"
            strokeDasharray="5 4"
            strokeLinecap="round"
          />

          {/* Actual line */}
          <path
            d={actualPath}
            fill="none"
            stroke="#2563EB"
            strokeWidth="2.5"
            strokeLinecap="round"
          />

          {/* Points */}
          {points.map((pt, i) => (
            <g key={pt.label}>
              <circle
                cx={pt.x}
                cy={pt.yActual}
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
            Actual: ₹{points[activeIdx].actual}k · Forecast: ₹{points[activeIdx].forecast}k
          </div>
        )}
      </div>
    </div>
  );
}
