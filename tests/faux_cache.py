# tests/faux_cache.py
"""Doublure du cache : un dictionnaire en mémoire, ni Redis ni réseau.

Respecte le contrat du composant réel — lecture = valeur ou None — et sérialise
en JSON comme lui, pour qu'une valeur non sérialisable échoue ici aussi et pas
seulement en production.

Les compteurs permettent aux tests de vérifier qu'un second appel est bien servi
par le cache au lieu de retaper TMDB.
"""
import json
from typing import Any


class FauxCache:
    def __init__(self):
        self.valeurs: dict[str, str] = {}
        self.compteurs = {"lire": 0, "ecrire": 0}

    @property
    def actif(self) -> bool:
        return True

    async def lire(self, cle: str) -> Any | None:
        self.compteurs["lire"] += 1
        brut = self.valeurs.get(cle)
        return None if brut is None else json.loads(brut)

    async def ecrire(self, cle: str, valeur: Any, duree_s: int) -> None:
        self.compteurs["ecrire"] += 1
        self.valeurs[cle] = json.dumps(valeur)

    async def fermer(self) -> None:
        pass
