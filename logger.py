"""
Configuracao centralizada de logging para o Scraper Sispubli.

Uso:
    from logger import get_logger
    log = get_logger(__name__)
    log.info("Mensagem")

Niveis:
    DEBUG   - Detalhes internos (payloads, offsets, HTML parcial)
    INFO    - Fluxo principal (inicio de busca, pagina processada, totais)
    WARNING - Situacoes inesperadas mas nao fatais (tipo desconhecido, MAX_PAGES)
    ERROR   - Falhas que interrompem o fluxo (HTTP != 200, token ausente)
"""

import logging
import sys

# Formato padrao: timestamp | nivel | modulo | mensagem
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Flag para evitar configuracao duplicada
_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configura o logging raiz uma unica vez."""
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger nomeado. Configura o sistema se necessario."""
    setup_logging()
    return logging.getLogger(name)
