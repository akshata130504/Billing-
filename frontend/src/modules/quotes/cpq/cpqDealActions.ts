import type { CPQDealOut } from '../../../types/catalog_cpq';

export interface CPQDealActionContext {
  /** Signed-in user's id; used to hide Approve on the user's own deal. */
  userId: string | null | undefined;
  /** finance+ may convert deals to quotes. */
  canEdit: boolean;
  /** admin+ may approve deals (mirrors the API's require_admin + not-own-deal rule). */
  canApprove: boolean;
}

export interface CPQDealActions {
  showApprove: boolean;
  showConvert: boolean;
  /** Text shown instead of the action buttons, if any. */
  note: string | null;
}

type DealLike = Pick<CPQDealOut, 'status' | 'approval_required'> & { created_by_id?: string | null };

/**
 * Which row actions a CPQ deal offers. Only offer what the API will accept: Approve for an admin
 * other than the creator while the deal awaits approval, Convert once the deal is approved (or
 * configured without needing approval).
 */
export function cpqDealActions(deal: DealLike, ctx: CPQDealActionContext): CPQDealActions {
  const status = deal.status as string;
  if (status === 'converted') return { showApprove: false, showConvert: false, note: 'Quote Generated' };
  if (status === 'rejected') return { showApprove: false, showConvert: false, note: 'Rejected' };

  const ownDeal = Boolean(deal.created_by_id && ctx.userId && deal.created_by_id === ctx.userId);
  if (status === 'pending_approval') {
    const showApprove = ctx.canApprove && !ownDeal;
    return {
      showApprove,
      showConvert: false,
      note: showApprove ? null : ownDeal && ctx.canApprove ? 'Awaiting approval by another admin' : 'Awaiting approval',
    };
  }

  const convertible = status === 'approved' || (status === 'configured' && !deal.approval_required);
  if (!convertible) return { showApprove: false, showConvert: false, note: null };
  if (!ctx.canEdit) return { showApprove: false, showConvert: false, note: 'View only' };
  return { showApprove: false, showConvert: true, note: null };
}
