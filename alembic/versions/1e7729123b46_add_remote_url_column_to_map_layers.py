"""add remote_url column to map_layers

Revision ID: 1e7729123b46
Revises: 158ce8e20754
Create Date: 2025-08-20 19:11:11.897191

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e7729123b46'
down_revision: Union[str, None] = '158ce8e20754'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add remote_url column as optional string to map_layers table
    op.add_column("map_layers", sa.Column("remote_url", sa.String(), nullable=True))


def downgrade() -> None:
    # Remove remote_url column from map_layers table
    op.drop_column("map_layers", "remote_url")