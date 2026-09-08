// ---------------------------------------------------------------------------
// Customization module types — mirrors backend/app/schemas/customization.py
// ---------------------------------------------------------------------------

export type DocumentType =
  | 'invoice'
  | 'quote'
  | 'credit_note'
  | 'payment_receipt'
  | 'customer_statement'
  | 'delivery_challan';

export type TemplateLayoutType = 'spreadsheet' | 'standard' | 'modern';

export const DOCUMENT_TYPES: DocumentType[] = [
  'invoice',
  'quote',
  'credit_note',
  'payment_receipt',
  'customer_statement',
  'delivery_challan',
];

export const TEMPLATE_LAYOUT_TYPES: TemplateLayoutType[] = ['standard', 'modern', 'spreadsheet'];

// ---------------------------------------------------------------------------
// Document templates
// ---------------------------------------------------------------------------

export interface DocumentTemplate {
  id: string;
  organization_id: string;
  document_type: DocumentType;
  name: string;
  layout_type: TemplateLayoutType;
  is_default: boolean;
  is_active: boolean;
  primary_color: string;
  accent_color: string;
  font_family: string;
  logo_url: string | null;
  header_text: string | null;
  footer_text: string | null;
  terms_and_conditions: string | null;
  custom_css: string | null;
  show_company_address: boolean;
  show_tax_summary: boolean;
  created_at: string;
  updated_at: string;
}

export interface DocumentTemplateCreate {
  document_type: DocumentType;
  name: string;
  layout_type: TemplateLayoutType;
  is_default: boolean;
  is_active: boolean;
  primary_color: string;
  accent_color: string;
  font_family: string;
  logo_url?: string | null;
  header_text?: string | null;
  footer_text?: string | null;
  terms_and_conditions?: string | null;
  custom_css?: string | null;
  show_company_address: boolean;
  show_tax_summary: boolean;
}

/** Note: document_type cannot be changed after creation (not part of the update schema). */
export type DocumentTemplateUpdate = Partial<Omit<DocumentTemplateCreate, 'document_type'>>;

export interface DocumentTemplatePreview {
  template_id: string | null;
  document_type: string;
  layout_type: string;
  rendered_html: string;
  rendered_text: string;
}

// ---------------------------------------------------------------------------
// Reporting tags
// ---------------------------------------------------------------------------

export interface ReportingTag {
  id: string;
  organization_id: string;
  name: string;
  code: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ReportingTagCreate {
  name: string;
  code: string;
  description?: string | null;
  is_active: boolean;
}

export type ReportingTagUpdate = Partial<ReportingTagCreate>;

// ---------------------------------------------------------------------------
// Transaction number series
// ---------------------------------------------------------------------------

export interface NumberSeries {
  id: string;
  organization_id: string;
  module: string;
  name: string;
  prefix: string;
  starting_number: number;
  padding: number;
  is_default: boolean;
  is_active: boolean;
  suffix: string | null;
  notes: string | null;
  /** The next number that will be issued from this series. */
  current_number: number;
  created_at: string;
  updated_at: string;
}

export interface NumberSeriesCreate {
  module: string;
  name: string;
  prefix: string;
  starting_number: number;
  padding: number;
  is_default: boolean;
  is_active: boolean;
  suffix?: string | null;
  notes?: string | null;
}

/** Note: module cannot be changed after creation (not part of the update schema). */
export type NumberSeriesUpdate = Partial<Omit<NumberSeriesCreate, 'module'>>;

export interface NumberSeriesPreviewRequest {
  prefix: string;
  starting_number: number;
  padding: number;
  suffix?: string | null;
}

export interface NumberSeriesPreviewResponse {
  sample_number: string;
  explanation: string;
}

// ---------------------------------------------------------------------------
// Web tabs
// ---------------------------------------------------------------------------

export interface WebTab {
  id: string;
  organization_id: string;
  tab_name: string;
  url: string;
  is_active: boolean;
  allowed_roles: string[];
  created_at: string;
  updated_at: string;
}

export interface WebTabCreate {
  tab_name: string;
  url: string;
  is_active: boolean;
  allowed_roles: string[];
}

export type WebTabUpdate = Partial<WebTabCreate>;

// ---------------------------------------------------------------------------
// Outbound webhook deliveries
// ---------------------------------------------------------------------------

export type WebhookDeliveryStatus = 'pending' | 'delivered' | 'failed';

export interface WebhookDelivery {
  id: string;
  organization_id: string;
  rule_id: string | null;
  destination_url: string;
  event_type: string;
  payload: Record<string, unknown>;
  status: WebhookDeliveryStatus | string;
  response_status_code: number | null;
  response_body: string | null;
  error_message: string | null;
  attempt_count: number;
  delivered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface WebhookDeliveryListParams {
  status?: WebhookDeliveryStatus;
}

export interface DeleteResponse {
  status: string;
  message: string;
}
