/**
 * Declarative editor for the landing-page content. Each section is described by field specs;
 * FieldEditor renders them (text, long text, links, media, colours, selects, numbers, toggles,
 * string lists and repeatable object lists with add / remove / reorder / show-hide).
 * The server validates every save; its errors are shown next to the field (by path).
 */
import { useRef, useState } from 'react';
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, Eye, EyeOff, Plus, Trash2, Upload } from 'lucide-react';
import { ICON_NAMES, TONE_NAMES } from '../../../pages/public/landing/icons';
import type { LandingContent, SectionKey } from '../../../pages/public/landing/types';
import { PlatformApiError } from '../../platformApi';
import { websiteApi } from '../../websiteApi';

type Obj = Record<string, unknown>;

export type FieldSpec =
  | { kind: 'text' | 'textarea' | 'link' | 'media' | 'color'; key: string; label: string; max?: number; help?: string }
  | { kind: 'bool'; key: string; label: string }
  | { kind: 'number'; key: string; label: string; min?: number; step?: number; nullable?: boolean; help?: string; showIf?: (item: Obj) => boolean }
  | { kind: 'select'; key: string; label: string; options: readonly string[] }
  | { kind: 'strings'; key: string; label: string; max?: number }
  | { kind: 'list'; key: string; label: string; itemLabel: (item: Obj, index: number) => string; fields: FieldSpec[]; newItem: () => Obj; max?: number; showIf?: (item: Obj) => boolean };

const S = (key: string, label: string, max = 160): FieldSpec => ({ kind: 'text', key, label, max });
const L = (key: string, label: string, max = 600): FieldSpec => ({ kind: 'textarea', key, label, max });
const VISIBLE: FieldSpec = { kind: 'bool', key: 'visible', label: 'Visible' };
const ICON = (key = 'icon'): FieldSpec => ({ kind: 'select', key, label: 'Icon', options: ICON_NAMES });
const TONE: FieldSpec = { kind: 'select', key: 'tone', label: 'Colour', options: TONE_NAMES };
const LINK = (key = 'link', label = 'Link'): FieldSpec => ({ kind: 'link', key, label, help: 'An internal path like /catalog, or an https:// URL.' });
const HEADING = (badgeLabel = 'Badge'): FieldSpec[] => [VISIBLE, S('badge', badgeLabel, 120), S('heading', 'Heading'), L('description', 'Description')];

const kind = (item: Obj) => String(item.kind ?? '');

export interface SectionSpec {
  key: keyof LandingContent;
  title: string;
  fields: FieldSpec[];
}

export const SECTION_TITLES: Record<SectionKey, string> = {
  capabilities: 'Core capabilities',
  how_it_works: 'How it works',
  workflow: 'Workflow (quote to cash)',
  pricing: 'Pricing models (examples)',
  why: 'Why choose Rooman Billing',
  audiences: 'Who it is for',
  customer_experience: 'Customer experience',
  operations: 'Operations & control',
  faq: 'FAQ',
  final_cta: 'Final call to action',
};

export const SECTIONS: SectionSpec[] = [
  { key: 'seo', title: 'SEO', fields: [S('title', 'Page title', 120), L('description', 'Meta description', 300)] },
  {
    key: 'header', title: 'Header & navigation', fields: [
      { kind: 'list', key: 'nav', label: 'Navigation links', max: 10, itemLabel: (i) => String(i.label || 'Link'),
        newItem: () => ({ target: 'features', label: 'New link', mobile_label: 'New link', visible: true }),
        fields: [VISIBLE, { kind: 'select', key: 'target', label: 'Scrolls to section', options: ['features', 'how-it-works', 'workflow', 'pricing-models', 'why-rooman', 'faq'] },
          S('label', 'Label', 80), S('mobile_label', 'Mobile label', 80)] },
      S('sign_in_label', 'Sign-in button', 80), S('get_started_label', 'Get-started button', 80),
      S('dashboard_label', 'Dashboard button (signed in)', 80), S('mobile_dashboard_label', 'Mobile dashboard button', 80),
    ],
  },
  {
    key: 'hero', title: 'Hero', fields: [
      VISIBLE, S('badge', 'Badge', 120), S('headline', 'Headline'), S('headline_highlight', 'Highlighted headline'),
      L('subheading', 'Subheading'), S('primary_cta_label', 'Primary button', 80), S('secondary_cta_label', 'Secondary button', 80),
      { kind: 'media', key: 'video_src', label: 'Background video', help: 'A bundled /videos/*.mp4 file or an uploaded video.' },
    ],
  },
  {
    key: 'capabilities', title: SECTION_TITLES.capabilities, fields: [
      VISIBLE, S('eyebrow', 'Eyebrow', 80), S('heading', 'Heading'), L('description', 'Description'),
      { kind: 'list', key: 'cards', label: 'Capability cards', max: 8, itemLabel: (i) => String(i.title || 'Card'),
        newItem: () => ({ title: 'New capability', desc: 'Short description', link: '/dashboard', icon: 'Layers', accent: '#3F51C9', badge_bg: '#E8EBFC', animation: 'catalog', visible: true }),
        fields: [VISIBLE, S('title', 'Title', 80), S('desc', 'Description', 120), LINK(), ICON(),
          { kind: 'color', key: 'accent', label: 'Accent colour' }, { kind: 'color', key: 'badge_bg', label: 'Badge background' },
          { kind: 'select', key: 'animation', label: 'Animation', options: ['catalog', 'pricing', 'cpq', 'quotes', 'invoices', 'payments'] }] },
    ],
  },
  {
    key: 'how_it_works', title: SECTION_TITLES.how_it_works, fields: [
      ...HEADING(),
      { kind: 'strings', key: 'video_sources', label: 'Video sources (first playable is used)', max: 3 },
      { kind: 'list', key: 'steps', label: 'Steps', max: 6, itemLabel: (i) => String(i.title || 'Step'),
        newItem: () => ({ step: '04', stage_label: 'Step 4', title: 'New step', desc: 'Description', icon: 'Layers', visible: true }),
        fields: [VISIBLE, S('step', 'Number', 8), S('stage_label', 'Stage label', 120), S('title', 'Title'), L('desc', 'Description'), ICON()] },
    ],
  },
  {
    key: 'workflow', title: SECTION_TITLES.workflow, fields: [
      ...HEADING(), S('pause_label', 'Pause button', 80), S('resume_label', 'Resume button', 80),
      S('open_label', 'Open button ({label} = stage name)', 120), S('footnote', 'Footnote', 120),
      S('panel_title', 'Panel title', 80), S('panel_status', 'Panel status', 80), S('panel_active_label', 'Active label', 80),
      S('panel_next_label', 'Next label', 80), S('panel_metric_label', 'Metric label', 80),
      S('panel_validation_label', 'Validation label', 80), S('panel_validation_value', 'Validation value', 80),
      { kind: 'list', key: 'steps', label: 'Stages', max: 12, itemLabel: (i) => String(i.label || 'Stage'),
        newItem: () => ({ key: `stage${Date.now() % 100000}`, label: 'New', step: '10', title: 'New stage', desc: 'Description', badge: 'Badge', link: '/dashboard', details: [], kpi: 'Metric', visible: true }),
        fields: [VISIBLE, S('label', 'Tab label', 80), S('step', 'Number', 8), S('title', 'Title'), L('desc', 'Description'),
          S('badge', 'Badge', 80), LINK(), { kind: 'strings', key: 'details', label: 'Feature pills', max: 6 }, S('kpi', 'Metric', 120)] },
    ],
  },
  {
    key: 'pricing', title: SECTION_TITLES.pricing, fields: [
      ...HEADING(),
      { kind: 'list', key: 'models', label: 'Example pricing models (illustrative, not Rooman prices)', max: 8,
        itemLabel: (i) => String(i.title || 'Model'),
        newItem: () => ({ kind: 'flat', title: 'New model', type: 'Type', desc: 'Description', example: 'Example', features: [], price: 100, visible: true }),
        fields: [VISIBLE, { kind: 'select', key: 'kind', label: 'Calculation', options: ['flat', 'per_unit', 'volume', 'tiered', 'package'] },
          S('title', 'Title', 80), S('type', 'Type badge', 80), L('desc', 'Description'), S('example', 'Structure example', 120),
          { kind: 'strings', key: 'features', label: 'Features', max: 6 },
          { kind: 'number', key: 'price', label: 'Price / unit price / bundle price (₹)', min: 0, step: 1, showIf: (i) => ['flat', 'per_unit', 'package'].includes(kind(i)) },
          { kind: 'number', key: 'bundle_size', label: 'Units per bundle', min: 1, step: 1, showIf: (i) => kind(i) === 'package' },
          { kind: 'list', key: 'tiers', label: 'Tiers', max: 6, showIf: (i) => ['volume', 'tiered'].includes(kind(i)),
            itemLabel: (t) => (t.up_to === null || t.up_to === undefined ? `Beyond @ ₹${t.rate}` : `Up to ${t.up_to} @ ₹${t.rate}`),
            newItem: () => ({ up_to: null, rate: 1 }),
            fields: [{ kind: 'number', key: 'up_to', label: 'Up to (units; empty = open-ended last tier)', min: 1, step: 1, nullable: true },
              { kind: 'number', key: 'rate', label: 'Rate per unit (₹)', min: 0, step: 1 }] }] },
      S('live_badge', 'Live badge', 80), S('live_caption', 'Live caption', 120), S('simulate_label', 'Slider label', 80),
      S('flat_note', 'Flat-fee note', 120), S('calculated_label', 'Price label', 80), S('verified_label', 'Verified label', 80),
      S('audit_label', 'Audit label', 80), S('isolation_label', 'Isolation label', 80), S('steps_title', 'Steps title', 80),
      S('steps_subtitle', 'Steps subtitle', 120), S('why_title', '"Why this price" title', 80),
      S('primary_cta_label', 'Primary button', 80), LINK('primary_cta_link', 'Primary link'),
      S('secondary_cta_label', 'Secondary button', 80), LINK('secondary_cta_link', 'Secondary link'),
    ],
  },
  {
    key: 'why', title: SECTION_TITLES.why, fields: [
      ...HEADING(), S('pipeline_title', 'Pipeline title', 120),
      { kind: 'list', key: 'pipeline', label: 'Pipeline steps', max: 12, itemLabel: (i) => String(i.name || 'Step'),
        newItem: () => ({ name: 'Step', icon: 'Layers' }), fields: [S('name', 'Name', 80), ICON()] },
      { kind: 'list', key: 'cards', label: 'Cards', max: 8, itemLabel: (i) => String(i.title || 'Card'),
        newItem: () => ({ title: 'New card', desc: 'Description', icon: 'Layers', tone: 'indigo', visible: true }),
        fields: [VISIBLE, S('title', 'Title', 80), L('desc', 'Description'), ICON(), TONE] },
    ],
  },
  {
    key: 'audiences', title: SECTION_TITLES.audiences, fields: [
      ...HEADING(),
      { kind: 'list', key: 'items', label: 'Audiences', max: 8, itemLabel: (i) => String(i.title || 'Audience'),
        newItem: () => ({ title: 'New audience', desc: 'Description', icon: 'Layers', benefit: 'Benefit', example: '', visible: true }),
        fields: [VISIBLE, S('title', 'Title', 80), L('desc', 'Description'), ICON(), S('benefit', 'Benefit', 120), S('example', 'Example (not shown)', 300)] },
    ],
  },
  {
    key: 'customer_experience', title: SECTION_TITLES.customer_experience, fields: [
      ...HEADING(),
      { kind: 'list', key: 'cards', label: 'Cards', max: 6, itemLabel: (i) => String(i.title || 'Card'),
        newItem: () => ({ title: 'New card', desc: 'Description', icon: 'Layers', tone: 'indigo', status_badge: 'Active', footer_text: 'Footer', footer_link: null, visible: true }),
        fields: [VISIBLE, S('title', 'Title', 80), L('desc', 'Description'), ICON(), TONE, S('status_badge', 'Status badge', 80),
          S('footer_text', 'Footer text', 120), { kind: 'link', key: 'footer_link', label: 'Footer link (optional)' }] },
    ],
  },
  {
    key: 'operations', title: SECTION_TITLES.operations, fields: [
      ...HEADING(),
      { kind: 'list', key: 'cards', label: 'Cards', max: 12, itemLabel: (i) => String(i.title || 'Card'),
        newItem: () => ({ title: 'New card', desc: 'Description', icon: 'Layers', tone: 'indigo', link: '/dashboard', visible: true }),
        fields: [VISIBLE, S('title', 'Title', 80), L('desc', 'Description'), ICON(), TONE, LINK()] },
    ],
  },
  {
    key: 'faq', title: SECTION_TITLES.faq, fields: [
      ...HEADING(),
      { kind: 'list', key: 'items', label: 'Questions', max: 20, itemLabel: (i) => String(i.q || 'Question'),
        newItem: () => ({ q: 'New question?', a: 'Answer.', visible: true }),
        fields: [VISIBLE, S('q', 'Question', 300), L('a', 'Answer', 2000)] },
    ],
  },
  {
    key: 'final_cta', title: SECTION_TITLES.final_cta, fields: [
      ...HEADING(), S('primary_cta_label', 'Primary button', 80), S('secondary_cta_label', 'Secondary button', 80),
    ],
  },
  {
    key: 'footer', title: 'Footer', fields: [
      L('tagline', 'Tagline'), S('copyright_holder', 'Copyright holder', 120),
      { kind: 'list', key: 'columns', label: 'Link columns', max: 6, itemLabel: (i) => String(i.title || 'Column'),
        newItem: () => ({ title: 'Column', links: [] }),
        fields: [S('title', 'Title', 80),
          { kind: 'list', key: 'links', label: 'Links', max: 12, itemLabel: (i) => String(i.label || 'Link'),
            newItem: () => ({ label: 'Link', link: '/' }), fields: [S('label', 'Label', 80), LINK()] }] },
      S('bottom_text', 'Bottom text', 120), { kind: 'strings', key: 'bottom_badges', label: 'Bottom badges', max: 6 },
    ],
  },
];

const inputClass = 'mt-1 block w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2';
function cls(error?: string) {
  return `${inputClass} ${error ? 'border-rose-400 focus:ring-rose-200' : 'border-slate-300 focus:border-brand-500 focus:ring-brand-500/20'}`;
}

function ErrorText({ error }: { error?: string }) {
  return error ? <p role="alert" className="mt-1 text-xs text-rose-600">{error}</p> : null;
}

function MediaInput({ value, onChange, error, label, help, id }: {
  value: string; onChange: (v: string) => void; error?: string; label: string; help?: string; id: string;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const upload = async (file: File) => {
    setBusy(true);
    setUploadError(null);
    try {
      onChange((await websiteApi.uploadAsset(file)).url);
    } catch (err) {
      setUploadError(err instanceof PlatformApiError ? err.message : 'Upload failed.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-slate-600">{label}</label>
      <div className="flex gap-2">
        <input id={id} value={value} onChange={(e) => onChange(e.target.value)} className={cls(error)} maxLength={120} />
        <button type="button" disabled={busy} onClick={() => fileRef.current?.click()}
          className="mt-1 inline-flex shrink-0 items-center gap-1 rounded-lg border border-slate-300 px-3 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50">
          <Upload className="h-4 w-4" aria-hidden="true" /> {busy ? 'Uploading...' : 'Upload'}
        </button>
        <input ref={fileRef} type="file" accept="video/mp4,image/png,image/jpeg,image/webp" className="hidden" aria-label={`Upload ${label}`}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ''; }} />
      </div>
      {help && <p className="mt-1 text-xs text-slate-500">{help}</p>}
      <ErrorText error={uploadError ?? error} />
    </div>
  );
}

export function FieldEditor({ spec, value, onChange, path, errors }: {
  spec: FieldSpec; value: unknown; onChange: (v: unknown) => void; path: string; errors: Record<string, string>;
}) {
  const error = errors[path];
  const id = `f-${path.replace(/[^a-zA-Z0-9]/g, '-')}`;
  switch (spec.kind) {
    case 'text':
    case 'link':
    case 'color':
      return (
        <div>
          <label htmlFor={id} className="block text-xs font-medium text-slate-600">{spec.label}</label>
          <div className="flex items-center gap-2">
            {spec.kind === 'color' && <span className="mt-1 h-8 w-8 shrink-0 rounded border border-slate-300" style={{ backgroundColor: String(value ?? '') }} aria-hidden="true" />}
            <input id={id} value={String(value ?? '')} maxLength={spec.kind === 'text' ? spec.max : 300}
              onChange={(e) => onChange(spec.kind === 'link' && e.target.value === '' && path.endsWith('footer_link') ? null : e.target.value)}
              className={cls(error)} />
          </div>
          {'help' in spec && spec.help && <p className="mt-1 text-xs text-slate-500">{spec.help}</p>}
          <ErrorText error={error} />
        </div>
      );
    case 'textarea':
      return (
        <div>
          <label htmlFor={id} className="block text-xs font-medium text-slate-600">{spec.label}</label>
          <textarea id={id} value={String(value ?? '')} maxLength={spec.max} rows={3} onChange={(e) => onChange(e.target.value)} className={cls(error)} />
          <ErrorText error={error} />
        </div>
      );
    case 'media':
      return <MediaInput id={id} value={String(value ?? '')} onChange={onChange} error={error} label={spec.label} help={spec.help} />;
    case 'bool':
      return (
        <label className="inline-flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={value !== false} onChange={(e) => onChange(e.target.checked)} />
          {spec.label}
        </label>
      );
    case 'number':
      return (
        <div>
          <label htmlFor={id} className="block text-xs font-medium text-slate-600">{spec.label}</label>
          <input id={id} type="number" min={spec.min} step={spec.step ?? 'any'} value={value === null || value === undefined ? '' : String(value)}
            onChange={(e) => onChange(e.target.value === '' ? (spec.nullable ? null : 0) : Number(e.target.value))} className={cls(error)} />
          {spec.help && <p className="mt-1 text-xs text-slate-500">{spec.help}</p>}
          <ErrorText error={error} />
        </div>
      );
    case 'select':
      return (
        <div>
          <label htmlFor={id} className="block text-xs font-medium text-slate-600">{spec.label}</label>
          <select id={id} value={String(value ?? '')} onChange={(e) => onChange(e.target.value)} className={cls(error)}>
            {spec.options.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
          <ErrorText error={error} />
        </div>
      );
    case 'strings': {
      const items = Array.isArray(value) ? (value as string[]) : [];
      return (
        <fieldset>
          <legend className="text-xs font-medium text-slate-600">{spec.label}</legend>
          <div className="mt-1 space-y-2">
            {items.map((item, i) => (
              <div key={i} className="flex gap-2">
                <input aria-label={`${spec.label} ${i + 1}`} value={item} maxLength={300}
                  onChange={(e) => onChange(items.map((x, j) => (j === i ? e.target.value : x)))} className={cls(errors[`${path}.${i}`])} />
                <button type="button" aria-label={`Remove ${spec.label} ${i + 1}`} onClick={() => onChange(items.filter((_, j) => j !== i))}
                  className="mt-1 rounded-lg border border-slate-300 px-2 text-slate-500 hover:bg-slate-50"><Trash2 className="h-4 w-4" /></button>
              </div>
            ))}
            {(!spec.max || items.length < spec.max) && (
              <button type="button" onClick={() => onChange([...items, ''])} className="inline-flex items-center gap-1 text-sm font-medium text-brand-600">
                <Plus className="h-4 w-4" /> Add
              </button>
            )}
          </div>
          <ErrorText error={error} />
        </fieldset>
      );
    }
    case 'list':
      return <ListEditor spec={spec} value={value} onChange={onChange} path={path} errors={errors} />;
    default:
      return null;
  }
}

function ListEditor({ spec, value, onChange, path, errors }: {
  spec: Extract<FieldSpec, { kind: 'list' }>; value: unknown; onChange: (v: unknown) => void; path: string; errors: Record<string, string>;
}) {
  const items = Array.isArray(value) ? (value as Obj[]) : [];
  const [open, setOpen] = useState<number | null>(null);
  const move = (from: number, to: number) => {
    if (to < 0 || to >= items.length) return;
    const next = [...items];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChange(next);
    setOpen(to);
  };
  return (
    <fieldset className="rounded-lg border border-slate-200 p-3">
      <legend className="px-1 text-xs font-semibold text-slate-700">{spec.label} ({items.length})</legend>
      <ul className="space-y-2">
        {items.map((item, i) => {
          const itemPath = `${path}.${i}`;
          const hasError = Object.keys(errors).some((k) => k === itemPath || k.startsWith(`${itemPath}.`));
          const hidden = item.visible === false;
          return (
            <li key={i} className={`rounded-lg border ${hasError ? 'border-rose-300' : 'border-slate-200'} bg-white`}>
              <div className="flex items-center gap-1 px-2 py-1.5">
                <button type="button" onClick={() => setOpen(open === i ? null : i)} aria-expanded={open === i}
                  className="flex min-w-0 flex-1 items-center gap-1 text-left text-sm font-medium text-slate-800">
                  {open === i ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
                  <span className={`truncate ${hidden ? 'text-slate-400 line-through' : ''}`}>{spec.itemLabel(item, i)}</span>
                </button>
                {'visible' in item && (
                  <button type="button" aria-label={hidden ? 'Show' : 'Hide'} title={hidden ? 'Show' : 'Hide'}
                    onClick={() => onChange(items.map((x, j) => (j === i ? { ...x, visible: hidden } : x)))} className="rounded p-1 text-slate-500 hover:bg-slate-100">
                    {hidden ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                )}
                <button type="button" aria-label="Move up" onClick={() => move(i, i - 1)} disabled={i === 0} className="rounded p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30"><ArrowUp className="h-4 w-4" /></button>
                <button type="button" aria-label="Move down" onClick={() => move(i, i + 1)} disabled={i === items.length - 1} className="rounded p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30"><ArrowDown className="h-4 w-4" /></button>
                <button type="button" aria-label="Remove" onClick={() => { onChange(items.filter((_, j) => j !== i)); setOpen(null); }} className="rounded p-1 text-rose-500 hover:bg-rose-50"><Trash2 className="h-4 w-4" /></button>
              </div>
              {open === i && (
                <div className="space-y-3 border-t border-slate-100 p-3">
                  {spec.fields
                    .filter((f) => !('showIf' in f) || !f.showIf || f.showIf(item))
                    .map((f) => (
                      <FieldEditor key={f.key} spec={f} value={item[f.key]} path={`${itemPath}.${f.key}`} errors={errors}
                        onChange={(v) => onChange(items.map((x, j) => (j === i ? { ...x, [f.key]: v } : x)))} />
                    ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {(!spec.max || items.length < spec.max) && (
        <button type="button" onClick={() => { onChange([...items, spec.newItem()]); setOpen(items.length); }}
          className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-brand-600">
          <Plus className="h-4 w-4" /> Add {spec.label.toLowerCase().replace(/\s*\(.*\)$/, '').replace(/s$/, '')}
        </button>
      )}
      <ErrorText error={errors[path]} />
    </fieldset>
  );
}
