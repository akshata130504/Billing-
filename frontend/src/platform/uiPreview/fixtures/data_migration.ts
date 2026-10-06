/**
 * Visual-editor preview sample data for Control Center > Data Migration (/control-center/migration).
 * Entirely fictional file names and counts.
 */
import type { ImportResult, Paginated } from '../../../types/api';

/** The API also returns `created_at` (read defensively by the page). */
type ImportHistoryItem = ImportResult & { created_at: string };

const IMPORTS: ImportHistoryItem[] = [
  {
    id: 'imp-preview-3', entity: 'plans', file_name: 'plans_sample.csv', status: 'completed_with_errors', dry_run: false,
    total_rows: 12, imported_rows: 10, failed_rows: 2, errors: [], preview: [], created_at: '2026-10-04T11:20:00Z',
  },
  {
    id: 'imp-preview-2', entity: 'products', file_name: 'products_sample.csv', status: 'completed', dry_run: false,
    total_rows: 42, imported_rows: 42, failed_rows: 0, errors: [], preview: [], created_at: '2026-09-30T10:05:00Z',
  },
  {
    id: 'imp-preview-1', entity: 'customers', file_name: 'customers_sample.csv', status: 'completed', dry_run: false,
    total_rows: 128, imported_rows: 128, failed_rows: 0, errors: [], preview: [], created_at: '2026-09-28T09:40:00Z',
  },
];

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/imports': (): Paginated<ImportHistoryItem> => ({
    items: IMPORTS, total: IMPORTS.length, page: 1, page_size: 10, total_pages: 1,
  }),
};
