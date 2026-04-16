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

import asyncio
import copy
import ipaddress
import os
import re
import socket
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from logger import logger
from rate_limit import auth_limiter, extrair_ip_real, ip_limiter, ticket_limiter
from scraper import fetch_all_certificates
from security import (
    derivar_session_hash,
    gerar_ticket_pdf,
    gerar_token_sessao,
    ler_ticket_pdf,
    ler_token_sessao,
    normalizar_cpf,
)

log = logger.bind(module=__name__)

# Esquema de autenticação para o Swagger UI reconhecer e adicionar o cadeado
security_scheme = HTTPBearer(auto_error=False)


# ===========================================================================
# Lifespan — Fail Fast em producao
# ===========================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Valida configuracoes criticas antes de aceitar requisicoes.

    Em producao (ENVIRONMENT=production), o servidor NAO sobe se:
        - HASH_SALT nao estiver definido
        - FERNET_SECRET_KEY nao estiver definido
        - SECRET_PEPPER nao estiver definido

    Isso garante conformidade LGPD e seguranca criptografica
    desde o primeiro deploy.
    """
    environment = os.environ.get("ENVIRONMENT", "development")

    if environment == "production":
        required_vars = ["HASH_SALT", "FERNET_SECRET_KEY", "SECRET_PEPPER"]
        missing = [v for v in required_vars if not os.environ.get(v)]

        if missing:
            msg = f"Variaveis obrigatorias ausentes: {', '.join(missing)}"
            log.critical(
                f"FALHA CRITICA DE CONFIGURACAO: ENVIRONMENT=production "
                f"mas {msg}. Defina antes de subir em producao."
            )
            raise RuntimeError(
                f"{msg}. Configure as variaveis de ambiente "
                "antes de iniciar o servidor em producao."
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


# ===================================================================
# ROTA: Listagem segura — GET /api/certificados
# ===================================================================

# Regex para limpar CPF de URLs e campos
_CPF_PATTERN = re.compile(r"\b\d{11}\b")


def _extrair_bearer_token(request: Request) -> str | None:
    """Extrai o token do header Authorization: Bearer <token>."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[7:]  # Remove 'Bearer '


def _substituir_urls_por_tickets(certificados: list[dict]) -> list[dict]:
    """Substitui url_download por /api/pdf/{ticket} criptografados."""
    resultado = []
    for cert in certificados:
        cert_copy = copy.deepcopy(cert)
        url = cert_copy.get("url_download")
        if url:
            ticket = gerar_ticket_pdf(url)
            cert_copy["url_download"] = f"/api/pdf/{ticket}"
        resultado.append(cert_copy)
    return resultado


def _sanitizar_cpf_resposta(certificados: list[dict]) -> list[dict]:
    """Remove qualquer CPF que ainda exista nos campos da resposta."""
    resultado = []
    for cert in certificados:
        cert_limpo = {}
        for key, value in cert.items():
            if isinstance(value, str):
                cert_limpo[key] = _CPF_PATTERN.sub("{cpf}", value)
            else:
                cert_limpo[key] = value
        resultado.append(cert_limpo)
    return resultado


@app.get(
    "/api/certificados",
    response_model=CertificadosResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Nao autenticado"},
        400: {"model": ErrorResponse, "description": "Token invalido"},
        502: {"model": ErrorResponse, "description": "Sispubli fora do ar"},
    },
)
async def listar_certificados(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),  # noqa: B008
):
    """Lista certificados do usuario autenticado via Bearer token.

    O CPF e descriptografado do token, enviado ao scraper, e as URLs
    resultantes sao substituidas por tickets criptografados (/api/pdf/{ticket}).
    Nenhum CPF real aparece na resposta.

    Args:
        request: Starlette Request para obter IP.
        credentials: Token Bearer extraido automaticamente.

    Returns:
        JSON com {data: {usuario_id, total, certificados}}.
    """
    # --- Extrair token ---
    raw_token = _extrair_bearer_token(request) if not credentials else credentials.credentials

    if not raw_token:
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "unauthorized",
                    "message": "Header Authorization: Bearer <token> obrigatorio.",
                }
            },
        )

    # --- Validar tamanho ---
    if len(raw_token) > 500:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "token_too_large",
                    "message": "Token excede tamanho maximo de 500 caracteres.",
                }
            },
        )

    # --- Descriptografar CPF do token ---
    try:
        cpf = ler_token_sessao(raw_token)
    except Exception:
        log.warning("Token de sessao invalido ou expirado na listagem")
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "invalid_token",
                    "message": "Token invalido, expirado ou corrompido.",
                }
            },
        )

    # --- Rate limit por IP ---
    ip = extrair_ip_real(request)
    if not await ip_limiter.check(ip):
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": "Limite de requisicoes excedido.",
                }
            },
        )

    # --- Buscar certificados ---
    try:
        resultado = fetch_all_certificates(cpf)
    except ConnectionError as exc:
        log.error(f"Erro de conexao com Sispubli: {exc}")
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "code": "upstream_error",
                    "message": "Sispubli temporariamente indisponivel.",
                }
            },
        )
    except Exception as exc:
        log.error(f"Erro inesperado na listagem: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": str(exc),
                }
            },
        )

    # --- Transformar resposta ---
    certs = resultado.get("certificados", [])
    certs_com_tickets = _substituir_urls_por_tickets(certs)
    certs_limpos = _sanitizar_cpf_resposta(certs_com_tickets)

    response_data = {
        "data": {
            "usuario_id": resultado.get("usuario_id", ""),
            "total": resultado.get("total", 0),
            "certificados": certs_limpos,
        }
    }

    response = JSONResponse(content=response_data)
    response.headers["Cache-Control"] = "public, s-maxage=600"
    response.headers["Vary"] = "Authorization"
    return response


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


# ===================================================================
# TUNEL DE DOWNLOAD SEGURO — GET /api/pdf/{ticket}
# ===================================================================

# Constantes
MAX_PDF_SIZE = 10_000_000  # 10 MB
TUNNEL_USER_AGENT = "Mozilla/5.0 (compatible; SispubliProxy/1.0)"
_tunnel_semaphore = asyncio.Semaphore(10)


def is_safe_host(hostname: str) -> bool:
    """Valida hostname contra ataques SSRF (DNS rebinding, IP privado).

    Camada 2 de defesa: garante que o host e o IP resolvido sao seguros:
        1. Hostname deve ser exatamente 'intranet.ifs.edu.br'
        2. IP resolvido nao pode ser privado, loopback ou link-local

    Args:
        hostname: Nome do host extraido da URL.

    Returns:
        True se seguro, False se bloqueado.
    """
    if hostname != "intranet.ifs.edu.br":
        log.warning(f"SSRF: hostname rejeitado: {hostname}")
        return False

    try:
        ip = socket.gethostbyname(hostname)
        ip_obj = ipaddress.ip_address(ip)

        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
            log.warning(f"SSRF: DNS rebinding detectado — {hostname} resolve para {ip}")
            return False
    except Exception:
        log.warning(f"SSRF: falha ao resolver DNS de {hostname}")
        return False

    return True


@app.get(
    "/api/pdf/{ticket}",
    responses={
        200: {"content": {"application/pdf": {}}, "description": "PDF streamado"},
        400: {"model": ErrorResponse, "description": "Ticket invalido"},
        403: {"model": ErrorResponse, "description": "SSRF bloqueado"},
        413: {"model": ErrorResponse, "description": "PDF muito grande"},
        429: {"model": ErrorResponse, "description": "Rate limit excedido"},
        502: {"model": ErrorResponse, "description": "Upstream indisponivel"},
    },
)
async def tunnel_pdf(ticket: str):
    """Tunel seguro para download de PDFs do Sispubli.

    7 camadas de defesa:
        1. Ticket Fernet (decrypt valida integridade)
        2. SSRF (hostname + DNS rebinding + IP privado)
        3. Rate limit por ticket hash
        4. Semaphore de concorrencia (10 max)
        5. User-Agent consistente
        6. Content-Length guard (10MB max)
        7. Streaming isolado (sem repasse de headers)

    Args:
        ticket: Ticket criptografado gerado pela rota de listagem.

    Returns:
        Response com o PDF streamado (application/pdf).
    """
    # --- Camada 1: Descriptografar ticket ---
    try:
        url = ler_ticket_pdf(ticket)
    except Exception:
        log.warning("Ticket de PDF invalido ou corrompido")
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "invalid_ticket",
                    "message": "Ticket invalido ou corrompido.",
                }
            },
        )

    # --- Camada 2: Validacao SSRF ---
    parsed = urlparse(url)
    if not parsed.hostname or not is_safe_host(parsed.hostname):
        log.warning(f"SSRF bloqueado para URL do ticket: {parsed.hostname}")
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "ssrf_blocked",
                    "message": "URL de destino bloqueada por politica de seguranca.",
                }
            },
        )

    # --- Camada 3: Rate limit por ticket ---
    ticket_hash = ticket[:32]  # Usar prefixo como chave
    if not await ticket_limiter.check(ticket_hash):
        log.warning(f"Rate limit de ticket excedido: {ticket_hash[:16]}...")
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": "Limite de downloads excedido para este certificado.",
                }
            },
        )

    # --- Camada 4: Semaphore de concorrencia ---
    async with _tunnel_semaphore:
        try:
            client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
            request_obj = client.build_request(
                "GET", url, headers={"User-Agent": TUNNEL_USER_AGENT}
            )

            # Use send with stream=True to read headers before starting the payload generator
            upstream_response = await client.send(request_obj, stream=True)

            # --- Camada 6: Content-Length guard antecipado ---
            content_length = int(upstream_response.headers.get("content-length", 0))
            if content_length > MAX_PDF_SIZE:
                log.warning(
                    f"PDF rejeitado por tamanho: {content_length} bytes (max {MAX_PDF_SIZE})"
                )
                await upstream_response.aclose()
                await client.aclose()
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "payload_too_large",
                            "message": "PDF excede o tamanho maximo permitido (10MB).",
                        }
                    },
                )

            # Verifica falha de upstream
            if upstream_response.status_code >= 400:
                log.error(f"Erro no upstream: status {upstream_response.status_code}")
                await upstream_response.aclose()
                await client.aclose()
                return JSONResponse(
                    status_code=502,
                    content={
                        "error": {
                            "code": "bad_gateway",
                            "message": "Falha ao obter arquivo original do Sispubli.",
                        }
                    },
                )

            # --- Camada 7: Streaming isolado (Byte Streaming Limiter) ---
            async def stream_generator():
                total_bytes = 0
                try:
                    async for chunk in upstream_response.aiter_bytes(chunk_size=65536):
                        total_bytes += len(chunk)
                        if total_bytes > MAX_PDF_SIZE:
                            log.warning(
                                f"PDF truncado ativamente por limite excedido: "
                                f"{total_bytes} bytes streamados"
                            )
                            break
                        yield chunk
                finally:
                    await upstream_response.aclose()
                    await client.aclose()

            content_type = upstream_response.headers.get("content-type", "application/pdf")
            log.info(f"PDF streamado com sucesso (informado {content_length} bytes)")

            return StreamingResponse(
                stream_generator(),
                status_code=200,
                media_type=content_type,
                headers={
                    "Content-Disposition": "inline; filename=certificado.pdf",
                    "Cache-Control": "public, max-age=86400",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        except httpx.ConnectError as exc:
            log.error(f"Erro de conexao com upstream para PDF: {exc}")
            return JSONResponse(
                status_code=502,
                content={
                    "error": {
                        "code": "upstream_error",
                        "message": "Sispubli temporariamente indisponivel.",
                    }
                },
            )
        except Exception as exc:
            log.error(f"Erro inesperado no tunel PDF: {exc}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "Erro interno no tunel de download.",
                    }
                },
            )
