"""
Esquemas globais e reutilizaveis — Sispubli API.
"""

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detalhe de erro padronizado para facilitar tratamento no cliente."""

    code: str = Field(
        ...,
        description="Codigo de erro em snake_case para tratamento programatico",
        json_schema_extra={"example": "invalid_cpf"},
    )
    message: str = Field(
        ...,
        description="Mensagem descritiva do erro em portugues",
        json_schema_extra={"example": "CPF deve conter exatamente 11 digitos numericos."},
    )


class ErrorResponse(BaseModel):
    """Envelope de resposta de erro — detalhes aninhados em 'error'."""

    error: ErrorDetail
