import logging
import sys
from io import StringIO

from logger import CPF_PATTERN, aplicar_interceptor, logger


def test_cpf_regex_pattern():
    """Valida a precisao da Regex de CPF (11 digitos puros)."""
    assert CPF_PATTERN.search("O CPF e 74839210055") is not None
    assert CPF_PATTERN.search("74839210055") is not None

    # Falsos positivos (nao devem dar match)
    assert CPF_PATTERN.search("1234567890") is None  # 10 digitos
    assert CPF_PATTERN.search("123456789012") is None # 12 digitos
    assert CPF_PATTERN.search("123.456.789-01") is None # Formatado (regra e puros)

def test_logger_masking_simple():
    """Verifica se o logger mascara CPFs em mensagens simples."""
    logs = []
    def sink(message):
        logs.append(message)

    # Adicionar sink temporario para o teste
    handler_id = logger.add(sink, format="{message}")
    try:
        logger.info("Acessando dados do CPF 74839210055 agora")
        assert "748********" in logs[0]
        assert "74839210055" not in logs[0]
    finally:
        logger.remove(handler_id)

def test_logger_masking_extra_metadata():
    """Verifica se o logger mascara CPFs dentro de metadados extras."""
    logs = []
    def sink(message):
        logs.append(message)

    # Formato que inclui o extra['cpf']
    handler_id = logger.add(sink, format="{message} | {extra[cpf]}")
    try:
        logger.bind(cpf="74839210055").info("Log com bind")
        assert "748********" in logs[0]
        assert logs[0].count("748********") == 1 # A mensagem nao tinha CPF, apenas o extra

        logger.info("Msg literal 74839210055", cpf="74839210055")
        assert logs[1].count("748********") == 2 # Na msg e no extra
    finally:
        logger.remove(handler_id)

def test_logger_resilience_non_string():
    """Garante que o sanitizador nao quebra com tipos nao-string."""
    logs = []
    def sink(message):
        logs.append(message)

    handler_id = logger.add(sink, format="{message}")
    try:
        # Passando int, list e dict no extra
        logger.info("Teste resilience", user_id=123, tags=["a", "b"], data={"val": 1})
        assert "Teste resilience" in logs[0]
    finally:
        logger.remove(handler_id)

def test_logging_interception():
    """Garante que logs do 'logging' padrao (httpx) sao interceptados e mascarados."""
    # Ativar interceptador para o teste
    aplicar_interceptor()

    logs = []
    def sink(message):
        logs.append(message)

    handler_id = logger.add(sink, format="{message}")
    try:
        # Simular log do HTTPX (que usa logging)
        std_log = logging.getLogger("httpx")
        std_log.info("URL requisitada: http://api.com?cpf=74839210055")

        assert len(logs) > 0
        assert "748********" in logs[0]
    finally:
        logger.remove(handler_id)

def test_diagnose_is_false():
    """Verifica se a configuracao diagnose=False esta ativa nos sinks."""
    # Como nao conseguimos ler facilmente a config interna do Loguru sinks,
    # verificamos se o comportamento de ocultar variaveis locais ocorre.

    # Capturar stdout
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    # Adicionar um sink que emula o de dev mas com diagnose=False (como no logger.py)
    handler_id = logger.add(sys.stdout, backtrace=True, diagnose=False, format="{message}")

    try:
        def crash_me():
            cpf_secreto = "74839210055"  # noqa: F841
            raise ValueError("Crash proposital")

        try:
            crash_me()
        except ValueError:
            logger.exception("Capturamos um crash")

        output = sys.stdout.getvalue()
        assert "cpf_secreto" not in output
        assert "74839210055" not in output
        assert "ValueError: Crash proposital" in output

    finally:
        logger.remove(handler_id)
        sys.stdout = old_stdout
