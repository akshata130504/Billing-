import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatCard } from './StatCard';
import { formatMoney } from '../../utils/format';

describe('<StatCard />', () => {
  it('renders the title and a pre-formatted money value verbatim', () => {
    render(<StatCard title="Outstanding" value={formatMoney('125000.50')} />);
    expect(screen.getByText('Outstanding')).toBeInTheDocument();
    expect(screen.getByText('₹1,25,000.50')).toBeInTheDocument();
  });

  it('renders a numeric value', () => {
    render(<StatCard title="Open invoices" value={12} />);
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('renders zero rather than hiding the tile', () => {
    render(<StatCard title="Overdue" value={0} />);
    expect(screen.getByText('0')).toBeInTheDocument();
  });

  it('shows no change chip or comparison text when neither is supplied', () => {
    const { container } = render(<StatCard title="Collected" value="₹0.00" />);
    expect(container.querySelector('.bg-emerald-50')).toBeNull();
    expect(container.querySelector('.bg-rose-50')).toBeNull();
  });

  it('renders a positive change in green with an up arrow', () => {
    const { container } = render(
      <StatCard title="MRR" value="₹1,00,000.00" change="+12.5%" isPositive comparisonText="vs last month" />
    );
    const chip = screen.getByText('+12.5%');
    expect(chip.className).toContain('bg-emerald-50');
    expect(screen.getByText('vs last month')).toBeInTheDocument();
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('renders a negative change in red', () => {
    render(<StatCard title="MRR" value="₹90,000.00" change="-8.0%" isPositive={false} />);
    expect(screen.getByText('-8.0%').className).toContain('bg-rose-50');
  });

  it('treats change as positive by default', () => {
    render(<StatCard title="MRR" value="₹1.00" change="+1%" />);
    expect(screen.getByText('+1%').className).toContain('bg-emerald-50');
  });

  it('renders comparison text on its own', () => {
    render(<StatCard title="Cash in" value="₹5,000.00" comparisonText="last 30 days" />);
    expect(screen.getByText('last 30 days')).toBeInTheDocument();
  });

  it('renders a supplied icon and merges a className', () => {
    const { container } = render(
      <StatCard title="Cash" value="₹1.00" icon={<span data-testid="icon">₹</span>} className="col-span-2" />
    );
    expect(screen.getByTestId('icon')).toBeInTheDocument();
    expect(container.firstElementChild!.className).toContain('col-span-2');
  });
});
