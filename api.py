"""
API REST do Sispubli — FastAPI.

Expoe o motor de extracao de certificados como endpoints HTTP.

Rotas:
    GET  /                        : Health check
    POST /api/auth/token          : Login — gera token de sessao
    GET  /api/certificados/{cpf}  : Busca certificados (DEPRECATED)

Seguranca:
    - Fail Fast em producao: HASH_SALT e FERNET_SECRET_KEY obrigatorios.
    - CPF nunca aparece em logs, URLs ou query parameters.
    - Tokens Fernet com TTL 15 min para sessao.
    - Rate limiting anti-enumeracao e anti-bot.

Respostas seguem o padrao:
    Sucesso: {"data": {...}} ou campos diretos
    Erro:    {"error": {"code": "...", "message": "..."}}
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from logger import logger
from rate_limit import auth_limiter, extrair_ip_real
from scraper import fetch_all_certificates
from security import (
    derivar_session_hash,
    gerar_token_sessao,
    normalizar_cpf,
)

log = logger.bind(module=__name__)


# ===========================================================================
# Lifespan — Fail Fast em producao
# ===========================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Valida configuracoes criticas antes de aceitar requisicoes.

    Em producao (ENVIRONMENT=production), o HASH_SALT DEVE estar definido.
    Caso contrario, o servidor nao sobe — essa e uma falha intencional
    para garantir conformidade LGPD desde o primeiro deploy.
    """
    environment = os.environ.get("ENVIRONMENT", "development")
    hash_salt = os.environ.get("HASH_SALT", "")

    if environment == "production" and not hash_salt:
        log.critical(
            "FALHA CRITICA DE CONFIGURACAO: ENVIRONMENT=production mas HASH_SALT nao definido. "
            "Defina a variavel de ambiente HASH_SALT antes de subir em producao."
        )
        raise RuntimeError(
            "HASH_SALT e obrigatorio em ambiente de producao. "
            "Configure a variavel de ambiente antes de iniciar o servidor."
        )

    log.info(f"API iniciando em modo: {environment}")
    yield
    log.info("API encerrando")


# ===========================================================================
# Modelos Pydantic — Tipagem das respostas para Swagger/OpenAPI
# ===========================================================================


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
            "example": "a3f8c2d1e4b7091f6e2a5d8c3b1f4e7a9d2c5b8e1f4a7c0d3b6e9f2a5c8b1e4"
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


class HealthResponse(BaseModel):
    """Resposta do health check."""

    status: str = Field(
        ...,
        description="Status atual da API",
        json_schema_extra={"example": "API do Sispubli rodando"},
    )


class TokenRequest(BaseModel):
    """Payload de entrada para geracao de token de sessao."""

    cpf: str = Field(
        ...,
        description="CPF do titular (11 digitos, aceita formatacao com pontos/traco)",
        json_schema_extra={"example": "12345678900"},
    )


class TokenResponse(BaseModel):
    """Resposta da rota de autenticacao."""

    access_token: str = Field(
        ...,
        description="Token Fernet criptografado (TTL 15 min)",
    )
    session_hash: str = Field(
        ...,
        description="Hash SHA-256 do token + pepper para cache key (64 chars hex)",
    )


# ===========================================================================
# App FastAPI
# ===========================================================================

app = FastAPI(
    title="Sispubli Certificados API",
    description=(
        "API REST para extracao de certificados do sistema Sispubli/IFS.\n\n"
        "**Nota de seguranca**: o campo `url_download` usa o padrao URL Template. "
        "Substitua `{cpf}` pelo CPF real do usuario antes de acessar a URL."
    ),
    version="1.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Mensagens de erro conhecidas que indicam falha no Sispubli (upstream)
# ---------------------------------------------------------------------------

UPSTREAM_ERROR_PATTERNS = [
    "Erro ao acessar",
    "Erro ao enviar POST",
    "Erro ao buscar pagina",
    "Token nao encontrado",
]


def _is_upstream_error(message: str) -> bool:
    """Verifica se a mensagem de erro indica falha no Sispubli."""
    return any(pattern in message for pattern in UPSTREAM_ERROR_PATTERNS)


# ===================================================================
# ROTAS
# ===================================================================


@app.get("/", response_model=HealthResponse)
def health_check():
    """Rota de verificacao de saude da API."""
    log.info("Health check acessado")
    return {"status": "API do Sispubli rodando"}


# ===================================================================
# ROTA: Autenticacao — POST /api/auth/token
# ===================================================================


@app.post(
    "/api/auth/token",
    response_model=TokenResponse,
    responses={
        400: {"model": ErrorResponse, "description": "CPF invalido"},
        429: {"model": ErrorResponse, "description": "Rate limit excedido"},
    },
)
async def auth_token(body: TokenRequest, request: Request):
    """Gera token de sessao e session_hash para um CPF.

    O CPF e normalizado, validado e criptografado via Fernet.
    O token tem TTL de 15 minutos. O session_hash e derivado
    com SHA-256 + SECRET_PEPPER para uso como cache key.

    Args:
        body: JSON com campo 'cpf' (aceita formatacao).
        request: Objeto Request para extracao de IP.

    Returns:
        JSON com access_token e session_hash.
    """
    # --- Rate limit anti-enumeracao ---
    ip = extrair_ip_real(request)
    if not await auth_limiter.check(ip):
        log.warning(f"Rate limit de auth excedido para IP: {ip}")
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": "Limite de requisicoes excedido. Tente novamente em breve.",
                }
            },
        )

    # --- Normalizacao e validacao do CPF ---
    cpf = normalizar_cpf(body.cpf)
    if not cpf.isdigit() or len(cpf) != 11:
        log.warning(f"CPF invalido recebido no auth: '{cpf[:3]}...' (len={len(cpf)})")
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "invalid_cpf",
                    "message": "CPF deve conter exatamente 11 digitos numericos.",
                }
            },
        )

    # --- Geracao de token e hash ---
    token = gerar_token_sessao(cpf)
    session_hash = derivar_session_hash(token)

    log.info(f"Token de sessao gerado com sucesso (hash: {session_hash[:16]}...)")
    return {"access_token": token, "session_hash": session_hash}


@app.get(
    "/api/certificados/{cpf}",
    response_model=CertificadosResponse,
    responses={
        400: {"model": ErrorResponse, "description": "CPF invalido"},
        502: {"model": ErrorResponse, "description": "Sispubli fora do ar"},
        500: {"model": ErrorResponse, "description": "Erro interno"},
    },
)
def buscar_certificados(cpf: str):
    """Busca todos os certificados disponiveis para um CPF.

    O CPF e validado, enviado ao Sispubli e nunca retornado em texto claro.
    O campo `url_download` de cada certificado contem `{cpf}` como placeholder
    — o cliente deve substituir pelo CPF real antes de acessar.

    Args:
        cpf: CPF do titular (apenas numeros, 11 digitos).

    Returns:
        JSON com a estrutura:
        {"data": {"usuario_id": "...", "total": N, "certificados": [...]}}

    Raises:
        400: CPF com formato invalido.
        502: Sispubli fora do ar ou com erro.
        500: Erro inesperado interno.
    """
    log.info(f"Requisicao recebida: GET /api/certificados/{cpf[:3]}***")

    # --- Validacao do CPF ---
    if not cpf.isdigit() or len(cpf) != 11:
        log.warning(f"CPF invalido recebido: '{cpf[:3]}...' (len={len(cpf)})")
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "invalid_cpf",
                    "message": "CPF deve conter exatamente 11 digitos numericos.",
                }
            },
        )

    # --- Chamada ao scraper ---
    try:
        log.info("Iniciando busca de certificados para CPF valido")
        resultado = fetch_all_certificates(cpf)
        log.info(f"Busca concluida: {resultado['total']} certificados encontrados")
        return {"data": resultado}

    except Exception as e:
        error_message = str(e)
        log.error(f"Erro durante busca de certificados: {error_message}")

        if _is_upstream_error(error_message):
            log.error("Classificado como erro de upstream (Sispubli)")
            return JSONResponse(
                status_code=502,
                content={
                    "error": {
                        "code": "upstream_error",
                        "message": f"Falha ao acessar o Sispubli: {error_message}",
                    }
                },
            )

        log.error("Classificado como erro interno inesperado")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": f"Erro interno do servidor: {error_message}",
                }
            },
        )
