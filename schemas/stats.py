# schemas/stats.py
from datetime import datetime

from pydantic import BaseModel


class StatsGlobales(BaseModel):
    episodes_vus: int
    films_vus: int
    series_suivies: int
    series_terminees: int
    minutes_episodes: int
    minutes_films: int
    minutes_totales: int


class PeriodeStats(BaseModel):
    periode: datetime
    episodes_vus: int
    minutes: int
