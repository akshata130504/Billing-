import { describe, expect, it } from 'vitest';
import { cpqDealActions } from './cpqDealActions';

const admin = { userId: 'u-admin', canEdit: true, canApprove: true };
const finance = { userId: 'u-fin', canEdit: true, canApprove: false };
const viewer = { userId: 'u-view', canEdit: false, canApprove: false };

describe('cpqDealActions', () => {
  it('does not offer Approve on the admin\'s own pending deal, nor Convert before approval', () => {
    const deal = { status: 'pending_approval' as const, approval_required: true, created_by_id: 'u-admin' };
    expect(cpqDealActions(deal, admin)).toEqual({
      showApprove: false,
      showConvert: false,
      note: 'Awaiting approval by another admin',
    });
  });

  it('offers Approve to another admin while the deal awaits approval', () => {
    const deal = { status: 'pending_approval' as const, approval_required: true, created_by_id: 'u-other' };
    expect(cpqDealActions(deal, admin)).toEqual({ showApprove: true, showConvert: false, note: null });
  });

  it('never offers Approve to finance users (the API requires admin)', () => {
    const deal = { status: 'pending_approval' as const, approval_required: true, created_by_id: 'u-other' };
    expect(cpqDealActions(deal, finance)).toEqual({ showApprove: false, showConvert: false, note: 'Awaiting approval' });
  });

  it('offers Convert once approved, or when configured without approval', () => {
    expect(cpqDealActions({ status: 'approved', approval_required: true }, finance).showConvert).toBe(true);
    expect(cpqDealActions({ status: 'configured', approval_required: false }, finance).showConvert).toBe(true);
    expect(cpqDealActions({ status: 'configured', approval_required: true }, finance).showConvert).toBe(false);
  });

  it('shows the generated / rejected / view-only states instead of actions', () => {
    expect(cpqDealActions({ status: 'converted', approval_required: false }, admin).note).toBe('Quote Generated');
    expect(cpqDealActions({ status: 'rejected', approval_required: true }, admin).note).toBe('Rejected');
    expect(cpqDealActions({ status: 'approved', approval_required: true }, viewer)).toEqual({
      showApprove: false,
      showConvert: false,
      note: 'View only',
    });
  });
});
