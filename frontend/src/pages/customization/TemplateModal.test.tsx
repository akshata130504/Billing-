import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TemplateModal, logoUrlError } from './TemplateModal';
import { TemplatePreviewModal } from './TemplatePreviewModal';
import { customizationService } from '../../services/customizationService';
import type { DocumentTemplate } from '../../types/customization';

vi.mock('../../services/customizationService', () => ({
  customizationService: {
    previewTemplate: vi.fn(),
    updateTemplate: vi.fn(),
    createTemplate: vi.fn(),
  },
}));

vi.mock('../../services/organizationService', () => ({
  organizationService: { uploadLogo: vi.fn() },
}));

vi.mock('../../components/common/Toast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));

const mocked = vi.mocked(customizationService);

const template: DocumentTemplate = {
  id: 'tmpl-1',
  organization_id: 'org-1',
  document_type: 'invoice',
  name: 'Standard',
  layout_type: 'standard',
  is_default: false,
  is_active: true,
  primary_color: '#1F2937',
  accent_color: '#3B82F6',
  font_family: 'Helvetica',
  logo_url: 'https://cdn.example.com/old.png',
  header_text: null,
  footer_text: null,
  terms_and_conditions: null,
  custom_css: null,
  show_company_address: true,
  show_tax_summary: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('logoUrlError', () => {
  it('accepts https URLs and same-origin paths', () => {
    expect(logoUrlError('')).toBeNull();
    expect(logoUrlError('https://cdn.example.com/logo.png')).toBeNull();
    expect(logoUrlError('/uploads/logos/a.png')).toBeNull();
    expect(logoUrlError('/logos/a.png')).toBeNull();
  });

  it('rejects http, protocol-relative, traversal and script URLs', () => {
    expect(logoUrlError('http://cdn.example.com/logo.png')).toMatch(/https/);
    expect(logoUrlError('//evil.example.com/a.png')).not.toBeNull();
    expect(logoUrlError('/uploads/../secret.png')).not.toBeNull();
    expect(logoUrlError('javascript:alert(1)')).not.toBeNull();
  });
});

describe('<TemplateModal /> preview of unsaved changes', () => {
  beforeEach(() => vi.clearAllMocks());

  it('passes the current (unsaved) logo URL to onPreview without saving', async () => {
    const onPreview = vi.fn();
    render(
      <TemplateModal isOpen template={template} onClose={vi.fn()} onSaved={vi.fn()} onPreview={onPreview} />
    );

    const logoInput = await screen.findByDisplayValue('https://cdn.example.com/old.png');
    fireEvent.change(logoInput, { target: { value: '/uploads/logos/new.png' } });
    fireEvent.click(screen.getByRole('button', { name: /Preview changes/ }));

    expect(onPreview).toHaveBeenCalledTimes(1);
    const [passedTemplate, draft] = onPreview.mock.calls[0];
    expect(passedTemplate.id).toBe('tmpl-1');
    expect(draft.logo_url).toBe('/uploads/logos/new.png');
    expect(draft).not.toHaveProperty('document_type');
    expect(mocked.updateTemplate).not.toHaveBeenCalled();
  });
});

describe('<TemplatePreviewModal />', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sends the draft values to the preview endpoint', async () => {
    mocked.previewTemplate.mockResolvedValue({
      template_id: 'tmpl-1',
      document_type: 'invoice',
      layout_type: 'standard',
      rendered_html: '<html><body><img src="/uploads/logos/new.png" /></body></html>',
      rendered_text: 'text',
    });
    const draft = { logo_url: '/uploads/logos/new.png' };
    render(<TemplatePreviewModal template={template} draft={draft} onClose={vi.fn()} />);

    await waitFor(() => expect(mocked.previewTemplate).toHaveBeenCalledWith('tmpl-1', draft));
    expect(screen.getByText(/unsaved changes/i)).toBeInTheDocument();
  });

  it('previews the saved version when no draft is given', async () => {
    mocked.previewTemplate.mockResolvedValue({
      template_id: 'tmpl-1',
      document_type: 'invoice',
      layout_type: 'standard',
      rendered_html: '<html></html>',
      rendered_text: '',
    });
    render(<TemplatePreviewModal template={template} onClose={vi.fn()} />);
    await waitFor(() => expect(mocked.previewTemplate).toHaveBeenCalledWith('tmpl-1'));
  });
});
