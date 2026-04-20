"""
Scraper Sispubli — Motor Iterativo de Extracao de Certificados.

Este modulo orquestra a comunicacao HTTP com o sistema Sispubli do IFS,
gerenciando a sessao, o envio de CPFs e a iteracao por paginas de resultados.

A logica de parsing, constantes e utilitarios de dominio estao desacopladas
em modulos internos do pacote.
"""

from functools import lru_cache

import requests

from src.core.logger import logger
from src.core.security import mask_cpf

from .constants import MAX_PAGES, TIPO_DESCRICAO_MAP, URL
from .parsers import extract_data, extract_next_offset
from .utils import generate_cert_id, montar_url

log = logger.bind(module=__name__)


@lru_cache(maxsize=128)
def fetch_all_certificates(cpf: str) -> dict:
    """Busca TODOS os certificados de um CPF, iterando por todas as paginas.

    Resultado e cacheado em memoria (lru_cache).

    Fluxo:
        1. GET inicial para obter token e cookies
        2. POST com CPF para primeira pagina
        3. Loop: se houver link 'Proximo' (nav_go), faz novo POST com offset
        4. Consolida todos os certificados em estrutura padrao

    Args:
        cpf: CPF do titular (apenas numeros, 11 digitos).

    Returns:
        Dict com usuario_id, total e lista de certificados.
    """
    log.info("=" * 60)
    log.info("INICIO DA BUSCA DE CERTIFICADOS")
    log.info(f"CPF: {mask_cpf(cpf)}")
    log.info("=" * 60)

    session = requests.Session()

    # --- Passo 1: GET inicial ---
    log.info("[PASSO 1] GET inicial para obter token e cookies")
    response_get = session.get(URL)
    if response_get.status_code != 200:
        log.error(f"Falha no GET inicial: HTTP {response_get.status_code}")
        raise Exception(f"Erro ao acessar pagina inicial: {response_get.status_code}")

    initial_data = extract_data(response_get.text)
    token = initial_data["token"]

    if not token:
        log.error("Token nao encontrado na pagina inicial")
        raise Exception("Token nao encontrado na pagina inicial")

    log.info(f"[PASSO 1] Token obtido: {token[:8]}...")

    # --- Passo 2: POST inicial com CPF ---
    log.info("[PASSO 2] POST inicial com CPF (mascarado)")
    payload = {
        "wi.page.prev": "site/indexCertificados",
        "wi.token": token,
        "tmp.acao": "",
        "tmp.params": "",
        "tmp.tx_cpf": cpf,
    }

    response_post = session.post(URL, data=payload)
    if response_post.status_code != 200:
        log.error(f"Falha no POST inicial: HTTP {response_post.status_code}")
        raise Exception(f"Erro ao enviar POST: {response_post.status_code}")

    # --- Passo 3: Loop de paginacao ---
    log.info(f"[PASSO 3] Iniciando loop de paginacao (MAX_PAGES={MAX_PAGES})")

    all_certificates_raw = []
    page_num = 1
    current_html = response_post.text

    while page_num <= MAX_PAGES:
        log.info(f"[PAGINA {page_num}] Processando...")

        page_data = extract_data(current_html)
        certs_in_page = page_data["certificates"]
        all_certificates_raw.extend(certs_in_page)

        log.info(
            f"[PAGINA {page_num}] {len(certs_in_page)} certificados extraidos"
            f" (acumulado: {len(all_certificates_raw)})"
        )

        next_offset = extract_next_offset(current_html)
        if next_offset is None:
            log.info(f"[PAGINA {page_num}] Ultima pagina detectada — encerrando loop")
            break

        log.info(f"[PAGINA {page_num}] Proxima pagina detectada: offset={next_offset}")

        if page_data["token"]:
            token = page_data["token"]

        payload_next = {
            "wi.page.prev": "site/indexCertificados",
            "wi.token": token,
            "tmp.acao": "",
            "tmp.params": "",
            "tmp.tx_cpf": cpf,
            "grid.certificadosDisponiveis.next": str(next_offset),
        }

        response_next = session.post(URL, data=payload_next)
        if response_next.status_code != 200:
            log.error(f"Falha no POST da pagina {page_num + 1}: HTTP {response_next.status_code}")
            raise Exception(f"Erro ao buscar pagina {page_num + 1}: {response_next.status_code}")

        current_html = response_next.text
        page_num += 1
    else:
        log.warning(
            f"LIMITE DE PAGINAS ATINGIDO (MAX_PAGES={MAX_PAGES}) — loop encerrado por seguranca"
        )

    # --- Passo 4: Consolidar resultado ---
    log.info(f"[PASSO 4] Consolidando {len(all_certificates_raw)} certificados...")

    certificados_finais = []
    for cert in all_certificates_raw:
        params = cert["params"]

        # Posicoes: [cpf, tipo, programa, edicao, sub_evento, ano, id_artigo]
        cpf_cert = params[0] if len(params) > 0 else cpf
        tipo = params[1] if len(params) > 1 else "0"
        programa = params[2] if len(params) > 2 else "0"
        edicao = params[3] if len(params) > 3 else "0"
        ano_raw = params[5] if len(params) > 5 else "0"

        cert_id = generate_cert_id(cpf_cert, tipo, programa, edicao)
        url = montar_url(params)

        try:
            ano = int(ano_raw)
        except (ValueError, TypeError):
            ano = 0
            log.warning(f"Ano invalido para certificado '{cert['title']}': '{ano_raw}'")

        tipo_codigo = int(tipo) if tipo.isdigit() else 0
        tipo_descricao = TIPO_DESCRICAO_MAP.get(tipo, f"Tipo {tipo}")

        certificados_finais.append(
            {
                "id_unico": cert_id,
                "titulo": cert["title"],
                "url_download": url,
                "ano": ano,
                "tipo_codigo": tipo_codigo,
                "tipo_descricao": tipo_descricao,
            }
        )
        log.debug(
            f"Certificado consolidado: id={cert_id[:16]}..."
            f" titulo={cert['title'][:30]} ano={ano} tipo={tipo_descricao}"
        )

    resultado = {
        "usuario_id": mask_cpf(cpf),
        "total": len(certificados_finais),
        "certificados": certificados_finais,
    }

    log.info("=" * 60)
    log.info("BUSCA FINALIZADA")
    log.info(f"Usuario: {resultado['usuario_id']} | Total: {resultado['total']} certificados")
    log.info("=" * 60)

    return resultado
