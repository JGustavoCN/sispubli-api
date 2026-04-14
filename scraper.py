"""
Scraper Sispubli — Motor Iterativo de Extracao de Certificados.

Extrai todos os certificados de um CPF no sistema Sispubli do IFS,
usando paginacao baseada em offsets via POST.

Fluxo do CPF dentro do sistema:
    1. CPF entra como parametro em fetch_all_certificates(cpf)
    2. Usado no POST payload ao Sispubli (campo tmp.tx_cpf) — nunca logado em claro
    3. Mascarado via mask_cpf() para qualquer log/observabilidade
    4. Hasheado com SHA-256 + SALT para gerar id_unico (LGPD-compliant)
    5. Substituido por "{cpf}" literal na url_download — cliente faz o replace
    6. Nunca persiste no retorno final em texto claro

Funcoes principais:
    fetch_all_certificates(cpf) -> dict  [PONTO DE ENTRADA — lru_cache]
    extract_data(html) -> dict           [PARSING DE HTML]
    mask_cpf(cpf) -> str                 [ANONIMIZACAO]
    generate_cert_id(cpf, tipo, prog, edic) -> str  [HASH SHA-256 + SALT]
    montar_url(params) -> str | None     [MONTAGEM DE URL TEMPLATE]
    extract_next_offset(html) -> int | None  [DETECCAO DE PAGINACAO]
"""

import hashlib
import os
import re
from functools import lru_cache

import requests
from bs4 import BeautifulSoup

from logger import logger

log = logger.bind(module=__name__)

URL = "http://intranet.ifs.edu.br/publicacoes/site/indexCertificados.wsp"
BASE_URL = "http://intranet.ifs.edu.br/publicacoes/relat"

# Limite de seguranca para evitar loops infinitos na paginacao
MAX_PAGES = 50

# SALT para hashing LGPD-compliant. Deve ser definido via env em producao.
# O Fail Fast em producao e feito pelo api.py no lifespan.
HASH_SALT = os.environ.get("HASH_SALT", "chave_secreta_padrao")

# ---------------------------------------------------------------------------
# Mapeamento de codigo de tipo para descricao legivel
# ---------------------------------------------------------------------------

TIPO_DESCRICAO_MAP: dict[str, str] = {
    "1": "Participacao",
    "2": "Autor",
    "3": "Mini-Curso",
    "4": "Avaliacao",
    "5": "Avaliacao de Programa",
    "6": "Certificado Interno",
    "7": "Orientacao",
    "8": "Aluno Voluntario",
    "9": "Aluno Bolsista",
    "10": "Ministrante de Sub-Evento",
    "11": "Coorientacao",
}

# ---------------------------------------------------------------------------
# Mapeamento de tipos de certificado para endpoints
# ---------------------------------------------------------------------------

# Cada entrada: tipo -> (endpoint, funcao_que_monta_query_params)
# Os params posicionais sao: [cpf, tipo, programa, edicao, sub_evento, ano, id_artigo]
#                              [0]   [1]   [2]       [3]     [4]         [5]  [6]
#
# SEGURANCA (URL Template): p[0] (CPF real) e substituido por "{cpf}" literal.
# O cliente (Flutter/MCP) e responsavel por dar o replace no momento do download.

URL_TYPE_MAP = {
    "1": {
        "endpoint": "certificado_participacao_process.wsp",
        "params_fn": lambda p: f"tmp.tx_cpf={{cpf}}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}",
    },
    "2": {
        "endpoint": "certificado_autor_process.wsp",
        "params_fn": lambda p: f"tmp.tx_cpf={{cpf}}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}",
    },
    "3": {
        "endpoint": "certificado_participacao_sub_evento_process.wsp",
        "params_fn": lambda p: (
            f"tmp.tx_cpf={{cpf}}&tmp.id_programa={p[2]}"
            f"&tmp.id_edicao={p[3]}&tmp.id_sub_evento={p[4]}"
        ),
    },
    "4": {
        "endpoint": "certificado_avaliacao_process.wsp",
        "params_fn": lambda p: f"tmp.tx_cpf={{cpf}}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}",
    },
    "5": {
        "endpoint": "certificado_avaliacao_programa_process.wsp",
        "params_fn": lambda p: f"tmp.tx_cpf={{cpf}}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}",
    },
    "6": {
        "endpoint": "certificado_process.wsp",
        "params_fn": lambda p: f"tmp.id={p[6]}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}",
    },
    "7": {
        "endpoint": "certificado_orientador_process.wsp",
        "params_fn": lambda p: (
            f"tmp.tx_cpf={{cpf}}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}&tmp.id_artigo={p[6]}"
        ),
    },
    "8": {
        "endpoint": "certificado_aluno_voluntario_process.wsp",
        "params_fn": lambda p: f"tmp.tx_cpf={{cpf}}&tmp.id_artigo={p[6]}",
    },
    "9": {
        "endpoint": "certificado_aluno_bolsista_process.wsp",
        "params_fn": lambda p: f"tmp.tx_cpf={{cpf}}&tmp.id_artigo={p[6]}",
    },
    "10": {
        "endpoint": "certificado_ministrante_sub_evento_process.wsp",
        "params_fn": lambda p: f"tmp.id_sub_evento={p[4]}",
    },
    "11": {
        "endpoint": "certificado_coorientador_process.wsp",
        "params_fn": lambda p: (
            f"tmp.tx_cpf={{cpf}}&tmp.id_programa={p[2]}&tmp.id_edicao={p[3]}&tmp.id_artigo={p[6]}"
        ),
    },
}


# ===================================================================
# FUNCOES UTILITARIAS
# ===================================================================


def mask_cpf(cpf: str) -> str:
    """Mascara um CPF para exibicao anonimizada em logs.

    Formato: ***.XXX.XXX-**
    Onde X sao os digitos do meio (posicoes 3-8).
    O CPF NUNCA deve aparecer em claro nos logs.

    Args:
        cpf: String numerica do CPF (11 digitos).

    Returns:
        CPF mascarado. Se invalido, retorna '***.***-**'.
    """
    if len(cpf) < 11:
        log.warning(f"CPF com tamanho invalido ({len(cpf)} digitos): mascarando generico")
        return "***.***.***-**"

    masked = f"***.{cpf[3:6]}.{cpf[6:9]}-**"
    log.debug(f"CPF mascarado: {masked}")
    return masked


def generate_cert_id(cpf: str, tipo: str, programa: str, edicao: str) -> str:
    """Gera um ID unico (hash SHA-256 + SALT) para um certificado.

    Concatena SALT+cpf+tipo+programa+edicao e gera o hash hexadecimal.
    O uso de SALT garante conformidade LGPD: mesmo que o hash vaze,
    a reversao para o CPF original e computacionalmente inviavel.

    Args:
        cpf: CPF do titular (nunca exposto no retorno).
        tipo: Tipo do certificado (1-11).
        programa: ID do programa.
        edicao: ID da edicao.

    Returns:
        String hexadecimal de 64 caracteres (SHA-256).
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

    Utiliza o mapeamento URL_TYPE_MAP para determinar o endpoint
    e os query params corretos para cada tipo de certificado.

    SEGURANCA: A URL retornada contem "{cpf}" no lugar do CPF real.
    O cliente (Flutter/MCP) deve executar url.replace("{cpf}", cpf_real)
    antes de fazer o download.

    Args:
        params: Lista de parametros posicionais extraidos do JavaScript:
                [cpf, tipo, programa, edicao, sub_evento, ano, id_artigo]

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
        log.debug(f"Offset da proxima pagina: {offset}")
        return offset

    log.debug(f"Link nav_go encontrado mas sem offset valido: {href}")
    return None


# ===================================================================
# FUNCAO DE PARSING
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
    log.debug(f"Token extraido: {token}")

    certificates = []

    # Extrair certificados via links abrirCertificado
    links = soup.find_all("a", href=re.compile(r"abrirCertificado"))
    log.debug(f"Links abrirCertificado encontrados: {len(links)}")

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
                    log.debug(f"Certificado encontrado: {title}")

    token_display = token[:8] + "..." if token else "N/A"
    log.info(f"Pagina processada: token={token_display}, certificados={len(certificates)}")
    return {"token": token, "certificates": certificates}


# ===================================================================
# MOTOR ITERATIVO — PONTO DE ENTRADA PRINCIPAL
# ===================================================================


@lru_cache(maxsize=128)
def fetch_all_certificates(cpf: str) -> dict:
    """Busca TODOS os certificados de um CPF, iterando por todas as paginas.

    Resultado e cacheado em memoria (lru_cache) para evitar requisicoes
    repetidas ao Sispubli para o mesmo CPF em um curto periodo.
    Use fetch_all_certificates.cache_clear() para invalidar o cache.

    RASTREIO DO CPF (fluxo de seguranca):
        - Recebido como parametro (str de 11 digitos)
        - Mascarado em todos os logs via mask_cpf()
        - Enviado ao Sispubli apenas no payload POST (campo tmp.tx_cpf)
        - Hasheado com SHA-256+SALT para gerar id_unico de cada cert
        - Substituido por "{cpf}" nas urls_download (URL Template)
        - Retornado mascarado em usuario_id
        - NUNCA aparece em texto claro no retorno JSON

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
            - certificados (list): lista de dicts com id_unico, titulo,
              url_download, ano, tipo_codigo, tipo_descricao

    Raises:
        Exception: Se o acesso HTTP falhar ou token nao for encontrado.
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
    # CPF e enviado ao Sispubli como dado de sessao — nao e logado em claro
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

        # Verificar se ha proxima pagina
        next_offset = extract_next_offset(current_html)
        if next_offset is None:
            log.info(f"[PAGINA {page_num}] Ultima pagina detectada — encerrando loop")
            break

        log.info(f"[PAGINA {page_num}] Proxima pagina detectada: offset={next_offset}")

        # Atualizar token da pagina atual (pode mudar entre paginas)
        if page_data["token"]:
            token = page_data["token"]

        # POST para proxima pagina — CPF necessario para manter sessao
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

        # Hash LGPD-compliant — CPF nunca aparece em claro no retorno
        cert_id = generate_cert_id(cpf_cert, tipo, programa, edicao)

        # URL Template — cliente substitui {cpf} pelo CPF real no momento do download
        url = montar_url(params)

        # Enriquecimento de dados
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


# ===================================================================
# PONTO DE ENTRADA CLI
# ===================================================================


if __name__ == "__main__":
    import json

    from dotenv import load_dotenv

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
            log.error(f"Erro durante execucao: {e}")
