"""0018_payment_integrity_and_credit_note_gst

- payments.gateway_payment_id: guarantee a UNIQUE index (NULLs allowed, so offline
  payments without a gateway id are unaffected). One Razorpay payment can then never
  settle two Payment rows (signature/payment-id replay).
- credit_notes / credit_note_lines: CGST/SGST/IGST heads plus the frozen place of
  supply and GSTINs, mirroring invoices.

Written defensively (inspector checks) so it is safe on databases that were
bootstrapped with Base.metadata.create_all.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-25 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


GATEWAY_PAYMENT_UNIQUE_INDEX = 'uq_payments_gateway_payment_id'

CREDIT_NOTE_COLUMNS = (
    ('cgst_amount', lambda: sa.Column('cgst_amount', sa.Numeric(14, 2), nullable=False, server_default='0')),
    ('sgst_amount', lambda: sa.Column('sgst_amount', sa.Numeric(14, 2), nullable=False, server_default='0')),
    ('igst_amount', lambda: sa.Column('igst_amount', sa.Numeric(14, 2), nullable=False, server_default='0')),
    ('supply_type', lambda: sa.Column('supply_type', sa.String(length=16), nullable=True)),
    ('place_of_supply_code', lambda: sa.Column('place_of_supply_code', sa.String(length=2), nullable=True)),
    ('place_of_supply_name', lambda: sa.Column('place_of_supply_name', sa.String(length=120), nullable=True)),
    ('customer_gstin', lambda: sa.Column('customer_gstin', sa.String(length=15), nullable=True)),
    ('supplier_gstin', lambda: sa.Column('supplier_gstin', sa.String(length=15), nullable=True)),
)

CREDIT_NOTE_LINE_COLUMNS = (
    ('cgst_amount', lambda: sa.Column('cgst_amount', sa.Numeric(14, 2), nullable=False, server_default='0')),
    ('sgst_amount', lambda: sa.Column('sgst_amount', sa.Numeric(14, 2), nullable=False, server_default='0')),
    ('igst_amount', lambda: sa.Column('igst_amount', sa.Numeric(14, 2), nullable=False, server_default='0')),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table_name):
    insp = _inspector()
    if not insp.has_table(table_name):
        return None
    return {c['name'] for c in insp.get_columns(table_name)}


def _add_columns(table_name, specs):
    existing = _columns(table_name)
    if existing is None:
        return
    missing = [factory() for name, factory in specs if name not in existing]
    if not missing:
        return
    with op.batch_alter_table(table_name) as batch:
        for column in missing:
            batch.add_column(column)


def _drop_columns(table_name, names):
    existing = _columns(table_name)
    if existing is None:
        return
    present = [n for n in names if n in existing]
    if not present:
        return
    with op.batch_alter_table(table_name) as batch:
        for name in present:
            batch.drop_column(name)


def _gateway_payment_id_is_unique() -> bool:
    insp = _inspector()
    for ix in insp.get_indexes('payments'):
        if ix.get('unique') and list(ix.get('column_names') or []) == ['gateway_payment_id']:
            return True
    for uc in insp.get_unique_constraints('payments'):
        if list(uc.get('column_names') or []) == ['gateway_payment_id']:
            return True
    return False


def upgrade() -> None:
    insp = _inspector()
    if insp.has_table('payments') and not _gateway_payment_id_is_unique():
        bind = op.get_bind()
        duplicates = bind.execute(
            sa.text(
                "SELECT gateway_payment_id FROM payments WHERE gateway_payment_id IS NOT NULL "
                "GROUP BY gateway_payment_id HAVING COUNT(*) > 1"
            )
        ).fetchall()
        if duplicates:
            # Do not block startup (a failed migration keeps the API down -> nginx 502). The
            # application already rejects a second settlement of the same gateway payment
            # (pre-check + savepoint); the index is added by re-running once reconciled.
            print(
                "WARNING [0018]: skipped the unique index on payments.gateway_payment_id - duplicate "
                f"gateway payment ids exist ({', '.join(str(r[0]) for r in duplicates[:10])}). Reconcile them "
                "(each Razorpay payment may settle only one Payment row), then create the index manually: "
                f"CREATE UNIQUE INDEX {GATEWAY_PAYMENT_UNIQUE_INDEX} ON payments (gateway_payment_id);"
            )
        else:
            op.create_index(GATEWAY_PAYMENT_UNIQUE_INDEX, 'payments', ['gateway_payment_id'], unique=True)

    _add_columns('credit_notes', CREDIT_NOTE_COLUMNS)
    _add_columns('credit_note_lines', CREDIT_NOTE_LINE_COLUMNS)


def downgrade() -> None:
    _drop_columns('credit_note_lines', [name for name, _ in CREDIT_NOTE_LINE_COLUMNS])
    _drop_columns('credit_notes', [name for name, _ in CREDIT_NOTE_COLUMNS])
    insp = _inspector()
    if insp.has_table('payments') and GATEWAY_PAYMENT_UNIQUE_INDEX in {ix['name'] for ix in insp.get_indexes('payments')}:
        op.drop_index(GATEWAY_PAYMENT_UNIQUE_INDEX, table_name='payments')
