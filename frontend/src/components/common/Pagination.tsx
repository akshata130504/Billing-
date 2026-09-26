import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from './Button';

export interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  /** Noun for the summary line, e.g. "quotes". */
  itemLabel?: string;
}

/** Table footer for server-paginated lists (matches the DataTable footer). */
export function Pagination({ page, pageSize, total, onPageChange, itemLabel = 'results' }: PaginationProps) {
  if (total <= 0) return null;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="px-4 py-3 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-slate-500 bg-slate-50/50">
      <div>
        Showing <span className="font-semibold text-slate-700">{(page - 1) * pageSize + 1}</span> to{' '}
        <span className="font-semibold text-slate-700">{Math.min(page * pageSize, total)}</span> of{' '}
        <span className="font-semibold text-slate-700">{total}</span> {itemLabel}
      </div>
      {totalPages > 1 && (
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
      )}
    </div>
  );
}
