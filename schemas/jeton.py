# schemas/jeton.py
from pydantic import BaseModel


class Jeton(BaseModel):
    # noms imposés par la spec OAuth2, ne pas franciser
    access_token: str
    token_type: str = "bearer"
