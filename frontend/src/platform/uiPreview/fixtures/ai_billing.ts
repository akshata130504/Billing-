/**
 * Visual-editor preview sample data for AI in Billing (/ai-billing). Fictional activity only.
 * The page loads GET /ai/history on mount (the History tab filters it by `mode`).
 */
import type { AIHistoryItem } from '../../../types/ai';

const history: AIHistoryItem[] = [
  { id: 'ai-req-6', conversation_id: 'conv-3', mode: 'query', prompt: 'Which invoices are overdue by more than 30 days?', status: 'completed', answer: '2 invoices are overdue by more than 30 days, totalling ₹50,858.00.', created_at: '2026-10-05T09:42:00' },
  { id: 'ai-req-5', conversation_id: 'conv-3', mode: 'query', prompt: 'What is our MRR this month?', status: 'completed', answer: 'MRR is ₹26,994.00 across 2 active subscriptions.', created_at: '2026-10-05T09:40:00' },
  { id: 'ai-req-4', conversation_id: 'conv-2', mode: 'writing', prompt: 'Friendly payment reminder for Bluewave Logistics', status: 'completed', answer: null, created_at: '2026-10-04T16:15:00' },
  { id: 'ai-req-3', conversation_id: 'conv-2', mode: 'draft', prompt: 'Credit note for a damaged shipment on INV-1046', status: 'completed', answer: null, created_at: '2026-10-03T11:05:00' },
  { id: 'ai-req-2', conversation_id: 'conv-1', mode: 'query', prompt: 'Who are my top customers by revenue?', status: 'completed', answer: 'Lotus Textiles leads with ₹76,700.00 invoiced this year.', created_at: '2026-10-02T14:20:00' },
  { id: 'ai-req-1', conversation_id: 'conv-1', mode: 'writing', prompt: 'Firm reminder for Acme Traders', status: 'failed', answer: null, created_at: '2026-10-01T10:00:00' },
];

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/ai/history': (query) => {
    const mode = query.get('mode');
    const limit = Number(query.get('limit')) || history.length;
    return history.filter((h) => !mode || h.mode === mode).slice(0, limit);
  },
};
