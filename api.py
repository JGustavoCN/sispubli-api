"""
API REST do Sispubli — FastAPI.

Expoe o motor de extracao de certificados como endpoints HTTP.

Rotas:
    GET /                        : Health check
    GET /api/certificados/{cpf}  : Busca todos os certificados de um CPF

Respostas seguem o padrao:
    Sucesso: {"data": {...}}
    Erro:    {"error": {"code": "...", "message": "..."}}
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from logger import get_logger
from scraper import fetch_all_certificates

log = get_logger(__name__)

app = FastAPI(
    title="Sispubli Certificados API",
    description="API para extracao de certificados do sistema Sispubli/IFS",
    version="1.0.0",
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


@app.get("/")
def health_check():
    """Rota de verificacao de saude da API."""
    log.info("Health check acessado")
    return {"status": "API do Sispubli rodando"}


@app.get("/api/certificados/{cpf}")
def buscar_certificados(cpf: str):
    """Busca todos os certificados disponiveis para um CPF.

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
    log.info("Requisicao recebida: GET /api/certificados/%s", cpf[:3] + "***")

    # --- Validacao do CPF ---
    if not cpf.isdigit() or len(cpf) != 11:
        log.warning("CPF invalido recebido: '%s' (len=%d)", cpf[:3] + "...", len(cpf))
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
        log.info("Busca concluida: %d certificados encontrados", resultado["total"])
        return {"data": resultado}

    except Exception as e:
        error_message = str(e)
        log.error("Erro durante busca de certificados: %s", error_message)

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
