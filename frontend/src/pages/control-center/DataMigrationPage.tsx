import { Fragment, useRef, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { controlCenterService, downloadAuthenticated, toApiError, triggerBlobDownload } from '../../services';
import { queryKeys } from '../../hooks/queries';
import { useAuth } from '../../hooks/useAuth';
import { formatDateTime, humanize, type BadgeVariant } from '../../utils/format';
import type { ImportEntity, ImportResult, ImportRowError } from '../../types/api';
import { usePageSpec } from '../../appUi/usePageSpec';
import {
  UploadCloud,
  FileSpreadsheet,
  CheckCircle2,
  Download,
  Users,
  Package,
  Layers,
  ArrowRight,
  RefreshCw,
  FileCheck,
  AlertTriangle,
  History,
  Lock,
} from 'lucide-react';

// The backend only supports importing these three entities via CSV (see
// backend/app/models/governance.py ImportEntity). Invoices, subscriptions and
// payments have no import endpoint — that is a real backend limitation, not
// something this page can add on the frontend.
interface EntityConfig {
  key: ImportEntity;
  title: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  requiredFields: string[];
  optionalFields: string[];
  route: string;
}

const entityConfigs: EntityConfig[] = [
  {
    key: 'customers',
    title: 'Customers',
    description: 'Import your customer directory — GSTIN/PAN, billing addresses, currency and payment terms.',
    icon: Users,
    requiredFields: ['display_name'],
    optionalFields: [
      'company_name',
      'email',
      'phone',
      'gstin',
      'pan',
      'currency',
      'payment_terms_days',
      'billing_address_line1',
      'billing_address_line2',
      'billing_city',
      'billing_state',
      'billing_postal_code',
      'billing_country',
      'notes',
    ],
    route: '/customers',
  },
  {
    key: 'products',
    title: 'Products',
    description: 'Import products and SKUs — HSN/SAC codes, units of measure and default tax rates.',
    icon: Package,
    requiredFields: ['name', 'sku'],
    optionalFields: ['description', 'type', 'unit', 'hsn_sac_code', 'tax_rate_pct', 'is_active'],
    route: '/catalog',
  },
  {
    key: 'plans',
    title: 'Plans',
    description:
      'Import recurring billing plans. Each row links to an existing product by SKU, so import Products before Plans.',
    icon: Layers,
    requiredFields: ['product_sku', 'name', 'code', 'billing_interval', 'unit_amount'],
    optionalFields: ['interval_count', 'pricing_model', 'currency', 'setup_fee', 'trial_days', 'is_active'],
    route: '/plans-pricing',
  },
];

type Step = 'upload' | 'validating' | 'preview' | 'importing' | 'completed';

const STATUS_BADGE: Record<string, BadgeVariant> = {
  completed: 'success',
  completed_with_errors: 'warning',
  failed: 'danger',
};

function formatFileSize(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function downloadErrorCsv(errors: ImportRowError[], filenamePrefix: string) {
  const escape = (value: string) => `"${value.replace(/"/g, '""')}"`;
  const lines = ['row,error', ...errors.map((e) => `${e.row},${escape(e.error)}`)];
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
  triggerBlobDownload(blob, `${filenamePrefix}_errors.csv`);
}

function ImportErrorsList({ errors, onDownload }: { errors: ImportRowError[]; onDownload: () => void }) {
  if (errors.length === 0) return null;
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50/60 text-left">
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-rose-200 gap-2">
        <span className="text-xs font-bold text-rose-800">
          {errors.length} row error{errors.length === 1 ? '' : 's'}
          {errors.length >= 100 ? ' (first 100 shown)' : ''}
        </span>
        <Button variant="outline" size="sm" leadingIcon={<Download className="w-3.5 h-3.5" />} onClick={onDownload}>
          Download error CSV
        </Button>
      </div>
      <div className="max-h-56 overflow-y-auto divide-y divide-rose-100">
        {errors.map((e, i) => (
          <div key={`${e.row}-${i}`} className="px-3.5 py-2 text-xs flex gap-2">
            <span className="font-mono font-semibold text-rose-700 shrink-0">Row {e.row}</span>
            <span className="text-rose-800">{e.error}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function DataMigrationPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canImport = hasRole('finance');
  const ui = usePageSpec('data_migration');

  const [selectedEntity, setSelectedEntity] = useState<ImportEntity>('customers');
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [step, setStep] = useState<Step>('upload');
  const [dryRunResult, setDryRunResult] = useState<ImportResult | null>(null);
  const [finalResult, setFinalResult] = useState<ImportResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeConfig = entityConfigs.find((c) => c.key === selectedEntity)!;
  // Display name of the selected data model (configurable label; import behaviour stays in code).
  const activeTitle = ui.label('entities', activeConfig.key);

  const importsHistory = useQuery({
    queryKey: queryKeys.controlCenter.imports(),
    queryFn: () => controlCenterService.listImports({ page: 1, page_size: 10 }),
  });

  const handleReset = () => {
    setSelectedFile(null);
    setDryRunResult(null);
    setFinalResult(null);
    setStep('upload');
    validateMutation.reset();
    importMutation.reset();
  };

  const handleDownloadTemplate = async () => {
    try {
      await downloadAuthenticated(controlCenterService.importTemplateUrl(selectedEntity), `${selectedEntity}_template.csv`);
      showToast('info', 'Template downloaded', `Downloaded the CSV template for ${activeTitle}.`);
    } catch (err) {
      showToast('error', 'Download failed', toApiError(err).message);
    }
  };

  const validateMutation = useMutation({
    mutationFn: (file: File) => controlCenterService.runImport(selectedEntity, file, true),
    onSuccess: (result) => {
      setDryRunResult(result);
      setStep('preview');
    },
    onError: (err) => {
      showToast('error', 'Validation failed', toApiError(err).message);
      setStep('upload');
      setSelectedFile(null);
    },
  });

  const importMutation = useMutation({
    mutationFn: () => controlCenterService.runImport(selectedEntity, selectedFile as File, false),
    onSuccess: (result) => {
      setFinalResult(result);
      setStep('completed');
      void queryClient.invalidateQueries({ queryKey: queryKeys.controlCenter.imports() });
      showToast(
        result.failed_rows > 0 ? 'warning' : 'success',
        result.failed_rows > 0 ? 'Import completed with errors' : 'Import successful',
        `Imported ${result.imported_rows} of ${result.total_rows} ${activeTitle.toLowerCase()} row(s).`
      );
    },
    onError: (err) => {
      showToast('error', 'Import failed', toApiError(err).message);
      setStep('preview');
    },
  });

  const handleFileSelect = (file: File) => {
    if (!canImport) {
      showToast('error', 'Finance role required', 'You need the Finance role to import data.');
      return;
    }
    setSelectedFile(file);
    setDryRunResult(null);
    setStep('validating');
    validateMutation.mutate(file);
  };

  const openFilePicker = () => {
    if (!canImport) {
      showToast('error', 'Finance role required', 'You need the Finance role to import data.');
      return;
    }
    fileInputRef.current?.click();
  };

  const historyColumns = ui.shown('columns');
  const historyAlign: Record<string, string> = { imported: ' text-right', failed: ' text-right', total: ' text-right', when: ' text-right' };
  // Outer columns keep the wider padding whatever the configured order.
  const historyPad = (index: number) => (index === 0 || index === historyColumns.length - 1 ? 'px-5' : 'px-3');
  const historyCells: Record<string, (job: ImportResult, createdAt: string | null | undefined, pad: string) => ReactNode> = {
    entity: (job, _c, pad) => <td className={`py-2.5 ${pad} text-xs font-medium text-slate-900 capitalize`}>{job.entity}</td>,
    file: (job, _c, pad) => (
      <td className={`py-2.5 ${pad} text-xs text-slate-600 truncate max-w-[220px]`}>
        {job.file_name}
      </td>
    ),
    status: (job, _c, pad) => (
      <td className={`py-2.5 ${pad}`}>
        <Badge variant={STATUS_BADGE[job.status] ?? 'neutral'} size="sm">
          {humanize(job.status)}
        </Badge>
      </td>
    ),
    imported: (job, _c, pad) => (
      <td className={`py-2.5 ${pad} text-xs text-right text-emerald-600 font-semibold`}>
        {job.imported_rows}
      </td>
    ),
    failed: (job, _c, pad) => (
      <td className={`py-2.5 ${pad} text-xs text-right font-semibold text-rose-600`}>
        {job.failed_rows}
      </td>
    ),
    total: (job, _c, pad) => <td className={`py-2.5 ${pad} text-xs text-right text-slate-500`}>{job.total_rows}</td>,
    when: (_job, createdAt, pad) => (
      <td className={`py-2.5 ${pad} text-xs text-right text-slate-500 whitespace-nowrap`}>
        {createdAt ? formatDateTime(createdAt) : '—'}
      </td>
    ),
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div {...ui.edit('header')}>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
              {ui.text('header', 'eyebrow')}
            </span>
            <span className="text-slate-300">•</span>
            <Badge variant="primary" size="sm">
              {ui.text('header', 'badge')}
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <UploadCloud className="w-6 h-6 text-brand-600" />
            {ui.text('header', 'title')}
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            {ui.text('header', 'subtitle')}
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          leadingIcon={<Download className="w-3.5 h-3.5" />}
          onClick={() => void handleDownloadTemplate()}
        >
          Download Template
        </Button>
      </div>

      {!canImport && (
        <div className="flex items-center gap-2.5 p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800">
          <Lock className="w-4 h-4 shrink-0" />
          <span>
            You have read-only access to this page. Importing data requires the <strong>Finance</strong> role or
            above.
          </span>
        </div>
      )}

      {/* Entity Selector Cards */}
      <div>
        <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2.5" {...ui.edit('upload')}>
          {ui.text('upload', 'select_title')}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" {...ui.edit('entities')}>
          {entityConfigs.map((config) => {
            const Icon = config.icon;
            const isSelected = selectedEntity === config.key;
            const item = ui.items('entities').find((i) => i.key === config.key);
            return (
              <div
                key={config.key}
                {...ui.edit(`entities.${config.key}`)}
                onClick={() => {
                  setSelectedEntity(config.key);
                  handleReset();
                }}
                className={`p-3.5 rounded-xl border transition-all cursor-pointer text-left ${
                  isSelected
                    ? 'bg-brand-50/70 border-brand-400 ring-1 ring-brand-500 shadow-xs'
                    : 'bg-white border-slate-200/90 hover:border-slate-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span
                    className={`p-2 rounded-lg ${
                      isSelected ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                  </span>
                  {isSelected && <CheckCircle2 className="w-4 h-4 text-brand-600" />}
                </div>
                <h4 className="text-xs font-bold text-slate-900 mt-2.5">{item?.label ?? config.title}</h4>
                <p className="text-[10px] text-slate-500 mt-0.5 line-clamp-2">{item?.caption ?? config.description}</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Migration Workflow Card */}
      <Card>
        <CardContent className="p-6">
          {step === 'upload' && (
            <div className="space-y-4">
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleFileSelect(file);
                  e.target.value = '';
                }}
              />
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  if (canImport) setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  const dropped = e.dataTransfer.files[0];
                  if (dropped) handleFileSelect(dropped);
                }}
                onClick={openFilePicker}
                className={`border-2 border-dashed rounded-2xl p-8 sm:p-12 text-center transition-colors ${
                  !canImport
                    ? 'border-slate-200 opacity-60 cursor-not-allowed'
                    : dragOver
                    ? 'border-brand-500 bg-brand-50/50 cursor-pointer'
                    : 'border-slate-200 hover:border-brand-400 hover:bg-slate-50/50 cursor-pointer'
                }`}
              >
                <div className="w-12 h-12 rounded-full bg-brand-50 text-brand-600 flex items-center justify-center mx-auto mb-3">
                  <UploadCloud className="w-6 h-6" />
                </div>
                <h4 className="text-sm font-bold text-slate-900" {...ui.edit('upload')}>
                  {ui.text('upload', 'drop_title')}
                </h4>
                <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                  Supports .csv exports up to 5 MB and 5,000 rows.
                </p>
                <div className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-brand-600 bg-brand-50 px-3 py-1.5 rounded-lg border border-brand-100">
                  <FileSpreadsheet className="w-4 h-4" />
                  <span>{ui.text('upload', 'choose_file')}</span>
                </div>
              </div>

              {/* Field Schema Hint */}
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2.5">
                <div>
                  <span className="text-[11px] font-bold text-slate-700 uppercase tracking-wider block mb-1">
                    {ui.text('upload', 'required_columns', { entity: activeTitle })}
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {activeConfig.requiredFields.map((field) => (
                      <span
                        key={field}
                        className="font-mono text-[11px] bg-white text-rose-700 px-2 py-0.5 rounded border border-rose-200"
                      >
                        {field}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <span className="text-[11px] font-bold text-slate-700 uppercase tracking-wider block mb-1">
                    {ui.text('upload', 'optional_columns')}
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {activeConfig.optionalFields.map((field) => (
                      <span
                        key={field}
                        className="font-mono text-[11px] bg-white text-slate-700 px-2 py-0.5 rounded border border-slate-200"
                      >
                        {field}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {step === 'validating' && (
            <div className="py-12 text-center space-y-3">
              <RefreshCw className="w-8 h-8 text-brand-600 animate-spin mx-auto" />
              <h4 className="text-sm font-bold text-slate-900">Validating {selectedFile?.name}...</h4>
              <p className="text-xs text-slate-500">
                Checking every row against the {activeTitle.toLowerCase()} schema — nothing is written yet.
              </p>
            </div>
          )}

          {step === 'preview' && selectedFile && dryRunResult && (
            <div className="space-y-5">
              <div
                className={`flex items-center justify-between p-3.5 rounded-xl border gap-3 ${
                  dryRunResult.failed_rows > 0
                    ? 'bg-amber-50/80 border-amber-200'
                    : 'bg-emerald-50/80 border-emerald-200'
                }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  {dryRunResult.failed_rows > 0 ? (
                    <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
                  ) : (
                    <FileCheck className="w-5 h-5 text-emerald-600 shrink-0" />
                  )}
                  <div className="min-w-0">
                    <h5
                      className={`text-xs font-bold truncate ${
                        dryRunResult.failed_rows > 0 ? 'text-amber-950' : 'text-emerald-950'
                      }`}
                    >
                      {selectedFile.name} ({formatFileSize(selectedFile.size)})
                    </h5>
                    <p className={`text-[11px] ${dryRunResult.failed_rows > 0 ? 'text-amber-800' : 'text-emerald-800'}`}>
                      {dryRunResult.total_rows} row{dryRunResult.total_rows === 1 ? '' : 's'} parsed •{' '}
                      {dryRunResult.imported_rows} would import
                      {dryRunResult.failed_rows > 0
                        ? ` • ${dryRunResult.failed_rows} would fail`
                        : ' • 0 errors detected'}
                    </p>
                  </div>
                </div>
                <Badge variant={dryRunResult.failed_rows > 0 ? 'warning' : 'success'} size="sm">
                  {dryRunResult.failed_rows > 0 ? 'Errors Found' : 'Schema Valid'}
                </Badge>
              </div>

              {/* Validation Summary Cards */}
              <div className="grid grid-cols-3 gap-3 text-center">
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                  <span className="text-xs text-slate-500">Total Rows</span>
                  <p className="text-lg font-bold text-slate-900 mt-0.5">{dryRunResult.total_rows}</p>
                </div>
                <div className="p-3 bg-emerald-50 rounded-xl border border-emerald-200">
                  <span className="text-xs text-emerald-700">Would Import</span>
                  <p className="text-lg font-bold text-emerald-600 mt-0.5">{dryRunResult.imported_rows}</p>
                </div>
                <div
                  className={`p-3 rounded-xl border ${
                    dryRunResult.failed_rows > 0 ? 'bg-amber-50 border-amber-200' : 'bg-slate-50 border-slate-200'
                  }`}
                >
                  <span className={`text-xs ${dryRunResult.failed_rows > 0 ? 'text-amber-700' : 'text-slate-500'}`}>
                    Would Fail
                  </span>
                  <p
                    className={`text-lg font-bold mt-0.5 ${
                      dryRunResult.failed_rows > 0 ? 'text-amber-600' : 'text-slate-900'
                    }`}
                  >
                    {dryRunResult.failed_rows}
                  </p>
                </div>
              </div>

              <ImportErrorsList
                errors={dryRunResult.errors}
                onDownload={() => downloadErrorCsv(dryRunResult.errors, `${selectedEntity}_validation`)}
              />

              {dryRunResult.imported_rows === 0 && (
                <p className="text-xs text-rose-600 font-medium">
                  Every row failed validation — fix the file and upload again before importing.
                </p>
              )}

              <div className="flex items-center justify-between pt-2">
                <Button variant="outline" size="sm" onClick={handleReset}>
                  Choose Different File
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  leadingIcon={<ArrowRight className="w-3.5 h-3.5" />}
                  disabled={!canImport || dryRunResult.imported_rows === 0}
                  onClick={() => {
                    setStep('importing');
                    importMutation.mutate();
                  }}
                >
                  Confirm & Execute Migration
                </Button>
              </div>
            </div>
          )}

          {step === 'importing' && (
            <div className="py-12 text-center space-y-3">
              <RefreshCw className="w-8 h-8 text-brand-600 animate-spin mx-auto" />
              <h4 className="text-sm font-bold text-slate-900">
                Importing {activeTitle} Records...
              </h4>
              <p className="text-xs text-slate-500">Writing valid rows into your organization's database.</p>
            </div>
          )}

          {step === 'completed' && finalResult && (
            <div className="py-8 text-center space-y-4">
              <div
                className={`w-12 h-12 rounded-full flex items-center justify-center mx-auto ${
                  finalResult.failed_rows > 0 ? 'bg-amber-50 text-amber-600' : 'bg-emerald-50 text-emerald-600'
                }`}
              >
                {finalResult.failed_rows > 0 ? (
                  <AlertTriangle className="w-6 h-6" />
                ) : (
                  <CheckCircle2 className="w-6 h-6" />
                )}
              </div>
              <div>
                <h4 className="text-base font-bold text-slate-900">
                  {finalResult.failed_rows > 0 ? 'Migration Completed With Errors' : 'Data Migration Complete!'}
                </h4>
                <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
                  Imported {finalResult.imported_rows} of {finalResult.total_rows} {activeTitle.toLowerCase()}{' '}
                  row(s) into your Rooman Billing workspace.
                  {finalResult.failed_rows > 0 && ` ${finalResult.failed_rows} row(s) failed and were skipped.`}
                </p>
              </div>

              {finalResult.errors.length > 0 && (
                <div className="max-w-lg mx-auto">
                  <ImportErrorsList
                    errors={finalResult.errors}
                    onDownload={() => downloadErrorCsv(finalResult.errors, `${selectedEntity}_import`)}
                  />
                </div>
              )}

              <div className="flex items-center justify-center gap-3 pt-2">
                <Button variant="outline" size="sm" onClick={handleReset}>
                  Import Another File
                </Button>
                <Button variant="primary" size="sm" onClick={() => navigate(activeConfig.route)}>
                  View Imported {activeTitle}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Import History */}
      <div>
        <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2.5 flex items-center gap-1.5" {...ui.edit('history')}>
          <History className="w-3.5 h-3.5" />
          {ui.text('history', 'title')}
        </h3>
        <Card>
          <CardContent className="p-0">
            {importsHistory.isPending ? (
              <LoadingState message="Loading import history..." className="py-8" />
            ) : importsHistory.isError ? (
              <ErrorState
                message={toApiError(importsHistory.error).message}
                onRetry={() => void importsHistory.refetch()}
              />
            ) : (importsHistory.data?.items.length ?? 0) === 0 ? (
              <p className="py-8 text-center text-xs text-slate-400" {...ui.edit('history')}>{ui.text('history', 'empty')}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[640px]">
                  <thead>
                    <tr
                      className="text-xs font-semibold text-slate-500 uppercase tracking-wider text-left border-b border-slate-100"
                      {...ui.edit('columns')}
                    >
                      {historyColumns.map((col, index) => (
                        <th
                          key={col.key}
                          className={`py-2.5 ${historyPad(index)}${historyAlign[col.key] ?? ''}`}
                          {...ui.edit(`columns.${col.key}`)}
                        >
                          {col.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {importsHistory.data?.items.map((job) => {
                      // The API response includes `created_at` (see
                      // backend/app/schemas/imports.py), but the shared ImportResult
                      // type does not declare it — read it defensively rather than
                      // widening the shared type from this page.
                      const createdAt = (job as ImportResult & { created_at?: string | null }).created_at;
                      return (
                        <tr key={job.id ?? `${job.entity}-${job.file_name}`}>
                          {historyColumns.map((col, index) => (
                            <Fragment key={col.key}>{historyCells[col.key]?.(job, createdAt, historyPad(index))}</Fragment>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
