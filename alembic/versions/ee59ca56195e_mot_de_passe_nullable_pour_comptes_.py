"""mot de passe nullable pour comptes google

Revision ID: ee59ca56195e
Revises: a7a21b8a70e3
Create Date: 2026-07-22 08:48:09.259476

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee59ca56195e'
down_revision: Union[str, Sequence[str], None] = 'a7a21b8a70e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # comptes créés via Google : pas de mot de passe
    op.alter_column('utilisateur', 'mot_de_passe',
                    existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('utilisateur', 'mot_de_passe',
                    existing_type=sa.String(length=255), nullable=False)
