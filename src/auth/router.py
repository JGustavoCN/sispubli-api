"""
Router de Autenticacao — Sispubli API.

Gerencia a geracao de tokens de sessao e hashes de sessao.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from rate_limit import auth_limiter, extrair_ip_real
from src.core.logger import logger
from src.core.schemas import ErrorResponse
from src.core.security import derivar_session_hash, gerar_token_sessao, normalizar_cpf
from src.core.validators import validar_cpf

from .schemas import TokenRequest, TokenResponse

log = logger.bind(module=__name__)

router = APIRouter(tags=["Autenticação"])


@router.post(
    "/api/auth/token",
    response_model=TokenResponse,
    responses={
        400: {"model": ErrorResponse, "description": "CPF invalido"},
        422: {"model": ErrorResponse, "description": "Erro de validacao de campos"},
        429: {"model": ErrorResponse, "description": "Rate limit excedido"},
    },
)
async def auth_token(body: TokenRequest, request: Request):
    """Gera token de sessao e session_hash para um CPF.

    O CPF e normalizado, validado e criptografado via Fernet.
    O token tem TTL de 15 minutos. O session_hash e derivado
    com SHA-256 + SECRET_PEPPER para uso como cache key.
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
