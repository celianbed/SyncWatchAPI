"""notifs sociales : id_acteur + types abonnement/recommandation

Revision ID: a1b2c3d4e5f6
Revises: f3a9c1d2e5b7
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f3a9c1d2e5b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TYPES = ("nouvel_episode', 'nouvelle_saison', 'sortie_film', 'systeme', "
          "'rappel', 'abonnement', 'recommandation")
_TYPES_ANCIENS = ("nouvel_episode', 'nouvelle_saison', 'sortie_film', "
                  "'systeme', 'rappel")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('notification',
                  sa.Column('id_acteur', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_notification_acteur', 'notification', 'utilisateur',
                          ['id_acteur'], ['id_utilisateur'], ondelete='CASCADE')
    op.drop_constraint('chk_type_notif', 'notification', type_='check')
    op.create_check_constraint('chk_type_notif', 'notification',
                               f"type IN ('{_TYPES}')")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('chk_type_notif', 'notification', type_='check')
    op.create_check_constraint('chk_type_notif', 'notification',
                               f"type IN ('{_TYPES_ANCIENS}')")
    op.drop_constraint('fk_notification_acteur', 'notification', type_='foreignkey')
    op.drop_column('notification', 'id_acteur')
