"""
Esquemas Pydantic para o modulo de Autenticacao — Sispubli API.
"""

from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    """Payload de entrada para geracao de token de sessao."""

    cpf: str = Field(
        ...,
        description="CPF do titular (11 dígitos). Aceita formatação com pontos e traço.",
        json_schema_extra={"example": "74839210055"},
    )


class TokenResponse(BaseModel):
    """Resposta da rota de autenticacao."""

    access_token: str = Field(
        ...,
        description="Token Fernet criptografado contendo o CPF do usuário (TTL 15 min).",
    )
