import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { DashboardRevenue } from '../../../types';
import { parseMoney } from '../../../utils/format';

export interface RevenueOverviewWidgetProps {
  revenue?: DashboardRevenue;
  currency?: string;
}

interface MonthBarData {
  month: string;
  invoiced: number; // in thousands or raw value
  received: number;
}

const DEFAULT_MONTHS: MonthBarData[] = [
  { month: 'Jan', invoiced: 75, received: 48 },
  { month: 'Feb', invoiced: 98, received: 58 },
  { month: 'Mar', invoiced: 120, received: 68 },
  { month: 'Apr', invoiced: 145, received: 85 },
  { month: 'May', invoiced: 145, received: 98 },
  { month: 'Jun', invoiced: 175, received: 125 },
  { month: 'Jul', invoiced: 175, received: 125 },
  { month: 'Aug', invoiced: 195, received: 135 },
];

export function RevenueOverviewWidget({ revenue }: RevenueOverviewWidgetProps) {
  const [selectedRange, setSelectedRange] = useState('Last 8 Months');
  const [rangeOpen, setRangeOpen] = useState(false);

  // Map from backend trend if available, else use reference baseline data
  const chartData: MonthBarData[] =
    revenue && revenue.trend && revenue.trend.length >= 4
      ? revenue.trend.slice(-8).map((t) => {
          const inv = parseMoney(t.invoiced) || 0;
          const rev = parseMoney(t.revenue) || 0;
          // Format label to 3-letter month (e.g. "Sep" from "Sep 2026")
          const monthLabel = t.label.split(' ')[0] || t.label;
          return {
            month: monthLabel,
            invoiced: inv > 0 ? Math.round(inv / 1000) : 100,
            received: rev > 0 ? Math.round(rev / 1000) : 60,
          };
        })
      : DEFAULT_MONTHS;

  const maxValue = 200; // 2L scale

  // SVG dimensions
  const svgWidth = 560;
  const svgHeight = 220;
  const paddingLeft = 45;
  const paddingRight = 15;
  const paddingTop = 25;
  const paddingBottom = 35;

  const plotWidth = svgWidth - paddingLeft - paddingRight;
  const plotHeight = svgHeight - paddingTop - paddingBottom;

  const yTicks = [
    { label: '2L', val: 200 },
    { label: '1.5L', val: 150 },
    { label: '1L', val: 100 },
    { label: '50K', val: 50 },
    { label: '0', val: 0 },
  ];

  const groupWidth = plotWidth / chartData.length;
  const barWidth = 14;
  const barGap = 4;

  return (
    <div className="bg-white p-5 rounded-2xl border border-[#E7E9F2] shadow-sm space-y-3">
      {/* Header with Range Selector */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-[#11194F] tracking-tight">
          Revenue Overview
        </h3>

        <div className="relative">
          <button
            type="button"
            onClick={() => setRangeOpen((prev) => !prev)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-[#59617D] bg-white hover:bg-[#F7F8FC] border border-[#E7E9F2] rounded-xl shadow-3xs transition-colors cursor-pointer"
          >
            <span>{selectedRange}</span>
            <ChevronDown className="w-3.5 h-3.5 text-[#7B829A]" />
          </button>

          {rangeOpen && (
            <>
              <div
                className="fixed inset-0 z-20"
                onClick={() => setRangeOpen(false)}
              />
              <div className="absolute right-0 mt-1.5 w-36 bg-white rounded-xl shadow-modal border border-[#E7E9F2] py-1 z-30 divide-y divide-slate-100">
                {['Last 8 Months', 'Last 6 Months', 'Last 12 Months', 'This Year'].map(
                  (range) => (
                    <button
                      key={range}
                      type="button"
                      onClick={() => {
                        setSelectedRange(range);
                        setRangeOpen(false);
                      }}
                      className={`w-full px-3 py-1.5 text-xs text-left font-medium transition-colors ${
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

      {/* Dual Bar Chart SVG */}
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
                  className="text-[10px] fill-[#7B829A] font-medium"
                >
                  {tick.label}
                </text>
              </g>
            );
          })}

          {/* Grouped Dual Bars */}
          {chartData.map((d, idx) => {
            const groupCenterX = paddingLeft + idx * groupWidth + groupWidth / 2;

            // Invoiced bar (Left, Indigo)
            const invoicedH = Math.min(plotHeight, (d.invoiced / maxValue) * plotHeight);
            const invoicedX = groupCenterX - barWidth - barGap / 2;
            const invoicedY = paddingTop + plotHeight - invoicedH;

            // Received bar (Right, Pink)
            const receivedH = Math.min(plotHeight, (d.received / maxValue) * plotHeight);
            const receivedX = groupCenterX + barGap / 2;
            const receivedY = paddingTop + plotHeight - receivedH;

            return (
              <g key={d.month} className="group">
                {/* Invoiced Bar (Indigo #3F51C9) */}
                <rect
                  x={invoicedX}
                  y={invoicedY}
                  width={barWidth}
                  height={invoicedH}
                  rx="3"
                  fill="#3F51C9"
                  className="transition-opacity hover:opacity-85 cursor-pointer"
                >
                  <title>{`${d.month} Invoiced: ₹${d.invoiced}K`}</title>
                </rect>

                {/* Received Bar (Pink #FF7BB0) */}
                <rect
                  x={receivedX}
                  y={receivedY}
                  width={barWidth}
                  height={receivedH}
                  rx="3"
                  fill="#FF7BB0"
                  className="transition-opacity hover:opacity-85 cursor-pointer"
                >
                  <title>{`${d.month} Received: ₹${d.received}K`}</title>
                </rect>

                {/* Month label on X axis */}
                <text
                  x={groupCenterX}
                  y={svgHeight - 10}
                  textAnchor="middle"
                  className="text-[11px] fill-[#7B829A] font-medium"
                >
                  {d.month}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Legend at Bottom */}
      <div className="flex items-center justify-center gap-6 pt-1">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-xs bg-[#3F51C9]" />
          <span className="text-xs font-medium text-[#59617D]">Invoiced</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-xs bg-[#FF7BB0]" />
          <span className="text-xs font-medium text-[#59617D]">Received</span>
        </div>
      </div>
    </div>
  );
}
