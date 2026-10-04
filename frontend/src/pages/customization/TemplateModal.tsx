import React, { useEffect, useState, useRef } from 'react';
import { Eye, Upload, X } from 'lucide-react';
import { organizationService } from '../../services/organizationService';
import { Modal } from '../../components/common/Modal';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { useToast } from '../../components/common/Toast';
import { customizationService } from '../../services/customizationService';
import { fieldErrors, toApiError } from '../../services/apiClient';
import { humanize } from '../../utils/format';
import {
  DOCUMENT_TYPES,
  TEMPLATE_LAYOUT_TYPES,
  type DocumentTemplate,
  type DocumentTemplateCreate,
  type DocumentTemplateUpdate,
  type DocumentType,
  type TemplateLayoutType,
} from '../../types/customization';
import { ColorField, Textarea, Toggle, nullable, str } from './shared';

interface TemplateModalProps {
  isOpen: boolean;
  /** When set, the modal edits this template; otherwise it creates a new one. */
  template: DocumentTemplate | null;
  onClose: () => void;
  onSaved: (saved: DocumentTemplate) => void;
  /** ``draft`` carries the current (possibly unsaved) form values to preview. */
  onPreview: (template: DocumentTemplate, draft?: DocumentTemplateUpdate) => void;
}

const FONT_OPTIONS = ['Helvetica', 'Arial', 'Georgia', 'Times New Roman', 'Courier New', 'Verdana', 'Roboto', 'Inter'];

interface FormState {
  name: string;
  document_type: DocumentType;
  layout_type: TemplateLayoutType;
  primary_color: string;
  accent_color: string;
  font_family: string;
  logo_url: string;
  header_text: string;
  footer_text: string;
  terms_and_conditions: string;
  custom_css: string;
  show_company_address: boolean;
  show_tax_summary: boolean;
  is_default: boolean;
  is_active: boolean;
}

const EMPTY_FORM: FormState = {
  name: '',
  document_type: 'invoice',
  layout_type: 'standard',
  primary_color: '#1F2937',
  accent_color: '#3B82F6',
  font_family: 'Helvetica',
  logo_url: '',
  header_text: '',
  footer_text: '',
  terms_and_conditions: '',
  custom_css: '',
  show_company_address: true,
  show_tax_summary: true,
  is_default: false,
  is_active: true,
};

function fromTemplate(t: DocumentTemplate): FormState {
  return {
    name: t.name,
    document_type: t.document_type,
    layout_type: t.layout_type,
    primary_color: t.primary_color,
    accent_color: t.accent_color,
    font_family: t.font_family,
    logo_url: str(t.logo_url),
    header_text: str(t.header_text),
    footer_text: str(t.footer_text),
    terms_and_conditions: str(t.terms_and_conditions),
    custom_css: str(t.custom_css),
    show_company_address: t.show_company_address,
    show_tax_summary: t.show_tax_summary,
    is_default: t.is_default,
    is_active: t.is_active,
  };
}

/**
 * Mirrors the backend preview rules (customization_service.resolve_preview_logo_src):
 * https:// URLs or same-origin paths. http:// is refused because the app's CSP
 * (img-src 'self' data: blob: https:) would block it, so it would never display.
 */
export function logoUrlError(raw: string): string | null {
  const value = raw.trim();
  if (!value) return null;
  if (/^https:\/\/[^\s"'<>`\\]+$/i.test(value)) return null;
  if (/^\/(?!\/)[^\s"'<>`\\]+$/.test(value) && !value.split('?')[0].split('/').includes('..')) return null;
  if (/^http:\/\//i.test(value)) return 'Use an https:// URL — insecure http:// images are blocked by the browser.';
  return 'Logo URL must be an https:// URL or a /uploads/... path';
}

export function TemplateModal({ isOpen, template, onClose, onSaved, onPreview }: TemplateModalProps) {
  const { showToast } = useToast();
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [isUploadingLogo, setIsUploadingLogo] = useState(false);
  const logoInputRef = useRef<HTMLInputElement | null>(null);

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setIsUploadingLogo(true);
      const res = await organizationService.uploadLogo(file);
      set('logo_url', res.logo_url);
      showToast('success', 'Logo uploaded', 'Logo was uploaded successfully.');
    } catch (err: any) {
      showToast('error', 'Upload failed', err?.response?.data?.detail || err.message || 'Could not upload logo.');
    } finally {
      setIsUploadingLogo(false);
      if (logoInputRef.current) logoInputRef.current.value = '';
    }
  };
  const isEdit = !!template;

  useEffect(() => {
    if (!isOpen) return;
    setForm(template ? fromTemplate(template) : EMPTY_FORM);
    setErrors({});
  }, [isOpen, template]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const validate = (): boolean => {
    const next: Record<string, string> = {};
    if (!form.name.trim()) next.name = 'Template name is required';
    if (!/^#[0-9a-fA-F]{6}$/.test(form.primary_color)) next.primary_color = 'Use a 6-digit hex colour, e.g. #1F2937';
    if (!/^#[0-9a-fA-F]{6}$/.test(form.accent_color)) next.accent_color = 'Use a 6-digit hex colour, e.g. #3B82F6';
    const logoError = logoUrlError(form.logo_url);
    if (logoError) next.logo_url = logoError;
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const buildPayload = (): DocumentTemplateCreate => ({
    document_type: form.document_type,
    name: form.name.trim(),
    layout_type: form.layout_type,
    is_default: form.is_default,
    is_active: form.is_active,
    primary_color: form.primary_color.trim(),
    accent_color: form.accent_color.trim(),
    font_family: form.font_family.trim() || 'Helvetica',
    logo_url: nullable(form.logo_url),
    header_text: nullable(form.header_text),
    footer_text: nullable(form.footer_text),
    terms_and_conditions: nullable(form.terms_and_conditions),
    custom_css: form.custom_css.trim() === '' ? null : form.custom_css,
    show_company_address: form.show_company_address,
    show_tax_summary: form.show_tax_summary,
  });

  /** Preview the current form values (including an unsaved logo) without saving. */
  const handlePreviewChanges = () => {
    if (!template) return;
    const logoError = logoUrlError(form.logo_url);
    if (logoError) {
      setErrors((prev) => ({ ...prev, logo_url: logoError }));
      return;
    }
    const { document_type: _omit, name: _name, is_default: _def, is_active: _act, ...draft } = buildPayload();
    onPreview(template, draft);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    setSaving(true);
    try {
      const payload = buildPayload();
      let saved: DocumentTemplate;
      if (template) {
        const { document_type: _omit, ...updateBody } = payload;
        saved = await customizationService.updateTemplate(template.id, updateBody);
        showToast('success', 'Template updated', `"${saved.name}" has been saved.`);
      } else {
        saved = await customizationService.createTemplate(payload);
        showToast('success', 'Template created', `"${saved.name}" is ready to use.`);
      }
      onSaved(saved);
    } catch (err: any) {
      const apiErr = toApiError(err);
      setErrors(fieldErrors(err));
      showToast('error', isEdit ? 'Could not update template' : 'Could not create template', apiErr.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEdit ? `Edit template: ${template?.name}` : 'New document template'}
      description={
        isEdit
          ? 'Changes apply to documents generated after you save. Preview shows your current, unsaved edits.'
          : 'Branding, layout and footer content used when rendering this document type.'
      }
      size="xl"
      footer={
        <>
          {isEdit && template && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handlePreviewChanges}
              leadingIcon={<Eye className="w-3.5 h-3.5" />}
              className="mr-auto"
            >
              Preview changes
            </Button>
          )}
          <Button type="button" variant="outline" size="sm" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" form="template-form" variant="primary" size="sm" isLoading={saving}>
            {isEdit ? 'Save changes' : 'Create template'}
          </Button>
        </>
      }
    >
      <form id="template-form" onSubmit={handleSubmit} className="space-y-5 max-h-[65vh] overflow-y-auto pr-1 -mr-1">
        {/* Identity */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-1">
            <Input
              label="Template name"
              required
              value={form.name}
              maxLength={100}
              placeholder="e.g. Standard GST invoice"
              onChange={(e) => set('name', e.target.value)}
              error={errors.name}
            />
          </div>
          <Select
            label="Document type"
            required
            value={form.document_type}
            disabled={isEdit}
            helperText={isEdit ? 'Cannot be changed after creation' : undefined}
            onChange={(e) => set('document_type', e.target.value as DocumentType)}
            options={DOCUMENT_TYPES.map((d) => ({ value: d, label: humanize(d) }))}
            error={errors.document_type}
          />
          <Select
            label="Layout"
            value={form.layout_type}
            onChange={(e) => set('layout_type', e.target.value as TemplateLayoutType)}
            options={TEMPLATE_LAYOUT_TYPES.map((l) => ({ value: l, label: humanize(l) }))}
            error={errors.layout_type}
          />
        </div>

        {/* Branding */}
        <fieldset className="space-y-3">
          <legend className="text-xs font-semibold uppercase tracking-wider text-slate-500">Branding</legend>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <ColorField label="Primary colour" value={form.primary_color} onChange={(v) => set('primary_color', v)} />
              {errors.primary_color && <p className="mt-1 text-xs text-rose-600 font-medium">{errors.primary_color}</p>}
            </div>
            <div>
              <ColorField label="Accent colour" value={form.accent_color} onChange={(v) => set('accent_color', v)} />
              {errors.accent_color && <p className="mt-1 text-xs text-rose-600 font-medium">{errors.accent_color}</p>}
            </div>
            <div>
              <Input
                label="Font family"
                list="template-font-options"
                value={form.font_family}
                maxLength={50}
                onChange={(e) => set('font_family', e.target.value)}
                error={errors.font_family}
              />
              <datalist id="template-font-options">
                {FONT_OPTIONS.map((f) => (
                  <option key={f} value={f} />
                ))}
              </datalist>
            </div>
          </div>
          <div className="space-y-2">
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <Input
                  label="Logo URL"
                  type="text"
                  value={form.logo_url}
                  maxLength={500}
                  placeholder="https://…/logo.png or upload a file"
                  onChange={(e) => set('logo_url', e.target.value)}
                  error={errors.logo_url}
                  helperText="https:// image URL, a /uploads/... path, or upload an image file. Leave blank to use the organization logo."
                />
              </div>
              <input
                ref={logoInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={handleLogoUpload}
                disabled={saving || isUploadingLogo}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mb-1"
                onClick={() => logoInputRef.current?.click()}
                disabled={saving || isUploadingLogo}
                isLoading={isUploadingLogo}
                leadingIcon={<Upload className="w-3.5 h-3.5" />}
              >
                Upload File
              </Button>
            </div>
            {form.logo_url && (
              <div className="flex items-center gap-3 p-2 border border-slate-200 rounded-lg bg-slate-50 w-fit">
                <img
                  src={form.logo_url}
                  alt="Logo preview"
                  className="max-h-8 max-w-[120px] object-contain"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none';
                  }}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-xs text-red-600 hover:text-red-700 h-7 px-2"
                  onClick={() => set('logo_url', '')}
                >
                  <X className="w-3.5 h-3.5 mr-1" /> Remove
                </Button>
              </div>
            )}
          </div>
        </fieldset>

        {/* Content */}
        <fieldset className="space-y-3">
          <legend className="text-xs font-semibold uppercase tracking-wider text-slate-500">Content</legend>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Header text"
              value={form.header_text}
              maxLength={255}
              placeholder="Shown above the document title"
              onChange={(e) => set('header_text', e.target.value)}
              error={errors.header_text}
            />
            <Input
              label="Footer text"
              value={form.footer_text}
              maxLength={255}
              placeholder="e.g. Thank you for your business"
              onChange={(e) => set('footer_text', e.target.value)}
              error={errors.footer_text}
            />
          </div>
          <Textarea
            label="Terms & conditions"
            rows={3}
            value={form.terms_and_conditions}
            placeholder="Payment terms, late fees, jurisdiction…"
            onChange={(e) => set('terms_and_conditions', e.target.value)}
            error={errors.terms_and_conditions}
          />
          <Textarea
            label="Custom CSS"
            code
            rows={6}
            spellCheck={false}
            value={form.custom_css}
            placeholder={'.header { font-size: 12px; }\ntable th { background: #f8fafc; }'}
            onChange={(e) => set('custom_css', e.target.value)}
            error={errors.custom_css}
            helperText="Appended to the document stylesheet. Available classes: .header, .accent, table, th, td."
          />
        </fieldset>

        {/* Options */}
        <fieldset className="space-y-2">
          <legend className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Options</legend>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            <Toggle
              label="Show company address"
              description="Print the customer's billing address block."
              checked={form.show_company_address}
              onChange={(v) => set('show_company_address', v)}
            />
            <Toggle
              label="Show tax summary"
              description="Include the GST / tax breakdown section."
              checked={form.show_tax_summary}
              onChange={(v) => set('show_tax_summary', v)}
            />
            <Toggle
              label="Default for this document type"
              description="Used automatically when no template is chosen."
              checked={form.is_default}
              onChange={(v) => set('is_default', v)}
            />
            <Toggle
              label="Active"
              description="Inactive templates are hidden from pickers."
              checked={form.is_active}
              onChange={(v) => set('is_active', v)}
            />
          </div>
        </fieldset>
      </form>
    </Modal>
  );
}
