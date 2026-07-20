# api/schemas/notification.py
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AppareilCreation(BaseModel):
    jeton_notif: str = Field(min_length=1, max_length=500)  # jeton FCM fourni par Flutter
    plateforme: Literal["android", "ios", "web"]


class AppareilPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_appareil: int
    plateforme: str
    date_enregistrement: datetime


class NotificationPublique(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_notification: int
    type: str
    contenu: str
    date_envoi: datetime
    lue: bool
    id_episode: int | None
    id_serie: int | None
    id_film: int | None
