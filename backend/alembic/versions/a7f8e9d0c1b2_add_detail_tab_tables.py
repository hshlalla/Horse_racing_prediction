"""add detail tab tables

Revision ID: a7f8e9d0c1b2
Revises: f1a2b3c4d5e6
Create Date: 2026-07-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7f8e9d0c1b2'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'start_training_records',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('horse_id', sa.Integer(), sa.ForeignKey('horses.id'), nullable=False),
        sa.Column('train_date', sa.Date(), nullable=False),
        sa.Column('rider', sa.String(30)),
        sa.Column('remark', sa.String(50)),
        sa.Column('passed', sa.Boolean()),
        sa.Column('equipment', sa.String(50)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('horse_id', 'train_date'),
    )
    op.create_index('ix_strain_horse_date', 'start_training_records', ['horse_id', 'train_date'])
    op.create_table(
        'pre_race_workouts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('race_id', sa.Integer(), sa.ForeignKey('races.id'), nullable=False),
        sa.Column('horse_id', sa.Integer(), sa.ForeignKey('horses.id'), nullable=False),
        sa.Column('day_label', sa.String(10), nullable=False),
        sa.Column('rider', sa.String(30)),
        sa.Column('count', sa.Integer()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('race_id', 'horse_id', 'day_label'),
    )
    op.create_index('ix_prw_race_horse', 'pre_race_workouts', ['race_id', 'horse_id'])
    op.add_column('race_entries', sa.Column('market_fav_rank', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('race_entries', 'market_fav_rank')
    op.drop_index('ix_prw_race_horse', table_name='pre_race_workouts')
    op.drop_table('pre_race_workouts')
    op.drop_index('ix_strain_horse_date', table_name='start_training_records')
    op.drop_table('start_training_records')
