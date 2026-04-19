import os
import re

import pytest

from validators import validar_cpf

# Valores de Mock Oficiais (LGPD Blindagem)
MOCK_CPF = "74839210055"
MOCK_NAME = "USUARIO MOCK DA SILVA"


@pytest.fixture(autouse=True)
def _set_test_environment(monkeypatch):
    """Define ENVIRONMENT=test para silenciar o Loguru durante testes."""
    monkeypatch.setenv("ENVIRONMENT", "test")


# =============================================================================
# VCR.py — Configuracao de Cassettes e Sanitizacao de PII
# =============================================================================


def _get_cpf_variants() -> list[str]:
    """Retorna lista de variacoes do CPF_TESTE para busca e substituicao."""
    real_cpf = os.getenv("CPF_TESTE")
    if not real_cpf or not validar_cpf(real_cpf):
        return []

    # Apenas numeros
    numeric_only = re.sub(r"\D", "", real_cpf)

    # Formato XXX.XXX.XXX-XX
    formatted = f"{numeric_only[:3]}.{numeric_only[3:6]}.{numeric_only[6:9]}-{numeric_only[9:]}"

    # Retorna variacoes (removendo duplicatas se ja estiver formatado)
    return list(set([numeric_only, formatted]))


def _scrub_pii(data: str | bytes) -> str | bytes:
    """Substitui valores reais por mocks em strings ou bytes."""
    if not data:
        return data

    is_bytes = isinstance(data, bytes)
    content = data.decode("utf-8", errors="ignore") if is_bytes else str(data)

    # 1. Limpar variações do CPF
    for variant in _get_cpf_variants():
        content = content.replace(variant, MOCK_CPF)

    # 2. Limpar Nome Real
    real_name = os.getenv("NOME_TESTE")
    if real_name and len(real_name) > 3:
        content = content.replace(real_name, MOCK_NAME)

    return content.encode("utf-8") if is_bytes else content


def _scrub_headers(headers: dict):
    """Itera e limpa PII de todos os headers."""
    if not headers:
        return headers

    for key, val_list in headers.items():
        if isinstance(val_list, list):
            headers[key] = [_scrub_pii(v) for v in val_list]
        else:
            headers[key] = _scrub_pii(val_list)
    return headers


def before_record_request(request):
    """Filtra PII da requisicao antes de gravar no disco."""
    # 1. Limpar URL
    request.uri = _scrub_pii(request.uri)

    # 2. Limpar Headers (Zero Leak - inclui Referer)
    request.headers = _scrub_headers(dict(request.headers))

    # 3. Limpar Body
    if request.body:
        request.body = _scrub_pii(request.body)

    return request


def before_record_response(response):
    """Filtra PII da resposta antes de gravar no disco."""
    # 1. Limpar Headers da resposta
    response["headers"] = _scrub_headers(response.get("headers", {}))

    # 2. Limpar Body da resposta
    if response.get("body") and response["body"].get("string"):
        response["body"]["string"] = _scrub_pii(response["body"]["string"])

    return response


@pytest.fixture(scope="session")
def vcr_config():
    """Configuracao global do plugin pytest-recording / vcrpy."""
    return {
        "before_record_request": before_record_request,
        "before_record_response": before_record_response,
        "decode_compressed_response": True,
        "filter_headers": [
            "Authorization",
            "Cookie",
            "Set-Cookie",
            "wi.token",
        ],
        "filter_query_parameters": ["wi.token"],
    }
