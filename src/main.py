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

import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth.router import router as auth_router
from .certificate_proxy.router import router as proxy_router
from .certificates.router import router as certificates_router
from .core.config import config
from .core.logger import aplicar_interceptor, logger

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

tags_metadata = [
    {
        "name": "Auth",
        "description": "Gestão de credenciais e tokens de acesso temporários.",
    },
    {
        "name": "Certificates",
        "description": "Extração iterativa via processamento upstream no sistema Sispubli.",
    },
    {
        "name": "Proxy",
        "description": "Túnel seguro para streaming de documentos binários.",
    },
    {
        "name": "System",
        "description": "Monitoramento de integridade e diagnósticos de infraestrutura.",
    },
]

app = FastAPI(
    title="Sispubli API",
    description=(
        "A Sispubli API fornece uma camada de abstração de alta performance sobre o sistema "
        "Sispubli/IFS, operando sob o padrão de **Vertical Slices**.\n\n"
        "**Pilares de Arquitetura:**\n"
        "- **Autenticação**: Gestão de identidade baseada em tokens Fernet com rotação de "
        "segredos e TTL estrito.\n"
        "- **Extração de Dados (Scraping)**: Motor de scraping resiliente que consolida "
        "informações do sistema upstream com otimização de cache.\n"
        "- **Privacidade e Segurança**: Blindagem de PII conforme LGPD através de hashing "
        "SHA-256 e mascaramento em repouso.\n"
        "- **Proxy de Documentos**: Túnel seguro de transporte de binários que elimina o "
        "vazamento de credenciais no downstream.\n"
    ),
    version="2.1.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
    docs_url=None,  # Desabilita Swagger padrão para usar versão customizada
    redoc_url=None,  # Desabilita ReDoc padrão
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Rotas Modularizadas (Vertical Slices)
app.include_router(auth_router)
app.include_router(certificates_router)
app.include_router(proxy_router)


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


@app.get("/", response_model=HealthResponse, tags=["System"])
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
