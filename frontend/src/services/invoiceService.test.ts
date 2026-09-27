import { beforeEach, describe, expect, it, vi } from 'vitest';
import { invoiceService } from './invoiceService';
import * as downloadModule from './download';

vi.mock('./download', () => ({
  downloadAuthenticated: vi.fn().mockResolvedValue(undefined),
}));

// Browser QA: the staff invoice page had no way to get the GST tax-invoice PDF although
// GET /invoices/{id}/pdf existed; it now downloads it like the quote page does.
describe('invoiceService PDF export', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('downloads the invoice PDF with the invoice number as file name (slashes made safe)', async () => {
    await invoiceService.downloadPdf('inv-1', 'INV/26-27/00011');
    expect(downloadModule.downloadAuthenticated).toHaveBeenCalledWith(
      expect.stringContaining('/invoices/inv-1/pdf'),
      'Invoice-INV_26-27_00011.pdf'
    );
  });

  it('falls back to the id', async () => {
    await invoiceService.downloadPdf('inv-2');
    expect(downloadModule.downloadAuthenticated).toHaveBeenCalledWith(
      expect.stringContaining('/invoices/inv-2/pdf'),
      'Invoice-inv-2.pdf'
    );
  });
});
