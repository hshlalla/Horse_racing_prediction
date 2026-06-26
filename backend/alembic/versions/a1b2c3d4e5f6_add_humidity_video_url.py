"""add_humidity_video_url

Revision ID: a1b2c3d4e5f6
Revises: 9212b3b827f2
Create Date: 2026-06-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '9212b3b827f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add humidity and video_url columns to races table."""
    op.add_column('races', sa.Column('humidity', sa.Integer(), nullable=True))
    op.add_column('races', sa.Column('video_url', sa.String(length=200), nullable=True))


def downgrade() -> None:
    """Remove humidity and video_url columns from races table."""
    op.drop_column('races', 'video_url')
    op.drop_column('races', 'humidity')
