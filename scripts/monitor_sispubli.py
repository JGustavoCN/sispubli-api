#!/usr/bin/env python3
"""
Sentinela Sispubli — Monitor de Integridade de Contrato.

Este script bate no sistema Sispubli REAL (IFS) para verificar se a estrutura
HTML esperada pelo scraper ainda existe. Atua como um alerta antecipado
de quebra de contrato.

Uso:
    python scripts/monitor_sispubli.py
"""

import os
import re
import sys

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Adiciona a raiz do projeto ao sys.path para importar logger
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.logger import logger

logger = logger.bind(module=__name__)

# Configurações de URL (devem bater com scraper.py)
URL_BUSCA = "http://intranet.ifs.edu.br/publicacoes/site/indexCertificados.wsp"


def monitor():
    load_dotenv()
    cpf = os.getenv("CPF_TESTE")

    if not cpf or len(cpf) < 11:
        logger.error("[ERRO] CPF_TESTE nao definido ou invalido no .env.")
        sys.exit(1)

    logger.info(f"[SENTINELA] Monitorando Sispubli para o CPF: ***{cpf[3:6]}***...")

    session = requests.Session()

    try:
        # Passo 1: GET (Captura Token CSRF/wi.token)
        logger.info("[SENTINELA] Passo 1: Capturando token inicial...")
        resp_get = session.get(URL_BUSCA, timeout=15)
        resp_get.raise_for_status()

        soup_get = BeautifulSoup(resp_get.text, "html.parser")
        token_input = soup_get.find("input", {"name": "wi.token"})

        if not token_input:
            logger.error("[ERRO] Nao foi possivel encontrar 'wi.token' no formulário inicial.")
            sys.exit(1)

        token = token_input.get("value")
        logger.info(f"OK: Token capturado: {token[:8]}...")

        # Passo 2: POST (Busca Real)
        logger.info("[SENTINELA] Passo 2: Submetendo busca real...")
        payload = {
            "wi.page.prev": "site/indexCertificados",
            "wi.token": token,
            "grid.certificadosDisponiveis.offset": "0",
            "tmp.tx_cpf": cpf,
            "wi.grid.certificadosDisponiveis.search": "Filtrar",
        }
        resp_post = session.post(URL_BUSCA, data=payload, timeout=15)
        resp_post.raise_for_status()

        # Passo 3: Validacao de Contrato (O "Coração" do Scraper)
        logger.info("[SENTINELA] Passo 3: Validando estrutura de dados HTML...")
        html = resp_post.text
        soup_post = BeautifulSoup(html, "html.parser")

        # Verificamos se existem links de certificados
        links = soup_post.find_all("a", href=True)
        cert_links = [link for link in links if "abrirCertificado" in link["href"]]

        # Se nao houver certificados, checamos se ha mensagem ou se o grid existe
        grid = soup_post.find("table", id=lambda x: x and "certificadosDisponiveis" in x)

        if not grid and len(cert_links) == 0:
            logger.warning("[AVISO] Nao foi possivel encontrar o grid de certificados.")
            logger.info("📄 Preview do HTML recebido (primeiros 500 chars):")
            logger.info(html[:500])
            logger.error("[FALHA] Possivel mudança de contrato no Sispubli Legado.")
            sys.exit(1)

        logger.info(f"OK: Estrutura base encontrada. ({len(cert_links)} links)")

        # Passo 4: Validacao de Parametros de Download (JasperReports)
        if len(cert_links) > 0:
            logger.info("[SENTINELA] Passo 4: Validando contrato de download (JS Parameters)...")

            test_link = cert_links[0]["href"]
            match = re.search(r"abrirCertificado\((.*?)\)", test_link)

            if not match:
                logger.error(f"[FALHA] Link JS com formato inesperado: {test_link}")
                sys.exit(1)

            params = [p.strip().strip("'") for p in match.group(1).split(",")]

            if len(params) < 4:
                logger.error(f"[FALHA] Faltam parametros no link JS: {params}")
                sys.exit(1)

            # Validar consitencia dos parametros criticos
            if not params[0].isdigit() or len(params[0]) < 11:
                logger.warning(f"[AVISO] CPF no Link JS parece invalido ou oculto: {params[0]}")

            if not all(p.isdigit() for p in params[1:4]):
                logger.error(
                    f"[FALHA] Parametros de JasperReports nao sao numericos: {params[1:4]}"
                )
                sys.exit(1)

            logger.info(
                f"OK: Parametros extraidos com sucesso: "
                f"Tipo={params[1]}, ID={params[2]}, Ano={params[3]}"
            )
        else:
            logger.info("[AVISO] Sem certificados para validar o Passo 4 (Download).")

        logger.info("OK: Contrato Sispubli (HTML + Download JS) permanece INTEGRAL.")
        sys.exit(0)

    except Exception as e:
        logger.exception(f"[ERRO] CRITICO durante monitoramento: {e}")
        sys.exit(1)


if __name__ == "__main__":
    monitor()
