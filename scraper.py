"""
Scraper Sispubli — Motor Iterativo de Extracao de Certificados.

Extrai todos os certificados de um CPF no sistema Sispubli do IFS,
usando paginacao baseada em offsets via POST.

Funcoes principais:
    fetch_all_certificates(cpf) -> dict  [PONTO DE ENTRADA]
    extract_data(html) -> dict           [PARSING DE HTML]
    mask_cpf(cpf) -> str                 [ANONIMIZACAO]
    generate_cert_id(cpf, tipo, prog, edic) -> str  [HASH MD5]
    montar_url(params) -> str | None     [MONTAGEM DE URL]
    extract_next_offset(html) -> int | None  [DETECCAO DE PAGINACAO]
"""

import hashlib
import re
import warnings

import requests
from bs4 import BeautifulSoup

from logger import get_logger

log = get_logger(__name__)

URL = "http://intranet.ifs.edu.br/publicacoes/site/indexCertificados.wsp"
BASE_URL = "http://intranet.ifs.edu.br/publicacoes/relat"

# Limite de seguranca para evitar loops infinitos na paginacao
MAX_PAGES = 50

# ---------------------------------------------------------------------------
# Mapeamento de tipos de certificado para endpoints
# ---------------------------------------------------------------------------

# Cada entrada: tipo -> (endpoint, funcao_que_monta_query_params)
# Os params posicionais sao: [cpf, tipo, programa, edicao, sub_evento, ano, id_artigo]
#                              [0]   [1]   [2]       [3]     [4]         [5]  [6]

URL_TYPE_MAP = {
    "1": {
        "endpoint": "certificado_participacao_process.wsp",
        "params_fn": lambda p: (
            f"tmp.tx_cpf={p[0]}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}"
        ),
    },
    "2": {
        "endpoint": "certificado_autor_process.wsp",
        "params_fn": lambda p: (
            f"tmp.tx_cpf={p[0]}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}"
        ),
    },
    "3": {
        "endpoint": "certificado_participacao_sub_evento_process.wsp",
        "params_fn": lambda p: (
            f"tmp.tx_cpf={p[0]}&tmp.id_programa={p[2]}"
            f"&tmp.id_edicao={p[3]}&tmp.id_sub_evento={p[4]}"
        ),
    },
    "4": {
        "endpoint": "certificado_avaliacao_process.wsp",
        "params_fn": lambda p: (
            f"tmp.tx_cpf={p[0]}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}"
        ),
    },
    "5": {
        "endpoint": "certificado_avaliacao_programa_process.wsp",
        "params_fn": lambda p: (
            f"tmp.tx_cpf={p[0]}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}"
        ),
    },
    "6": {
        "endpoint": "certificado_process.wsp",
        "params_fn": lambda p: (
            f"tmp.id={p[6]}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}"
        ),
    },
    "7": {
        "endpoint": "certificado_orientador_process.wsp",
        "params_fn": lambda p: (
            f"tmp.tx_cpf={p[0]}&tmp.id_programa={p[2]}"
            f"&tmp.id_edicao={p[3]}&tmp.id_artigo={p[6]}"
        ),
    },
    "8": {
        "endpoint": "certificado_aluno_voluntario_process.wsp",
        "params_fn": lambda p: (
            f"tmp.tx_cpf={p[0]}&tmp.id_artigo={p[6]}"
        ),
    },
    "9": {
        "endpoint": "certificado_aluno_bolsista_process.wsp",
        "params_fn": lambda p: (
            f"tmp.tx_cpf={p[0]}&tmp.id_artigo={p[6]}"
        ),
    },
    "10": {
        "endpoint": "certificado_ministrante_sub_evento_process.wsp",
        "params_fn": lambda p: (
            f"tmp.id_sub_evento={p[4]}"
        ),
    },
    "11": {
        "endpoint": "certificado_coorientador_process.wsp",
        "params_fn": lambda p: (
            f"tmp.tx_cpf={p[0]}&tmp.id_programa={p[2]}"
            f"&tmp.id_edicao={p[3]}&tmp.id_artigo={p[6]}"
        ),
    },
}


# ===================================================================
# FUNCOES UTILITARIAS
# ===================================================================


def mask_cpf(cpf: str) -> str:
    """Mascara um CPF para exibicao anonimizada.

    Formato: ***.XXX.XXX-**
    Onde X sao os digitos do meio (posicoes 3-8).

    Args:
        cpf: String numerica do CPF (11 digitos).

    Returns:
        CPF mascarado. Se invalido, retorna '***.***-**'.
    """
    if len(cpf) < 11:
        log.warning("CPF com tamanho invalido (%d digitos): mascarando generico", len(cpf))
        return "***.***.***-**"

    masked = f"***.{cpf[3:6]}.{cpf[6:9]}-**"
    log.debug("CPF mascarado: %s", masked)
    return masked


def generate_cert_id(cpf: str, tipo: str, programa: str, edicao: str) -> str:
    """Gera um ID unico (hash MD5) para um certificado.

    Concatena cpf+tipo+programa+edicao e gera o hash hexadecimal.

    Args:
        cpf: CPF do titular.
        tipo: Tipo do certificado (1-11).
        programa: ID do programa.
        edicao: ID da edicao.

    Returns:
        String hexadecimal de 32 caracteres (MD5).
    """
    raw = f"{cpf}{tipo}{programa}{edicao}"
    cert_hash = hashlib.md5(raw.encode("utf-8")).hexdigest()
    log.debug("Hash gerado para [cpf=%s..., tipo=%s, prog=%s, edic=%s]: %s",
              cpf[:3], tipo, programa, edicao, cert_hash)
    return cert_hash


def montar_url(params: list) -> str | None:
    """Monta a URL completa do certificado baseada no tipo.

    Utiliza o mapeamento URL_TYPE_MAP para determinar o endpoint
    e os query params corretos para cada tipo de certificado.

    Args:
        params: Lista de parametros posicionais extraidos do JavaScript:
                [cpf, tipo, programa, edicao, sub_evento, ano, id_artigo]

    Returns:
        URL completa ou None se o tipo nao for mapeado.
    """
    if len(params) < 7:
        log.error("Parametros insuficientes para montar URL: %s", params)
        return None

    tipo = params[1]
    type_config = URL_TYPE_MAP.get(tipo)

    if type_config is None:
        log.warning("Tipo de certificado nao mapeado: '%s' — URL nao gerada", tipo)
        return None

    endpoint = type_config["endpoint"]
    query_params = type_config["params_fn"](params)
    url = f"{BASE_URL}/{endpoint}?{query_params}"
    log.debug("URL montada [tipo=%s]: %s", tipo, url)
    return url


def extract_next_offset(html_content: str) -> int | None:
    """Extrai o offset da proxima pagina do HTML.

    Procura o link com class='nav_go' que contem o JavaScript
    submitWIGrid('grid.certificadosDisponiveis', OFFSET).

    Args:
        html_content: HTML da pagina atual.

    Returns:
        Valor numerico do offset ou None se for a ultima pagina.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    nav_link = soup.find("a", class_="nav_go")

    if not nav_link:
        log.debug("Nenhum link nav_go encontrado — ultima pagina")
        return None

    href = nav_link.get("href", "")
    match = re.search(r"submitWIGrid\([^,]+,\s*(\d+)\)", href)

    if match:
        offset = int(match.group(1))
        log.debug("Offset da proxima pagina: %d", offset)
        return offset

    log.debug("Link nav_go encontrado mas sem offset valido: %s", href)
    return None


# ===================================================================
# FUNCAO DE PARSING (LEGADA — mantida para compatibilidade)
# ===================================================================


def extract_data(html_content: str) -> dict:
    """Extrai token e certificados de uma pagina HTML do Sispubli.

    Args:
        html_content: HTML completo da pagina.

    Returns:
        Dict com 'token' (str) e 'certificates' (list de dicts
        com 'title' e 'params').
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Extrair token
    token_input = soup.find("input", {"name": "wi.token"})
    token = token_input["value"] if token_input else None
    log.debug("Token extraido: %s", token)

    certificates = []

    # Extrair certificados via links abrirCertificado
    links = soup.find_all("a", href=re.compile(r"abrirCertificado"))
    log.debug("Links abrirCertificado encontrados: %d", len(links))

    for link in links:
        href = link["href"]
        match = re.search(r"abrirCertificado\((.*?)\)", href)
        if match:
            params_raw = match.group(1).split(",")
            params = [p.strip().replace("'", "") for p in params_raw]

            row = link.find_parent("tr")
            if row:
                title_td = row.find("td", valign="center", align=None)
                if title_td:
                    title = title_td.get_text(strip=True)
                    certificates.append({"title": title, "params": params})
                    log.debug("Certificado encontrado: %s", title)

    log.info("Pagina processada: token=%s, certificados=%d",
             token[:8] + "..." if token else "N/A", len(certificates))
    return {"token": token, "certificates": certificates}


# ===================================================================
# MOTOR ITERATIVO — PONTO DE ENTRADA PRINCIPAL
# ===================================================================


def fetch_all_certificates(cpf: str) -> dict:
    """Busca TODOS os certificados de um CPF, iterando por todas as paginas.

    Fluxo:
        1. GET inicial para obter token e cookies
        2. POST com CPF para primeira pagina
        3. Loop: se houver link 'Proximo' (nav_go), faz novo POST com offset
        4. Consolida todos os certificados em estrutura padrao

    Args:
        cpf: CPF do titular (apenas numeros, 11 digitos).

    Returns:
        Dict com:
            - usuario_id (str): CPF mascarado
            - total (int): quantidade total de certificados
            - certificados (list): lista de dicts com id_unico, titulo, url

    Raises:
        Exception: Se o acesso HTTP falhar ou token nao for encontrado.
    """
    log.info("="*60)
    log.info("INICIO DA BUSCA DE CERTIFICADOS")
    log.info("CPF: %s", mask_cpf(cpf))
    log.info("="*60)

    session = requests.Session()

    # --- Passo 1: GET inicial ---
    log.info("[PASSO 1] GET inicial para obter token e cookies")
    response_get = session.get(URL)
    if response_get.status_code != 200:
        log.error("Falha no GET inicial: HTTP %d", response_get.status_code)
        raise Exception(f"Erro ao acessar pagina inicial: {response_get.status_code}")

    initial_data = extract_data(response_get.text)
    token = initial_data["token"]

    if not token:
        log.error("Token nao encontrado na pagina inicial")
        raise Exception("Token nao encontrado na pagina inicial")

    log.info("[PASSO 1] Token obtido: %s...", token[:8])

    # --- Passo 2: POST inicial com CPF ---
    log.info("[PASSO 2] POST inicial com CPF")
    payload = {
        "wi.page.prev": "site/indexCertificados",
        "wi.token": token,
        "tmp.acao": "",
        "tmp.params": "",
        "tmp.tx_cpf": cpf,
    }

    response_post = session.post(URL, data=payload)
    if response_post.status_code != 200:
        log.error("Falha no POST inicial: HTTP %d", response_post.status_code)
        raise Exception(f"Erro ao enviar POST: {response_post.status_code}")

    # --- Passo 3: Loop de paginacao ---
    log.info("[PASSO 3] Iniciando loop de paginacao (MAX_PAGES=%d)", MAX_PAGES)

    all_certificates_raw = []
    page_num = 1
    current_html = response_post.text

    while page_num <= MAX_PAGES:
        log.info("[PAGINA %d] Processando...", page_num)

        page_data = extract_data(current_html)
        certs_in_page = page_data["certificates"]
        all_certificates_raw.extend(certs_in_page)

        log.info("[PAGINA %d] %d certificados extraidos (acumulado: %d)",
                 page_num, len(certs_in_page), len(all_certificates_raw))

        # Verificar se ha proxima pagina
        next_offset = extract_next_offset(current_html)
        if next_offset is None:
            log.info("[PAGINA %d] Ultima pagina detectada — encerrando loop", page_num)
            break

        log.info("[PAGINA %d] Proxima pagina detectada: offset=%d", page_num, next_offset)

        # Atualizar token da pagina atual (pode mudar entre paginas)
        if page_data["token"]:
            token = page_data["token"]

        # POST para proxima pagina
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
            log.error("Falha no POST da pagina %d: HTTP %d",
                      page_num + 1, response_next.status_code)
            raise Exception(f"Erro ao buscar pagina {page_num + 1}: {response_next.status_code}")

        current_html = response_next.text
        page_num += 1
    else:
        log.warning("LIMITE DE PAGINAS ATINGIDO (MAX_PAGES=%d) — loop encerrado por seguranca",
                    MAX_PAGES)

    # --- Passo 4: Consolidar resultado ---
    log.info("[PASSO 4] Consolidando %d certificados...", len(all_certificates_raw))

    certificados_finais = []
    for cert in all_certificates_raw:
        params = cert["params"]
        cpf_cert = params[0] if len(params) > 0 else cpf
        tipo = params[1] if len(params) > 1 else "0"
        programa = params[2] if len(params) > 2 else "0"
        edicao = params[3] if len(params) > 3 else "0"

        cert_id = generate_cert_id(cpf_cert, tipo, programa, edicao)
        url = montar_url(params)

        certificados_finais.append({
            "id_unico": cert_id,
            "titulo": cert["title"],
            "url": url,
        })
        log.debug("Certificado consolidado: id=%s titulo=%s", cert_id[:8], cert["title"])

    resultado = {
        "usuario_id": mask_cpf(cpf),
        "total": len(certificados_finais),
        "certificados": certificados_finais,
    }

    log.info("="*60)
    log.info("BUSCA FINALIZADA")
    log.info("Usuario: %s | Total: %d certificados", resultado["usuario_id"], resultado["total"])
    log.info("="*60)

    return resultado


# ===================================================================
# FUNCAO LEGADA (DEPRECADA)
# ===================================================================


def fetch_certificates(cpf: str) -> dict:
    """[DEPRECADA] Use fetch_all_certificates() ao inves desta.

    Mantida para compatibilidade. Busca apenas a primeira pagina.
    """
    warnings.warn(
        "fetch_certificates() esta deprecada. Use fetch_all_certificates().",
        DeprecationWarning,
        stacklevel=2,
    )
    log.warning("Chamada a funcao deprecada fetch_certificates()")

    session = requests.Session()

    response_get = session.get(URL)
    if response_get.status_code != 200:
        raise Exception(f"Erro ao acessar pagina inicial: {response_get.status_code}")

    initial_data = extract_data(response_get.text)
    token = initial_data["token"]

    if not token:
        raise Exception("Token nao encontrado na pagina inicial")

    payload = {
        "wi.page.prev": "site/indexCertificados",
        "wi.token": token,
        "tmp.acao": "",
        "tmp.params": "",
        "tmp.tx_cpf": cpf,
    }

    response_post = session.post(URL, data=payload)
    if response_post.status_code != 200:
        raise Exception(f"Erro ao enviar POST: {response_post.status_code}")

    return extract_data(response_post.text)


# ===================================================================
# PONTO DE ENTRADA CLI
# ===================================================================


if __name__ == "__main__":
    import json
    import os

    from dotenv import load_dotenv

    # Em modo CLI, ativar logs DEBUG para visibilidade completa
    import logging
    logging.getLogger().setLevel(logging.DEBUG)

    load_dotenv()
    cpf = os.getenv("CPF_TESTE")

    if not cpf:
        log.error("CPF_TESTE nao definido no .env")
    else:
        try:
            result = fetch_all_certificates(cpf)
            print("\n" + "=" * 60)
            print("RESULTADO FINAL (JSON)")
            print("=" * 60)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as e:
            log.error("Erro durante execucao: %s", e)
