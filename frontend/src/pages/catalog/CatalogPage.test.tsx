import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { CatalogPage } from './CatalogPage';
import { catalogCpqService } from '../../services/catalogCpqService';
import { dashboardSummaryService } from '../../services/dashboardSummaryService';

const showToast = vi.fn();

vi.mock('../../components/common/Toast', () => ({ useToast: () => ({ showToast }) }));
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ hasRole: () => true }) }));
vi.mock('../../services/catalogCpqService', () => ({
  catalogCpqService: {
    listOfferings: vi.fn(),
    listPriceBooks: vi.fn(),
    archiveOffering: vi.fn(),
    unarchiveOffering: vi.fn(),
    updateOffering: vi.fn(),
    createOffering: vi.fn(),
  },
}));
vi.mock('../../services/dashboardSummaryService', () => ({
  dashboardSummaryService: { catalog: vi.fn() },
}));
vi.mock('./components/OfferingModal', () => ({
  OfferingModal: ({ isOpen }: { isOpen: boolean }) => (isOpen ? <div>offering-modal-open</div> : null),
}));
vi.mock('./components/PriceBookModal', () => ({ PriceBookModal: () => null }));
vi.mock('../../components/common/ConfirmDialog', () => ({
  ConfirmDialog: ({ isOpen, onConfirm, confirmLabel }: any) =>
    isOpen ? <button onClick={() => void onConfirm()}>confirm-{confirmLabel}</button> : null,
}));

function Search() {
  return <div data-testid="search">{useLocation().search}</div>;
}

function renderCatalog(path = '/catalog') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <CatalogPage />
      <Search />
    </MemoryRouter>
  );
}

function offering(id: string, name: string, is_active: boolean) {
  return {
    id,
    name,
    sku: `SKU-${id}`,
    type: 'product',
    pricing_model: 'flat',
    base_price: 100,
    unit: 'unit',
    billing_frequency: 'one_time',
    is_active,
  } as any;
}

describe('<CatalogPage /> archived offerings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(catalogCpqService.listOfferings).mockResolvedValue({
      items: [offering('a1', 'Active One', true), offering('x1', 'Archived One', false)],
      total: 2,
    } as any);
    vi.mocked(catalogCpqService.listPriceBooks).mockResolvedValue({ items: [], total: 0 } as any);
    vi.mocked(dashboardSummaryService.catalog).mockResolvedValue({
      offerings: { total: 2, active: 1, by_type: {} },
    } as any);
    vi.mocked(catalogCpqService.archiveOffering).mockResolvedValue(undefined);
    vi.mocked(catalogCpqService.unarchiveOffering).mockResolvedValue(offering('x1', 'Archived One', true));
  });

  const rowOf = (name: string) => screen.getByText(name).closest('tr') as HTMLElement;
  const within = (row: HTMLElement, title: string) => row.querySelector(`button[title="${title}"]`);

  it('archived row shows Unarchive and no Edit/Archive; active row is unchanged', async () => {
    renderCatalog();
    await waitFor(() => expect(screen.getByText('Archived One')).toBeInTheDocument());

    const archived = rowOf('Archived One');
    expect(archived).toHaveTextContent('Archived');
    expect(within(archived, 'Edit Offering')).toBeNull();
    expect(within(archived, 'Archive Offering')).toBeNull();
    expect(within(archived, 'Unarchive Offering')).not.toBeNull();

    const active = rowOf('Active One');
    expect(within(active, 'Edit Offering')).not.toBeNull();
    expect(within(active, 'Archive Offering')).not.toBeNull();
    expect(within(active, 'Unarchive Offering')).toBeNull();
  });

  it('Unarchive calls the service, toasts and reloads', async () => {
    renderCatalog();
    await waitFor(() => expect(screen.getByText('Archived One')).toBeInTheDocument());
    const loadsBefore = vi.mocked(catalogCpqService.listOfferings).mock.calls.length;

    fireEvent.click(within(rowOf('Archived One'), 'Unarchive Offering') as HTMLElement);
    fireEvent.click(screen.getByText('confirm-Unarchive'));

    await waitFor(() => expect(catalogCpqService.unarchiveOffering).toHaveBeenCalledWith('x1'));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('success', 'Offering unarchived'));
    await waitFor(() =>
      expect(vi.mocked(catalogCpqService.listOfferings).mock.calls.length).toBeGreaterThan(loadsBefore)
    );
    expect(catalogCpqService.archiveOffering).not.toHaveBeenCalled();
  });

  it('shows an error toast when unarchive fails', async () => {
    vi.mocked(catalogCpqService.unarchiveOffering).mockRejectedValue(new Error('nope'));
    renderCatalog();
    await waitFor(() => expect(screen.getByText('Archived One')).toBeInTheDocument());
    fireEvent.click(within(rowOf('Archived One'), 'Unarchive Offering') as HTMLElement);
    fireEvent.click(screen.getByText('confirm-Unarchive'));
    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith('error', 'Could not unarchive offering', expect.anything())
    );
  });

  it('Edit on an active row opens the modal; Archive still archives', async () => {
    renderCatalog();
    await waitFor(() => expect(screen.getByText('Active One')).toBeInTheDocument());

    fireEvent.click(within(rowOf('Active One'), 'Edit Offering') as HTMLElement);
    expect(screen.getByText('offering-modal-open')).toBeInTheDocument();

    fireEvent.click(within(rowOf('Active One'), 'Archive Offering') as HTMLElement);
    fireEvent.click(screen.getByText('confirm-Archive'));
    await waitFor(() => expect(catalogCpqService.archiveOffering).toHaveBeenCalledWith('a1'));
    expect(catalogCpqService.unarchiveOffering).not.toHaveBeenCalled();
  });
});

describe('<CatalogPage /> quick-action deep link (BUG-51)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(catalogCpqService.listOfferings).mockResolvedValue({ items: [], total: 0 } as any);
    vi.mocked(catalogCpqService.listPriceBooks).mockResolvedValue({ items: [], total: 0 } as any);
    vi.mocked(dashboardSummaryService.catalog).mockResolvedValue({ offerings: { total: 0, active: 0, by_type: {} } } as any);
  });

  it('opens the new-offering form for /catalog?new=product and drops the parameter', async () => {
    renderCatalog('/catalog?new=product');
    expect(await screen.findByText('offering-modal-open')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('search').textContent).toBe(''));
  });

  it('does not open the form without the parameter', async () => {
    renderCatalog();
    await waitFor(() => expect(catalogCpqService.listOfferings).toHaveBeenCalled());
    expect(screen.queryByText('offering-modal-open')).toBeNull();
  });
});
