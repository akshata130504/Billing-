// ---------------------------------------------------------------------------
// AI in Billing — mirrors backend/app/schemas/ai.py and models/ai.py
// ---------------------------------------------------------------------------

export type AIRequestMode = 'query' | 'draft' | 'writing';
export type AIRequestStatus = 'queued' | 'running' | 'completed' | 'failed';
/** The only action type the backend can currently draft and execute. */
export type AIActionType = 'credit_note';
export type AIActionDraftStatus =
  | 'proposed'
  | 'validated'
  | 'approved'
  | 'executed'
  | 'rejected'
  | 'expired';

export const AI_ACTION_TYPES: AIActionType[] = ['credit_note'];
export const AI_REQUEST_MODES: AIRequestMode[] = ['query', 'draft', 'writing'];

/** Writing purposes the backend renders templates for (anything else falls back to 'custom'). */
export type AIWritingPurpose = 'payment_reminder' | 'custom';
export type AIWritingTone = 'friendly' | 'firm' | 'neutral';

export const AI_WRITING_PURPOSES: AIWritingPurpose[] = ['payment_reminder', 'custom'];
export const AI_WRITING_TONES: AIWritingTone[] = ['neutral', 'friendly', 'firm'];

// ---------------------------------------------------------------------------
// Sources
// ---------------------------------------------------------------------------

export interface AISourceReference {
  source_type: string;
  source_id: string | null;
  label: string;
  snippet: string | null;
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export interface AIQueryRequest {
  prompt: string;
  conversation_id?: string | null;
}

export interface AIQueryResponse {
  request_id: string;
  conversation_id: string;
  answer: string;
  sources: AISourceReference[];
  data: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Drafts
// ---------------------------------------------------------------------------

export interface AIActionDraftLineIn {
  description: string;
  quantity: number;
  unit_price: number;
  tax_rate_pct: number;
}

export interface AIDraftRequest {
  prompt: string;
  action_type: AIActionType;
  customer_id: string;
  invoice_id?: string | null;
  reason?: string | null;
  lines: AIActionDraftLineIn[];
  conversation_id?: string | null;
}

export interface AIActionDraftPayload {
  customer_id: string;
  invoice_id: string | null;
  reason: string | null;
  lines: AIActionDraftLineIn[];
}

export interface AIActionDraft {
  id: string;
  request_id: string;
  action_type: AIActionType;
  proposed_payload: AIActionDraftPayload;
  status: AIActionDraftStatus;
  validation_errors: { errors?: string[] } | null;
  executed_entity_type: string | null;
  executed_entity_id: string | null;
  expires_at: string;
  created_at: string;
}

export interface AIDraftResponse {
  draft: AIActionDraft;
  preview: AIActionDraftPayload;
}

export interface AIDraftExecutedResult {
  credit_note_id?: string;
  credit_note_number?: string;
  total?: string;
  [key: string]: unknown;
}

export interface AIDraftConfirmResponse {
  draft: AIActionDraft;
  executed_result: AIDraftExecutedResult;
}

// ---------------------------------------------------------------------------
// Writing assistant
// ---------------------------------------------------------------------------

export interface AIWritingContext {
  customer_name?: string;
  invoice_number?: string;
  amount_due?: string;
  due_date?: string;
  [key: string]: string | undefined;
}

export interface AIWritingRequest {
  purpose: AIWritingPurpose | string;
  tone: AIWritingTone | string;
  context: AIWritingContext;
  instructions?: string | null;
}

export interface AIWritingResponse {
  request_id: string;
  subject: string | null;
  body: string;
}

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------

export interface AIHistoryItem {
  id: string;
  conversation_id: string;
  mode: AIRequestMode;
  prompt: string;
  status: AIRequestStatus;
  answer: string | null;
  created_at: string;
}

export interface AIHistoryParams {
  mode?: AIRequestMode;
  limit?: number;
}
