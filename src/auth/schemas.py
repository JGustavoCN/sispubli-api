"""
Esquemas Pydantic para o modulo de Autenticacao — Sispubli API.
"""

from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    """Payload de entrada para geracao de token de sessao."""

    cpf: str = Field(
        ...,
        description="CPF do titular (11 digitos, aceita formatacao com pontos/traco)",
        json_schema_extra={"example": "74839210055"},
    )


class TokenResponse(BaseModel):
    """Resposta da rota de autenticacao."""

    access_token: str = Field(
        ...,
        description="Token Fernet criptografado (TTL 15 min)",
    )
