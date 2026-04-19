"""
API REST do Sispubli — FastAPI.

Expoe o motor de extracao de certificados como endpoints HTTP.

Rotas:
    GET  /                        : Health check
    POST /api/auth/token          : Login — gera token de sessao
    GET  /api/certificados        : Lista certificados (Seguro, via Bearer Token)

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
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from logger import aplicar_interceptor, logger
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
from validators import validar_cpf

log = logger.bind(module=__name__)

# Esquema de autenticação para o Swagger UI reconhecer e adicionar o cadeado
security_scheme = HTTPBearer(auto_error=False)


# ===========================================================================
# Lifespan — Fail Fast em producao
# ===========================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ativa sistemas de seguranca e valida configuracoes criticas."""
    # 1. Ativar interceptacao de logs (httpx, uvicorn -> Loguru sanitizado)
    aplicar_interceptor()

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
    """Resposta do health check detalhado."""

    status: str = Field(..., description="Status geral da nossa API")
    environment: str = Field(..., description="Ambiente de execução (development/production)")
    version: str = Field(..., description="Versão atual da API")
    timestamp: datetime = Field(..., description="Momento exato da verificação (UTC)")
    security_configured: bool = Field(..., description="Indica se chaves críticas estão no .env")
    sispubli_online: bool = Field(..., description="Status de conectividade com o sistema upstream")


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
    docs_url=None,  # Desabilita Swagger padrão
    redoc_url=None,  # Desabilita ReDoc padrão
)

# Montar diretório estático para servir imagens e ativos
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """Renderiza interface Swagger UI customizada com favicon local."""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_favicon_url="/favicon.ico",
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    """Renderiza interface ReDoc customizada com favicon local."""
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_favicon_url="/favicon.ico",
    )


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Middleware global para seguranca e politica de cache.

    1. Adiciona X-Content-Type-Options: nosniff
    2. Garante no-store em qualquer erro (4xx/5xx) para evitar vazamento de informacao
       ou cache indevido de falhas na CDN da Vercel.
    """
    response = await call_next(request)

    # Adicionar nosniff globalmente por seguranca (RFC 7034)
    if "X-Content-Type-Options" not in response.headers:
        response.headers["X-Content-Type-Options"] = "nosniff"

    # Trava de seguranca Zero Leak: Erros nunca devem ser cacheados em CDNs
    if response.status_code >= 400:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"

    return response


async def _check_upstream_connectivity() -> bool:
    """Valida se o Sispubli (IFS) está respondendo.

    Usa timeout agressivo de 3s para evitar Cascading Failures.
    Se falhar, retorna False sem derrubar a API.
    """
    url = "http://intranet.ifs.edu.br/publicacoes/site/indexCertificados.wsp"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.head(url)
            return resp.status_code < 400
    except Exception as exc:
        log.warning(f"Upstream Health Check falhou (esperado): {exc}")
        return False


@app.get("/", response_model=HealthResponse, tags=["Sistema"])
async def health_check():
    """Painel de saúde e diagnóstico da API."""
    log.info("Health check acessado")

    # Diagnóstico de segurança (Valida se as chaves existem no ambiente)
    env_vars = ["HASH_SALT", "FERNET_SECRET_KEY", "SECRET_PEPPER"]
    is_secure = all(os.environ.get(v) for v in env_vars)

    response_data = {
        "status": "online",
        "environment": os.environ.get("ENVIRONMENT", "development"),
        "version": app.version,
        "timestamp": datetime.now(UTC),
        "security_configured": is_secure,
        "sispubli_online": await _check_upstream_connectivity(),
    }

    response = JSONResponse(content=jsonable_encoder(response_data))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Interceta chamadas ao favicon para evitar spam de 404 e usar a logo do IFS."""
    # Usar caminho absoluto baseado na raiz do projeto é mais seguro para deploy serverless
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, "static", "favicon.ico")

    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="image/x-icon")
    return Response(status_code=204)


# ===================================================================
# ROTA: Autenticacao — POST /api/auth/token
# ===================================================================


@app.post(
    "/api/auth/token",
    response_model=TokenResponse,
    tags=["Autenticação"],
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
    if not validar_cpf(cpf):
        log.warning(f"CPF matematicamente invalido no auth: '{cpf[:3]}...'")
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_cpf",
                    "message": "CPF invalido",
                }
            },
        )

    # --- Geracao de token e hash ---
    token = gerar_token_sessao(cpf)
    session_hash = derivar_session_hash(token)

    log.info(f"Token de sessao gerado com sucesso (hash: {session_hash[:16]}...)")
    response = JSONResponse(content={"access_token": token, "session_hash": session_hash})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


# ===================================================================
# ROTA: Listagem segura — GET /api/certificados
# ===================================================================

# Regex para limpar CPF de URLs e campos (captura 3 digitos para manter LGPD + rastreabilidade)
_CPF_PATTERN = re.compile(r"(?<!\d)(\d{3})\d{8}(?!\d)")


def _extrair_bearer_token(request: Request) -> str | None:
    """Extrai o token do header Authorization: Bearer <token>."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[7:]  # Remove 'Bearer '


def _substituir_urls_por_tickets(certificados: list[dict], cpf_real: str) -> list[dict]:
    """Substitui url_download por /api/pdf/{ticket} criptografados.

    Preenche o placeholder {cpf} da URL com o CPF real do servidor ANTES de
    encapsular no Ticket Fernet, caso contrario o Sispubli geraria Relatorios
    Brancos Vázios (Blank Page de 1096 bytes) buscando pelo cpf literal '{cpf}'.
    """
    resultado = []
    for cert in certificados:
        cert_copy = copy.deepcopy(cert)
        url = cert_copy.get("url_download")
        if url:
            # Resolucao fundamental para o 'Blank Page Jasper Bug':
            url_preenchida = url.replace("{cpf}", cpf_real)
            ticket = gerar_ticket_pdf(url_preenchida)
            cert_copy["url_download"] = f"/api/pdf/{ticket}"
        resultado.append(cert_copy)
    return resultado


def _sanitizar_cpf_resposta(certificados: list[dict]) -> list[dict]:
    """Remove qualquer CPF que ainda exista nos campos da resposta."""
    resultado = []
    for cert in certificados:
        cert_limpo = {}
        for key, value in cert.items():
            # id_unico ja e um hash seguro com SALT, sanitizacao o corromperia
            if key == "id_unico":
                cert_limpo[key] = value
            elif isinstance(value, str):
                cert_limpo[key] = _CPF_PATTERN.sub("{cpf}", value)
            else:
                cert_limpo[key] = value
        resultado.append(cert_limpo)
    return resultado


@app.get(
    "/api/certificados",
    response_model=CertificadosResponse,
    tags=["Certificados"],
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
    if len(raw_token) > 2048:
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

    # --- Chamada ao scraper ---
    try:
        resultado_raw = fetch_all_certificates(cpf)
        # Deepcopy fundamental para nao 'envenenar' o cache do scraper com tickets/mascaras
        resultado = copy.deepcopy(resultado_raw)
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
    certs_com_tickets = _substituir_urls_por_tickets(certs, cpf)
    certs_limpos = _sanitizar_cpf_resposta(certs_com_tickets)

    response_data = {
        "data": {
            "usuario_id": resultado.get("usuario_id", ""),
            "total": resultado.get("total", 0),
            "certificados": certs_limpos,
        }
    }

    response = JSONResponse(content=response_data)
    # Cache privado no cliente (App/Browser) por 5 minutos
    response.headers["Cache-Control"] = "private, max-age=300, must-revalidate"
    response.headers["Vary"] = "Authorization"
    return response


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
    tags=["Certificados"],
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
    """Tunel seguro para download de PDFs do Sispubli com bypass de frameset."""
    # --- Camada 1: Descriptografar ticket ---
    try:
        url = ler_ticket_pdf(ticket)
    except Exception:
        log.warning("Ticket de PDF invalido ou corrompido")
        return JSONResponse(
            status_code=400,
            content={
                "error": {"code": "invalid_ticket", "message": "Ticket invalido ou corrompido."}
            },
        )

    # --- Camada 2: Validacao SSRF ---
    parsed = urlparse(url)
    if not parsed.hostname or not is_safe_host(parsed.hostname):
        log.warning(f"SSRF bloqueado. Hostname: {parsed.hostname} | URL decriptada: {url}")
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
    ticket_hash = ticket[:32]
    if not await ticket_limiter.check(ticket_hash):
        log.warning(f"Rate limit de ticket excedido: {ticket_hash[:16]}...")
        return JSONResponse(
            status_code=429,
            content={
                "error": {"code": "rate_limit_exceeded", "message": "Limite de downloads excedido."}
            },
        )

    async def pdf_streamer(authenticated_client, first_chunk, upstream_response, content_iterator):
        """Gerador assincrono que consome o resto do PDF do Sispubli."""
        try:
            yield first_chunk
            total_bytes = len(first_chunk)
            async for chunk in content_iterator:
                total_bytes += len(chunk)
                yield chunk

            log.info(f"✅ [TUNEL SUCESSO] Certificado entregue. Total: {total_bytes} bytes.")
        except Exception as e:
            log.error(f"❌ [TUNEL ERRO] Falha durante o streaming: {str(e)}")
        finally:
            await upstream_response.aclose()
            await authenticated_client.aclose()

    # Camada 4: Controle de Concorrência
    async with _tunnel_semaphore:
        # Camada 5: Simulamos ser o Google Chrome perfeito para burlar firewalls/WAF
        browser_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",  # noqa: E501
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",  # noqa: E501
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
        }

        # O httpx vai reter os cookies de sessao temporarios entre a Etapa A e B
        client = httpx.AsyncClient(timeout=20.0, follow_redirects=True)
        try:
            # ETAPA A: O Gatilho (Bate na URL com o CPF para armar o PDF no backend)
            prep_response = await client.get(url, headers=browser_headers)

            if prep_response.status_code >= 400:
                await client.aclose()
                log.error(f"[TUNEL ERRO] Falha no gatilho. Status {prep_response.status_code}")
                return JSONResponse(
                    status_code=502,
                    content={
                        "error": {
                            "code": "upstream_error",
                            "message": "O sistema de origem nao respondeu corretamente ao gatilho.",
                        }
                    },
                )

            # ETAPA B: A Captura (Requisita o binario passando o Referer forjado)
            base_sispubli = f"{parsed.scheme}://{parsed.netloc}"
            target_url = f"{base_sispubli}/publicacoes/ReportConnector.wsp?tmp.reportShow=true"

            pdf_headers = browser_headers.copy()
            pdf_headers["Referer"] = url  # <-- O SEGREDO DO SISPUBLI ESTA AQUI

            # Abrimos o stream manualmente para inspecionar o primeiro chunk
            # antes de dar 200 pro cliente
            stream_req = client.build_request("GET", target_url, headers=pdf_headers)
            upstream_response = await client.send(stream_req, stream=True)

            # --- A INTERCEPTACAO ANTECIPADA (Camada 2 da SPEC) ---
            if upstream_response.status_code != 200:
                await upstream_response.aclose()
                await client.aclose()
                log.error(f"❌ [TUNEL ERRO] Upstream status {upstream_response.status_code}")
                return JSONResponse(
                    status_code=502,
                    content={
                        "error": {
                            "code": "upstream_refusal",
                            "message": "O sistema de origem recusou a entrega do arquivo.",
                        }
                    },
                )

            # Lemos o primeiro chunk para validar os Magic Bytes do PDF
            content_iterator = upstream_response.aiter_bytes()
            try:
                primeiro_chunk = await anext(content_iterator)
            except StopAsyncIteration:
                primeiro_chunk = b""

            # Validação rigorosa do PDF (Magic Bytes %PDF-)
            if not primeiro_chunk.lstrip().startswith(b"%PDF-"):
                log.error("❌ [TUNEL ERRO] O Sispubli retornou HTML/Erro em vez de PDF!")
                log.error(f"Conteudo interceptado: {primeiro_chunk[:100]!r}")
                await upstream_response.aclose()
                await client.aclose()
                return JSONResponse(
                    status_code=502,
                    content={
                        "error": {
                            "code": "fake_pdf",
                            "message": (
                                "O arquivo retornado pelo sistema de origem nao e um PDF valido."
                            ),
                        }
                    },
                )

            # Se chegou aqui, o arquivo é um PDF legítimo.
            # Iniciamos o streaming real para o navegador.
            return StreamingResponse(
                pdf_streamer(client, primeiro_chunk, upstream_response, content_iterator),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": 'inline; filename="certificado.pdf"',
                    "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=86400",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        except httpx.TimeoutException:
            await client.aclose()
            log.error(f"⏳ [TUNEL TIMEOUT] O Sispubli demorou +20s: {ticket[:10]}...")
            return JSONResponse(
                status_code=504,
                content={
                    "error": {
                        "code": "gateway_timeout",
                        "message": "O sistema de origem demorou a responder.",
                    }
                },
            )
        except Exception as e:
            if "client" in locals():
                await client.aclose()

            # Sanitizacao de PII na string da excecao antes de logar ou responder
            safe_error_msg = _CPF_PATTERN.sub(r"\g<1>********", str(e))

            log.error(f"💥 [TUNEL CRASH] Erro inesperado no motor: {safe_error_msg}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": f"Erro no tunel: {safe_error_msg}",
                    }
                },
            )
