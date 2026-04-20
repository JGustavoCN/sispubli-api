"""
Parsers de HTML — Certificados.

Responsavel pela extracao de dados estruturados a partir do HTML bruto
do sistema Sispubli, utilizando BeautifulSoup4 e Regex.
"""

import re

from bs4 import BeautifulSoup

from src.core.logger import logger

log = logger.bind(module=__name__)


def extract_next_offset(html_content: str) -> int | None:
    """Extrai o offset da proxima pagina do HTML.

    Procura o link com class='nav_go' que contem o JavaScript
    submitWIGrid('grid.certificadosDisponiveis', OFFSET).
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
