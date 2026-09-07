import { useState, useRef, useEffect } from 'react';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import {
  UploadCloud,
  FileSpreadsheet,
  CheckCircle2,
  Download,
  Users,
  Package,
  Receipt,
  Repeat,
  CreditCard,
  ArrowRight,
  RefreshCw,
  FileCheck,
} from 'lucide-react';

export type MigrationEntity = 'customers' | 'products' | 'invoices' | 'subscriptions' | 'payments';

interface EntityConfig {
  key: MigrationEntity;
  title: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  sampleFields: string[];
}

const entityConfigs: EntityConfig[] = [
  {
    key: 'customers',
    title: 'Customers',
    description: 'Import client directories, GSTIN / tax IDs, primary contacts, and currencies.',
    icon: Users,
    sampleFields: ['customer_name', 'email', 'phone', 'gstin', 'currency', 'billing_street', 'country'],
  },
  {
    key: 'products',
    title: 'Products & Plans',
    description: 'Import recurring subscription plans, SKU tiers, units of measure, and one-off add-ons.',
    icon: Package,
    sampleFields: ['product_name', 'sku', 'billing_interval', 'unit_price', 'currency', 'tax_code'],
  },
  {
    key: 'invoices',
    title: 'Invoices & Balances',
    description: 'Historical invoices, line item breakdowns, tax amounts, and payment due dates.',
    icon: Receipt,
    sampleFields: ['invoice_number', 'customer_email', 'issue_date', 'due_date', 'subtotal', 'tax', 'status'],
  },
  {
    key: 'subscriptions',
    title: 'Subscriptions',
    description: 'Active subscriptions, renewal cycle anchors, seat counts, and trial states.',
    icon: Repeat,
    sampleFields: ['subscription_id', 'customer_email', 'plan_sku', 'started_at', 'current_period_end', 'status'],
  },
  {
    key: 'payments',
    title: 'Payments & Collections',
    description: 'Past payment settlements, gateway reference IDs, wire UTR numbers, and allocations.',
    icon: CreditCard,
    sampleFields: ['payment_ref', 'invoice_number', 'amount', 'gateway', 'transaction_id', 'paid_at'],
  },
];

export function DataMigrationPage() {
  const { showToast } = useToast();
  const [selectedEntity, setSelectedEntity] = useState<MigrationEntity>('customers');
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<{ name: string; size: string } | null>(null);
  const [step, setStep] = useState<'upload' | 'validating' | 'preview' | 'importing' | 'completed'>('upload');
  const [progress, setProgress] = useState(0);

  // Pending simulated async work, so a reset or unmount can cancel it cleanly
  const validationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const importIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearPendingTimers = () => {
    if (validationTimerRef.current !== null) {
      clearTimeout(validationTimerRef.current);
      validationTimerRef.current = null;
    }
    if (importIntervalRef.current !== null) {
      clearInterval(importIntervalRef.current);
      importIntervalRef.current = null;
    }
  };

  useEffect(() => clearPendingTimers, []);

  const activeConfig = entityConfigs.find((c) => c.key === selectedEntity)!;

  const handleDownloadTemplate = () => {
    const csvContent = activeConfig.sampleFields.join(',') + '\n';
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `rooman_${selectedEntity}_template.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('info', 'Template Downloaded', `Downloaded sample CSV template for ${activeConfig.title}.`);
  };

  const handleFileSelect = (name: string, size: string) => {
    clearPendingTimers();
    setSelectedFile({ name, size });
    setStep('validating');
    validationTimerRef.current = setTimeout(() => {
      validationTimerRef.current = null;
      setStep('preview');
      showToast('success', 'File Validated', 'All columns mapped successfully against schema.');
    }, 600);
  };

  const handleStartImport = () => {
    clearPendingTimers();
    setStep('importing');
    let current = 15;
    setProgress(current);
    importIntervalRef.current = setInterval(() => {
      current = Math.min(current + 25, 100);
      setProgress(current);
      if (current >= 100) {
        clearPendingTimers();
        setStep('completed');
        showToast('success', 'Import Successful', `Migrated 142 records into ${activeConfig.title}.`);
      }
    }, 300);
  };

  const handleReset = () => {
    clearPendingTimers();
    setSelectedFile(null);
    setStep('upload');
    setProgress(0);
  };

  const formatFileSize = (bytes: number) =>
    bytes >= 1024 * 1024
      ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
      : `${Math.max(1, Math.round(bytes / 1024))} KB`;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
              Control Center
            </span>
            <span className="text-slate-300">•</span>
            <Badge variant="primary" size="sm">
              Self-Service Import
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <UploadCloud className="w-6 h-6 text-brand-600" />
            Data Migration & Onboarding
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            Import legacy billing data, customer registries, product catalogs, and historical invoices seamlessly via validated CSV and JSON templates.
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          leadingIcon={<Download className="w-3.5 h-3.5" />}
          onClick={handleDownloadTemplate}
        >
          Download Template
        </Button>
      </div>

      {/* Entity Selector Cards */}
      <div>
        <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2.5">
          1. Select Target Data Model
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {entityConfigs.map((config) => {
            const Icon = config.icon;
            const isSelected = selectedEntity === config.key;
            return (
              <div
                key={config.key}
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
                <h4 className="text-xs font-bold text-slate-900 mt-2.5">{config.title}</h4>
                <p className="text-[10px] text-slate-500 mt-0.5 line-clamp-2">{config.description}</p>
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
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  // Reflect the dropped file's real name/size; the parsing itself is still simulated
                  const dropped = e.dataTransfer.files[0];
                  if (dropped) {
                    handleFileSelect(dropped.name, formatFileSize(dropped.size));
                  } else {
                    handleFileSelect('legacy_export_data.csv', '248 KB');
                  }
                }}
                onClick={() => handleFileSelect(`${selectedEntity}_export_sample.csv`, '184 KB')}
                className={`border-2 border-dashed rounded-2xl p-8 sm:p-12 text-center transition-colors cursor-pointer ${
                  dragOver
                    ? 'border-brand-500 bg-brand-50/50'
                    : 'border-slate-200 hover:border-brand-400 hover:bg-slate-50/50'
                }`}
              >
                <div className="w-12 h-12 rounded-full bg-brand-50 text-brand-600 flex items-center justify-center mx-auto mb-3">
                  <UploadCloud className="w-6 h-6" />
                </div>
                <h4 className="text-sm font-bold text-slate-900">
                  Drop your CSV or JSON file here, or browse
                </h4>
                <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                  Supports .csv and .json exports from Stripe, Chargebee, Zoho Billing, or customized spreadsheets.
                </p>
                <div className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-brand-600 bg-brand-50 px-3 py-1.5 rounded-lg border border-brand-100">
                  <FileSpreadsheet className="w-4 h-4" />
                  <span>Click to simulate upload</span>
                </div>
              </div>

              {/* Field Schema Hint */}
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80">
                <span className="text-[11px] font-bold text-slate-700 uppercase tracking-wider block mb-1">
                  Expected Column Headers for {activeConfig.title}:
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {activeConfig.sampleFields.map((field) => (
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
          )}

          {step === 'validating' && (
            <div className="py-12 text-center space-y-3">
              <RefreshCw className="w-8 h-8 text-brand-600 animate-spin mx-auto" />
              <h4 className="text-sm font-bold text-slate-900">Validating Data Model & Headers...</h4>
              <p className="text-xs text-slate-500">Checking rows against validation constraints...</p>
            </div>
          )}

          {step === 'preview' && selectedFile && (
            <div className="space-y-5">
              <div className="flex items-center justify-between p-3.5 rounded-xl bg-emerald-50/80 border border-emerald-200">
                <div className="flex items-center gap-3">
                  <FileCheck className="w-5 h-5 text-emerald-600 shrink-0" />
                  <div>
                    <h5 className="text-xs font-bold text-emerald-950">
                      File Ready for Migration: {selectedFile.name} ({selectedFile.size})
                    </h5>
                    <p className="text-[11px] text-emerald-800">
                      142 records parsed • 7 columns matched • 0 critical errors detected
                    </p>
                  </div>
                </div>
                <Badge variant="success" size="sm">Schema Valid</Badge>
              </div>

              {/* Validation Summary Cards */}
              <div className="grid grid-cols-3 gap-3 text-center">
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                  <span className="text-xs text-slate-500">Total Records</span>
                  <p className="text-lg font-bold text-slate-900 mt-0.5">142</p>
                </div>
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                  <span className="text-xs text-slate-500">Auto-Mapped</span>
                  <p className="text-lg font-bold text-emerald-600 mt-0.5">100%</p>
                </div>
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                  <span className="text-xs text-slate-500">Format Warnings</span>
                  <p className="text-lg font-bold text-amber-600 mt-0.5">2 (Coerced)</p>
                </div>
              </div>

              <div className="flex items-center justify-between pt-2">
                <Button variant="outline" size="sm" onClick={handleReset}>
                  Choose Different File
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  leadingIcon={<ArrowRight className="w-3.5 h-3.5" />}
                  onClick={handleStartImport}
                >
                  Confirm & Execute Migration
                </Button>
              </div>
            </div>
          )}

          {step === 'importing' && (
            <div className="py-8 space-y-4 text-center">
              <h4 className="text-sm font-bold text-slate-900">
                Importing {activeConfig.title} Records...
              </h4>
              <p className="text-xs text-slate-500">
                Inserting and indexing into multi-tenant database ({progress}%)
              </p>
              <div className="w-full bg-slate-100 rounded-full h-2 max-w-md mx-auto overflow-hidden">
                <div
                  className="bg-brand-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {step === 'completed' && (
            <div className="py-8 text-center space-y-4">
              <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-base font-bold text-slate-900">Data Migration Complete!</h4>
                <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
                  Successfully imported 142 {activeConfig.title} records into your Rooman Billing workspace. All IDs and financial balances are active.
                </p>
              </div>
              <div className="flex items-center justify-center gap-3 pt-2">
                <Button variant="outline" size="sm" onClick={handleReset}>
                  Import Another File
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    handleReset();
                    showToast('info', 'Workspace', `Navigating to ${activeConfig.title}`);
                  }}
                >
                  View Imported {activeConfig.title}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
