"""0024_offering_plans_and_quote_subscriptions

Unifies Plans & Pricing (catalog offerings) with subscriptions and links quotes to the
subscription they were converted into:

* plans.offering_id / plans.offering_terms_key - a recurring catalog Offering is
  subscribed through a *linked* legacy Plan (created on first subscribe). The pair
  (organization_id, offering_id, offering_terms_key) is unique, so one offering never
  produces duplicate plans for the same billing terms (interval / currency / model).
* products.offering_id - the linked plan's product carries the offering's tax rate and
  HSN/SAC; unique per (organization_id, offering_id).
* quotes.converted_subscription_id - set when an accepted quote is converted into a
  subscription (POST /quotes/{id}/convert-to-subscription).

All columns are nullable, so existing plans, products, quotes and subscriptions are
untouched (legacy rows keep NULL). Every step is defensive (re-runnable).

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
Create Date: 2026-09-26 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b3c4d5e6f7a'
down_revision: Union[str, None] = '1a2b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_column(table_name, column_name):
    insp = _inspector()
    if not insp.has_table(table_name):
        return False
    return column_name in {c["name"] for c in insp.get_columns(table_name)}


def _has_unique(table_name, name):
    insp = _inspector()
    if not insp.has_table(table_name):
        return False
    names = {uc.get("name") for uc in insp.get_unique_constraints(table_name)}
    # SQLite may surface a unique constraint as a unique index instead.
    names |= {ix.get("name") for ix in insp.get_indexes(table_name) if ix.get("unique")}
    return name in names


def _has_index(table_name, name):
    insp = _inspector()
    if not insp.has_table(table_name):
        return False
    return name in {ix.get("name") for ix in insp.get_indexes(table_name)}


def upgrade() -> None:
    insp = _inspector()

    if insp.has_table('plans') and insp.has_table('offerings'):
        add_offering = not _has_column('plans', 'offering_id')
        add_terms = not _has_column('plans', 'offering_terms_key')
        if add_offering or add_terms:
            with op.batch_alter_table('plans') as batch_op:
                if add_offering:
                    batch_op.add_column(
                        sa.Column(
                            'offering_id',
                            sa.String(length=36),
                            sa.ForeignKey('offerings.id', ondelete='SET NULL', name='fk_plans_offering_id'),
                            nullable=True,
                        )
                    )
                if add_terms:
                    batch_op.add_column(sa.Column('offering_terms_key', sa.String(length=64), nullable=True))
        if not _has_unique('plans', 'uq_plan_offering_terms'):
            with op.batch_alter_table('plans') as batch_op:
                batch_op.create_unique_constraint(
                    'uq_plan_offering_terms', ['organization_id', 'offering_id', 'offering_terms_key']
                )

    if insp.has_table('products') and insp.has_table('offerings'):
        if not _has_column('products', 'offering_id'):
            with op.batch_alter_table('products') as batch_op:
                batch_op.add_column(
                    sa.Column(
                        'offering_id',
                        sa.String(length=36),
                        sa.ForeignKey('offerings.id', ondelete='SET NULL', name='fk_products_offering_id'),
                        nullable=True,
                    )
                )
        if not _has_unique('products', 'uq_product_offering'):
            with op.batch_alter_table('products') as batch_op:
                batch_op.create_unique_constraint('uq_product_offering', ['organization_id', 'offering_id'])

    if insp.has_table('quotes') and insp.has_table('subscriptions'):
        if not _has_column('quotes', 'converted_subscription_id'):
            with op.batch_alter_table('quotes') as batch_op:
                batch_op.add_column(
                    sa.Column(
                        'converted_subscription_id',
                        sa.String(length=36),
                        sa.ForeignKey(
                            'subscriptions.id', ondelete='SET NULL', name='fk_quotes_converted_subscription_id'
                        ),
                        nullable=True,
                    )
                )
        if not _has_index('quotes', 'ix_quotes_converted_subscription_id'):
            op.create_index('ix_quotes_converted_subscription_id', 'quotes', ['converted_subscription_id'])


def downgrade() -> None:
    if _has_index('quotes', 'ix_quotes_converted_subscription_id'):
        op.drop_index('ix_quotes_converted_subscription_id', table_name='quotes')
    if _has_column('quotes', 'converted_subscription_id'):
        with op.batch_alter_table('quotes') as batch_op:
            batch_op.drop_column('converted_subscription_id')

    if _has_unique('products', 'uq_product_offering') or _has_column('products', 'offering_id'):
        with op.batch_alter_table('products') as batch_op:
            if _has_unique('products', 'uq_product_offering'):
                batch_op.drop_constraint('uq_product_offering', type_='unique')
            if _has_column('products', 'offering_id'):
                batch_op.drop_column('offering_id')

    if (
        _has_unique('plans', 'uq_plan_offering_terms')
        or _has_column('plans', 'offering_id')
        or _has_column('plans', 'offering_terms_key')
    ):
        with op.batch_alter_table('plans') as batch_op:
            if _has_unique('plans', 'uq_plan_offering_terms'):
                batch_op.drop_constraint('uq_plan_offering_terms', type_='unique')
            if _has_column('plans', 'offering_terms_key'):
                batch_op.drop_column('offering_terms_key')
            if _has_column('plans', 'offering_id'):
                batch_op.drop_column('offering_id')
