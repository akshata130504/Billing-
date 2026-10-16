/**
 * Which frontend files belong to which product module (modularization).
 *
 * Module keys follow src/entitlements/modules.json. Only the pilot module is mapped so far;
 * everything else stays unassigned until its own phase. Entries are paths relative to src/:
 * a trailing "/" maps a whole folder, otherwise a single file.
 */
export const MODULES: Record<string, string[]> = {
  projects: ['pages/projects/', 'services/projectService.ts'],
};
