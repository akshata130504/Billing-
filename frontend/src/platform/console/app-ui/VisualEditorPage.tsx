/**
 * Super Admin → Visual editor: structured, live editing of the tenant application's UI.
 *
 * Draft state lives in the browser (instant preview, undo/redo); "Save draft" persists it, and
 * "Publish" makes it live for every organization (step-up + reason, audited). The preview is a
 * same-origin iframe running the REAL tenant components with read-only sample data.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowDown, ArrowUp, Eye, EyeOff, History, Monitor, Redo2, RotateCcw, Save, Smartphone, Tablet, Undo2, Upload,
} from 'lucide-react';
import { Badge } from '../../../components/common/Badge';
import { Button } from '../../../components/common/Button';
import { ErrorState } from '../../../components/common/ErrorState';
import { LoadingState } from '../../../components/common/LoadingState';
import { CAPTION_LIMIT, CORE_PAGE_KEYS, PAGE_SPECS, THEME_DEFAULTS, resolveList, type ItemOverride, type ListDef, type PageConfigs, type PageKey } from '../../../appUi/registry';
import { UI_ICON_NAMES } from '../../../appUi/icons';
import { ActionDialog } from '../ActionDialog';
import { formatDateTime } from '../ui';
import { PlatformApiError } from '../../platformApi';
import { appUiApi, type AppUiPageState, type AppUiVersion } from '../../appUiApi';
import { PREVIEW_PATH, isReadyMessage, isSelectMessage, type RenderMessage } from '../../uiPreview/protocol';
import {
  PAGE_TITLES, groupsFor, locate, moveItem, moveNavSection, navSections, patchItem, patchNavSection,
  setList, setNavItems, setText, setTheme, summarize, type Content, type Group,
} from './editorModel';

const VIEWPORTS = { desktop: 1280, tablet: 820, mobile: 390 } as const;
type Viewport = keyof typeof VIEWPORTS;
const HISTORY_LIMIT = 100;

function errorText(err: unknown): string {
  if (err instanceof PlatformApiError) {
    const problems = (err.details?.problems as { field: string; message: string }[] | undefined) ?? [];
    return problems.length ? `${err.message} ${problems.map((p) => `${p.field}: ${p.message}`).join('; ')}` : err.message;
  }
  return 'That did not work. Please try again.';
}

export function VisualEditorPage() {
  const [page, setPage] = useState<PageKey>('overview');
  const [canEdit, setCanEdit] = useState(false);
  const [state, setState] = useState<AppUiPageState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [content, setContent] = useState<Content>({});
  const [past, setPast] = useState<Content[]>([]);
  const [future, setFuture] = useState<Content[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [viewport, setViewport] = useState<Viewport>('desktop');
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState<null | { kind: 'publish' } | { kind: 'rollback'; version: number }>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [versions, setVersions] = useState<(AppUiVersion & { live: boolean })[]>([]);
  const [viewing, setViewing] = useState<{ version: number; content: Content } | null>(null);

  const live: Content = (state?.published?.content as Content) ?? (state?.defaults as Content) ?? {};
  const saved: Content = (state?.draft?.content as Content) ?? live;
  const dirty = JSON.stringify(content) !== JSON.stringify(saved);
  const changes = useMemo(() => summarize(page, live, content), [page, live, content]);

  const load = useCallback(async (key: PageKey) => {
    setLoadError(null);
    try {
      const [summary, pageState] = await Promise.all([appUiApi.pages(), appUiApi.state(key)]);
      setCanEdit(summary.can_edit);
      setState(pageState);
      setContent(((pageState.draft?.content ?? pageState.published?.content ?? pageState.defaults) as Content) ?? {});
      setPast([]);
      setFuture([]);
      setViewing(null);
    } catch (err) {
      setLoadError(errorText(err));
    }
  }, []);

  useEffect(() => {
    setSelectedId(null);
    void load(page);
  }, [page, load]);

  const edit = (next: Content) => {
    setPast((p) => [...p.slice(-HISTORY_LIMIT + 1), content]);
    setFuture([]);
    setContent(next);
    setMessage(null);
  };
  const undo = () => {
    if (!past.length) return;
    setFuture((f) => [content, ...f]);
    setContent(past[past.length - 1]);
    setPast((p) => p.slice(0, -1));
  };
  const redo = () => {
    if (!future.length) return;
    setPast((p) => [...p, content]);
    setContent(future[0]);
    setFuture((f) => f.slice(1));
  };

  // --- preview frame ---------------------------------------------------------------------------------
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [frameReady, setFrameReady] = useState(false);
  const previewContent = viewing?.content ?? content;
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== frameRef.current?.contentWindow) return;
      if (isReadyMessage(event.data)) setFrameReady(true);
      if (isSelectMessage(event.data)) setSelectedId(event.data.id);
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, []);
  useEffect(() => {
    if (!frameReady || !frameRef.current?.contentWindow) return;
    // Theme previews apply on top of every page; other pages preview with the live theme.
    const pages: PageConfigs = { [page]: previewContent };
    const msg: RenderMessage = { type: 'rb-ui-preview:render', page, pages, selectedId };
    frameRef.current.contentWindow.postMessage(msg, window.location.origin);
  }, [frameReady, page, previewContent, selectedId]);

  const frameBoxRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const box = frameBoxRef.current;
    if (!box) return;
    const update = () => setScale(Math.min(1, box.clientWidth / VIEWPORTS[viewport]));
    update();
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(update) : null;
    observer?.observe(box);
    return () => observer?.disconnect();
    // The preview box only exists once the page state has loaded.
  }, [viewport, Boolean(state)]);

  // --- server actions --------------------------------------------------------------------------------
  const run = async (action: () => Promise<AppUiPageState>, ok: string) => {
    setBusy(true);
    setMessage(null);
    try {
      const next = await action();
      setState(next);
      setContent(((next.draft?.content ?? next.published?.content ?? next.defaults) as Content) ?? {});
      setPast([]);
      setFuture([]);
      setMessage({ tone: 'ok', text: ok });
    } catch (err) {
      setMessage({ tone: 'error', text: errorText(err) });
    } finally {
      setBusy(false);
    }
  };
  const saveDraft = () => run(() => appUiApi.saveDraft(page, content, state?.draft?.revision ?? 0), 'Draft saved. It is not live yet.');
  const discard = () => run(() => appUiApi.discardDraft(page), 'Draft discarded.');
  const openHistory = async () => {
    setShowHistory((v) => !v);
    try {
      setVersions((await appUiApi.versions(page)).items);
    } catch (err) {
      setMessage({ tone: 'error', text: errorText(err) });
    }
  };
  const viewVersion = async (version: number) => {
    try {
      const v = await appUiApi.version(page, version);
      setViewing({ version, content: v.content as Content });
    } catch (err) {
      setMessage({ tone: 'error', text: errorText(err) });
    }
  };

  const located = locate(page, selectedId);
  const readOnly = !canEdit || Boolean(viewing);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Visual editor</h1>
          <p className="text-sm text-slate-500">
            Change how the Rooman Billing app looks for every organization. Business logic, data and security are not editable.
          </p>
        </div>
      </div>

      {/* Top bar */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-3">
        <label className="text-xs font-medium text-slate-500" htmlFor="ve-page">Page</label>
        <select id="ve-page" value={page} onChange={(e) => setPage(e.target.value as PageKey)}
          className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm" disabled={busy}>
          <optgroup label="Application">
            {CORE_PAGE_KEYS.map((k) => <option key={k} value={k}>{PAGE_TITLES[k]}</option>)}
          </optgroup>
          <optgroup label="Modules">
            {Object.keys(PAGE_SPECS).map((k) => <option key={k} value={k}>{PAGE_TITLES[k]}</option>)}
          </optgroup>
        </select>
        <div className="flex rounded-lg border border-slate-200" role="group" aria-label="Preview size">
          {([['desktop', Monitor], ['tablet', Tablet], ['mobile', Smartphone]] as const).map(([v, Icon]) => (
            <button key={v} type="button" onClick={() => setViewport(v)} aria-pressed={viewport === v} title={v}
              className={`px-2.5 py-1.5 ${viewport === v ? 'bg-brand-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}>
              <Icon className="h-4 w-4" aria-hidden="true" /><span className="sr-only">{v}</span>
            </button>
          ))}
        </div>
        <Button size="sm" variant="outline" onClick={undo} disabled={!past.length || readOnly} leadingIcon={<Undo2 className="h-4 w-4" />}>Undo</Button>
        <Button size="sm" variant="outline" onClick={redo} disabled={!future.length || readOnly} leadingIcon={<Redo2 className="h-4 w-4" />}>Redo</Button>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {state?.published ? <Badge variant="success" dot>Live: version {state.published.version}</Badge> : <Badge dot>Live: built-in defaults</Badge>}
          {state?.draft && <Badge variant="warning" dot>Saved draft</Badge>}
          {dirty && <Badge variant="info">Unsaved changes</Badge>}
          <Button size="sm" variant="outline" onClick={() => void openHistory()} leadingIcon={<History className="h-4 w-4" />}>History</Button>
          {canEdit && (
            <>
              {state?.draft && !dirty && (
                <Button size="sm" variant="ghost" onClick={() => void discard()} disabled={busy}>Discard draft</Button>
              )}
              <Button size="sm" variant="secondary" onClick={() => void saveDraft()} disabled={!dirty || busy || Boolean(viewing)} isLoading={busy}
                leadingIcon={<Save className="h-4 w-4" />}>Save draft</Button>
              <Button size="sm" onClick={() => setDialog({ kind: 'publish' })} disabled={!state?.draft || dirty || busy || Boolean(viewing)}
                leadingIcon={<Upload className="h-4 w-4" />}>Publish</Button>
            </>
          )}
        </div>
      </div>

      {!canEdit && state && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Read-only: your platform role can preview but not change the application design.
        </p>
      )}
      {viewing && (
        <p className="flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-800">
          <Eye className="h-4 w-4" /> Previewing version {viewing.version} (read-only).
          <button type="button" className="ml-auto underline" onClick={() => setViewing(null)}>Back to editing</button>
        </p>
      )}
      {message && (
        <p role={message.tone === 'error' ? 'alert' : 'status'}
          className={`rounded-lg border px-3 py-2 text-sm ${message.tone === 'error' ? 'border-rose-200 bg-rose-50 text-rose-700' : 'border-emerald-200 bg-emerald-50 text-emerald-800'}`}>
          {message.text}
        </p>
      )}

      {loadError ? (
        <ErrorState message={loadError} onRetry={() => void load(page)} />
      ) : !state ? (
        <LoadingState message="Loading the editor…" />
      ) : (
        <div className="grid gap-4 xl:grid-cols-[230px,1fr,320px]">
          {/* Component tree */}
          <nav aria-label="Components" className="space-y-1 rounded-xl border border-slate-200 bg-white p-3 text-sm">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">{PAGE_TITLES[page]}</p>
            {groupsFor(page).map((g) => (
              <div key={g.id}>
                <button type="button" onClick={() => setSelectedId(g.id)}
                  className={`w-full rounded-md px-2 py-1.5 text-left font-medium ${located?.group.id === g.id ? 'bg-brand-600 text-white' : 'text-slate-700 hover:bg-slate-100'}`}>
                  {g.label}
                </button>
                {g.defs && located?.group.id === g.id && (
                  <ul className="ml-3 mt-1 space-y-0.5 border-l border-slate-200 pl-2 text-xs">
                    {resolveList(g.defs, listFor(page, g, content)).map((item) => (
                      <li key={item.key}>
                        <button type="button" onClick={() => setSelectedId(`${g.itemPrefix ?? `${g.id}.`}${item.key}`)}
                          className={`w-full truncate rounded px-1.5 py-1 text-left ${located?.itemKey === item.key ? 'bg-brand-50 font-semibold text-brand-700' : 'text-slate-600 hover:bg-slate-50'} ${item.hidden ? 'line-through opacity-60' : ''}`}>
                          {item.label}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
            <p className="pt-3 text-xs text-slate-400">Tip: click any outlined element in the preview to select it.</p>
          </nav>

          {/* Live preview */}
          <div ref={frameBoxRef} className="min-w-0 overflow-hidden rounded-xl border border-slate-200 bg-slate-100">
            <div className="flex items-center justify-between border-b border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-500">
              <span>Preview · sample data · actions disabled</span>
              <span>{VIEWPORTS[viewport]}px</span>
            </div>
            <div style={{ height: 720 * scale }}>
              <iframe
                ref={frameRef}
                title="Application preview"
                src={PREVIEW_PATH}
                sandbox="allow-scripts allow-same-origin"
                onLoad={() => setFrameReady(false)}
                style={{ width: VIEWPORTS[viewport], height: 720, transform: `scale(${scale})`, transformOrigin: 'top left', border: 0, background: 'white' }}
              />
            </div>
          </div>

          {/* Properties */}
          <aside aria-label="Properties" className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
            {located ? (
              <PropertiesPanel page={page} group={located.group} itemKey={located.itemKey} content={content}
                readOnly={readOnly} onChange={edit} />
            ) : (
              <p className="text-sm text-slate-500">Select a component in the tree or the preview to edit it.</p>
            )}
            {changes.length > 0 && (
              <div className="border-t border-slate-100 pt-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Differences from live ({changes.length})</p>
                <ul className="mt-1 space-y-1 text-xs text-slate-600">{changes.map((c) => <li key={c}>• {c}</li>)}</ul>
              </div>
            )}
          </aside>
        </div>
      )}

      {showHistory && state && (
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-900">Version history – {PAGE_TITLES[page]}</h2>
          {versions.length === 0 ? (
            <p className="text-sm text-slate-500">Never published: the built-in defaults are live.</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-400"><tr><th className="py-1">Version</th><th>Published</th><th>By</th><th>Summary</th><th /></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {versions.map((v) => (
                  <tr key={v.id}>
                    <td className="py-2 font-medium">v{v.version} {v.live && <Badge variant="success" size="sm">Live</Badge>}</td>
                    <td>{formatDateTime(v.published_at)}</td>
                    <td className="font-mono text-xs">{v.published_by_staff_id?.slice(0, 8) ?? '—'}</td>
                    <td className="max-w-xs truncate">{v.note ?? '—'}</td>
                    <td className="space-x-2 whitespace-nowrap text-right">
                      <button type="button" className="text-brand-700 hover:underline" onClick={() => void viewVersion(v.version!)}>Preview</button>
                      {canEdit && !v.live && (
                        <>
                          <button type="button" className="text-brand-700 hover:underline" disabled={dirty}
                            onClick={() => void run(() => appUiApi.restore(page, v.version!, state.draft?.revision ?? 0), `Version ${v.version} loaded into the draft.`)}>
                            Restore to draft
                          </button>
                          <button type="button" className="text-rose-700 hover:underline" onClick={() => setDialog({ kind: 'rollback', version: v.version! })}>
                            Roll back
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {canEdit && state.published && (
            <Button className="mt-3" size="sm" variant="outline" leadingIcon={<RotateCcw className="h-4 w-4" />}
              onClick={() => setDialog({ kind: 'rollback', version: 0 })}>Restore built-in defaults</Button>
          )}
        </div>
      )}

      <ActionDialog<AppUiPageState>
        isOpen={dialog?.kind === 'publish'}
        title={`Publish ${PAGE_TITLES[page]}`}
        description={`${changes.length} change${changes.length === 1 ? '' : 's'} will go live for every organization.`}
        confirmLabel="Publish"
        notes={changes.slice(0, 12)}
        onClose={() => setDialog(null)}
        onSubmit={(body) => appUiApi.publish(page, state?.draft?.revision ?? 0, body.reason.slice(0, 300))}
        onDone={(next) => {
          setDialog(null);
          setState(next);
          setContent(((next.published?.content ?? next.defaults) as Content) ?? {});
          setMessage({ tone: 'ok', text: `Published version ${next.published?.version}. Tenants see it within a minute.` });
          if (showHistory) void appUiApi.versions(page).then((r) => setVersions(r.items));
        }}
      />
      <ActionDialog<AppUiPageState>
        isOpen={dialog?.kind === 'rollback'}
        title={dialog?.kind === 'rollback' && dialog.version === 0 ? 'Restore built-in defaults' : `Roll back to version ${dialog?.kind === 'rollback' ? dialog.version : ''}`}
        description="This publishes the selected configuration as a new version. History is kept."
        confirmLabel="Roll back"
        danger
        onClose={() => setDialog(null)}
        onSubmit={(body) => appUiApi.rollback(page, dialog?.kind === 'rollback' ? dialog.version : 0, body.reason.slice(0, 300))}
        onDone={(next) => {
          setDialog(null);
          setState(next);
          setContent(((next.draft?.content ?? next.published?.content ?? next.defaults) as Content) ?? {});
          setMessage({ tone: 'ok', text: `Rolled back. Version ${next.published?.version} is live.` });
          void appUiApi.versions(page).then((r) => setVersions(r.items));
        }}
      />
    </div>
  );
}

function listFor(page: PageKey, group: Group, content: Content): ItemOverride[] | undefined {
  if (page === 'navigation') {
    if (group.kind === 'nav-sections') return navSections(content);
    return navSections(content).find((s) => s.key === group.sectionKey)?.items;
  }
  return group.field ? (content[group.field] as ItemOverride[] | undefined) : undefined;
}

function PropertiesPanel({ page, group, itemKey, content, readOnly, onChange }: {
  page: PageKey;
  group: Group;
  itemKey?: string;
  content: Content;
  readOnly: boolean;
  onChange: (next: Content) => void;
}) {
  const inputClass = 'w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm disabled:bg-slate-50';

  if (group.kind === 'theme') {
    return (
      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-900">Theme colours</h2>
        {(Object.keys(THEME_DEFAULTS) as (keyof typeof THEME_DEFAULTS)[]).map((field) => {
          const value = ((content as Record<string, string>)[field] ?? THEME_DEFAULTS[field]).toLowerCase();
          return (
            <label key={field} className="flex items-center justify-between gap-3 text-sm">
              <span className="capitalize text-slate-700">{field.replace(/_/g, ' ')}</span>
              <span className="flex items-center gap-2">
                <input type="color" value={value} disabled={readOnly} aria-label={field}
                  onChange={(e) => onChange(setTheme(content, field, e.target.value))} />
                <code className="text-xs text-slate-500">{value}</code>
              </span>
            </label>
          );
        })}
        <p className="text-xs text-slate-500">Colours that would make white text unreadable are refused when saving.</p>
      </div>
    );
  }

  if ((group.kind === 'header' || group.kind === 'empty') && group.field && group.textFields) {
    const values = (content[group.field] as Record<string, string>) ?? {};
    return (
      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-900">{group.label}</h2>
        {group.textFields.map((f) => (
          <label key={f.name} className="block text-sm">
            <span className="text-slate-700">{f.label}</span>
            {f.multiline ? (
              <textarea className={inputClass} rows={3} maxLength={f.maxLength ?? 300} disabled={readOnly} aria-label={f.label}
                value={values[f.name] ?? f.default}
                onChange={(e) => onChange(setText(content, group.field!, f.name, e.target.value, f.default))} />
            ) : (
              <input className={inputClass} maxLength={f.maxLength ?? 120} disabled={readOnly} value={values[f.name] ?? f.default}
                onChange={(e) => onChange(setText(content, group.field!, f.name, e.target.value, f.default))} />
            )}
            {f.hint && <span className="text-xs text-slate-400">{f.hint}</span>}
          </label>
        ))}
      </div>
    );
  }

  const defs = group.defs as ListDef[];
  const list = listFor(page, group, content);
  const items = resolveList(defs, list);
  const isNavSection = group.kind === 'nav-section';
  const isNavSections = group.kind === 'nav-sections';
  const writeList = (next: ItemOverride[]) => {
    if (isNavSection) onChange(setNavItems(content, group.sectionKey!, next));
    else onChange(setList(content, group.field!, next, defs));
  };
  const sectionOverride = isNavSection ? navSections(content).find((s) => s.key === group.sectionKey) : undefined;

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-slate-900">{group.label}</h2>
      {isNavSection && (
        <label className="block text-sm">
          <span className="text-slate-700">Section label</span>
          <input className={inputClass} maxLength={60} disabled={readOnly}
            value={sectionOverride?.label ?? group.label}
            onChange={(e) => onChange(patchNavSection(content, group.sectionKey!, { label: e.target.value }))} />
        </label>
      )}
      <ul className="space-y-2">
        {items.map((item, index) => {
          const def = defs.find((d) => d.key === item.key)!;
          const icon = isNavSection ? (list ?? []).find((i) => i.key === item.key) as { icon?: string } | undefined : undefined;
          const focused = itemKey === item.key;
          return (
            <li key={item.key} className={`rounded-lg border p-2 ${focused ? 'border-brand-500 bg-brand-50/40' : 'border-slate-200'}`}>
              <div className="flex items-center gap-1">
                <input className={inputClass} aria-label={`${def.label} label`} maxLength={60} disabled={readOnly}
                  value={item.label}
                  onChange={(e) => {
                    if (isNavSections) onChange(patchNavSection(content, item.key, { label: e.target.value }));
                    else writeList(patchItem(defs, list, item.key, { label: e.target.value }));
                  }} />
                <button type="button" title={item.hidden ? 'Show' : 'Hide'} aria-label={item.hidden ? `Show ${def.label}` : `Hide ${def.label}`}
                  disabled={readOnly || def.required || group.hide === false}
                  className="rounded p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30"
                  onClick={() => {
                    if (isNavSections) onChange(patchNavSection(content, item.key, { hidden: !item.hidden }));
                    else writeList(patchItem(defs, list, item.key, { hidden: !item.hidden }));
                  }}>
                  {item.hidden ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
                {group.reorder !== false && <>
                <button type="button" aria-label={`Move ${def.label} up`} disabled={readOnly || index === 0}
                  className="rounded p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30"
                  onClick={() => (isNavSections ? onChange(moveNavSection(content, item.key, -1)) : writeList(moveItem(defs, list, item.key, -1)))}>
                  <ArrowUp className="h-4 w-4" />
                </button>
                <button type="button" aria-label={`Move ${def.label} down`} disabled={readOnly || index === items.length - 1}
                  className="rounded p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30"
                  onClick={() => (isNavSections ? onChange(moveNavSection(content, item.key, 1)) : writeList(moveItem(defs, list, item.key, 1)))}>
                  <ArrowDown className="h-4 w-4" />
                </button>
                </>}
              </div>
              {group.captions && (
                <input className={`${inputClass} mt-1 text-xs`} aria-label={`${def.label} caption`} maxLength={CAPTION_LIMIT}
                  disabled={readOnly} value={item.caption ?? ''}
                  onChange={(e) => writeList(patchItem(defs, list, item.key, { caption: e.target.value }))} />
              )}
              {isNavSection && (
                <select className="mt-1 w-full rounded border border-slate-200 px-2 py-1 text-xs" aria-label={`${def.label} icon`}
                  disabled={readOnly} value={icon?.icon ?? ''}
                  onChange={(e) => writeList(patchItem(defs, list as ItemOverride[] | undefined, item.key, { icon: e.target.value || undefined } as Partial<ItemOverride>))}>
                  <option value="">Default icon</option>
                  {UI_ICON_NAMES.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              )}
              {def.required && <p className="mt-1 text-xs text-slate-400">Always visible</p>}
            </li>
          );
        })}
      </ul>
      <p className="text-xs text-slate-500">Labels are plain text. Hidden entries keep working; they are only not shown.</p>
      {page === 'navigation' && !isNavSections && <p className="text-xs text-slate-400">Items stay in their section.</p>}
      {group.reorder === false && <p className="text-xs text-slate-400">The order of this list is fixed by the application.</p>}
    </div>
  );
}

export default VisualEditorPage;
