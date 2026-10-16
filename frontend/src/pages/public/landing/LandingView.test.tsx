import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LandingView } from '../LandingView';
import { DEFAULT_LANDING_CONTENT, isLandingContent } from './content';
import { buildBreakdown, calculatePrice } from './pricing';
import type { LandingContent } from './types';

let authenticated = false;
vi.mock('../../../hooks/useAuth', () => ({ useAuth: () => ({ isAuthenticated: authenticated }) }));

class NoopObserver {
  observe() {}
  disconnect() {}
  unobserve() {}
}

beforeEach(() => {
  vi.stubGlobal('IntersectionObserver', NoopObserver);
  if (!window.matchMedia) {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {},
      addListener: () => {}, removeListener: () => {}, onchange: null, dispatchEvent: () => false,
    }));
  }
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('CMS landing content', () => {
  it('seeded content validates', () => {
    expect(isLandingContent(DEFAULT_LANDING_CONTENT)).toBe(true);
  });

  it('renders the seeded page signed out and signed in', () => {
    for (const isAuth of [false, true]) {
      authenticated = isAuth;
      const { container, unmount } = render(
        <MemoryRouter><LandingView content={DEFAULT_LANDING_CONTENT} isAuthenticated={isAuth} /></MemoryRouter>
      );
      expect(container.querySelector('#pricing-models .grid')!.children).toHaveLength(5);
      expect(container.querySelectorAll('#workflow .min-w-\\[800px\\] > button')).toHaveLength(9);
      unmount();
    }
  });
});

// Reference implementation copied verbatim from the original page (the pre-CMS pricingModels and
// currentBreakdown), used to prove the parameterised calculator is exact for every quantity.
function legacyCalculate(model: number, qty: number): number {
  switch (model) {
    case 0: return 299;
    case 1: return qty * 15;
    case 2: { const rate = qty > 200 ? 10 : qty > 50 ? 14 : 20; return qty * rate; }
    case 3: {
      let total = 0;
      total += Math.min(qty, 50) * 20;
      if (qty > 50) total += Math.min(qty - 50, 100) * 12;
      if (qty > 150) total += (qty - 150) * 8;
      return total;
    }
    default: return Math.ceil(qty / 50) * 450;
  }
}

describe('illustrative pricing calculator', () => {
  const models = DEFAULT_LANDING_CONTENT.pricing.models;

  it('matches the original arithmetic for every quantity 1..500', () => {
    for (let m = 0; m < 5; m++) {
      for (let qty = 1; qty <= 500; qty++) {
        expect(calculatePrice(models[m], qty)).toBe(legacyCalculate(m, qty));
        expect(buildBreakdown(models[m], qty).finalPrice).toBe(legacyCalculate(m, qty));
      }
    }
  });

  it('recalculates from edited example values without code changes', () => {
    const edited: LandingContent = JSON.parse(JSON.stringify(DEFAULT_LANDING_CONTENT));
    edited.pricing.models[0].price = 499;
    edited.pricing.models[1].price = 20;
    edited.pricing.models[4].bundle_size = 25;
    edited.pricing.models[4].price = 300;
    expect(calculatePrice(edited.pricing.models[0], 10)).toBe(499);
    expect(buildBreakdown(edited.pricing.models[0], 1).formula).toBe('Fixed Platform Rate = ₹499.00 / month');
    expect(calculatePrice(edited.pricing.models[1], 10)).toBe(200);
    expect(buildBreakdown(edited.pricing.models[4], 60).quantity).toBe('3 bundles');
    expect(calculatePrice(edited.pricing.models[4], 60)).toBe(900);
  });
});

describe('content controls', () => {
  it('hides invisible sections and items, reorders sections, and keeps links safe', () => {
    authenticated = false;
    const edited: LandingContent = JSON.parse(JSON.stringify(DEFAULT_LANDING_CONTENT));
    edited.faq.visible = false;
    edited.hero.visible = false;
    edited.operations.cards[0].visible = false;
    edited.section_order = ['final_cta', ...edited.section_order.filter((k) => k !== 'final_cta')];
    edited.footer.columns[0].links[0] = { label: 'Docs', link: 'https://docs.example.com/start' };
    const { container } = render(<MemoryRouter><LandingView content={edited} isAuthenticated={false} /></MemoryRouter>);
    expect(container.querySelector('#faq')).toBeNull();
    expect(container.textContent).not.toContain('Powerful billing.');
    expect(container.textContent).not.toContain('Centralized inbox for pending invoices');
    const sections = Array.from(container.querySelectorAll('section'));
    expect(sections[0].textContent).toContain('Ready to simplify your billing?');
    const external = Array.from(container.querySelectorAll('a')).find((a) => a.textContent === 'Docs')!;
    expect(external.getAttribute('href')).toBe('https://docs.example.com/start');
    expect(external.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('renders markup-looking text as text, never as HTML', () => {
    const edited: LandingContent = JSON.parse(JSON.stringify(DEFAULT_LANDING_CONTENT));
    edited.hero.headline = '<img src=x onerror=alert(1)>';
    const { container } = render(<MemoryRouter><LandingView content={edited} isAuthenticated={false} /></MemoryRouter>);
    expect(container.querySelector('img[src="x"]')).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>');
  });
});
