"""
Router de Certificados — Sispubli API.

Encapsula os endpoints relacionados a busca e listagem de certificados,
aplicando seguranca Bearer, rate limiting e transformacoes de PII.
"""

import copy

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials

from rate_limit import extrair_ip_real, ip_limiter
from src.core.logger import logger
from src.core.security import ler_token_sessao, security_scheme

from .schemas import CertificadosResponse
from .scraper import fetch_all_certificates
from .utils import sanitizar_cpf_resposta, substituir_urls_por_tickets

log = logger.bind(module=__name__)

router = APIRouter(tags=["Certificados"])


@router.get(
    "/api/certificados",
    response_model=CertificadosResponse,
    responses={
        401: {"description": "Nao autenticado"},
        400: {"description": "Token invalido"},
        429: {"description": "Rate limit excedido"},
        502: {"description": "Sispubli fora do ar"},
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
    """
    token = credentials.credentials

    # 1. Validar tamanho (segurança adicional contra DoS)
    if len(token) > 2048:
        log.warning("Token rejeitado por tamanho excessivo")
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "token_too_large",
                    "message": "Token excede tamanho maximo permitido.",
                }
            },
        )

    # 2. Descriptografar CPF do token
    try:
        cpf = ler_token_sessao(token)
        if not cpf:
            raise ValueError("Token vazio")
    except Exception:
        log.warning("Tentativa de listagem com token invalido ou expirado")
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "invalid_token",
                    "message": "Token de sessao invalido, corrompido ou expirado.",
                }
            },
        )

    # 3. Rate limit por IP
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

    # 4. Chamada ao scraper
    try:
        resultado_raw = fetch_all_certificates(cpf)
        # Deepcopy fundamental para nao 'envenenar' o cache do scraper
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

    # 5. Transformar resposta (Tickets + Sanitizacao)
    certs = resultado.get("certificados", [])
    certs_com_tickets = substituir_urls_por_tickets(certs, cpf)
    certs_limpos = sanitizar_cpf_resposta(certs_com_tickets)

    response_data = {
        "data": {
            "usuario_id": resultado.get("usuario_id", ""),
            "total": resultado.get("total", 0),
            "certificados": certs_limpos,
        }
    }

    response = JSONResponse(content=response_data)
    # Cache privado no cliente por 5 minutos
    response.headers["Cache-Control"] = "private, max-age=300, must-revalidate"
    response.headers["Vary"] = "Authorization"
    return response
