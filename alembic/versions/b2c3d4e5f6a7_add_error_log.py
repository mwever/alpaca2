"""add_error_log

Revision ID: b2c3d4e5f6a7
Revises: 37b89478e54c
Create Date: 2026-03-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = '37b89478e54c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'error_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('method', sa.String(length=16), nullable=False),
        sa.Column('path', sa.String(length=1024), nullable=False),
        sa.Column('query_string', sa.String(length=1024), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('exception_type', sa.String(length=255), nullable=True),
        sa.Column('message', sa.String(length=2000), nullable=True),
        sa.Column('traceback', sa.Text(), nullable=True),
        sa.Column('user_agent', sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_error_logs_id'), 'error_logs', ['id'], unique=False)
    op.create_index(op.f('ix_error_logs_occurred_at'), 'error_logs', ['occurred_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_error_logs_occurred_at'), table_name='error_logs')
    op.drop_index(op.f('ix_error_logs_id'), table_name='error_logs')
    op.drop_table('error_logs')
