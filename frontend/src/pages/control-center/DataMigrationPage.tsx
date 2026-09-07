import { useState } from 'react';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import {
  UploadCloud,
  FileSpreadsheet,
  CheckCircle2,
  Download,
  FileText,
  Users,
  Package,
  Repeat,
  CreditCard,
  ArrowRight,
} from 'lucide-react';

interface MigrationJob {
  id: string;
  category: 'Customers' | 'Products' | 'Invoices' | 'Subscriptions' | 'Payments';
  filename: string;
  totalRecords: number;
  imported: number;
  failed: number;
  pending: number;
  status: 'Validated' | 'Imported' | 'Pending' | 'Failed';
  timestamp: string;
}

const initialJobs: MigrationJob[] = [
  {
    id: 'MIG-01',
    category: 'Customers',
    filename: 'salesforce_accounts_dump.csv',
    totalRecords: 1250,
    imported: 1248,
    failed: 2,
    pending: 0,
    status: 'Imported',
    timestamp: 'Today, 10:15 AM',
  },
  {
    id: 'MIG-02',
    category: 'Products',
    filename: 'stripe_products_catalog.csv',
    totalRecords: 84,
    imported: 84,
    failed: 0,
    pending: 0,
    status: 'Imported',
    timestamp: 'Yesterday, 03:20 PM',
  },
  {
    id: 'MIG-03',
    category: 'Subscriptions',
    filename: 'chargebee_recurring_contracts.csv',
    totalRecords: 412,
    imported: 0,
    failed: 0,
    pending: 412,
    status: 'Validated',
    timestamp: 'Today, 01:40 PM',
  },
  {
    id: 'MIG-04',
    category: 'Invoices',
    filename: 'quickbooks_invoices_2025.csv',
    totalRecords: 3820,
    imported: 3790,
    failed: 30,
    pending: 0,
    status: 'Failed',
    timestamp: 'Sep 04, 2026',
  },
];

export function DataMigrationPage() {
  const [jobs] = useState<MigrationJob[]>(initialJobs);
  const [selectedCategory, setSelectedCategory] = useState<string>('Customers');
  const { showToast } = useToast();

  const handleUploadClick = () => {
    showToast('info', 'Mock Upload', `Simulated CSV upload opened for ${selectedCategory}.`);
  };

  const handleValidateClick = () => {
    showToast('success', 'Validation Complete', 'Schema and tax identifiers validated successfully (0 syntax errors).');
  };

  const handleImportClick = () => {
    showToast('info', 'Import Scheduled', 'Batch data ingestion runner queued in Phase 0 demo state.');
  };

  const handleDownloadErrors = (jobId: string) => {
    showToast('info', 'Error Report', `Downloading error diagnosis report for ${jobId}.`);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
              Control Center
            </span>
            <span className="text-slate-300">•</span>
            <Badge variant="primary" size="sm">
              Data Ingestion
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Data Migration
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            Self-serve migration toolchain to bulk ingest historical customers, product price books, open invoices, active subscriptions, and payment ledgers into Rooman Billing.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<Download className="w-3.5 h-3.5" />}
            onClick={() => showToast('info', 'Templates', 'Downloading standard Rooman Billing CSV templates bundle.')}
          >
            Download CSV Templates
          </Button>
        </div>
      </div>

      {/* Migration Category Selector Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {[
          { name: 'Customers', icon: Users, count: '1,250 records' },
          { name: 'Products', icon: Package, count: '84 plans' },
          { name: 'Invoices', icon: FileText, count: '3,820 historical' },
          { name: 'Subscriptions', icon: Repeat, count: '412 active' },
          { name: 'Payments', icon: CreditCard, count: '5,100 ledger' },
        ].map((cat) => {
          const Icon = cat.icon;
          const isSelected = selectedCategory === cat.name;
          return (
            <button
              key={cat.name}
              type="button"
              onClick={() => setSelectedCategory(cat.name)}
              className={`p-3.5 rounded-xl border text-left transition-all cursor-pointer ${
                isSelected
                  ? 'bg-blue-50/70 border-brand-500 ring-1 ring-brand-500 shadow-2xs'
                  : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50'
              }`}
            >
              <Icon className={`w-5 h-5 ${isSelected ? 'text-brand-600' : 'text-slate-500'}`} />
              <h4 className={`text-xs font-bold mt-2 ${isSelected ? 'text-brand-900' : 'text-slate-900'}`}>
                {cat.name}
              </h4>
              <p className="text-[10px] text-slate-400 mt-0.5">{cat.count}</p>
            </button>
          );
        })}
      </div>

      {/* Upload & Ingestion Staging Card */}
      <Card>
        <CardContent className="p-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-bold text-slate-900">
                Staging Area: {selectedCategory} Migration
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Upload CSV file containing formatted {selectedCategory.toLowerCase()} records to validate headers and staging integrity.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                leadingIcon={<UploadCloud className="w-3.5 h-3.5" />}
                onClick={handleUploadClick}
              >
                Upload CSV
              </Button>
              <Button
                variant="outline"
                size="sm"
                leadingIcon={<CheckCircle2 className="w-3.5 h-3.5" />}
                onClick={handleValidateClick}
              >
                Validate Schema
              </Button>
              <Button
                variant="primary"
                size="sm"
                leadingIcon={<ArrowRight className="w-3.5 h-3.5" />}
                onClick={handleImportClick}
              >
                Execute Import
              </Button>
            </div>
          </div>

          <div className="mt-5 p-4 rounded-xl border border-dashed border-slate-200 bg-slate-50/60 flex flex-col items-center justify-center text-center py-8">
            <div className="p-3 rounded-xl bg-white text-brand-600 border border-slate-200 shadow-2xs mb-2">
              <FileSpreadsheet className="w-6 h-6" />
            </div>
            <p className="text-xs font-bold text-slate-900">
              Drag and drop {selectedCategory} CSV file here
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Supports standard CSV, TSV, or XLSX exports up to 50MB (UTF-8 encoded)
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Import History Table */}
      <Card>
        <CardContent className="p-0 overflow-x-auto">
          <div className="p-4 border-b border-slate-100 flex items-center justify-between">
            <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
              Import & Migration History
            </h4>
            <span className="text-xs text-slate-400">Showing recent 4 batch runs</span>
          </div>
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-200/80 bg-slate-50/75 text-slate-500 font-semibold uppercase tracking-wider text-[11px]">
                <th className="py-3 px-4">Batch ID & Category</th>
                <th className="py-3 px-4">Source File</th>
                <th className="py-3 px-4">Total Records</th>
                <th className="py-3 px-4">Imported</th>
                <th className="py-3 px-4">Failed</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {jobs.map((job) => (
                <tr key={job.id} className="hover:bg-slate-50/60 transition-colors">
                  <td className="py-3.5 px-4">
                    <p className="font-bold text-slate-900">{job.id}</p>
                    <p className="text-[11px] text-slate-500">{job.category} • {job.timestamp}</p>
                  </td>
                  <td className="py-3.5 px-4 font-mono text-[11px] text-slate-600">
                    {job.filename}
                  </td>
                  <td className="py-3.5 px-4 font-semibold text-slate-900">
                    {job.totalRecords.toLocaleString()}
                  </td>
                  <td className="py-3.5 px-4 text-emerald-600 font-semibold">
                    {job.imported.toLocaleString()}
                  </td>
                  <td className="py-3.5 px-4 font-semibold text-rose-600">
                    {job.failed > 0 ? job.failed : '0'}
                  </td>
                  <td className="py-3.5 px-4">
                    <Badge
                      variant={
                        job.status === 'Imported'
                          ? 'success'
                          : job.status === 'Validated'
                          ? 'primary'
                          : job.status === 'Pending'
                          ? 'warning'
                          : 'danger'
                      }
                      size="sm"
                    >
                      {job.status}
                    </Badge>
                  </td>
                  <td className="py-3.5 px-4 text-right">
                    {job.failed > 0 ? (
                      <button
                        onClick={() => handleDownloadErrors(job.id)}
                        className="text-xs text-rose-600 hover:underline font-medium inline-flex items-center gap-1"
                      >
                        <Download className="w-3 h-3" /> Error Log
                      </button>
                    ) : (
                      <span className="text-slate-400 text-[11px]">No errors</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
