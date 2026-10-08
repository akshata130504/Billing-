/**
 * Runtime access to the application UI configuration.
 *
 * - Tenant app: <UiConfigProvider> loads the PUBLISHED configuration once (GET /ui-config, cached
 *   by React Query and revalidated with an ETag) and applies the theme tokens.
 * - Visual-editor preview: <UiConfigOverride> supplies the editor's in-memory draft instead, plus
 *   a `selection` API so components can be picked; nothing is fetched or saved from here.
 *
 * Components read their page's overrides with usePageUi(key) and merge them over the registry
 * defaults; without a provider they get no overrides, i.e. the built-in UI.
 */
import { createContext, useContext, useEffect, useMemo, type HTMLAttributes, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../services/apiClient';
import { THEME_CSS_VARS, type PageConfigs, type PageKey, type ThemeConfig } from './registry';

export interface UiSelection {
  selectedId: string | null;
  select: (id: string) => void;
}

interface UiConfigValue {
  pages: PageConfigs;
  selection?: UiSelection;
}

const UiConfigContext = createContext<UiConfigValue>({ pages: {} });

const HEX = /^#[0-9a-fA-F]{6}$/;

/** Apply validated theme colours as CSS custom properties (never arbitrary CSS). */
export function applyTheme(theme: ThemeConfig | undefined, root: HTMLElement = document.documentElement): void {
  for (const [field, cssVar] of Object.entries(THEME_CSS_VARS)) {
    const value = theme?.[field as keyof ThemeConfig];
    if (typeof value === 'string' && HEX.test(value)) root.style.setProperty(cssVar, value);
    else root.style.removeProperty(cssVar);
  }
}

export interface UiConfigBundle {
  pages: PageConfigs;
  versions: Record<string, number>;
  etag: string;
}

export const UI_CONFIG_QUERY_KEY = ['ui-config'] as const;

export async function fetchUiConfig(): Promise<UiConfigBundle> {
  const { data } = await apiClient.get<UiConfigBundle>('/ui-config');
  return data;
}

/** Tenant app: published configuration for every page (defaults while loading or on error). */
export function UiConfigProvider({ children }: { children: ReactNode }) {
  const query = useQuery({
    queryKey: UI_CONFIG_QUERY_KEY,
    queryFn: fetchUiConfig,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
    retry: 1,
  });
  const pages = query.data?.pages ?? {};
  useEffect(() => {
    applyTheme(pages.theme);
  }, [pages.theme]);
  const value = useMemo(() => ({ pages }), [pages]);
  return <UiConfigContext.Provider value={value}>{children}</UiConfigContext.Provider>;
}

/** Visual-editor preview: a fixed (draft) configuration and component selection. */
export function UiConfigOverride({ pages, selection, children }: UiConfigValue & { children: ReactNode }) {
  useEffect(() => {
    applyTheme(pages.theme);
  }, [pages.theme]);
  const value = useMemo(() => ({ pages, selection }), [pages, selection]);
  return <UiConfigContext.Provider value={value}>{children}</UiConfigContext.Provider>;
}

export function usePageUi<K extends PageKey>(key: K): NonNullable<PageConfigs[K]> {
  return (useContext(UiConfigContext).pages[key] ?? {}) as NonNullable<PageConfigs[K]>;
}

export type EditableProps = HTMLAttributes<HTMLElement> & { 'data-ui-id'?: string };

/**
 * Returns a function giving the props that make an element selectable in the visual-editor
 * preview (highlighted when selected). Outside the editor every call returns {} so the tenant DOM
 * is unchanged. One hook call per component; call the returned function freely in loops.
 */
export function useUiEditable(): (id: string) => EditableProps {
  const selection = useContext(UiConfigContext).selection;
  return useMemo(() => {
    if (!selection) return () => ({});
    return (id: string) => ({
      'data-ui-id': id,
      style:
        selection.selectedId === id
          ? { outline: '2px solid #E83E8C', outlineOffset: '2px', borderRadius: '8px' }
          : { cursor: 'pointer' },
    });
  }, [selection]);
}
