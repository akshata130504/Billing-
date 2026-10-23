import React, { useEffect, useMemo, useState } from 'react';
import { Hash, Pencil, Plus, Sparkles, Star, Trash2 } from 'lucide-react';
import { Button } from '../../../components/common/Button';
import { Badge } from '../../../components/common/Badge';
import { Input } from '../../../components/common/Input';
import { Select } from '../../../components/common/Select';
import { Modal } from '../../../components/common/Modal';
import { LoadingState } from '../../../components/common/LoadingState';
import { ErrorState } from '../../../components/common/ErrorState';
import { EmptyState } from '../../../components/common/EmptyState';
import { ConfirmDialog } from '../../../components/common/ConfirmDialog';
import { useToast } from '../../../components/common/Toast';
import { customizationService } from '../../../services/customizationService';
import { fieldErrors, toApiError } from '../../../services/apiClient';
import { formatNumber, humanize } from '../../../utils/format';
import { DOCUMENT_TYPES, type NumberSeries, type NumberSeriesCreate, type NumberSeriesPreviewResponse } from '../../../types/customization';
import { ReadOnlyNotice, TabHeader, Textarea, Toggle, formatSeriesNumber, nullable, str, type Resource } from './shared';

interface NumberSeriesTabProps {
  resource: Resource<NumberSeries>;
  canManage: boolean;
}

/** Modules that consume transaction numbers. Document types first, then other numbered records. */
const MODULE_OPTIONS: string[] = [...DOCUMENT_TYPES, 'payment', 'expense', 'subscription', 'customer', 'project'];

interface SeriesForm {
  module: string;
  name: string;
  prefix: string;
  suffix: string;
  starting_number: string;
  padding: string;
  notes: string;
  is_default: boolean;
  is_active: boolean;
}

const EMPTY_SERIES: SeriesForm = {
  module: 'invoice',
  name: '',
  prefix: '',
  suffix: '',
  starting_number: '1',
  padding: '6',
  notes: '',
  is_default: false,
  is_active: true,
};

export function NumberSeriesTab({ resource, canManage }: NumberSeriesTabProps) {
  const { showToast } = useToast();
  const { items, loading, error, reload } = resource;

  const [moduleFilter, setModuleFilter] = useState<string>('all');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<NumberSeries | null>(null);
  const [form, setForm] = useState<SeriesForm>(EMPTY_SERIES);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState<NumberSeriesPreviewResponse | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [deleting, setDeleting] = useState<NumberSeries | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    if (!modalOpen) return;
    setForm(
      editing
        ? {
            module: editing.module,
            name: editing.name,
            prefix: editing.prefix,
            suffix: str(editing.suffix),
            starting_number: String(editing.starting_number),
            padding: String(editing.padding),
            notes: str(editing.notes),
            is_default: editing.is_default,
            is_active: editing.is_active,
          }
        : EMPTY_SERIES
    );
    setErrors({});
    setPreview(null);
  }, [modalOpen, editing]);

  const modulesInUse = useMemo(() => Array.from(new Set(items.map((s) => s.module))).sort(), [items]);
  const filtered = useMemo(
    () => (moduleFilter === 'all' ? items : items.filter((s) => s.module === moduleFilter)),
    [items, moduleFilter]
  );

  const paddingNum = Number(form.padding);
  const startNum = Number(form.starting_number);
  const localSample =
    Number.isInteger(paddingNum) && paddingNum >= 1 && Number.isInteger(startNum) && startNum >= 1
      ? formatSeriesNumber(form.prefix, startNum, paddingNum, form.suffix || null)
      : null;

  const openCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };
  const openEdit = (s: NumberSeries) => {
    setEditing(s);
    setModalOpen(true);
  };

  const validate = (): boolean => {
    const next: Record<string, string> = {};
    if (!form.name.trim()) next.name = 'Series name is required';
    if (!form.module.trim()) next.module = 'Module is required';
    if (!Number.isInteger(startNum) || startNum < 1) next.starting_number = 'Must be a whole number of 1 or more';
    if (!Number.isInteger(paddingNum) || paddingNum < 1 || paddingNum > 12) next.padding = 'Padding must be between 1 and 12 digits';
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handlePreview = async () => {
    if (!validate()) return;
    setPreviewing(true);
    try {
      const data = await customizationService.previewNumberSeries({
        prefix: form.prefix,
        starting_number: startNum,
        padding: paddingNum,
        suffix: nullable(form.suffix),
      });
      setPreview(data);
    } catch (err: any) {
      showToast('error', 'Could not preview number', toApiError(err).message);
    } finally {
      setPreviewing(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    setSaving(true);
    try {
      const payload: NumberSeriesCreate = {
        module: form.module.trim(),
        name: form.name.trim(),
        prefix: form.prefix,
        suffix: nullable(form.suffix),
        starting_number: startNum,
        padding: paddingNum,
        notes: nullable(form.notes),
        is_default: form.is_default,
        is_active: form.is_active,
      };
      if (editing) {
        const { module: _omit, ...updateBody } = payload;
        const saved = await customizationService.updateNumberSeries(editing.id, updateBody);
        showToast('success', 'Number series updated', `"${saved.name}" has been saved.`);
      } else {
        const saved = await customizationService.createNumberSeries(payload);
        showToast('success', 'Number series created', `Next ${humanize(saved.module).toLowerCase()} number: ${formatSeriesNumber(saved.prefix, saved.current_number, saved.padding, saved.suffix)}`);
      }
      setModalOpen(false);
      await reload();
    } catch (err: any) {
      setErrors(fieldErrors(err));
      showToast('error', editing ? 'Could not update series' : 'Could not create series', toApiError(err).message);
    } finally {
      setSaving(false);
    }
  };

  const handleSetDefault = async (s: NumberSeries) => {
    setBusyId(s.id);
    try {
      await customizationService.updateNumberSeries(s.id, { is_default: true });
      showToast('success', 'Default series updated', `"${s.name}" now numbers new ${humanize(s.module).toLowerCase()}s.`);
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
      await customizationService.deleteNumberSeries(deleting.id);
      showToast('success', 'Number series deleted', `"${deleting.name}" has been removed.`);
      setDeleting(null);
      await reload();
    } catch (err: any) {
      showToast('error', 'Could not delete series', toApiError(err).message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-5">
      <TabHeader
        title="Transaction number series"
        description="Define how invoices, quotes and other records are numbered. Prefixes and suffixes may include {YYYY}, {MM} and {DD}, which resolve to the issue date — e.g. INV-{YYYY}- gives INV-2026-000001."
        actions={
          <>
            {modulesInUse.length > 1 && (
              <Select
                aria-label="Filter by module"
                value={moduleFilter}
                onChange={(e) => setModuleFilter(e.target.value)}
                className="!py-1.5 text-xs w-44"
                options={[{ value: 'all', label: 'All modules' }, ...modulesInUse.map((m) => ({ value: m, label: humanize(m) }))]}
              />
            )}
            {canManage && (
              <Button size="sm" onClick={openCreate} leadingIcon={<Plus className="w-4 h-4" />}>
                New series
              </Button>
            )}
          </>
        }
      />

      {!canManage && <ReadOnlyNotice what="number series" />}

      {loading ? (
        <LoadingState message="Loading number series..." />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<Hash className="w-6 h-6 stroke-1" />}
          title={moduleFilter === 'all' ? 'No custom number series' : `No series for ${humanize(moduleFilter).toLowerCase()}`}
          description={
            moduleFilter === 'all'
              ? 'Records currently use the organization-wide prefix from Settings → Billing & numbering. Add a series to number a module differently, e.g. per financial year or per branch.'
              : 'Clear the filter or create a series for this module.'
          }
          action={
            canManage ? (
              <Button size="sm" onClick={openCreate} leadingIcon={<Plus className="w-4 h-4" />}>
                Create series
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm min-w-[820px]">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/80 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                  <th className="py-3.5 px-4">Series</th>
                  <th className="py-3.5 px-4">Module</th>
                  <th className="py-3.5 px-4">Prefix / suffix</th>
                  <th className="py-3.5 px-4 text-right">Next number</th>
                  <th className="py-3.5 px-4 text-center">Padding</th>
                  <th className="py-3.5 px-4">Next issued as</th>
                  <th className="py-3.5 px-4">Status</th>
                  <th className="py-3.5 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((s) => {
                  const busy = busyId === s.id;
                  return (
                    <tr key={s.id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-3.5 px-4">
                        <div className="font-medium text-slate-900">{s.name}</div>
                        {s.notes && <div className="text-xs text-slate-500 mt-0.5 line-clamp-1">{s.notes}</div>}
                      </td>
                      <td className="py-3.5 px-4">
                        <Badge variant="neutral" size="sm">
                          {humanize(s.module)}
                        </Badge>
                      </td>
                      <td className="py-3.5 px-4 font-mono text-xs text-slate-700">
                        {s.prefix || s.suffix ? (
                          <>
                            {s.prefix && <span>{s.prefix}</span>}
                            {s.suffix && (
                              <>
                                <span className="text-slate-300 mx-1">…</span>
                                <span>{s.suffix}</span>
                              </>
                            )}
                          </>
                        ) : (
                          <span className="text-slate-400 font-sans">None</span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-right font-medium text-slate-900 tabular-nums">
                        {formatNumber(s.current_number)}
                        {s.current_number > s.starting_number && (
                          <div className="text-[11px] text-slate-400 font-normal">
                            {formatNumber(s.current_number - s.starting_number)} issued
                          </div>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-center text-slate-700 tabular-nums">{s.padding}</td>
                      <td className="py-3.5 px-4">
                        <code className="text-xs font-mono bg-slate-100 text-slate-800 px-1.5 py-0.5 rounded">
                          {formatSeriesNumber(s.prefix, s.current_number, s.padding, s.suffix)}
                        </code>
                      </td>
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-1.5">
                          {s.is_default && (
                            <Badge variant="primary" size="sm" dot>
                              Default
                            </Badge>
                          )}
                          <Badge variant={s.is_active ? 'success' : 'neutral'} size="sm">
                            {s.is_active ? 'Active' : 'Inactive'}
                          </Badge>
                        </div>
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        {canManage ? (
                          <div className="inline-flex items-center gap-1">
                            {!s.is_default && (
                              <Button
                                variant="ghost"
                                size="sm"
                                isLoading={busy}
                                onClick={() => void handleSetDefault(s)}
                                leadingIcon={<Star className="w-3.5 h-3.5" />}
                              >
                                Default
                              </Button>
                            )}
                            <Button variant="ghost" size="sm" className="!px-2" onClick={() => openEdit(s)} aria-label={`Edit ${s.name}`}>
                              <Pencil className="w-3.5 h-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="!px-2 text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                              onClick={() => setDeleting(s)}
                              aria-label={`Delete ${s.name}`}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </Button>
                          </div>
                        ) : (
                          <span className="text-xs text-slate-400">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? `Edit series: ${editing.name}` : 'New number series'}
        description={
          editing
            ? `${formatNumber(editing.current_number - editing.starting_number)} number(s) issued so far. Changing the start does not renumber existing records.`
            : 'Numbers are issued sequentially and never reused. Only one series per module can be the default.'
        }
        size="lg"
        footer={
          <>
            <Button
              variant="ghost"
              size="sm"
              className="mr-auto"
              onClick={() => void handlePreview()}
              isLoading={previewing}
              leadingIcon={<Sparkles className="w-3.5 h-3.5" />}
            >
              Preview next number
            </Button>
            <Button variant="outline" size="sm" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="number-series-form" size="sm" isLoading={saving}>
              {editing ? 'Save changes' : 'Create series'}
            </Button>
          </>
        }
      >
        <form id="number-series-form" onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Input
              label="Series name"
              required
              maxLength={100}
              value={form.name}
              placeholder="e.g. FY 2026-27 invoices"
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              error={errors.name}
            />
            <div>
              <Select
                label="Module"
                required
                value={MODULE_OPTIONS.includes(form.module) ? form.module : '__custom'}
                disabled={!!editing}
                helperText={editing ? 'Cannot be changed after creation' : undefined}
                onChange={(e) => setForm((f) => ({ ...f, module: e.target.value === '__custom' ? '' : e.target.value }))}
                options={[
                  ...MODULE_OPTIONS.map((m) => ({ value: m, label: humanize(m) })),
                  { value: '__custom', label: 'Other (type below)' },
                ]}
                error={errors.module}
              />
              {!MODULE_OPTIONS.includes(form.module) && !editing && (
                <Input
                  aria-label="Custom module key"
                  className="mt-2 font-mono"
                  maxLength={50}
                  value={form.module}
                  placeholder="module_key"
                  onChange={(e) => setForm((f) => ({ ...f, module: e.target.value.toLowerCase().replace(/\s+/g, '_') }))}
                />
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Input
              label="Prefix"
              maxLength={20}
              value={form.prefix}
              placeholder="INV-{YYYY}-"
              className="font-mono"
              onChange={(e) => setForm((f) => ({ ...f, prefix: e.target.value }))}
              error={errors.prefix}
            />
            <Input
              label="Suffix"
              maxLength={20}
              value={form.suffix}
              placeholder="/{MM}"
              className="font-mono"
              onChange={(e) => setForm((f) => ({ ...f, suffix: e.target.value }))}
              error={errors.suffix}
            />
            <Input
              label="Starting number"
              type="number"
              min={1}
              step={1}
              required
              value={form.starting_number}
              onChange={(e) => setForm((f) => ({ ...f, starting_number: e.target.value }))}
              error={errors.starting_number}
            />
            <Input
              label="Padding (digits)"
              type="number"
              min={1}
              max={12}
              step={1}
              required
              value={form.padding}
              onChange={(e) => setForm((f) => ({ ...f, padding: e.target.value }))}
              error={errors.padding}
            />
          </div>

          {/* Live sample */}
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                {preview ? 'Server preview' : 'Sample'}
              </p>
              <p className="font-mono text-base font-semibold text-slate-900 truncate">
                {preview?.sample_number ?? localSample ?? '—'}
              </p>
              {preview && <p className="text-xs text-slate-500 mt-1 leading-relaxed">{preview.explanation}</p>}
            </div>
            {!preview && (
              <p className="text-xs text-slate-500 sm:max-w-[200px]">
                Click <span className="font-medium text-slate-700">Preview next number</span> to confirm with the server.
              </p>
            )}
          </div>

          <Textarea
            label="Notes"
            rows={2}
            maxLength={255}
            value={form.notes}
            placeholder="Internal note, e.g. which branch or financial year this covers"
            onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            error={errors.notes}
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <Toggle
              label="Default for this module"
              description="New records draw from the default series."
              checked={form.is_default}
              onChange={(v) => setForm((f) => ({ ...f, is_default: v }))}
            />
            <Toggle
              label="Active"
              description="Inactive series never issue numbers."
              checked={form.is_active}
              onChange={(v) => setForm((f) => ({ ...f, is_active: v }))}
            />
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        isOpen={!!deleting}
        onClose={() => setDeleting(null)}
        onConfirm={handleDelete}
        title="Delete number series?"
        description={
          deleting
            ? `"${deleting.name}" will be removed. Numbers already issued stay on their records${
                deleting.is_default ? '; new records will fall back to the organization-wide numbering' : ''
              }.`
            : undefined
        }
        confirmLabel="Delete series"
        variant="danger"
        isLoading={!!deleting && busyId === deleting.id}
      />
    </div>
  );
}
