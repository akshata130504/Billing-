import type { BadgeProps } from '../../components/common/Badge';
import type { CreditNoteStatus } from '../../services/creditNoteService';

export const CREDIT_NOTE_STATUS_LABELS: Record<CreditNoteStatus, string> = {
  draft: 'Draft',
  issued: 'Issued',
  partially_applied: 'Partially applied',
  applied: 'Applied',
  void: 'Void',
};

export function creditNoteStatusVariant(status: string): NonNullable<BadgeProps['variant']> {
  switch (status) {
    case 'issued':
      return 'primary';
    case 'partially_applied':
      return 'warning';
    case 'applied':
      return 'success';
    case 'void':
      return 'danger';
    default:
      return 'neutral';
  }
}

export function creditNoteStatusLabel(status: string): string {
  return CREDIT_NOTE_STATUS_LABELS[status as CreditNoteStatus] ?? status;
}
