import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react';
import { History, Save, Send, Undo2 } from 'lucide-react';
import { Badge } from '../../../components/common/Badge';
import { Button } from '../../../components/common/Button';
import { EmptyState } from '../../../components/common/EmptyState';
import { ErrorState } from '../../../components/common/ErrorState';
import { LoadingState } from '../../../components/common/LoadingState';
import { PageHeader } from '../../../components/common/PageHeader';
import { useToast } from '../../../components/common/Toast';
import type { LandingContent, SectionKey } from '../../../pages/public/landing/types';
import { PlatformApiError } from '../../platformApi';
import { fieldErrors, websiteApi, type WebsiteCompare, type WebsitePageState, type WebsiteVersion } from '../../websiteApi';
import { ActionDialog } from '../ActionDialog';
import { formatDateTime } from '../ui';
import { FieldEditor, SECTIONS, SECTION_TITLES } from './fields';

const LandingPreview = lazy(() => import('./LandingPreview'));

type Tab = 'edit' | 'preview' | 'changes' | 'history';
type Pending = { kind: 'publish' } | { kind: 'rollback'; version: number } | null;

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

/** Website -> Landing page: draft, preview, publish, history and rollback (Platform Administrator). */
export function WebsitePage() {
  const { showToast } = useToast();
  const [state, setState] = useState<WebsitePageState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<LandingContent | null>(null);
  const [dirty, setDirty] = useState(false);
  const [tab, setTab] = useState<Tab>('edit');
  const [section, setSection] = useState<string>('hero');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [previewOf, setPreviewOf] = useState<'draft' | 'live'>('draft');
  const [compare, setCompare] = useState<WebsiteCompare | null>(null);
  const [history, setHistory] = useState<(WebsiteVersion & { live: boolean })[] | null>(null);
  const [pending, setPending] = useState<Pending>(null);
  const [viewing, setViewing] = useState<{ version: number; content: LandingContent } | null>(null);

  const apply = useCallback((next: WebsitePageState) => {
    setState(next);
    setDraft(clone(next.draft?.content ?? next.published.content));
    setDirty(false);
    setErrors({});
    setSaveError(null);
  }, []);

  const load = useCallback(async () => {
    setError(null);
    try {
      apply(await websiteApi.state());
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'Could not load the website content.');
    }
  }, [apply]);

  useEffect(() => {
    void load();
  }, [load]);

  const revision = state?.draft?.revision ?? 0;

  const loadExtras = useCallback(async (which: Tab) => {
    try {
      if (which === 'changes') setCompare(await websiteApi.compare());
      if (which === 'history') setHistory((await websiteApi.versions()).items);
    } catch (err) {
      showToast('error', 'Could not load', err instanceof PlatformApiError ? err.message : undefined);
    }
  }, [showToast]);

  useEffect(() => {
    if (tab === 'changes' || tab === 'history') void loadExtras(tab);
  }, [tab, loadExtras]);

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    setSaveError(null);
    try {
      apply(await websiteApi.saveDraft(draft, revision));
      showToast('success', 'Draft saved', 'Nothing is public until you publish.');
    } catch (err) {
      if (err instanceof PlatformApiError) {
        setErrors(fieldErrors(err.details));
        setSaveError(err.status === 422 ? 'Some fields are not valid - see the highlighted fields.' : err.message);
      } else setSaveError('Saving failed.');
    } finally {
      setSaving(false);
    }
  };

  const discard = async () => {
    try {
      apply(await websiteApi.discardDraft());
      showToast('success', 'Draft discarded');
    } catch (err) {
      showToast('error', 'Could not discard', err instanceof PlatformApiError ? err.message : undefined);
    }
  };

  const restore = async (version: number) => {
    try {
      apply(await websiteApi.restore(version, revision));
      setTab('edit');
      showToast('success', `Version ${version} loaded into the draft`, 'Review and publish when ready.');
    } catch (err) {
      showToast('error', 'Could not restore', err instanceof PlatformApiError ? err.message : undefined);
    }
  };

  const sectionSpec = useMemo(() => SECTIONS.find((s) => s.key === section) ?? SECTIONS[0], [section]);

  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!state || !draft) return <LoadingState message="Loading website content..." />;

  const hasDraft = state.draft !== null;
  const sectionValue = draft[sectionSpec.key] as unknown as Record<string, unknown> | string[];
  const setSectionValue = (key: string, v: unknown) => {
    setDraft({ ...draft, [sectionSpec.key]: { ...(draft[sectionSpec.key] as object), [key]: v } } as LandingContent);
    setDirty(true);
  };
  const order = draft.section_order;
  const moveSection = (i: number, to: number) => {
    if (to < 0 || to >= order.length) return;
    const next = [...order];
    const [k] = next.splice(i, 1);
    next.splice(to, 0, k);
    setDraft({ ...draft, section_order: next });
    setDirty(true);
  };
  const sectionErrorCount = (key: string) => Object.keys(errors).filter((k) => k === key || k.startsWith(`${key}.`)).length;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Website"
        title="Landing page"
        subtitle="Public marketing content. Pricing figures on this page are illustrative examples, not Rooman Billing subscription prices."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              leadingIcon={<Save className="h-4 w-4" />}
              onClick={() => void save()}
              isLoading={saving}
              disabled={!dirty}
            >
              Save draft
            </Button>
            <Button
              size="sm"
              leadingIcon={<Send className="h-4 w-4" />}
              onClick={() => setPending({ kind: 'publish' })}
              disabled={!hasDraft || dirty}
            >
              Publish
            </Button>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm">
        <span className="text-slate-600">Live: <strong>version {state.published.version}</strong> · published {formatDateTime(state.published.published_at)}</span>
        {hasDraft ? (
          <Badge variant="warning" dot>Draft r{state.draft!.revision} · {state.draft!.changed_sections.length} changed section(s)</Badge>
        ) : (
          <Badge variant="success" dot>No draft - editing starts a new one</Badge>
        )}
        {dirty && <Badge variant="info">Unsaved changes</Badge>}
        {hasDraft && !dirty && (
          <button type="button" onClick={() => void discard()} className="ml-auto inline-flex items-center gap-1 text-sm text-rose-600 hover:underline">
            <Undo2 className="h-4 w-4" /> Discard draft
          </button>
        )}
      </div>

      <div role="tablist" aria-label="Website editor" className="flex gap-1 border-b border-slate-200">
        {(['edit', 'preview', 'changes', 'history'] as Tab[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} type="button" onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium capitalize ${tab === t ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>
            {t === 'changes' ? 'Changes vs live' : t}
          </button>
        ))}
      </div>

      {tab === 'edit' && (
        <div className="grid gap-6 lg:grid-cols-[260px,1fr]">
          <nav aria-label="Sections" className="space-y-1">
            {SECTIONS.map((s) => {
              const count = sectionErrorCount(String(s.key));
              return (
                <button key={s.key} type="button" onClick={() => setSection(String(s.key))}
                  className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm ${section === s.key ? 'bg-brand-50 font-semibold text-brand-700' : 'text-slate-700 hover:bg-slate-100'}`}>
                  <span>{s.title}</span>
                  {count > 0 && <span className="rounded-full bg-rose-100 px-2 text-xs text-rose-700">{count}</span>}
                </button>
              );
            })}
            <button type="button" onClick={() => setSection('section_order')}
              className={`w-full rounded-lg px-3 py-2 text-left text-sm ${section === 'section_order' ? 'bg-brand-50 font-semibold text-brand-700' : 'text-slate-700 hover:bg-slate-100'}`}>
              Section order
            </button>
          </nav>
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            {saveError && <p role="alert" className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{saveError}</p>}
            {section === 'section_order' ? (
              <div>
                <h2 className="text-sm font-semibold text-slate-900">Section order</h2>
                <p className="mt-1 text-xs text-slate-500">The header, hero and footer stay in place. Hide a section from its own editor.</p>
                <ol className="mt-4 space-y-2">
                  {order.map((key: SectionKey, i) => (
                    <li key={key} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm">
                      <span className={draft[key].visible ? '' : 'text-slate-400 line-through'}>{i + 1}. {SECTION_TITLES[key]}</span>
                      <span className="flex gap-1">
                        <Button size="sm" variant="ghost" onClick={() => moveSection(i, i - 1)} disabled={i === 0} aria-label={`Move ${SECTION_TITLES[key]} up`}>Up</Button>
                        <Button size="sm" variant="ghost" onClick={() => moveSection(i, i + 1)} disabled={i === order.length - 1} aria-label={`Move ${SECTION_TITLES[key]} down`}>Down</Button>
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            ) : (
              <div className="space-y-4">
                <h2 className="text-sm font-semibold text-slate-900">{sectionSpec.title}</h2>
                {sectionSpec.fields.map((f) => (
                  <FieldEditor key={f.key} spec={f} value={(sectionValue as Record<string, unknown>)[f.key]}
                    path={`${String(sectionSpec.key)}.${f.key}`} errors={errors} onChange={(v) => setSectionValue(f.key, v)} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'preview' && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-slate-600">Show:</span>
            <Button size="sm" variant={previewOf === 'draft' ? 'primary' : 'outline'} onClick={() => setPreviewOf('draft')}>
              {dirty ? 'Current edits (unsaved)' : hasDraft ? 'Draft' : 'Draft (same as live)'}
            </Button>
            <Button size="sm" variant={previewOf === 'live' ? 'primary' : 'outline'} onClick={() => setPreviewOf('live')}>Live version {state.published.version}</Button>
          </div>
          <Suspense fallback={<LoadingState message="Loading preview..." />}>
            <LandingPreview content={previewOf === 'draft' ? draft : state.published.content} />
          </Suspense>
        </div>
      )}

      {tab === 'changes' && (
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          {dirty && <p className="mb-3 text-sm text-amber-700">Save the draft to compare your latest edits.</p>}
          {!compare ? <LoadingState message="Comparing..." /> : !compare.has_draft ? (
            <EmptyState title="No draft" description="The live page is what you see. Edit and save to start a draft." />
          ) : compare.changes.length === 0 ? (
            <EmptyState title="No differences" description="The draft is identical to the live page." />
          ) : (
            <ul className="divide-y divide-slate-100 text-sm">
              {compare.changes.map((c) => (
                <li key={c.path} className="grid gap-1 py-2 md:grid-cols-[220px,1fr,1fr]">
                  <code className="text-xs text-slate-500">{c.path}</code>
                  <span className="break-words text-rose-700 line-through">{c.published === null || c.published === undefined ? '(none)' : String(JSON.stringify(c.published))}</span>
                  <span className="break-words text-emerald-700">{c.draft === null || c.draft === undefined ? '(removed)' : String(JSON.stringify(c.draft))}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tab === 'history' && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          {!history ? <LoadingState message="Loading history..." /> : (
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <tr><th className="px-4 py-3">Version</th><th className="px-4 py-3">Published</th><th className="hidden px-4 py-3 md:table-cell">Note</th><th className="px-4 py-3 text-right">Actions</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {history.map((v) => (
                  <tr key={v.id}>
                    <td className="px-4 py-3 font-medium">
                      <History className="mr-1 inline h-4 w-4 text-slate-400" aria-hidden="true" /> v{v.version} {v.live && <Badge variant="success" size="sm">Live</Badge>}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{formatDateTime(v.published_at)}</td>
                    <td className="hidden px-4 py-3 text-slate-600 md:table-cell">{v.note ?? '-'}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap justify-end gap-2">
                        <Button size="sm" variant="ghost" onClick={async () => {
                          const full = await websiteApi.version(v.version!);
                          setViewing({ version: v.version!, content: full.content });
                        }}>Preview</Button>
                        <Button size="sm" variant="outline" disabled={dirty} onClick={() => void restore(v.version!)}>Restore to draft</Button>
                        {!v.live && <Button size="sm" variant="danger" onClick={() => setPending({ kind: 'rollback', version: v.version! })}>Roll back to this</Button>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {viewing && (
            <div className="border-t border-slate-200 p-4">
              <div className="mb-2 flex items-center justify-between text-sm">
                <span className="font-medium">Version {viewing.version}</span>
                <Button size="sm" variant="ghost" onClick={() => setViewing(null)}>Close preview</Button>
              </div>
              <Suspense fallback={<LoadingState message="Loading preview..." />}>
                <LandingPreview content={viewing.content} />
              </Suspense>
            </div>
          )}
        </div>
      )}

      {pending?.kind === 'publish' && state.draft && (
        <ActionDialog
          isOpen
          title="Publish the landing page"
          description={`Makes draft revision ${state.draft.revision} the live public page (as version ${(state.published.version ?? 0) + 1}).`}
          notes={[`Changed sections: ${state.draft.changed_sections.join(', ') || 'none'}.`, 'You can roll back to any earlier version afterwards.']}
          confirmLabel="Publish"
          onClose={() => setPending(null)}
          onSubmit={(body) => websiteApi.publish(state.draft!.revision, body.reason)}
          onDone={(next) => { apply(next); setPending(null); showToast('success', `Version ${next.published.version} is live`); }}
        />
      )}
      {pending?.kind === 'rollback' && (
        <ActionDialog
          isOpen
          danger
          title={`Roll back to version ${pending.version}`}
          description="Publishes that version's content again as a new version. History is kept; an open draft is not changed."
          confirmLabel="Roll back"
          onClose={() => setPending(null)}
          onSubmit={(body) => websiteApi.rollback(pending.version, body.reason)}
          onDone={(next) => { apply(next); setPending(null); void loadExtras('history'); showToast('success', `Version ${next.published.version} is live`); }}
        />
      )}
    </div>
  );
}
