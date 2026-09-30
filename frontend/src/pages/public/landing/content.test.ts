import { afterEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_LANDING_CONTENT, applySeo, fetchPublishedLanding } from './content';

afterEach(() => vi.unstubAllGlobals());

describe('public landing content loader', () => {
  it('requests only the published endpoint, without credentials', async () => {
    const published = JSON.parse(JSON.stringify(DEFAULT_LANDING_CONTENT));
    published.hero.headline = 'Published headline';
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ content: published, version: 7 }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const content = await fetchPublishedLanding('/api/v1');
    expect(content.hero.headline).toBe('Published headline');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/public/website/landing');
    expect(init.credentials).toBe('omit');
    expect(String(url)).not.toMatch(/draft|preview|version/);
  });

  it('falls back to the original page content when the API fails or returns junk', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    expect(await fetchPublishedLanding('/api/v1')).toBe(DEFAULT_LANDING_CONTENT);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"content":{"hero":1}}', { status: 200 })));
    expect(await fetchPublishedLanding('/api/v1')).toBe(DEFAULT_LANDING_CONTENT);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('nope', { status: 500 })));
    expect(await fetchPublishedLanding('/api/v1')).toBe(DEFAULT_LANDING_CONTENT);
  });

  it('applies the SEO title and description', () => {
    const edited = JSON.parse(JSON.stringify(DEFAULT_LANDING_CONTENT));
    edited.seo = { title: 'New title', description: 'New description' };
    applySeo(edited);
    expect(document.title).toBe('New title');
    expect(document.querySelector('meta[name="description"]')?.getAttribute('content')).toBe('New description');
  });
});
