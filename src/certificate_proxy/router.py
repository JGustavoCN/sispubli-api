"""
Router do Tunel de PDF — Sispubli API.
"""

from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from rate_limit import ticket_limiter
from src.core.logger import logger
from src.core.schemas import ErrorResponse
from src.core.security import CPF_PATTERN, ler_ticket_pdf

from .constants import _tunnel_semaphore
from .services import get_certificate_stream, pdf_streamer
from .validators import is_safe_host

log = logger.bind(module=__name__)

router = APIRouter(tags=["Certificados"])


@router.get(
    "/api/pdf/{ticket}",
    responses={
        200: {"content": {"application/pdf": {}}, "description": "PDF streamado"},
        400: {"model": ErrorResponse, "description": "Ticket invalido"},
        403: {"model": ErrorResponse, "description": "SSRF bloqueado"},
        429: {"model": ErrorResponse, "description": "Rate limit excedido"},
        502: {"model": ErrorResponse, "description": "Upstream indisponivel"},
        504: {"model": ErrorResponse, "description": "Upstream timeout"},
    },
)
async def tunnel_pdf(ticket: str, request: Request):
    """Tunel seguro para download de PDFs do Sispubli com bypass de frameset.

    O ticket e decriptado para obter a URL real, validado contra SSRF
    e entao processado em duas etapas (Gatilho + Captura) para entrega
    do binario direto para o navegador.
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
        log.warning(f"SSRF bloqueado. Hostname: {parsed.hostname}")
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

    # --- Camada 4: Orquestracao do Proxy (com Controle de Concorrencia) ---
    async with _tunnel_semaphore:
        try:
            base_sispubli = f"{parsed.scheme}://{parsed.netloc}"
            client, chunk, upstream_resp, content_iter = await get_certificate_stream(
                url, base_sispubli
            )

            return StreamingResponse(
                pdf_streamer(client, chunk, upstream_resp, content_iter),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": 'inline; filename="certificado.pdf"',
                    "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=86400",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        except ValueError as e:
            msg = str(e)
            if msg.startswith("falha_"):
                status_code = 502
                code = "upstream_error"
                text = "O sistema de origem nao respondeu corretamente."
            elif msg.startswith("upstream_refusal"):
                status_code = 502
                code = "upstream_refusal"
                text = "O sistema de origem recusou a entrega do arquivo."
            elif msg == "fake_pdf":
                status_code = 502
                code = "fake_pdf"
                text = "O arquivo retornado pelo sistema de origem nao e um PDF valido."
            else:
                status_code = 500
                code = "internal_error"
                text = f"Erro no tunel: {msg}"

            return JSONResponse(
                status_code=status_code,
                content={"error": {"code": code, "message": text}},
            )

        except httpx.TimeoutException:
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
            safe_error_msg = CPF_PATTERN.sub(r"\g<1>********", str(e))
            log.error(f"💥 [TUNEL CRASH] Erro inesperado: {safe_error_msg}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": f"Erro no tunel: {safe_error_msg}",
                    }
                },
            )
