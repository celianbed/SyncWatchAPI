"""sub_apple pour Sign in with Apple

Revision ID: b4c7d1e9f230
Revises: a1b2c3d4e5f6
Create Date: 2026-09-05 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4c7d1e9f230'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # identifiant stable du compte Apple : Apple ne redonne pas l'adresse mail
    # aux connexions suivantes, seul le "sub" permet de retrouver le compte
    op.add_column('utilisateur', sa.Column('sub_apple', sa.String(length=255), nullable=True))
    op.create_unique_constraint('uq_utilisateur_sub_apple', 'utilisateur', ['sub_apple'])
    # gardé uniquement pour révoquer l'accès Apple à la suppression du compte
    op.add_column('utilisateur',
                  sa.Column('jeton_revocation_apple', sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('utilisateur', 'jeton_revocation_apple')
    op.drop_constraint('uq_utilisateur_sub_apple', 'utilisateur', type_='unique')
    op.drop_column('utilisateur', 'sub_apple')
