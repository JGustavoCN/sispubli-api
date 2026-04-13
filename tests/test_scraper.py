import pytest
from bs4 import BeautifulSoup
import re
import os

# Função que será implementada no scraper.py
from scraper import extract_data, fetch_certificates
from dotenv import load_dotenv


def test_extract_data_from_mock():
    # Caminho para o arquivo mock
    mock_path = os.path.join("tests", "mock_sispubli.html")

    with open(mock_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    data = extract_data(html_content)

    # a) O valor do input oculto wi.token
    assert data["token"] == "F8EQDGSELWFLUEFV0HIV"

    # b) O título do certificado ("Certificado de Participação...")
    # No mock, o primeiro é "Participação no(a) PFisc 2023"
    assert data["certificates"][0]["title"] == "Participação no(a) PFisc 2023"

    # c) Os parâmetros numéricos exatos de dentro do href contendo o javascript
    # abrirCertificado('10955952530', '1', '1850', '2011', '0', 2023, 0)
    expected_params = ["10955952530", "1", "1850", "2011", "0", "2023", "0"]
    assert data["certificates"][0]["params"] == expected_params


def test_integration_online():
    load_dotenv()
    cpf = os.getenv("CPF_TESTE")

    # Garantir que o CPF existe
    assert cpf, "CPF_TESTE não encontrado no .env"

    # Chamar função de busca real
    data = fetch_certificates(cpf)

    # Validações básicas de sucesso
    assert data["token"] is not None
    assert len(data["token"]) > 0
    assert isinstance(data["certificates"], list)

    # Se houver certificados, validar estrutura do primeiro
    if len(data["certificates"]) > 0:
        cert = data["certificates"][0]
        assert "title" in cert
        assert "params" in cert
        assert len(cert["params"]) >= 6
