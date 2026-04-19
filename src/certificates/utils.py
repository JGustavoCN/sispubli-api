"""
Utilitarios de Dominio — Certificados.

Funcoes auxiliares para enriquecimento de dados de certificados,
incluindo geracao de IDs (hashing) e montagem de URLs.
"""

import hashlib

from src.core.logger import logger
from src.core.security import mask_cpf

from .constants import BASE_URL, HASH_SALT, URL_TYPE_MAP

log = logger.bind(module=__name__)


def generate_cert_id(cpf: str, tipo: str, programa: str, edicao: str) -> str:
    """Gera um ID unico (hash SHA-256 + SALT) para um certificado.

    Concatena SALT+cpf+tipo+programa+edicao e gera o hash hexadecimal.
    """
    raw = f"{HASH_SALT}{cpf}{tipo}{programa}{edicao}"
    cert_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    log.debug(
        f"Hash SHA-256 gerado para [cpf={mask_cpf(cpf)}, tipo={tipo},"
        f" prog={programa}, edic={edicao}]: {cert_hash[:16]}..."
    )
    return cert_hash


def montar_url(params: list) -> str | None:
    """Monta a URL template do certificado baseada no tipo.

    Returns:
        URL template com {cpf} ou None se o tipo nao for mapeado.
    """
    if len(params) < 7:
        log.error(f"Parametros insuficientes para montar URL: {len(params)} recebidos (min 7)")
        return None

    tipo = params[1]
    type_config = URL_TYPE_MAP.get(tipo)

    if type_config is None:
        log.warning(f"Tipo de certificado nao mapeado: '{tipo}' — URL nao gerada")
        return None

    endpoint = type_config["endpoint"]
    query_params = type_config["params_fn"](params)
    url = f"{BASE_URL}/{endpoint}?{query_params}"
    log.debug(f"URL template montada [tipo={tipo}]: {url}")
    return url
