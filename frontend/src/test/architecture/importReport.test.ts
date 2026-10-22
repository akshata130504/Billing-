import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { MODULES } from './moduleMap';

// Report-only import-boundary check (modularization P0). It never fails on an import between
// modules: it lists who imports each mapped module (inbound, production code and tests apart,
// since vi.mock paths are coupling too) and what the module imports (outbound), and only
// asserts that the scan itself works. The report is printed to the test output.

const SRC = resolve(__dirname, '../..');
const EXTENSIONS = ['', '.ts', '.tsx', '/index.ts', '/index.tsx'];
// import ... from 'x' | export ... from 'x' | import 'x' | import('x') | vi.mock('x')
const SPECIFIER = /(?:\bfrom\s+|\bimport\s*\(\s*|\bimport\s+|\bvi\.mock\(\s*)['"]([^'"]+)['"]/g;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.(ts|tsx)$/.test(name) && !name.endsWith('.d.ts') ? [full] : [];
  });
}

const rel = (file: string) => relative(SRC, file).split('\\').join('/');

/** src-relative file a specifier points at, or null for packages and unresolvable paths. */
function resolveSpecifier(fromFile: string, spec: string): string | null {
  let base: string;
  if (spec.startsWith('@/')) base = join(SRC, spec.slice(2));
  else if (spec.startsWith('.')) base = resolve(dirname(fromFile), spec);
  else return null;
  for (const ext of EXTENSIONS) {
    const candidate = base + ext;
    if (existsSync(candidate) && statSync(candidate).isFile()) return rel(candidate);
  }
  return null;
}

function moduleOf(path: string): string | null {
  for (const [key, entries] of Object.entries(MODULES)) {
    if (entries.some((entry) => (entry.endsWith('/') ? path.startsWith(entry) : path === entry))) return key;
  }
  return null;
}

const isTest = (path: string) => /\.test\.tsx?$/.test(path) || path.startsWith('test/');

function buildReport() {
  const files = sourceFiles(SRC);
  const unresolved: string[] = [];
  // Importing a path with a ?raw suffix reads a file's source text: tests that assert on another
  // file's text break (or silently stop applying) when that file moves or is rewritten.
  const rawSourceReads: string[] = [];
  const inbound: Record<string, { code: Set<string>; tests: Set<string> }> = {};
  const outbound: Record<string, Set<string>> = {};
  for (const key of Object.keys(MODULES)) {
    inbound[key] = { code: new Set(), tests: new Set() };
    outbound[key] = new Set();
  }
  for (const file of files) {
    const from = rel(file);
    const fromModule = moduleOf(from);
    for (const match of readFileSync(file, 'utf8').matchAll(SPECIFIER)) {
      const [spec, query] = match[1].split('?');
      const to = resolveSpecifier(file, spec);
      if (to && query === 'raw') {
        rawSourceReads.push(`${from} reads the text of ${to}`);
        continue;
      }
      if (!to) {
        if (spec.startsWith('.') || spec.startsWith('@/')) unresolved.push(`${from} -> ${match[1]}`);
        continue;
      }
      const toModule = moduleOf(to);
      if (toModule === fromModule) continue;
      if (toModule) inbound[toModule][isTest(from) ? 'tests' : 'code'].add(`${from} -> ${to}`);
      if (fromModule && !isTest(from)) outbound[fromModule].add(`${from} -> ${to}`);
    }
  }
  return { filesScanned: files.length, unresolved, rawSourceReads, inbound, outbound };
}

function format(report: ReturnType<typeof buildReport>): string {
  const lines = [`Import report: ${report.filesScanned} files scanned under src/`];
  for (const key of Object.keys(MODULES).sort()) {
    const { code, tests } = report.inbound[key];
    lines.push(`\n[${key}] inbound from code (${code.size}):`, ...[...code].sort().map((l) => `  ${l}`));
    lines.push(`[${key}] inbound from tests (${tests.size}):`, ...[...tests].sort().map((l) => `  ${l}`));
    const out = [...report.outbound[key]].sort();
    lines.push(`[${key}] outbound (${out.length}):`, ...out.map((l) => `  ${l}`));
  }
  lines.push(`\nSource-text reads (?raw) (${report.rawSourceReads.length}):`, ...report.rawSourceReads.sort().map((l) => `  ${l}`));
  if (report.unresolved.length) {
    lines.push(`\nUnresolved local imports (${report.unresolved.length}):`, ...report.unresolved.map((l) => `  ${l}`));
  }
  return lines.join('\n');
}

describe('import report (report-only)', () => {
  const report = buildReport();

  it('scans the source tree and prints the report', () => {
    console.info(format(report));
    expect(report.filesScanned).toBeGreaterThan(0);
  });

  it('maps only paths that exist', () => {
    for (const entries of Object.values(MODULES)) {
      for (const entry of entries) expect(existsSync(join(SRC, entry)), entry).toBe(true);
    }
  });

  it('sees the known entry points, so it cannot silently under-report', () => {
    // Scanner self-check: lazy route imports, plain imports and vi.mock paths are all followed.
    const { code, tests } = report.inbound.projects;
    expect(code).toContain('routes/index.tsx -> pages/projects/ProjectsPage.tsx');
    expect(code).toContain('pages/expenses/useCustomerProjects.ts -> services/projectService.ts');
    expect(tests).toContain('modules/timesheets/TimeEntryModal.test.tsx -> services/projectService.ts');
    expect(report.rawSourceReads).toContain('routes/AdminRoutes.test.tsx reads the text of routes/index.tsx');
  });
});
