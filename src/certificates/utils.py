"""
Utilitarios de Dominio — Certificados.

Funcoes auxiliares para enriquecimento de dados de certificados,
incluindo geracao de IDs (hashing) e montagem de URLs.
"""

import copy
import hashlib
import re

from src.core.logger import logger
from src.core.security import CPF_PATTERN, gerar_ticket_pdf, mask_cpf

from .constants import BASE_URL, HASH_SALT, URL_TYPE_MAP

log = logger.bind(module=__name__)


def substituir_urls_por_tickets(certificados: list[dict], cpf_real: str) -> list[dict]:
    """Substitui url_download por tickets criptografados (/api/pdf/{ticket}).

    Injeta o CPF do titular na URL original antes de encapsulá-la no Ticket
    Fernet. Este processamento no backend garante que o upstream (Sispubli)
    receba os parâmetros necessários para gerar o documento binário.
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
    """Remove ocorrências de PII sensível dos campos da resposta."""
    resultado = []
    for cert in certificados:
        cert_limpo = {}
        for key, value in cert.items():
            # id_unico ja e um hash seguro com SALT, sanitizacao o corromperia
            if key == "id_unico":
                cert_limpo[key] = value
            elif isinstance(value, str):
                # Substitui padrões de CPF por placeholder genérico
                cert_limpo[key] = CPF_PATTERN.sub("*", value)
            else:
                cert_limpo[key] = value
        resultado.append(cert_limpo)
    return resultado


def generate_cert_id(
    cpf: str,
    tipo: str,
    programa: str,
    edicao: str,
    sub_evento: str = "0",
    id_artigo: str = "0",
) -> str:
    """Gera um ID unico (hash SHA-256 + SALT) para um certificado.

    Concatena SALT+cpf+tipo+programa+edicao+sub_evento+id_artigo e gera
    o hash hexadecimal. Todos os 6 campos discriminatorios sao incluidos
    para evitar colisoes entre atividades do mesmo evento pai.
    """
    raw = f"{HASH_SALT}{cpf}{tipo}{programa}{edicao}{sub_evento}{id_artigo}"
    cert_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    log.debug(
        f"Hash SHA-256 gerado para [cpf={mask_cpf(cpf)}, tipo={tipo},"
        f" prog={programa}, edic={edicao},"
        f" sub={sub_evento}, art={id_artigo}]: {cert_hash[:16]}..."
    )
    return cert_hash


def montar_url(params: list) -> str | None:
    """Monta a URL parametrizada do certificado baseada no tipo.

    Returns:
        URL base com parâmetros de extração ou None se o tipo não for mapeado.
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
    log.debug(f"URL parametrizada montada [tipo={tipo}]: {url}")
    return url


def limpar_titulo(titulo: str) -> str:
    """Limpa prefixos redundantes do titulo do certificado.

    Remove os textos fixos gerados pelo Sispubli que apenas repetem
    o 'tipo' da atividade (informacao ja contida em tipo_descricao).

    Exemplos:
        "Participação no(a) mini curso, Como usar..." -> "Como usar..."
        "Participação no(a) palestra, Scrum..." -> "Scrum..."
        "Participação no(a) PFisc 2023" -> "PFisc 2023"
    """
    # Remove "Participacao no(a) " seguido opcionalmente de
    # um texto indicativo do tipo ate uma virgula ou hifen
    padrao = r"^Participa[cç][aã]o no\(a\)\s*(?:[^,]+,\s*)?"

    titulo_limpo = re.sub(padrao, "", titulo, flags=re.IGNORECASE).strip()
    return titulo_limpo
