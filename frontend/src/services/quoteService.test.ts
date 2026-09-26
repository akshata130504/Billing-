import { describe, it, expect, vi, beforeEach } from 'vitest';
import { quoteService } from './quoteService';
import * as downloadModule from './download';

vi.mock('./download', () => ({
  downloadAuthenticated: vi.fn().mockResolvedValue(undefined),
}));

describe('quoteService PDF export', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('builds the correct quote PDF download URL', () => {
    const url = quoteService.getDownloadPdfUrl('test-quote-123');
    expect(url).toContain('/quotes/test-quote-123/pdf');
  });

  it('downloads quote PDF using downloadAuthenticated with custom quote number filename', async () => {
    await quoteService.downloadPdf('test-quote-123', 'QT-000099');

    expect(downloadModule.downloadAuthenticated).toHaveBeenCalledTimes(1);
    expect(downloadModule.downloadAuthenticated).toHaveBeenCalledWith(
      expect.stringContaining('/quotes/test-quote-123/pdf'),
      'Quote-QT-000099.pdf'
    );
  });

  it('falls back to quote ID when quote number is not provided', async () => {
    await quoteService.downloadPdf('test-quote-123');

    expect(downloadModule.downloadAuthenticated).toHaveBeenCalledTimes(1);
    expect(downloadModule.downloadAuthenticated).toHaveBeenCalledWith(
      expect.stringContaining('/quotes/test-quote-123/pdf'),
      'Quote-test-quote-123.pdf'
    );
  });
});
