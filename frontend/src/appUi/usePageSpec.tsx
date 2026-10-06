/**
 * usePageSpec(key): the one API a module page uses to read its visual-editor configuration.
 *
 *   const ui = usePageSpec('quotes');
 *   <h1 {...ui.edit('header')}>{ui.text('header', 'title')}</h1>
 *   {ui.render('kpis', { total: (item, edit) => <Kpi {...edit} label={item.label} caption={item.caption} /> })}
 *   ui.shown('columns')            // visible columns, configured order
 *
 * Published overrides (or the editor's draft, in the preview) are merged over the spec defaults,
 * so with no configuration every page renders exactly its built-in UI. Values are plain text and
 * are only ever rendered as React text nodes. `edit(id)` returns {} outside the visual editor.
 */
import { Fragment, useMemo, type ReactNode } from 'react';
import { PAGE_SPECS, fillTokens, resolveList, type ItemOverride, type ListDef, type ResolvedItem, type SpecConfig } from './registry';
import { usePageUi, useUiEditable, type EditableProps } from './UiConfigContext';

export type ItemRenderer = (item: ResolvedItem, edit: EditableProps) => ReactNode;

export interface SpecUi {
  /** A text field's configured value (or its default), with {tokens} filled in. */
  text: (group: string, field: string, tokens?: Record<string, string>) => string;
  /** Every entry of a list, configured order, with hidden flags. */
  items: (list: string) => ResolvedItem[];
  /** Visible entries of a list, configured order. */
  shown: (list: string) => ResolvedItem[];
  /** One list entry's configured label. */
  label: (list: string, key: string) => string;
  /** Render a list's visible entries in configured order. Entries without a renderer are skipped
   *  (e.g. cards a member's role does not show), so pass only those this render can show. */
  render: (list: string, renderers: Partial<Record<string, ItemRenderer>>) => ReactNode[];
  /** Selection props for the editor preview: 'header', 'kpis', 'kpis.total'... */
  edit: (id: string) => EditableProps;
}

const STRICT = import.meta.env.DEV || import.meta.env.MODE === 'test';

function missing(what: string): never | undefined {
  // Typos surface in development and tests; production keeps rendering with an empty value.
  if (STRICT) throw new Error(`usePageSpec: ${what}`);
  return undefined;
}

export function usePageSpec(key: string): SpecUi {
  const spec = PAGE_SPECS[key];
  if (!spec) missing(`no spec for page '${key}'`);
  const config = usePageUi(key) as SpecConfig;
  const editable = useUiEditable();

  return useMemo<SpecUi>(() => {
    const lists = new Map<string, ResolvedItem[]>();
    const listOf = (id: string): ResolvedItem[] => {
      const cached = lists.get(id);
      if (cached) return cached;
      const list = spec?.lists?.find((l) => l.id === id);
      if (!list) return missing(`page '${key}' has no list '${id}'`) ?? [];
      const defs: ListDef[] = list.items.map((i) => ({
        key: i.key, label: i.label,
        // A list whose entries cannot be hidden treats every entry as required.
        required: i.required || list.hide === false,
        caption: i.caption,
      }));
      const overrides = Array.isArray(config[id]) ? (config[id] as ItemOverride[]) : undefined;
      let resolved = resolveList(defs, overrides);
      if (list.reorder === false) {
        const order = list.items.map((i) => i.key);
        resolved = [...resolved].sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
      }
      lists.set(id, resolved);
      return resolved;
    };
    const edit = (id: string) => editable(`${key}.${id}`);

    return {
      text(group, field, tokens) {
        const def = spec?.texts?.find((g) => g.id === group)?.fields.find((f) => f.name === field);
        if (!def) return missing(`page '${key}' has no text '${group}.${field}'`) ?? '';
        const values = config[group];
        const value = values && !Array.isArray(values) && typeof values === 'object' ? values[field] : undefined;
        const text = typeof value === 'string' && value ? value : def.default;
        return tokens ? fillTokens(text, tokens) : text;
      },
      items: listOf,
      shown: (id) => listOf(id).filter((i) => !i.hidden),
      label: (id, itemKey) => listOf(id).find((i) => i.key === itemKey)?.label ?? missing(`'${id}' has no '${itemKey}'`) ?? '',
      render(id, renderers) {
        return listOf(id)
          .filter((i) => !i.hidden && renderers[i.key])
          .map((i) => <Fragment key={i.key}>{renderers[i.key]!(i, edit(`${id}.${i.key}`))}</Fragment>);
      },
      edit,
    };
  }, [spec, key, config, editable]);
}
