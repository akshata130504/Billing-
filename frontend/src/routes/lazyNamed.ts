import { lazy, type ComponentType, type LazyExoticComponent } from 'react';

/**
 * React.lazy for modules that use named exports:
 *   const CatalogPage = lazyNamed(() => import('../pages/catalog/CatalogPage'), 'CatalogPage');
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function lazyNamed<M, K extends keyof M>(
  loader: () => Promise<M>,
  key: K
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
): LazyExoticComponent<M[K] extends ComponentType<any> ? M[K] : never> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return lazy(() => loader().then((module) => ({ default: module[key] as any })));
}
