"""
Utilitarios de Dominio — Certificados.

Funcoes auxiliares para enriquecimento de dados de certificados,
incluindo geracao de IDs (hashing) e montagem de URLs.
"""

import copy
import hashlib

from src.core.logger import logger
from src.core.security import CPF_PATTERN, gerar_ticket_pdf, mask_cpf

from .constants import BASE_URL, HASH_SALT, URL_TYPE_MAP

log = logger.bind(module=__name__)


def substituir_urls_por_tickets(certificados: list[dict], cpf_real: str) -> list[dict]:
    """Substitui url_download por /api/pdf/{ticket} criptografados.

    Preenche o placeholder {cpf} da URL com o CPF real do servidor ANTES de
    encapsular no Ticket Fernet, caso contrario o Sispubli geraria Relatorios
    Brancos Vazios (Blank Page de 1096 bytes) buscando pelo cpf literal '{cpf}'.
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


def sanitizar_cpf_resposta(certificados: list[dict]) -> list[dict]:
    """Remove qualquer CPF que ainda exista nos campos da resposta."""
    resultado = []
    for cert in certificados:
        cert_limpo = {}
        for key, value in cert.items():
            # id_unico ja e um hash seguro com SALT, sanitizacao o corromperia
            if key == "id_unico":
                cert_limpo[key] = value
            elif isinstance(value, str):
                cert_limpo[key] = CPF_PATTERN.sub("{cpf}", value)
            else:
                cert_limpo[key] = value
        resultado.append(cert_limpo)
    return resultado


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
