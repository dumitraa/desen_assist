"""add action and extra columns"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'aa0001'
down_revision = '5e3040523203'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('editevent', sa.Column('action', sa.String(), nullable=True, server_default=''))
    op.add_column('editevent', sa.Column('layer', sa.String(), nullable=True))
    op.add_column('editevent', sa.Column('fid', sa.Integer(), nullable=True))
    op.add_column('editevent', sa.Column('field', sa.String(), nullable=True))
    op.add_column('editevent', sa.Column('extra', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('editevent', 'extra')
    op.drop_column('editevent', 'field')
    op.drop_column('editevent', 'fid')
    op.drop_column('editevent', 'layer')
    op.drop_column('editevent', 'action')
