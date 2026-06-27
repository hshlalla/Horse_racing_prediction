"""add_performance_indexes

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # races — date range queries and track filtering
    op.create_index('ix_races_race_date', 'races', ['race_date'])
    op.create_index('ix_races_track', 'races', ['track'])
    op.create_index('ix_races_track_date', 'races', ['track', 'race_date'])

    # race_entries — horse/jockey/trainer win-rate sub-queries
    op.create_index('ix_race_entries_horse_id', 'race_entries', ['horse_id'])
    op.create_index('ix_race_entries_jockey_id', 'race_entries', ['jockey_id'])
    op.create_index('ix_race_entries_trainer_id', 'race_entries', ['trainer_id'])

    # race_results — finish_position filtered queries (win-rate calcs)
    op.create_index('ix_race_results_horse_id', 'race_results', ['horse_id'])

    # odds_snapshots — live race lookups
    op.create_index('ix_odds_snapshots_race_id', 'odds_snapshots', ['race_id'])


def downgrade() -> None:
    op.drop_index('ix_odds_snapshots_race_id', 'odds_snapshots')
    op.drop_index('ix_race_results_horse_id', 'race_results')
    op.drop_index('ix_race_entries_trainer_id', 'race_entries')
    op.drop_index('ix_race_entries_jockey_id', 'race_entries')
    op.drop_index('ix_race_entries_horse_id', 'race_entries')
    op.drop_index('ix_races_track_date', 'races')
    op.drop_index('ix_races_track', 'races')
    op.drop_index('ix_races_race_date', 'races')
