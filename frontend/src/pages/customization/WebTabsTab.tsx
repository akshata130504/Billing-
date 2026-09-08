import React, { useEffect, useState } from 'react';
import { AppWindow, ExternalLink, Info, Pencil, Plus, Trash2 } from 'lucide-react';
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
import { ROLE_LABELS, formatDate } from '../../utils/format';
import { cn } from '../../utils/cn';
import type { WebTab, WebTabCreate } from '../../types/customization';
import { ReadOnlyNotice, TabHeader, Toggle, type Resource } from './shared';

interface WebTabsTabProps {
  resource: Resource<WebTab>;
  canManage: boolean;
}

const ALL_ROLES = ['owner', 'admin', 'finance', 'viewer'] as const;

interface WebTabForm {
  tab_name: string;
  url: string;
  allowed_roles: string[];
  is_active: boolean;
}

const EMPTY_TAB: WebTabForm = { tab_name: '', url: '', allowed_roles: [...ALL_ROLES], is_active: true };

function hostOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

export function WebTabsTab({ resource, canManage }: WebTabsTabProps) {
  const { showToast } = useToast();
  const { items, loading, error, reload } = resource;

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<WebTab | null>(null);
  const [form, setForm] = useState<WebTabForm>(EMPTY_TAB);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<WebTab | null>(null);
  const [deletingBusy, setDeletingBusy] = useState(false);

  useEffect(() => {
    if (!modalOpen) return;
    setForm(
      editing
        ? { tab_name: editing.tab_name, url: editing.url, allowed_roles: [...editing.allowed_roles], is_active: editing.is_active }
        : EMPTY_TAB
    );
    setErrors({});
  }, [modalOpen, editing]);

  const openCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };
  const openEdit = (t: WebTab) => {
    setEditing(t);
    setModalOpen(true);
  };

  const toggleRole = (role: string) =>
    setForm((f) => ({
      ...f,
      allowed_roles: f.allowed_roles.includes(role) ? f.allowed_roles.filter((r) => r !== role) : [...f.allowed_roles, role],
    }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const next: Record<string, string> = {};
    if (!form.tab_name.trim()) next.tab_name = 'Label is required';
    const url = form.url.trim();
    if (!url) next.url = 'URL is required';
    else if (!/^https?:\/\/\S+$/i.test(url)) next.url = 'Enter a full URL starting with http:// or https://';
    if (form.allowed_roles.length === 0) next.allowed_roles = 'Pick at least one role that can see this tab';
    setErrors(next);
    if (Object.keys(next).length > 0) return;

    setSaving(true);
    try {
      const payload: WebTabCreate = {
        tab_name: form.tab_name.trim(),
        url,
        allowed_roles: ALL_ROLES.filter((r) => form.allowed_roles.includes(r)),
        is_active: form.is_active,
      };
      if (editing) {
        const saved = await customizationService.updateWebTab(editing.id, payload);
        showToast('success', 'Web tab updated', `"${saved.tab_name}" has been saved.`);
      } else {
        const saved = await customizationService.createWebTab(payload);
        showToast('success', 'Web tab created', `"${saved.tab_name}" now links to ${hostOf(saved.url)}.`);
      }
      setModalOpen(false);
      await reload();
    } catch (err: any) {
      setErrors(fieldErrors(err));
      showToast('error', editing ? 'Could not update web tab' : 'Could not create web tab', toApiError(err).message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleting) return;
    setDeletingBusy(true);
    try {
      await customizationService.deleteWebTab(deleting.id);
      showToast('success', 'Web tab deleted', `"${deleting.tab_name}" has been removed.`);
      setDeleting(null);
      await reload();
    } catch (err: any) {
      showToast('error', 'Could not delete web tab', toApiError(err).message);
    } finally {
      setDeletingBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <TabHeader
        title="Web tabs"
        description="Add links to external tools your team uses alongside billing — a CRM, a BI dashboard, a support desk. Web tabs appear as custom links in the navigation for the roles you allow."
        actions={
          canManage ? (
            <Button size="sm" onClick={openCreate} leadingIcon={<Plus className="w-4 h-4" />}>
              New web tab
            </Button>
          ) : undefined
        }
      />

      <div className="flex items-start gap-2.5 rounded-lg border border-blue-100 bg-blue-50/60 px-3.5 py-2.5 text-xs text-slate-700">
        <Info className="w-3.5 h-3.5 mt-0.5 shrink-0 text-brand-600" />
        <span>
          Web tabs open in a new browser tab and never share your billing session with the destination. Only members
          whose role is in the allowed list will see the link.
        </span>
      </div>

      {!canManage && <ReadOnlyNotice what="web tabs" />}

      {loading ? (
        <LoadingState message="Loading web tabs..." />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<AppWindow className="w-6 h-6 stroke-1" />}
          title="No web tabs configured"
          description="Link the tools your team already uses so they are one click away from invoices and customers."
          action={
            canManage ? (
              <Button size="sm" onClick={openCreate} leadingIcon={<Plus className="w-4 h-4" />}>
                Add web tab
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm min-w-[720px]">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/80 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                  <th className="py-3.5 px-4">Label</th>
                  <th className="py-3.5 px-4">Destination</th>
                  <th className="py-3.5 px-4">Visible to</th>
                  <th className="py-3.5 px-4">Status</th>
                  <th className="py-3.5 px-4">Added</th>
                  <th className="py-3.5 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((t) => (
                  <tr key={t.id} className={cn('hover:bg-slate-50/70 transition-colors', !t.is_active && 'opacity-70')}>
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-2.5">
                        <span className="p-1.5 rounded-md bg-slate-100 text-slate-500">
                          <AppWindow className="w-3.5 h-3.5" />
                        </span>
                        <span className="font-medium text-slate-900">{t.tab_name}</span>
                      </div>
                    </td>
                    <td className="py-3.5 px-4 max-w-xs">
                      <a
                        href={t.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-brand-700 hover:underline truncate max-w-full"
                        title={t.url}
                      >
                        <span className="truncate">{hostOf(t.url)}</span>
                        <ExternalLink className="w-3 h-3 shrink-0" />
                      </a>
                      <div className="text-[11px] text-slate-400 truncate" title={t.url}>
                        {t.url}
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="flex flex-wrap gap-1">
                        {t.allowed_roles.length === ALL_ROLES.length ? (
                          <Badge variant="neutral" size="sm">
                            All roles
                          </Badge>
                        ) : (
                          t.allowed_roles.map((r) => (
                            <Badge key={r} variant="neutral" size="sm">
                              {ROLE_LABELS[r] ?? r}
                            </Badge>
                          ))
                        )}
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <Badge variant={t.is_active ? 'success' : 'neutral'} size="sm" dot>
                        {t.is_active ? 'Active' : 'Hidden'}
                      </Badge>
                    </td>
                    <td className="py-3.5 px-4 text-xs text-slate-500">{formatDate(t.created_at)}</td>
                    <td className="py-3.5 px-4 text-right">
                      <div className="inline-flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="!px-2"
                          onClick={() => window.open(t.url, '_blank', 'noopener,noreferrer')}
                          aria-label={`Open ${t.tab_name}`}
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </Button>
                        {canManage && (
                          <>
                            <Button variant="ghost" size="sm" className="!px-2" onClick={() => openEdit(t)} aria-label={`Edit ${t.tab_name}`}>
                              <Pencil className="w-3.5 h-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="!px-2 text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                              onClick={() => setDeleting(t)}
                              aria-label={`Delete ${t.tab_name}`}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </Button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? `Edit web tab: ${editing.tab_name}` : 'New web tab'}
        description="The label is shown in the navigation; the URL opens in a new browser tab."
        size="md"
        footer={
          <>
            <Button variant="outline" size="sm" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="web-tab-form" size="sm" isLoading={saving}>
              {editing ? 'Save changes' : 'Create web tab'}
            </Button>
          </>
        }
      >
        <form id="web-tab-form" onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Label"
            required
            maxLength={100}
            value={form.tab_name}
            placeholder="e.g. Support desk"
            onChange={(e) => setForm((f) => ({ ...f, tab_name: e.target.value }))}
            error={errors.tab_name}
          />
          <Input
            label="URL"
            required
            type="url"
            maxLength={500}
            value={form.url}
            placeholder="https://…"
            onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
            error={errors.url}
          />
          <div>
            <p className="block text-xs font-medium text-slate-700 mb-1.5">Visible to roles</p>
            <div className="grid grid-cols-2 gap-2">
              {ALL_ROLES.map((role) => {
                const checked = form.allowed_roles.includes(role);
                return (
                  <label
                    key={role}
                    className={cn(
                      'flex items-center gap-2.5 rounded-lg border px-3 py-2 text-sm cursor-pointer select-none transition-colors',
                      checked ? 'border-brand-300 bg-brand-50 text-brand-800' : 'border-slate-200 text-slate-700 hover:bg-slate-50'
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleRole(role)}
                      className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                    />
                    {ROLE_LABELS[role]}
                  </label>
                );
              })}
            </div>
            {errors.allowed_roles && <p className="mt-1 text-xs text-rose-600 font-medium">{errors.allowed_roles}</p>}
          </div>
          <Toggle
            label="Active"
            description="Hidden tabs are kept but not shown in the navigation."
            checked={form.is_active}
            onChange={(v) => setForm((f) => ({ ...f, is_active: v }))}
          />
        </form>
      </Modal>

      <ConfirmDialog
        isOpen={!!deleting}
        onClose={() => setDeleting(null)}
        onConfirm={handleDelete}
        title="Delete web tab?"
        description={deleting ? `"${deleting.tab_name}" will disappear from the navigation for everyone.` : undefined}
        confirmLabel="Delete web tab"
        variant="danger"
        isLoading={deletingBusy}
      />
    </div>
  );
}
