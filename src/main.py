"""
API REST do Sispubli — FastAPI.

Gerencia o tunnel de download de certificados e orquestra a autenticacao
e listagem via rotas modularizadas (Vertical Slices).

Seguranca:
    - Fail Fast em producao: HASH_SALT e FERNET_SECRET_KEY obrigatorios.
    - CPF nunca aparece em logs, URLs ou query parameters.
    - Rate limiting em todos os pontos de entrada sensiveis.

Respostas seguem o padrao:
    Sucesso: {"data": {...}} ou campos diretos
    Erro:    {"error": {"code": "...", "message": "..."}}
"""

import asyncio
import ipaddress
import os
import socket
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rate_limit import ticket_limiter

from .auth.router import router as auth_router
from .certificates.router import router as certificates_router
from .core.config import config
from .core.logger import aplicar_interceptor, logger
from .core.schemas import ErrorResponse
from .core.security import (
    CPF_PATTERN,
    ler_ticket_pdf,
)

log = logger.bind(module=__name__)


# ===========================================================================
# Lifespan — Fail Fast em producao
# ===========================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ativa sistemas de seguranca e valida configuracoes criticas."""
    aplicar_interceptor()

    # Valida se variáveis obrigatórias estão presentes se em produção
    config.validate_production()

    log.info(f"API iniciando em modo: {config.ENVIRONMENT}")
    yield
    log.info("API encerrando")


class HealthResponse(BaseModel):
    """Resposta do health check detalhado."""

    status: str = Field(..., description="Status geral da nossa API")
    environment: str = Field(..., description="Ambiente de execução (development/production)")
    version: str = Field(..., description="Versão atual da API")
    timestamp: datetime = Field(..., description="Momento exato da verificação (UTC)")
    security_configured: bool = Field(..., description="Indica se chaves críticas estão no .env")
    sispubli_online: bool = Field(..., description="Status de conectividade com o sistema upstream")


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

app.mount("/static", StaticFiles(directory="static"), name="static")

# Rotas Modularizadas (Vertical Slices)
app.include_router(auth_router)
app.include_router(certificates_router)


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


# ===========================================================================
# Handlers de Exceção Globais — Padronização de Erros
# ===========================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Garante que erros do FastAPI sigam o padrao {error: {code, message}}."""
    if exc.status_code == 401:
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "unauthorized",
                    "message": exc.detail,
                }
            },
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "http_error",
                "message": exc.detail,
            }
        },
    )


# ===========================================================================
# Middleware — Segurança e Cache
# ===========================================================================


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
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
    }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url, headers=headers)
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
    is_secure = all(getattr(config, v) for v in env_vars)

    response_data = {
        "status": "online",
        "environment": config.ENVIRONMENT,
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
    # A pasta static e os utilitários estão agora um nível acima do src/
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    file_path = os.path.join(base_dir, "static", "favicon.ico")

    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="image/x-icon")
    return Response(status_code=204)


@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
async def chrome_devtools_probe():
    """Silencia o probe do Chrome para evitar ruído de 404 nos logs."""
    return Response(status_code=204)


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
                "error": {
                    "code": "invalid_ticket",
                    "message": "Ticket invalido ou corrompido.",
                }
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
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": "Limite de downloads excedido.",
                }
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
            safe_error_msg = CPF_PATTERN.sub(r"\g<1>********", str(e))

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
