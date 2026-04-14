"""
Configuracao centralizada de logging para o Sispubli API — Loguru.

Comportamento dinamico baseado na variavel de ambiente ENVIRONMENT:
    - "test"        : Logs desabilitados (silencio total para pytest)
    - "development" : Logs coloridos no terminal, nivel DEBUG (padrao)
    - "production"  : Logs serializados (JSON) no stdout, nivel INFO

Uso:
    from logger import logger
    logger.info("Mensagem")

    # Ou com contexto de modulo:
    from logger import logger
    log = logger.bind(module="meu_modulo")
    log.info("Mensagem com contexto")
"""

import os
import sys

from loguru import logger

# Remover o sink padrao do Loguru (stderr) para configurar do zero
logger.remove()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

if ENVIRONMENT == "test":
    # Silencio total — sem nenhum sink configurado
    pass

elif ENVIRONMENT == "production":
    # JSON serializado para stdout, nivel INFO
    logger.add(
        sys.stdout,
        level="INFO",
        serialize=True,
        backtrace=False,
        diagnose=False,
    )

else:
    # development (padrao): logs coloridos no terminal, nivel DEBUG
    logger.add(
        sys.stdout,
        level="DEBUG",
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[module]!s: <20}</cyan> | "
            "<level>{message}</level>"
        ),
        backtrace=True,
        diagnose=True,
    )


def get_logger(name: str) -> logger.__class__:
    """Wrapper de compatibilidade — retorna logger com contexto de modulo.

    Permite manter imports existentes sem quebrar:
        from logger import get_logger
        log = get_logger(__name__)

    Args:
        name: Nome do modulo (tipicamente __name__).

    Returns:
        Logger Loguru com o campo 'module' vinculado.
    """
    return logger.bind(module=name)
