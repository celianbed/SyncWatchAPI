"""table abonnement (social : suivre un utilisateur)

Revision ID: f3a9c1d2e5b7
Revises: ee59ca56195e
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a9c1d2e5b7'
down_revision: Union[str, Sequence[str], None] = 'ee59ca56195e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'abonnement',
        sa.Column('id_suiveur', sa.Integer(), nullable=False),
        sa.Column('id_suivi', sa.Integer(), nullable=False),
        sa.Column('date_abonnement', sa.DateTime(),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['id_suiveur'], ['utilisateur.id_utilisateur'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_suivi'], ['utilisateur.id_utilisateur'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id_suiveur', 'id_suivi'),
        sa.CheckConstraint('id_suiveur <> id_suivi', name='chk_pas_auto_abonnement'),
    )
    op.create_index('idx_abonnement_suivi', 'abonnement', ['id_suivi'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_abonnement_suivi', table_name='abonnement')
    op.drop_table('abonnement')
