# api/schemas/avis.py
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AvisCreation(BaseModel):
    # arc exclusif : exactement une des trois cibles (validé ci-dessous,
    # en miroir du CHECK chk_avis_cible en base)
    id_serie: int | None = None
    id_film: int | None = None
    id_episode: int | None = None
    note: int | None = Field(default=None, ge=1, le=10)
    commentaire: str | None = None

    @model_validator(mode="after")
    def verifier_regles(self):
        cibles = [c for c in (self.id_serie, self.id_film, self.id_episode) if c is not None]
        if len(cibles) != 1:
            raise ValueError("exactement une cible attendue : id_serie, id_film ou id_episode")
        if self.note is None and not (self.commentaire or "").strip():
            raise ValueError("une note ou un commentaire est requis")
        return self


class AvisMaj(BaseModel):
    """PATCH : seuls les champs fournis changent ; null explicite efface le champ."""

    note: int | None = Field(default=None, ge=1, le=10)
    commentaire: str | None = None


class AuteurAvis(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_utilisateur: int
    pseudo: str


class AvisPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_avis: int
    utilisateur: AuteurAvis
    id_serie: int | None
    id_film: int | None
    id_episode: int | None
    note: int | None
    commentaire: str | None
    date_creation: datetime
    date_modification: datetime | None
