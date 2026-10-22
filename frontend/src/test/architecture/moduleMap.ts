/**
 * Which frontend files belong to which product module (modularization).
 *
 * Module keys follow src/entitlements/modules.json. Only modules whose frontend has moved are
 * mapped; everything else stays unassigned until its own phase. Entries are paths relative to src/:
 * a trailing "/" maps a whole folder, otherwise a single file.
 */
export const MODULES: Record<string, string[]> = {
  projects: ['pages/projects/', 'services/projectService.ts'],
  // Products, plans and the catalog page (offerings and price books). pages/plans-pricing (/pricing) stays unassigned.
  products: ['modules/products/', 'pages/catalog/', 'services/catalogService.ts'],
  // services/customerService.ts stays shared: it has 28 importers across other features.
  customers: ['modules/customers/', 'pages/customers/'],
  timesheets: ['modules/timesheets/', 'pages/timesheets/'],
};
