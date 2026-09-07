import { FileText, Receipt, CreditCard, CheckCircle2, ChevronRight } from 'lucide-react';
import { mockBillingPipeline, PipelineStage } from '../mockDashboardData';

export function BillingPipelineWidget() {
  const getStageIcon = (stage: PipelineStage['stage']) => {
    switch (stage) {
      case 'quote':
        return <FileText className="w-4 h-4 text-brand-600" />;
      case 'invoice':
        return <Receipt className="w-4 h-4 text-purple-600" />;
      case 'payment':
        return <CreditCard className="w-4 h-4 text-amber-600" />;
      case 'paid':
        return <CheckCircle2 className="w-4 h-4 text-emerald-600" />;
    }
  };

  const getStageColor = (stage: PipelineStage['stage']) => {
    switch (stage) {
      case 'quote':
        return 'border-brand-200 bg-blue-50/40';
      case 'invoice':
        return 'border-purple-200 bg-purple-50/40';
      case 'payment':
        return 'border-amber-200 bg-amber-50/40';
      case 'paid':
        return 'border-emerald-200 bg-emerald-50/40';
    }
  };

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
        <div>
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">
            Billing Pipeline
          </h3>
          <p className="text-xs text-slate-400">
            End-to-end lifecycle throughput from initial quote to settled cash
          </p>
        </div>
        <span className="text-xs font-semibold text-slate-500">
          Total Cycle: <strong className="text-slate-900">₹1,728,900.00</strong>
        </span>
      </div>

      {/* Visual Pipeline Stages */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 relative">
        {mockBillingPipeline.map((stage, idx) => (
          <div
            key={stage.stage}
            className={`p-4 rounded-xl border relative flex flex-col justify-between transition-all hover:shadow-xs ${getStageColor(
              stage.stage
            )}`}
          >
            {/* Top Row: Icon, Title & Count */}
            <div>
              <div className="flex items-center justify-between">
                <div className="p-2 rounded-lg bg-white shadow-subtle border border-slate-100">
                  {getStageIcon(stage.stage)}
                </div>
                <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-white border border-slate-200 text-slate-700">
                  {stage.count} {stage.stage === 'paid' ? 'Settled' : 'Active'}
                </span>
              </div>

              <div className="mt-3">
                <h4 className="text-xs font-bold text-slate-900 tracking-tight">
                  {stage.title}
                </h4>
                <span className="text-base font-bold text-slate-900 tabular-nums block mt-0.5">
                  {stage.monetaryValue}
                </span>
              </div>
            </div>

            <p className="text-[10px] text-slate-500 mt-2 font-medium">
              {stage.description}
            </p>

            {/* Desktop Chevron connector */}
            {idx < mockBillingPipeline.length - 1 && (
              <div className="hidden lg:flex absolute -right-2.5 top-1/2 -translate-y-1/2 z-10 w-5 h-5 rounded-full bg-white border border-slate-200 items-center justify-center text-slate-400 shadow-subtle">
                <ChevronRight className="w-3 h-3" />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
