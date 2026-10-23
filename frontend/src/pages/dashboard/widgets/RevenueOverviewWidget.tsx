import { useState, useMemo } from 'react';
import { ChevronDown } from 'lucide-react';
import type { DashboardRevenue } from '../../../types';
import { parseMoney, formatMoney } from '../../../utils/format';

export interface RevenueOverviewWidgetProps {
  /** Card title (configurable in the Super Admin visual editor). */
  title?: string;
  revenue?: DashboardRevenue;
  currency?: string;
}

interface MonthBarData {
  month: string;
  fullLabel: string;
  invoiced: number; // raw value in currency
  received: number; // raw value in currency
}

export function RevenueOverviewWidget({ revenue, currency = 'INR', title = 'Revenue Overview' }: RevenueOverviewWidgetProps) {
  const [selectedRange, setSelectedRange] = useState('Last 8 Months');
  const [rangeOpen, setRangeOpen] = useState(false);
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  // Dynamic month count from selected range
  const monthsCount = useMemo(() => {
    switch (selectedRange) {
      case 'Last 6 Months':
        return 6;
      case 'Last 12 Months':
        return 12;
      case 'This Year': {
        const currentMonthIdx = new Date().getMonth() + 1; // 1-12
        return Math.max(1, Math.min(12, currentMonthIdx));
      }
      case 'Last 8 Months':
      default:
        return 8;
    }
  }, [selectedRange]);

  // Dynamically derive chart data based on selected range and real revenue trend
  const chartData: MonthBarData[] = useMemo(() => {
    const trend = revenue?.trend || [];
    if (trend.length === 0) {
      return [];
    }

    const sliced = trend.slice(-monthsCount);

    return sliced.map((t) => {
      const inv = parseMoney(t.invoiced) || 0;
      const rev = parseMoney(t.revenue) || 0;
      const monthLabel = t.label.split(' ')[0] || t.label;

      return {
        month: monthLabel,
        fullLabel: t.label,
        invoiced: inv,
        received: rev,
      };
    });
  }, [revenue?.trend, monthsCount]);

  // Dynamic max value auto-scaling to prevent overflow and ensure comfortable headroom
  const { maxValue, yTicks } = useMemo(() => {
    const rawPeak = Math.max(
      ...chartData.map((d) => Math.max(d.invoiced, d.received)),
      10000
    );

    // Dynamic scale in Lakhs (1L = 100,000)
    const peakLakhs = rawPeak / 100000;
    let ceilingLakhs = 2;
    if (peakLakhs > 10) {
      ceilingLakhs = Math.ceil(peakLakhs / 2) * 2; // e.g. 14 or 16L
    } else if (peakLakhs > 5) {
      ceilingLakhs = Math.ceil(peakLakhs); // e.g. 6L, 7L, 8L
    } else if (peakLakhs > 2) {
      ceilingLakhs = Math.ceil(peakLakhs); // 3L, 4L, 5L
    } else {
      ceilingLakhs = 2;
    }

    const calculatedMax = ceilingLakhs * 100000;

    const ticks = [
      { label: `${ceilingLakhs}L`, val: calculatedMax },
      { label: `${(ceilingLakhs * 0.75).toFixed(ceilingLakhs % 4 === 0 ? 0 : 1)}L`, val: calculatedMax * 0.75 },
      { label: `${(ceilingLakhs * 0.5).toFixed(ceilingLakhs % 2 === 0 ? 0 : 1)}L`, val: calculatedMax * 0.5 },
      { label: `${(ceilingLakhs * 0.25).toFixed(ceilingLakhs % 4 === 0 ? 0 : 1)}L`, val: calculatedMax * 0.25 },
      { label: '0', val: 0 },
    ];

    return { maxValue: calculatedMax, yTicks: ticks };
  }, [chartData]);

  // Dynamic totals for the active range
  const { totalInvoiced, totalReceived, collectionRate } = useMemo(() => {
    const inv = chartData.reduce((acc, d) => acc + d.invoiced, 0);
    const rec = chartData.reduce((acc, d) => acc + d.received, 0);
    const rate = inv > 0 ? Math.round((rec / inv) * 100) : 0;
    return { totalInvoiced: inv, totalReceived: rec, collectionRate: rate };
  }, [chartData]);

  // Invoiced/received in other currencies over the same months (never converted or summed in).
  const otherCurrencies = useMemo(() => {
    const totals: Record<string, { invoiced: number; revenue: number }> = {};
    for (const t of (revenue?.trend || []).slice(-monthsCount)) {
      for (const row of t.by_currency || []) {
        if (row.currency === currency) continue;
        const entry = (totals[row.currency] ||= { invoiced: 0, revenue: 0 });
        entry.invoiced += parseMoney(row.invoiced) || 0;
        entry.revenue += parseMoney(row.revenue) || 0;
      }
    }
    return Object.entries(totals).sort(([a], [b]) => a.localeCompare(b));
  }, [revenue?.trend, monthsCount, currency]);

  // SVG dimensions
  const svgWidth = 560;
  const svgHeight = 220;
  const paddingLeft = 45;
  const paddingRight = 15;
  const paddingTop = 25;
  const paddingBottom = 35;

  const plotWidth = svgWidth - paddingLeft - paddingRight;
  const plotHeight = svgHeight - paddingTop - paddingBottom;

  const groupWidth = plotWidth / Math.max(1, chartData.length);
  const barWidth = Math.max(8, Math.min(15, (groupWidth - 8) / 2));
  const barGap = 3;

  return (
    <div className="bg-white p-5 rounded-2xl border border-[#E7E9F2] shadow-sm space-y-3 relative">
      {/* Header with Range Selector & Live Status */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <h3 className="text-sm font-bold text-[#11194F] tracking-tight">
            {title}
          </h3>
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            Live Sync
          </span>
        </div>

        {/* Dynamic Range Dropdown */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setRangeOpen((prev) => !prev)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-[#59617D] bg-white hover:bg-[#F7F8FC] border border-[#E7E9F2] rounded-xl shadow-3xs transition-colors cursor-pointer active:scale-[0.98]"
          >
            <span>{selectedRange}</span>
            <ChevronDown className="w-3.5 h-3.5 text-[#7B829A] shrink-0" />
          </button>

          {rangeOpen && (
            <>
              <div
                className="fixed inset-0 z-20"
                onClick={() => setRangeOpen(false)}
              />
              <div className="absolute right-0 mt-1.5 w-40 bg-white rounded-xl shadow-modal border border-[#E7E9F2] py-1 z-30 divide-y divide-slate-100 animate-in fade-in zoom-in-95 duration-100">
                {['Last 6 Months', 'Last 8 Months', 'Last 12 Months', 'This Year'].map(
                  (range) => (
                    <button
                      key={range}
                      type="button"
                      onClick={() => {
                        setSelectedRange(range);
                        setRangeOpen(false);
                      }}
                      className={`w-full px-3.5 py-2 text-xs text-left font-medium transition-colors ${
                        selectedRange === range
                          ? 'bg-[#E8EBFC] text-[#25247A] font-semibold'
                          : 'text-[#59617D] hover:bg-[#F7F8FC]'
                      }`}
                    >
                      {range}
                    </button>
                  )
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {chartData.length === 0 ? (
        <div className="w-full h-48 flex flex-col items-center justify-center text-slate-400 text-xs">
          <p className="font-medium text-slate-500">No revenue data available for this period.</p>
          <p className="text-[11px] text-slate-400 mt-1">Invoiced and collected amounts will appear here automatically.</p>
        </div>
      ) : (
        /* Dual Bar Chart SVG */
        <div className="w-full relative">
          <svg
            viewBox={`0 0 ${svgWidth} ${svgHeight}`}
            className="w-full h-48 overflow-visible"
          >
            {/* Y-axis gridlines & labels */}
            {yTicks.map((tick) => {
              const y = paddingTop + plotHeight - (tick.val / maxValue) * plotHeight;
              return (
                <g key={tick.label}>
                  <line
                    x1={paddingLeft}
                    y1={y}
                    x2={svgWidth - paddingRight}
                    y2={y}
                    stroke="#F1F5F9"
                    strokeWidth="1"
                    strokeDasharray="3 3"
                  />
                  <text
                    x={paddingLeft - 10}
                    y={y + 3.5}
                    textAnchor="end"
                    className="text-[10px] fill-[#7B829A] font-medium font-mono"
                  >
                    {tick.label}
                  </text>
                </g>
              );
            })}

            {/* Grouped Dual Bars with Dynamic Transitions */}
            {chartData.map((d, idx) => {
              const groupCenterX = paddingLeft + idx * groupWidth + groupWidth / 2;

              // Invoiced bar (Left, Indigo)
              const invoicedH = d.invoiced > 0 ? Math.max(3, Math.min(plotHeight, (d.invoiced / maxValue) * plotHeight)) : 0;
              const invoicedX = groupCenterX - barWidth - barGap / 2;
              const invoicedY = paddingTop + plotHeight - invoicedH;

              // Received bar (Right, Pink)
              const receivedH = d.received > 0 ? Math.max(3, Math.min(plotHeight, (d.received / maxValue) * plotHeight)) : 0;
              const receivedX = groupCenterX + barGap / 2;
              const receivedY = paddingTop + plotHeight - receivedH;

            const isHovered = hoveredIdx === idx;

            return (
              <g
                key={d.month + idx}
                className="cursor-pointer transition-opacity duration-200"
                onMouseEnter={() => setHoveredIdx(idx)}
                onMouseLeave={() => setHoveredIdx(null)}
                style={{ opacity: hoveredIdx === null || isHovered ? 1 : 0.45 }}
              >
                {/* Column Hover Hit Area */}
                <rect
                  x={groupCenterX - groupWidth / 2}
                  y={paddingTop}
                  width={groupWidth}
                  height={plotHeight}
                  fill="transparent"
                />

                {/* Invoiced Bar (Indigo #3F51C9) */}
                <rect
                  x={invoicedX}
                  y={invoicedY}
                  width={barWidth}
                  height={invoicedH}
                  rx="3"
                  fill="#3F51C9"
                  className="transition-all duration-500 ease-out"
                >
                  <title>{`${d.fullLabel} Invoiced: ${formatMoney(d.invoiced, currency)}`}</title>
                </rect>

                {/* Received Bar (Pink #FF7BB0) */}
                <rect
                  x={receivedX}
                  y={receivedY}
                  width={barWidth}
                  height={receivedH}
                  rx="3"
                  fill="#FF7BB0"
                  className="transition-all duration-500 ease-out"
                >
                  <title>{`${d.fullLabel} Received: ${formatMoney(d.received, currency)}`}</title>
                </rect>

                {/* Month label on X axis */}
                <text
                  x={groupCenterX}
                  y={svgHeight - 10}
                  textAnchor="middle"
                  className={`text-[11px] transition-colors ${
                    isHovered ? 'fill-[#11194F] font-bold' : 'fill-[#7B829A] font-medium'
                  }`}
                >
                  {d.month}
                </text>
              </g>
            );
          })}
        </svg>

        {/* Interactive Floating Tooltip on Hover */}
        {hoveredIdx !== null && chartData[hoveredIdx] && (
          <div
            className="absolute top-0 right-2 pointer-events-none bg-slate-900/90 text-white text-xs px-3 py-1.5 rounded-lg shadow-lg backdrop-blur-xs font-mono space-y-0.5 border border-slate-700/60 animate-in fade-in duration-150 z-10"
          >
            <div className="font-bold text-slate-200 border-b border-slate-700 pb-0.5 mb-1 text-[11px]">
              {chartData[hoveredIdx].fullLabel}
            </div>
            <div className="flex justify-between gap-3 text-indigo-300 text-[11px]">
              <span>Invoiced:</span>
              <span className="font-bold">{formatMoney(chartData[hoveredIdx].invoiced, currency)}</span>
            </div>
            <div className="flex justify-between gap-3 text-pink-300 text-[11px]">
              <span>Received:</span>
              <span className="font-bold">{formatMoney(chartData[hoveredIdx].received, currency)}</span>
            </div>
          </div>
        )}
      </div>
      )}

      {/* Dynamic Legend with Period Totals */}
      <div className="flex flex-wrap items-center justify-between gap-4 pt-2 border-t border-slate-100 text-xs">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-xs bg-[#3F51C9]" />
            <span className="text-slate-500">Invoiced:</span>
            <span className="font-semibold text-slate-800 font-mono">
              {formatMoney(totalInvoiced, currency, { compact: true })}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-xs bg-[#FF7BB0]" />
            <span className="text-slate-500">Received:</span>
            <span className="font-semibold text-slate-800 font-mono">
              {formatMoney(totalReceived, currency, { compact: true })}
            </span>
          </div>
        </div>

        <div className="text-[11px] text-slate-500 font-medium">
          Collection Rate ({currency}): <span className="font-bold text-emerald-600 font-mono">{collectionRate}%</span>
        </div>
      </div>
      {otherCurrencies.length > 0 && (
        <p className="text-[11px] text-slate-500" data-testid="revenue-other-currencies">
          Chart in {currency}. Other currencies (not converted):{' '}
          {otherCurrencies
            .map(([cur, t]) => `${cur} invoiced ${formatMoney(t.invoiced, cur)}, received ${formatMoney(t.revenue, cur)}`)
            .join(' · ')}
        </p>
      )}
    </div>
  );
}

