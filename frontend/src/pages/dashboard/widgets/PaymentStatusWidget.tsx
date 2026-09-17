import type { DashboardPipeline, DashboardMetrics, DashboardCustomerHealth } from '../../../types';

export interface PaymentStatusWidgetProps {
  pipeline?: DashboardPipeline;
  metrics?: DashboardMetrics;
  customerHealth?: DashboardCustomerHealth;
}

export function PaymentStatusWidget({ pipeline }: PaymentStatusWidgetProps = {}) {
  const paidCount = pipeline?.paid_this_period?.count ?? 0;
  const pendingCount = (pipeline?.sent?.count ?? 0) + (pipeline?.partially_paid?.count ?? 0);
  const overdueCount = pipeline?.overdue?.count ?? 0;
  const cancelledCount = pipeline?.draft?.count ?? 0;

  const safeTotal = paidCount + pendingCount + overdueCount + cancelledCount;

  const paidPct = safeTotal > 0 ? Math.round((paidCount / safeTotal) * 100) : 0;
  const pendingPct = safeTotal > 0 ? Math.round((pendingCount / safeTotal) * 100) : 0;
  const overduePct = safeTotal > 0 ? Math.round((overdueCount / safeTotal) * 100) : 0;
  const cancelledPct = safeTotal > 0 ? Math.max(0, 100 - paidPct - pendingPct - overduePct) : 0;

  // Donut chart geometry
  const radius = 52;
  const strokeWidth = 14;
  const circumference = 2 * Math.PI * radius; // ~326.726

  const paidStroke = (paidPct / 100) * circumference;
  const pendingStroke = (pendingPct / 100) * circumference;
  const overdueStroke = (overduePct / 100) * circumference;
  const cancelledStroke = (cancelledPct / 100) * circumference;

  const paidOffset = 0;
  const pendingOffset = -paidStroke;
  const overdueOffset = -(paidStroke + pendingStroke);
  const cancelledOffset = -(paidStroke + pendingStroke + overdueStroke);

  const statuses = [
    { label: 'Paid', count: paidCount, pct: `${paidPct}%`, dotColor: 'bg-[#10B981]' },
    { label: 'Pending', count: pendingCount, pct: `${pendingPct}%`, dotColor: 'bg-[#E83E8C]' },
    { label: 'Overdue', count: overdueCount, pct: `${overduePct}%`, dotColor: 'bg-[#F9D9E8] border border-[#F3B8D4]' },
    { label: 'Cancelled', count: cancelledCount, pct: `${cancelledPct}%`, dotColor: 'bg-[#94A3B8]' },
  ];

  return (
    <div className="bg-white p-5 rounded-2xl border border-[#E7E9F2] shadow-sm space-y-4">
      {/* Header */}
      <h3 className="text-sm font-bold text-[#11194F] tracking-tight">
        Payment Status
      </h3>

      <div className="flex items-center justify-between gap-4">
        {/* SVG Donut Chart */}
        <div className="relative w-36 h-36 shrink-0 flex items-center justify-center">
          <svg
            viewBox="0 0 130 130"
            className="w-full h-full -rotate-90 transform"
          >
            {/* Background Track */}
            <circle
              cx="65"
              cy="65"
              r={radius}
              fill="transparent"
              stroke="#F1F5F9"
              strokeWidth={strokeWidth}
            />

            {/* Paid Segment (Green) */}
            <circle
              cx="65"
              cy="65"
              r={radius}
              fill="transparent"
              stroke="#10B981"
              strokeWidth={strokeWidth}
              strokeDasharray={`${paidStroke} ${circumference - paidStroke}`}
              strokeDashoffset={paidOffset}
              strokeLinecap="round"
            />

            {/* Pending Segment (Vibrant Pink/Magenta) */}
            <circle
              cx="65"
              cy="65"
              r={radius}
              fill="transparent"
              stroke="#E83E8C"
              strokeWidth={strokeWidth}
              strokeDasharray={`${pendingStroke} ${circumference - pendingStroke}`}
              strokeDashoffset={pendingOffset}
            />

            {/* Overdue Segment (Soft Pink) */}
            <circle
              cx="65"
              cy="65"
              r={radius}
              fill="transparent"
              stroke="#F9D9E8"
              strokeWidth={strokeWidth}
              strokeDasharray={`${overdueStroke} ${circumference - overdueStroke}`}
              strokeDashoffset={overdueOffset}
            />

            {/* Cancelled Segment (Grey) */}
            <circle
              cx="65"
              cy="65"
              r={radius}
              fill="transparent"
              stroke="#94A3B8"
              strokeWidth={strokeWidth}
              strokeDasharray={`${cancelledStroke} ${circumference - cancelledStroke}`}
              strokeDashoffset={cancelledOffset}
            />
          </svg>

          {/* Center Label */}
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center pointer-events-none">
            <span className="text-xl font-bold text-[#11194F] leading-none tabular-nums">
              {safeTotal}
            </span>
            <span className="text-[10.5px] font-medium text-[#7B829A] mt-1">
              Invoices
            </span>
          </div>
        </div>

        {/* Breakdown Legend */}
        <div className="flex-1 space-y-2.5 min-w-[120px]">
          {statuses.map((s) => (
            <div
              key={s.label}
              className="flex items-center justify-between text-xs"
            >
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full shrink-0 ${s.dotColor}`} />
                <span className="text-[#59617D] font-medium text-xs">{s.label}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="font-bold text-[#11194F] tabular-nums text-xs">
                  {s.count}
                </span>
                <span className="text-[11px] text-[#7B829A] tabular-nums w-8 text-right font-medium">
                  {s.pct}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
