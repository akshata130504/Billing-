import React, { useEffect, useMemo, useState } from 'react';
import { Pencil, Plus, Search, Tags, Trash2 } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Input } from '../../components/common/Input';
import { Modal } from '../../components/common/Modal';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { EmptyState } from '../../components/common/EmptyState';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { useToast } from '../../components/common/Toast';
import { customizationService } from '../../services/customizationService';
import { fieldErrors, toApiError } from '../../services/apiClient';
import { formatDate } from '../../utils/format';
import type { ReportingTag, ReportingTagCreate } from '../../types/customization';
import { ReadOnlyNotice, TabHeader, Textarea, Toggle, nullable, str, type Resource } from './shared';

interface ReportingTagsTabProps {
  resource: Resource<ReportingTag>;
  canManage: boolean;
}

interface TagForm {
  name: string;
  code: string;
  description: string;
  is_active: boolean;
}

const EMPTY_TAG: TagForm = { name: '', code: '', description: '', is_active: true };

/** Deterministic swatch colour derived from the tag code so tags are visually distinguishable. */
const SWATCHES = ['bg-sky-500', 'bg-emerald-500', 'bg-amber-500', 'bg-rose-500', 'bg-violet-500', 'bg-teal-500', 'bg-orange-500', 'bg-indigo-500'];
function swatchFor(code: string): string {
  let hash = 0;
  for (let i = 0; i < code.length; i += 1) hash = (hash * 31 + code.charCodeAt(i)) >>> 0;
  return SWATCHES[hash % SWATCHES.length];
}

export function ReportingTagsTab({ resource, canManage }: ReportingTagsTabProps) {
  const { showToast } = useToast();
  const { items, loading, error, reload } = resource;

  const [search, setSearch] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ReportingTag | null>(null);
  const [form, setForm] = useState<TagForm>(EMPTY_TAG);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<ReportingTag | null>(null);
  const [deletingBusy, setDeletingBusy] = useState(false);

  useEffect(() => {
    if (!modalOpen) return;
    setForm(
      editing
        ? { name: editing.name, code: editing.code, description: str(editing.description), is_active: editing.is_active }
        : EMPTY_TAG
    );
    setErrors({});
  }, [modalOpen, editing]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (t) => t.name.toLowerCase().includes(q) || t.code.toLowerCase().includes(q) || (t.description ?? '').toLowerCase().includes(q)
    );
  }, [items, search]);

  const openCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };
  const openEdit = (t: ReportingTag) => {
    setEditing(t);
    setModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const next: Record<string, string> = {};
    if (!form.name.trim()) next.name = 'Name is required';
    if (!form.code.trim()) next.code = 'Code is required';
    else if (!/^[A-Za-z0-9_-]+$/.test(form.code.trim())) next.code = 'Use letters, numbers, dashes or underscores only';
    setErrors(next);
    if (Object.keys(next).length > 0) return;

    setSaving(true);
    try {
      const payload: ReportingTagCreate = {
        name: form.name.trim(),
        code: form.code.trim().toUpperCase(),
        description: nullable(form.description),
        is_active: form.is_active,
      };
      if (editing) {
        const saved = await customizationService.updateReportingTag(editing.id, payload);
        showToast('success', 'Tag updated', `"${saved.name}" has been saved.`);
      } else {
        const saved = await customizationService.createReportingTag(payload);
        showToast('success', 'Tag created', `"${saved.name}" (${saved.code}) is ready to use.`);
      }
      setModalOpen(false);
      await reload();
    } catch (err: any) {
      setErrors(fieldErrors(err));
      showToast('error', editing ? 'Could not update tag' : 'Could not create tag', toApiError(err).message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleting) return;
    setDeletingBusy(true);
    try {
      await customizationService.deleteReportingTag(deleting.id);
      showToast('success', 'Tag deleted', `"${deleting.name}" has been removed.`);
      setDeleting(null);
      await reload();
    } catch (err: any) {
      showToast('error', 'Could not delete tag', toApiError(err).message);
    } finally {
      setDeletingBusy(false);
    }
  };

  const activeCount = items.filter((t) => t.is_active).length;

  return (
    <div className="space-y-5">
      <TabHeader
        title="Reporting tags"
        description="Tags are an extra dimension for slicing revenue and expenses in reports — by region, business unit, campaign or cost centre — without changing your chart of accounts."
        actions={
          canManage ? (
            <Button size="sm" onClick={openCreate} leadingIcon={<Plus className="w-4 h-4" />}>
              New tag
            </Button>
          ) : undefined
        }
      />

      {!canManage && <ReadOnlyNotice what="reporting tags" />}

      {loading ? (
        <LoadingState message="Loading reporting tags..." />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Tags className="w-6 h-6 stroke-1" />}
          title="No reporting tags yet"
          description="Create tags such as REGION-SOUTH or PROJECT-ALPHA and apply them to transactions to group them in reports."
          action={
            canManage ? (
              <Button size="sm" onClick={openCreate} leadingIcon={<Plus className="w-4 h-4" />}>
                Create tag
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="search"
                placeholder="Search tags..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 focus:bg-white transition-colors"
              />
            </div>
            <p className="text-xs text-slate-500">
              <span className="font-semibold text-slate-700">{activeCount}</span> active of{' '}
              <span className="font-semibold text-slate-700">{items.length}</span> tags
            </p>
          </div>

          {filtered.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-sm font-medium text-slate-700">No tags match "{search}"</p>
              <p className="text-xs text-slate-400 mt-0.5">Try a different name or code.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm min-w-[640px]">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/80 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    <th className="py-3.5 px-4">Tag</th>
                    <th className="py-3.5 px-4">Code</th>
                    <th className="py-3.5 px-4">Description</th>
                    <th className="py-3.5 px-4">Status</th>
                    <th className="py-3.5 px-4">Created</th>
                    {canManage && <th className="py-3.5 px-4 text-right">Actions</th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filtered.map((t) => (
                    <tr key={t.id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-2.5">
                          <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${swatchFor(t.code)}`} aria-hidden="true" />
                          <span className="font-medium text-slate-900">{t.name}</span>
                        </div>
                      </td>
                      <td className="py-3.5 px-4">
                        <code className="text-xs font-mono bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded">{t.code}</code>
                      </td>
                      <td className="py-3.5 px-4 text-slate-600 max-w-md">
                        {t.description ? (
                          <span className="line-clamp-2">{t.description}</span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="py-3.5 px-4">
                        <Badge variant={t.is_active ? 'success' : 'neutral'} size="sm" dot>
                          {t.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </td>
                      <td className="py-3.5 px-4 text-slate-500 text-xs">{formatDate(t.created_at)}</td>
                      {canManage && (
                        <td className="py-3.5 px-4 text-right">
                          <div className="inline-flex items-center gap-1">
                            <Button variant="ghost" size="sm" className="!px-2" onClick={() => openEdit(t)} aria-label={`Edit ${t.name}`}>
                              <Pencil className="w-3.5 h-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="!px-2 text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                              onClick={() => setDeleting(t)}
                              aria-label={`Delete ${t.name}`}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </Button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? `Edit tag: ${editing.name}` : 'New reporting tag'}
        description="Codes are stored in uppercase and must be unique within your organization."
        size="md"
        footer={
          <>
            <Button variant="outline" size="sm" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="reporting-tag-form" size="sm" isLoading={saving}>
              {editing ? 'Save changes' : 'Create tag'}
            </Button>
          </>
        }
      >
        <form id="reporting-tag-form" onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-5 gap-4">
            <div className="sm:col-span-3">
              <Input
                label="Name"
                required
                maxLength={100}
                value={form.name}
                placeholder="e.g. South region"
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                error={errors.name}
              />
            </div>
            <div className="sm:col-span-2">
              <Input
                label="Code"
                required
                maxLength={50}
                value={form.code}
                placeholder="REGION-SOUTH"
                className="font-mono uppercase"
                onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
                error={errors.code}
              />
            </div>
          </div>
          <Textarea
            label="Description"
            rows={2}
            maxLength={255}
            value={form.description}
            placeholder="What this tag groups, and who should use it"
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            error={errors.description}
          />
          <Toggle
            label="Active"
            description="Inactive tags stay on historical records but cannot be applied to new ones."
            checked={form.is_active}
            onChange={(v) => setForm((f) => ({ ...f, is_active: v }))}
          />
        </form>
      </Modal>

      <ConfirmDialog
        isOpen={!!deleting}
        onClose={() => setDeleting(null)}
        onConfirm={handleDelete}
        title="Delete reporting tag?"
        description={
          deleting
            ? `"${deleting.name}" (${deleting.code}) will be removed. Consider marking it inactive instead if it has been applied to past transactions.`
            : undefined
        }
        confirmLabel="Delete tag"
        variant="danger"
        isLoading={deletingBusy}
      />
    </div>
  );
}
