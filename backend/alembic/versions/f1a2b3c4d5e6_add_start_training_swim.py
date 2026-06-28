"""add_start_training_swim

Revision ID: f1a2b3c4d5e6
Revises: d4e5f6a7b8c9
Create Date: 2026-06-29 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workout_times', sa.Column('start_training_passed', sa.Boolean(), nullable=True))
    op.add_column('workout_times', sa.Column('swim_count_recent', sa.Integer(), nullable=True))
    op.add_column('horses', sa.Column('last_start_training_date', sa.Date(), nullable=True))
    op.add_column('horses', sa.Column('last_start_training_passed', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('workout_times', 'start_training_passed')
    op.drop_column('workout_times', 'swim_count_recent')
    op.drop_column('horses', 'last_start_training_date')
    op.drop_column('horses', 'last_start_training_passed')
