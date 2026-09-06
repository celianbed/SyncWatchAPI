# schemas/moderation.py
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Les motifs proposés à l'écran. Une liste fermée vaut mieux qu'un texte libre :
# elle se traite plus vite, et elle guide la personne qui signale.
MOTIFS = Literal["haine", "harcelement", "contenu_sexuel", "spoiler", "spam", "autre"]


class SignalementCreation(BaseModel):
    """Signalement d'un avis OU d'une personne — exactement une cible."""

    id_avis: int | None = None
    id_vise: int | None = None
    motif: MOTIFS
    precision: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def cible_unique(self) -> "SignalementCreation":
        if (self.id_avis is None) == (self.id_vise is None):
            raise ValueError("un signalement vise un avis ou une personne, pas les deux")
        return self


class SignalementPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_signalement: int
    motif: str
    date_signalement: datetime
    statut: str
