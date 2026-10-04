import { useEffect, useState } from 'react';
import { Code2, FileText, RefreshCw } from 'lucide-react';
import { Modal } from '../../components/common/Modal';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { customizationService } from '../../services/customizationService';
import { toApiError } from '../../services/apiClient';
import { humanize } from '../../utils/format';
import { cn } from '../../utils/cn';
import type { DocumentTemplate, DocumentTemplatePreview, DocumentTemplateUpdate } from '../../types/customization';

interface TemplatePreviewModalProps {
  template: DocumentTemplate | null;
  /**
   * Unsaved editor values to preview instead of the stored template (e.g. a logo
   * that was just typed or uploaded). Omit to preview the saved version.
   */
  draft?: DocumentTemplateUpdate | null;
  onClose: () => void;
}

type PreviewMode = 'html' | 'text';

/**
 * Renders the backend's sample-data preview for a template. The HTML is placed in a
 * sandboxed iframe (no scripts, no same-origin) via srcdoc so custom CSS cannot escape.
 */
export function TemplatePreviewModal({ template, draft, onClose }: TemplatePreviewModalProps) {
  const [preview, setPreview] = useState<DocumentTemplatePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<PreviewMode>('html');

  const templateId = template?.id ?? null;

  const load = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = draft
        ? await customizationService.previewTemplate(id, draft)
        : await customizationService.previewTemplate(id);
      setPreview(data);
    } catch (err: any) {
      setError(toApiError(err).message || 'Failed to render preview');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!templateId) {
      setPreview(null);
      setError(null);
      return;
    }
    setMode('html');
    void load(templateId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateId, draft]);

  return (
    <Modal
      isOpen={!!template}
      onClose={onClose}
      title={template ? `Preview: ${template.name}` : 'Preview'}
      description={
        draft
          ? 'Previewing your unsaved changes with sample data. Save the template to apply them to documents.'
          : 'Rendered with sample data. Real documents use the customer and line items of each record.'
      }
      size="xl"
      footer={
        <>
          {templateId && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => void load(templateId)}
              isLoading={loading}
              leadingIcon={<RefreshCw className="w-3.5 h-3.5" />}
            >
              Re-render
            </Button>
          )}
          <Button variant="primary" size="sm" onClick={onClose}>
            Done
          </Button>
        </>
      }
    >
      {template && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Badge variant="primary" size="sm">
                {humanize(template.document_type)}
              </Badge>
              <Badge variant="neutral" size="sm">
                {humanize(draft?.layout_type ?? template.layout_type)} layout
              </Badge>
              <span className="text-xs text-slate-500 font-mono">{draft?.font_family ?? template.font_family}</span>
            </div>
            <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5" role="tablist">
              {(
                [
                  { key: 'html', label: 'HTML', icon: Code2 },
                  { key: 'text', label: 'Plain text', icon: FileText },
                ] as { key: PreviewMode; label: string; icon: typeof Code2 }[]
              ).map((opt) => {
                const Icon = opt.icon;
                const active = mode === opt.key;
                return (
                  <button
                    key={opt.key}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => setMode(opt.key)}
                    className={cn(
                      'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors',
                      active ? 'bg-white text-brand-700 shadow-subtle' : 'text-slate-600 hover:text-slate-900'
                    )}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>

          {loading && !preview ? (
            <LoadingState message="Rendering preview..." />
          ) : error ? (
            <ErrorState title="Preview failed" message={error} onRetry={() => void load(template.id)} />
          ) : preview ? (
            mode === 'html' ? (
              <div className="rounded-xl border border-slate-200 bg-slate-100 p-3">
                <iframe
                  title={`Preview of ${template.name}`}
                  sandbox="allow-same-origin"
                  srcDoc={preview.rendered_html}
                  className="w-full h-[520px] bg-white rounded-lg border border-slate-200 shadow-card"
                />
              </div>
            ) : (
              <pre className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs font-mono text-slate-800 whitespace-pre-wrap leading-relaxed max-h-[520px] overflow-auto">
                {preview.rendered_text}
              </pre>
            )
          ) : null}
        </div>
      )}
    </Modal>
  );
}
