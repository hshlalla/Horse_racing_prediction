"""add_race_predictions

Revision ID: 9212b3b827f2
Revises: e03b7948ec7d
Create Date: 2026-06-26 23:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9212b3b827f2'
down_revision: Union[str, Sequence[str], None] = 'e03b7948ec7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'race_predictions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('race_id', sa.Integer(), nullable=False),
        sa.Column('horse_id', sa.Integer(), nullable=False),
        sa.Column('win_probability', sa.Float(), nullable=False),
        sa.Column('place_probability', sa.Float(), nullable=False),
        sa.Column('model_version', sa.String(length=64), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('is_stale', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['horse_id'], ['horses.id']),
        sa.ForeignKeyConstraint(['race_id'], ['races.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('race_id', 'horse_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('race_predictions')
