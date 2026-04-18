import logging
import os
import re
import sys

from loguru import logger

# --- Camada de Seguranca LGPD (Zero Leak) ---

# Regex focada em 11 digitos puros (formato Sispubli), capturando os 3 primeiros
CPF_PATTERN = re.compile(r"(?<!\d)(\d{3})\d{8}(?!\d)")


def sanitizador_lgpd(record):
    """Censura CPFs em mensagens e metadados de logs antes de chegarem ao sink."""
    # 1. Sanitizar a mensagem principal (se for string)

    if isinstance(record["message"], str):
        record["message"] = CPF_PATTERN.sub(r"\g<1>********", record["message"])

    # 2. Sanitizar metadados extras (iterando sobre o dicionario extra)
    for key, value in record["extra"].items():
        if isinstance(value, str):
            record["extra"][key] = CPF_PATTERN.sub(r"\g<1>********", value)


# Aplicar o patch de sanitizacao globalmente no Loguru
logger = logger.patch(sanitizador_lgpd)

# --- Configuracao de Sinks ---

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
        diagnose=False,  # REQUISITO: Impedir vazamento de variaveis locais em tracebacks
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
        diagnose=False,  # SEGURANCA: Mesmo em dev, evitamos vazar CPFs da stack frame
    )


# --- Interceptacao de Logs de Bibliotecas Externas (ex: httpx, uvicorn) ---


class InterceptHandler(logging.Handler):
    """Handler para capturar logs do modulo 'logging' padrao e rota-los para o Loguru."""

    def emit(self, record):
        # Obter nivel correspondente do Loguru (se existir)
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Encontrar de onde veio a chamada do log original
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def aplicar_interceptor():
    """Captura todos os logs do root logger e redireciona para o Loguru sanitizado."""
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Opcional: silenciar loggers barulhentos ou ajustar niveis especificos
    # Mas manteremos httpx em INFO conforme SPEC para manter observabilidade censurada.
    logging.getLogger("httpx").setLevel(logging.INFO)


# --- Utilitarios ---


def get_logger(name: str) -> logger.__class__:
    """Wrapper de compatibilidade — retorna logger com contexto de modulo."""
    return logger.bind(module=name)
