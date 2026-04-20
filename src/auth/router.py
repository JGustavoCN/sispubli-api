"""
Router de Autenticacao — Sispubli API.

Gerencia a geracao de tokens de sessao e hashes de sessao.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.core.logger import logger
from src.core.rate_limit import auth_limiter, extrair_ip_real
from src.core.schemas import ErrorResponse
from src.core.security import gerar_token_sessao, normalizar_cpf
from src.core.validators import validar_cpf

from .schemas import TokenRequest, TokenResponse

log = logger.bind(module=__name__)

router = APIRouter(tags=["Auth"])


@router.post(
    "/api/auth/token",
    response_model=TokenResponse,
    summary="Geração de credenciais de acesso temporárias",
    description=(
        "Normaliza, valida e criptografa o CPF do titular em um token de acesso efêmero. "
        "O token resultante utiliza criptografia Fernet (AES-128-CBC) e possui um "
        "tempo de vida (TTL) de 15 minutos."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "CPF invalido"},
        422: {"model": ErrorResponse, "description": "Erro de validacao de campos"},
        429: {"model": ErrorResponse, "description": "Rate limit excedido"},
    },
)
async def auth_token(body: TokenRequest, request: Request):
    """Gera token de sessao para um CPF.

    O CPF e normalizado, validado e criptografado via Fernet.
    O token tem TTL de 15 minutos.
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

    # --- Geracao de token ---
    token = gerar_token_sessao(cpf)

    log.info("Token de sessao gerado com sucesso")
    response = JSONResponse(content={"access_token": token})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response
