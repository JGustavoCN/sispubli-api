"""
Esquemas Pydantic — Certificados.

Define a estrutura de dados para as respostas da API de certificados,
garantindo validacao rigorosa e documentacao OpenAPI (Swagger).
"""

from pydantic import BaseModel, Field


class CertificadoItem(BaseModel):
    """Representa um certificado individual no retorno da API.

    A url_download usa o padrao URL Template: o campo {cpf} deve ser
    substituido pelo CPF real do usuario no cliente (Flutter/MCP)
    antes de realizar o download. Isso evita trafegar dados sensiveis
    no JSON de resposta.
    """

    id_unico: str = Field(
        ...,
        description="Hash SHA-256 unico do certificado (LGPD-compliant, gerado com SALT)",
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
            "URL template para download do certificado. "
            "Substitua '{cpf}' pelo CPF real antes de acessar. "
            "Ex: url.replace('{cpf}', cpf_do_usuario)"
        ),
        json_schema_extra={
            "example": (
                "http://intranet.ifs.edu.br/publicacoes/relat/"
                "certificado_participacao_process.wsp?"
                "tmp.tx_cpf={cpf}&tmp.id_programa=1850&tmp.id_edicao=2011"
            )
        },
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
