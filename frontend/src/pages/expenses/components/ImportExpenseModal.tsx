import { useState, useRef, ChangeEvent } from 'react';
import { X, UploadCloud, Download, CheckCircle, AlertCircle, FileSpreadsheet } from 'lucide-react';
import {
  Expense,
  ExpenseCategory,
  PaymentMethod,
  EXPENSE_CATEGORIES,
  EXPENSE_PAYMENT_METHODS,
} from '../types';
import { triggerBlobDownload } from '../../../services/download';
import { todayIso } from '../../../utils/format';

interface ImportExpenseModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImport: (expenses: Omit<Expense, 'id' | 'createdAt'>[]) => number;
}

const SAMPLE_CSV = `Name,Category,Amount,Date,Customer,Project,Billable,Payment Method,Status,Description
AWS Cloud Hosting,Cloud Services,14200,2026-03-01,Tata Motors,Cloud Migration,true,Corporate Card,recorded,Monthly EC2 and RDS instances
Client Dinner with Stakeholders,Meals,3850,2026-03-03,Reliance Industries,ERP Rollout,true,Corporate Card,recorded,Dinner with procurement team
Flight Tickets to Mumbai,Travel,18600,2026-03-04,Wipro Digital,Onsite Audit,true,Bank Transfer,recorded,Roundtrip flight for 2 engineers
Figma Enterprise Seats,Software,4500,2026-03-05,Internal,—,false,Corporate Card,recorded,Product design quarterly renewal
`;

export function ImportExpenseModal({ isOpen, onClose, onImport }: ImportExpenseModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [parsedRows, setParsedRows] = useState<Omit<Expense, 'id' | 'createdAt'>[]>([]);
  const [parseError, setParseError] = useState<string | null>(null);
  /** Rows that could not be imported, and values that were coerced. Surfaced to
   *  the user: silently importing 60 of 100 expenses is a data-loss bug. */
  const [parseWarnings, setParseWarnings] = useState<string[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  const handleDownloadSample = () => {
    const blob = new Blob([SAMPLE_CSV], { type: 'text/csv;charset=utf-8;' });
    triggerBlobDownload(blob, 'expenses_import_sample.csv');
  };

  const parseCSV = (text: string) => {
    try {
      const lines = text
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter((l) => l.length > 0);

      if (lines.length < 2) {
        setParseError('The file appears to be empty or missing data rows.');
        setParsedRows([]);
        return;
      }

      // Parse headers
      const headers = lines[0].split(',').map((h) => h.trim().toLowerCase().replace(/^["']|["']$/g, ''));
      const nameIdx = headers.findIndex((h) => h === 'name' || h === 'expense name' || h === 'title');
      const catIdx = headers.findIndex((h) => h === 'category');
      const amtIdx = headers.findIndex((h) => h === 'amount' || h === 'total' || h === 'cost');
      const dateIdx = headers.findIndex((h) => h === 'date');
      const custIdx = headers.findIndex((h) => h === 'customer' || h === 'client');
      const projIdx = headers.findIndex((h) => h === 'project');
      const billIdx = headers.findIndex((h) => h === 'billable');
      const payIdx = headers.findIndex((h) => h === 'payment method' || h === 'method');
      const statusIdx = headers.findIndex((h) => h === 'status');
      const descIdx = headers.findIndex((h) => h === 'description' || h === 'notes');

      if (nameIdx === -1 || amtIdx === -1) {
        setParseError('CSV must at least contain "Name" and "Amount" columns.');
        setParsedRows([]);
        return;
      }

      const rows: Omit<Expense, 'id' | 'createdAt'>[] = [];
      const warnings: string[] = [];
      const defaultDate = todayIso();

      for (let i = 1; i < lines.length; i++) {
        const line = lines[i];
        // Split with basic quote awareness
        const values: string[] = [];
        let current = '';
        let inQuotes = false;
        for (let c = 0; c < line.length; c++) {
          const ch = line[c];
          if (ch === '"') {
            inQuotes = !inQuotes;
          } else if (ch === ',' && !inQuotes) {
            values.push(current.trim().replace(/^"|"$/g, ''));
            current = '';
          } else {
            current += ch;
          }
        }
        values.push(current.trim().replace(/^"|"$/g, ''));

        const name = values[nameIdx] || '';
        const rawAmt = values[amtIdx]?.replace(/[^0-9.-]/g, '') || '0';
        const amount = parseFloat(rawAmt);

        if (!name) {
          warnings.push(`Row ${i + 1}: skipped — no expense name.`);
          continue;
        }
        if (isNaN(amount) || amount <= 0) {
          warnings.push(`Row ${i + 1}: skipped — amount "${values[amtIdx] ?? ''}" is not a positive number.`);
          continue;
        }

        const rawCategory = catIdx !== -1 && values[catIdx] ? values[catIdx] : 'Other';
        // A category outside the canonical list would be invisible to the
        // category filter (which matches exactly) while still counting in totals.
        const category = (EXPENSE_CATEGORIES as readonly string[]).includes(rawCategory)
          ? (rawCategory as ExpenseCategory)
          : 'Other';
        if (category !== rawCategory) {
          warnings.push(`Row ${i + 1}: unknown category "${rawCategory}" imported as "Other".`);
        }
        const date = (dateIdx !== -1 && values[dateIdx] ? values[dateIdx] : defaultDate);
        const customer = (custIdx !== -1 && values[custIdx] ? values[custIdx] : 'Internal');
        const project = (projIdx !== -1 && values[projIdx] ? values[projIdx] : '—');
        const isBillableRaw = billIdx !== -1 ? values[billIdx]?.toLowerCase() : 'false';
        const billable = isBillableRaw === 'true' || isBillableRaw === '1' || isBillableRaw === 'yes';
        const rawPaymentMethod = payIdx !== -1 && values[payIdx] ? values[payIdx] : 'Corporate Card';
        const paymentMethod = (EXPENSE_PAYMENT_METHODS as readonly string[]).includes(rawPaymentMethod)
          ? (rawPaymentMethod as PaymentMethod)
          : 'Other';
        if (paymentMethod !== rawPaymentMethod) {
          warnings.push(`Row ${i + 1}: unknown payment method "${rawPaymentMethod}" imported as "Other".`);
        }
        const status = (statusIdx !== -1 && values[statusIdx] ? values[statusIdx].toLowerCase() : 'recorded') as any;
        const description = (descIdx !== -1 ? values[descIdx] : '');

        rows.push({
          name,
          category,
          amount,
          currency: 'INR',
          date,
          customer,
          project,
          billable,
          billableAmount: billable ? amount : 0,
          paymentMethod,
          paidBy: 'Corporate Account',
          status: ['draft', 'recorded', 'billable', 'invoiced', 'reimbursed', 'cancelled'].includes(status)
            ? status
            : billable ? 'billable' : 'recorded',
          description,
        });
      }

      const dataRowCount = lines.length - 1;
      if (rows.length === 0) {
        setParseError('No valid expense rows could be parsed. Check column formats and numbers.');
        setParsedRows([]);
        setParseWarnings(warnings);
      } else {
        setParseError(null);
        setParsedRows(rows);
        if (rows.length < dataRowCount) {
          warnings.unshift(`${dataRowCount - rows.length} of ${dataRowCount} rows will not be imported.`);
        }
        setParseWarnings(warnings);
      }
    } catch (err) {
      setParseError('Failed to parse file. Please verify CSV format.');
      setParsedRows([]);
      setParseWarnings([]);
    }
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (!selected) return;
    setFile(selected);
    setIsProcessing(true);
    const reader = new FileReader();
    reader.onload = (evt) => {
      const text = evt.target?.result as string;
      parseCSV(text);
      setIsProcessing(false);
    };
    reader.onerror = () => {
      setParseError('Error reading file.');
      setIsProcessing(false);
    };
    reader.readAsText(selected);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) {
      setFile(dropped);
      setIsProcessing(true);
      const reader = new FileReader();
      reader.onload = (evt) => {
        const text = evt.target?.result as string;
        parseCSV(text);
        setIsProcessing(false);
      };
      reader.readAsText(dropped);
    }
  };

  const handleExecuteImport = () => {
    if (parsedRows.length === 0) return;
    onImport(parsedRows);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl border border-slate-200/80 w-full max-w-2xl overflow-hidden animate-in fade-in-0 zoom-in-95">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-200/80 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-brand-50 border border-brand-100 rounded-lg text-brand-600">
              <UploadCloud className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">Import Expenses</h2>
              <p className="text-xs text-slate-500">
                Upload a CSV file to batch-import operating, client, or vendor expenses.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 p-1 rounded-md transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-5">
          {/* Sample Download Banner */}
          <div className="flex items-center justify-between p-3 bg-blue-50/60 border border-blue-100 rounded-lg text-xs">
            <div className="flex items-center gap-2 text-blue-900">
              <FileSpreadsheet className="w-4 h-4 text-blue-600 shrink-0" />
              <span>Need the right format? Use our pre-formatted spreadsheet template.</span>
            </div>
            <button
              type="button"
              onClick={handleDownloadSample}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 font-semibold text-blue-700 bg-white border border-blue-200 rounded hover:bg-blue-50 transition-colors shrink-0"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Sample CSV</span>
            </button>
          </div>

          {/* Upload Dropzone */}
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className="border-2 border-dashed border-slate-300 hover:border-brand-500 rounded-xl p-6 text-center cursor-pointer transition-colors bg-slate-50/50 hover:bg-slate-50"
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".csv,.txt"
              className="hidden"
            />
            <UploadCloud className="w-8 h-8 mx-auto text-slate-400 mb-2" />
            <p className="text-xs font-semibold text-slate-800">
              {file ? file.name : 'Click to browse or drag and drop your CSV file here'}
            </p>
            <p className="text-2xs text-slate-500 mt-1">
              Supports CSV files with columns: Name, Category, Amount, Date, Customer, Project, Billable
            </p>
          </div>

          {/* Error Message */}
          {parseError && (
            <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-100 rounded-lg text-xs text-red-700">
              <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
              <span>{parseError}</span>
            </div>
          )}

          {/* Rows that will not import, and values that were coerced. */}
          {parseWarnings.length > 0 && (
            <div className="p-3 bg-amber-50 border border-amber-100 rounded-lg text-xs text-amber-800">
              <div className="flex items-center gap-2 font-semibold mb-1.5">
                <AlertCircle className="w-4 h-4 text-amber-500 shrink-0" />
                <span>Review before importing</span>
              </div>
              <ul className="list-disc pl-5 space-y-0.5 max-h-28 overflow-y-auto">
                {parseWarnings.slice(0, 20).map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
                {parseWarnings.length > 20 && <li>…and {parseWarnings.length - 20} more</li>}
              </ul>
            </div>
          )}

          {/* Preview Table if rows parsed */}
          {parsedRows.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700">
                  <CheckCircle className="w-4 h-4 text-emerald-600" />
                  <span>Ready to import {parsedRows.length} valid expense(s)</span>
                </div>
                <span className="text-2xs text-slate-500">Previewing first 4 rows</span>
              </div>

              <div className="border border-slate-200 rounded-lg overflow-hidden max-h-48 overflow-y-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-2xs text-slate-600 font-semibold uppercase tracking-wider">
                    <tr>
                      <th className="px-3 py-2">Expense Name</th>
                      <th className="px-3 py-2">Category</th>
                      <th className="px-3 py-2">Date</th>
                      <th className="px-3 py-2">Customer</th>
                      <th className="px-3 py-2 text-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {parsedRows.slice(0, 4).map((row, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/50">
                        <td className="px-3 py-1.5 font-medium text-slate-900 truncate max-w-[140px]">{row.name}</td>
                        <td className="px-3 py-1.5">{row.category}</td>
                        <td className="px-3 py-1.5 text-slate-500">{row.date}</td>
                        <td className="px-3 py-1.5 truncate max-w-[120px]">{row.customer}</td>
                        <td className="px-3 py-1.5 text-right font-semibold text-slate-900">
                          ₹{row.amount.toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3.5 border-t border-slate-200/80 bg-slate-50/50 flex items-center justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={parsedRows.length === 0 || isProcessing}
            onClick={handleExecuteImport}
            className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-2xs"
          >
            <UploadCloud className="w-3.5 h-3.5" />
            <span>Import {parsedRows.length > 0 ? `${parsedRows.length} Expenses` : ''}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
