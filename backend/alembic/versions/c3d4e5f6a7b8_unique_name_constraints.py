"""unique_name_constraints

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'cf6d3b5f9bc7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint('uq_horses_name', 'horses', ['name'])
    op.create_unique_constraint('uq_jockeys_name', 'jockeys', ['name'])
    op.create_unique_constraint('uq_trainers_name', 'trainers', ['name'])


def downgrade() -> None:
    op.drop_constraint('uq_trainers_name', 'trainers')
    op.drop_constraint('uq_jockeys_name', 'jockeys')
    op.drop_constraint('uq_horses_name', 'horses')
