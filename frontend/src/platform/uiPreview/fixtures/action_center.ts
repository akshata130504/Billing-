/**
 * Visual-editor preview sample data for the Action Center (/control-center/action-center).
 * Its only request on mount, GET /action-center, is already answered by the built-in
 * `sampleActionCenter` route in ../sampleData.ts (built-in routes win), so nothing is added here.
 */
export const routes: Record<string, (query: URLSearchParams) => unknown> = {};
