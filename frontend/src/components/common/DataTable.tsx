import React from 'react';
import { cn } from '../../utils/cn';
import { ChevronLeft, ChevronRight, Inbox } from 'lucide-react';
import { Button } from './Button';

export interface Column<T> {
  key: string;
  title: string;
  render?: (item: T, index: number) => React.ReactNode;
  align?: 'left' | 'center' | 'right';
  className?: string;
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (item: T) => string | number;
  emptyMessage?: string;
  emptySubtext?: string;
  page?: number;
  pageSize?: number;
  total?: number;
  onPageChange?: (newPage: number) => void;
  isLoading?: boolean;
}

export function DataTable<T>({
  columns,
  data,
  keyExtractor,
  emptyMessage = 'No records found',
  emptySubtext = 'Get started by creating a new entry.',
  page = 1,
  pageSize = 10,
  total,
  onPageChange,
  isLoading = false,
}: DataTableProps<T>) {
  const totalPages = total ? Math.ceil(total / pageSize) : 1;

  return (
    <div className="w-full bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50/80 text-xs font-semibold text-slate-600 uppercase tracking-wider">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={cn(
                    'py-3.5 px-4',
                    col.align === 'right' && 'text-right',
                    col.align === 'center' && 'text-center',
                    col.className
                  )}
                >
                  {col.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-sm">
            {isLoading ? (
              <tr>
                <td colSpan={columns.length} className="py-12 text-center text-slate-400">
                  <div className="inline-flex items-center gap-2 text-xs font-medium">
                    <span className="w-4 h-4 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
                    Loading data...
                  </div>
                </td>
              </tr>
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="py-12 text-center">
                  <div className="flex flex-col items-center justify-center text-slate-400">
                    <Inbox className="w-8 h-8 stroke-1 text-slate-300 mb-2" />
                    <p className="text-sm font-medium text-slate-700">{emptyMessage}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{emptySubtext}</p>
                  </div>
                </td>
              </tr>
            ) : (
              data.map((item, index) => (
                <tr
                  key={keyExtractor(item)}
                  className="hover:bg-slate-50/70 transition-colors"
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        'py-3.5 px-4 text-slate-700 font-normal',
                        col.align === 'right' && 'text-right',
                        col.align === 'center' && 'text-center',
                        col.className
                      )}
                    >
                      {col.render
                        ? col.render(item, index)
                        : (item as Record<string, unknown>)[col.key] !== undefined
                        ? String((item as Record<string, unknown>)[col.key])
                        : '—'}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      {total !== undefined && onPageChange && total > 0 && (
        <div className="px-4 py-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500 bg-slate-50/50">
          <div>
            Showing{' '}
            <span className="font-semibold text-slate-700">
              {(page - 1) * pageSize + 1}
            </span>{' '}
            to{' '}
            <span className="font-semibold text-slate-700">
              {Math.min(page * pageSize, total)}
            </span>{' '}
            of <span className="font-semibold text-slate-700">{total}</span> results
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
              leadingIcon={<ChevronLeft className="w-3.5 h-3.5" />}
            >
              Previous
            </Button>
            <span className="px-2 font-medium text-slate-600">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
              trailingIcon={<ChevronRight className="w-3.5 h-3.5" />}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
