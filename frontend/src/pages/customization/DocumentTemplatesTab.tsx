import { useMemo, useState } from 'react';
import { Eye, LayoutTemplate, Pencil, Plus, Star, Trash2 } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Select } from '../../components/common/Select';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { EmptyState } from '../../components/common/EmptyState';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { useToast } from '../../components/common/Toast';
import { customizationService } from '../../services/customizationService';
import { toApiError } from '../../services/apiClient';
import { formatRelative, humanize } from '../../utils/format';
import { cn } from '../../utils/cn';
import { DOCUMENT_TYPES, type DocumentTemplate, type DocumentTemplateUpdate, type DocumentType } from '../../types/customization';
import { TemplateModal } from './TemplateModal';
import { TemplatePreviewModal } from './TemplatePreviewModal';
import { ReadOnlyNotice, TabHeader, type Resource } from './shared';

interface DocumentTemplatesTabProps {
  resource: Resource<DocumentTemplate>;
  canManage: boolean;
}

export function DocumentTemplatesTab({ resource, canManage }: DocumentTemplatesTabProps) {
  const { showToast } = useToast();
  const { items, loading, error, reload } = resource;

  const [typeFilter, setTypeFilter] = useState<'all' | DocumentType>('all');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<DocumentTemplate | null>(null);
  const [previewing, setPreviewing] = useState<DocumentTemplate | null>(null);
  // Unsaved editor values to preview (null = preview the saved template).
  const [previewDraft, setPreviewDraft] = useState<DocumentTemplateUpdate | null>(null);
  const [deleting, setDeleting] = useState<DocumentTemplate | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const filtered = useMemo(
    () => (typeFilter === 'all' ? items : items.filter((t) => t.document_type === typeFilter)),
    [items, typeFilter]
  );

  const openCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };
  const openEdit = (t: DocumentTemplate) => {
    setEditing(t);
    setModalOpen(true);
  };

  const handleSetDefault = async (t: DocumentTemplate) => {
    setBusyId(t.id);
    try {
      await customizationService.updateTemplate(t.id, { is_default: true });
      showToast('success', 'Default template updated', `"${t.name}" is now the default for ${humanize(t.document_type).toLowerCase()}s.`);
      await reload();
    } catch (err: any) {
      showToast('error', 'Could not set default', toApiError(err).message);
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async () => {
    if (!deleting) return;
    setBusyId(deleting.id);
    try {
      await customizationService.deleteTemplate(deleting.id);
      showToast('success', 'Template deleted', `"${deleting.name}" has been removed.`);
      setDeleting(null);
      await reload();
    } catch (err: any) {
      showToast('error', 'Could not delete template', toApiError(err).message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-5">
      <TabHeader
        title="Document templates"
        description="Control how invoices, quotes, credit notes and receipts look when rendered as PDF or email. One template per document type can be the default."
        actions={
          <>
            <Select
              aria-label="Filter by document type"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as 'all' | DocumentType)}
              className="!py-1.5 text-xs w-44"
              options={[
                { value: 'all', label: 'All document types' },
                ...DOCUMENT_TYPES.map((d) => ({ value: d, label: humanize(d) })),
              ]}
            />
            {canManage && (
              <Button size="sm" onClick={openCreate} leadingIcon={<Plus className="w-4 h-4" />}>
                New template
              </Button>
            )}
          </>
        }
      />

      {!canManage && <ReadOnlyNotice what="document templates" />}

      {loading ? (
        <LoadingState message="Loading templates..." />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<LayoutTemplate className="w-6 h-6 stroke-1" />}
          title={typeFilter === 'all' ? 'No document templates yet' : `No ${humanize(typeFilter).toLowerCase()} templates`}
          description={
            typeFilter === 'all'
              ? 'Documents are rendered with the built-in layout until you add a template. Create one to apply your brand colours, fonts and footer text.'
              : 'Clear the filter to see templates for other document types, or create one for this type.'
          }
          action={
            canManage ? (
              <Button size="sm" onClick={openCreate} leadingIcon={<Plus className="w-4 h-4" />}>
                Create template
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((t) => {
            const busy = busyId === t.id;
            return (
              <div
                key={t.id}
                className={cn(
                  'bg-white rounded-xl border shadow-card overflow-hidden flex flex-col transition-all hover:shadow-elevated',
                  t.is_default ? 'border-brand-200' : 'border-slate-200/90',
                  !t.is_active && 'opacity-70'
                )}
              >
                {/* Swatch band */}
                <div className="h-2 flex">
                  <span className="flex-1" style={{ backgroundColor: t.primary_color }} />
                  <span className="w-1/3" style={{ backgroundColor: t.accent_color }} />
                </div>

                <div className="p-5 flex-1 space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="text-sm font-semibold text-slate-900 truncate" title={t.name}>
                        {t.name}
                      </h3>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {humanize(t.layout_type)} layout · {t.font_family}
                      </p>
                    </div>
                    {t.is_default && (
                      <Badge variant="primary" size="sm" dot>
                        Default
                      </Badge>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge variant="neutral" size="sm">
                      {humanize(t.document_type)}
                    </Badge>
                    {!t.is_active && (
                      <Badge variant="warning" size="sm">
                        Inactive
                      </Badge>
                    )}
                    {t.show_tax_summary && (
                      <Badge variant="info" size="sm">
                        Tax summary
                      </Badge>
                    )}
                  </div>

                  <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                    <dt className="text-slate-500">Primary</dt>
                    <dd className="flex items-center gap-1.5 font-mono text-slate-700">
                      <span className="w-3 h-3 rounded-sm border border-slate-200" style={{ backgroundColor: t.primary_color }} />
                      {t.primary_color}
                    </dd>
                    <dt className="text-slate-500">Accent</dt>
                    <dd className="flex items-center gap-1.5 font-mono text-slate-700">
                      <span className="w-3 h-3 rounded-sm border border-slate-200" style={{ backgroundColor: t.accent_color }} />
                      {t.accent_color}
                    </dd>
                    <dt className="text-slate-500">Header</dt>
                    <dd className="text-slate-700 truncate" title={t.header_text ?? undefined}>
                      {t.header_text || <span className="text-slate-400">—</span>}
                    </dd>
                    <dt className="text-slate-500">Custom CSS</dt>
                    <dd className="text-slate-700">{t.custom_css ? `${t.custom_css.split('\n').length} lines` : <span className="text-slate-400">None</span>}</dd>
                  </dl>
                </div>

                <div className="px-5 py-3 bg-slate-50/75 border-t border-slate-100 flex items-center justify-between gap-2 text-xs">
                  <span className="text-slate-400 truncate">Updated {formatRelative(t.updated_at)}</span>
                  <div className="flex items-center gap-1 shrink-0">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setPreviewDraft(null);
                        setPreviewing(t);
                      }}
                      leadingIcon={<Eye className="w-3.5 h-3.5" />}
                      aria-label={`Preview ${t.name}`}
                    >
                      Preview
                    </Button>
                    {canManage && (
                      <>
                        {!t.is_default && (
                          <Button
                            variant="ghost"
                            size="sm"
                            isLoading={busy}
                            onClick={() => void handleSetDefault(t)}
                            leadingIcon={<Star className="w-3.5 h-3.5" />}
                            aria-label={`Set ${t.name} as default`}
                          >
                            Default
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEdit(t)}
                          aria-label={`Edit ${t.name}`}
                          className="!px-2"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleting(t)}
                          aria-label={`Delete ${t.name}`}
                          className="!px-2 text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <TemplateModal
        isOpen={modalOpen}
        template={editing}
        onClose={() => setModalOpen(false)}
        onSaved={() => {
          setModalOpen(false);
          void reload();
        }}
        onPreview={(t, draft) => {
          setPreviewDraft(draft ?? null);
          setPreviewing(t);
        }}
      />

      <TemplatePreviewModal
        template={previewing}
        draft={previewDraft}
        onClose={() => {
          setPreviewing(null);
          setPreviewDraft(null);
        }}
      />

      <ConfirmDialog
        isOpen={!!deleting}
        onClose={() => setDeleting(null)}
        onConfirm={handleDelete}
        title="Delete template?"
        description={
          deleting
            ? `"${deleting.name}" will be removed permanently. Documents already generated are not affected${
                deleting.is_default ? ', but this document type will fall back to the built-in layout' : ''
              }.`
            : undefined
        }
        confirmLabel="Delete template"
        variant="danger"
        isLoading={!!deleting && busyId === deleting.id}
      />
    </div>
  );
}
