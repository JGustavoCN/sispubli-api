"""
Esquemas Pydantic — Certificados.

Define a estrutura de dados para as respostas da API de certificados,
garantindo validacao rigorosa e documentacao OpenAPI (Swagger).
"""

from pydantic import BaseModel, Field


class CertificadoItem(BaseModel):
    """Representa um certificado individual no retorno da API.

    A url_download fornece o recurso final via túnel seguro, eliminando a
    necessidade de processamento de PII no lado do cliente.
    """

    id_unico: str = Field(
        ...,
        description="Identificador único (SHA-256 + SALT) para anonimato (LGPD).",
        json_schema_extra={
            "example": (
                "a3f8c2d1e4b7091f6e2a5d8c3b1f4e7a9d..."  # pragma: allowlist secret
            )
        },
    )
    titulo: str = Field(
        ...,
        description="Titulo do evento ou certificado conforme registrado no Sispubli",
        json_schema_extra={"example": "Participacao no(a) SEPEX 2023"},
    )
    url_download: str | None = Field(
        None,
        description=(
            "Link direto para o endpoint de túnel da API. O acesso a este recurso consome "
            "um ticket criptografado efêmero, acionando o streaming direto do documento "
            "binário do sistema upstream, garantindo que nenhuma PII seja manipulada ou "
            "exposta no lado do cliente (downstream)."
        ),
        json_schema_extra={"example": "https://api.sispubli.edu.br/api/pdf/38f92bd3a84e..."},
    )
    ano: int = Field(
        ...,
        description="Ano de realizacao do evento, extraido dos parametros do Sispubli",
        json_schema_extra={"example": 2023},
    )
    tipo_codigo: int = Field(
        ...,
        description="Codigo numerico do tipo de certificado (1=Participacao, 2=Autor, etc.)",
        json_schema_extra={"example": 1},
    )
    tipo_descricao: str = Field(
        ...,
        description="Descricao legivel do tipo de certificado",
        json_schema_extra={"example": "Participacao"},
    )


class CertificadosResult(BaseModel):
    """Resultado consolidado da busca de certificados para um CPF."""

    usuario_id: str = Field(
        ...,
        description="CPF mascarado do titular no formato ***.XXX.XXX-** (LGPD)",
        json_schema_extra={"example": "***.456.789-**"},
    )
    total: int = Field(
        ...,
        description="Quantidade total de certificados encontrados",
        json_schema_extra={"example": 42},
    )
    certificados: list[CertificadoItem] = Field(
        default_factory=list,
        description="Lista completa de certificados disponiveis para o CPF informado",
    )


class CertificadosResponse(BaseModel):
    """Envelope de resposta de sucesso — dados aninhados em 'data'."""

    data: CertificadosResult
