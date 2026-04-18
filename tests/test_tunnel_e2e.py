import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api import app
from security import gerar_ticket_pdf

# Setup do cliente de testes
client = TestClient(app)

valid_ticket = gerar_ticket_pdf("http://intranet.ifs.edu.br/publicacoes/site/foo.pdf")


class MockAsyncResponseManager:
    """Mocka o resultado de 'client.stream' devolvendo um iterador assincrono."""

    def __init__(self, status_code, content_type, chunks):
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self.chunks = chunks

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def aclose(self):
        pass

    async def aread(self):
        return b"".join(self.chunks)

    async def aiter_bytes(self, chunk_size=None):
        for chunk in self.chunks:
            yield chunk


class MockAsyncClient:
    """Mocka a instancia do httpx.AsyncClient() para suportar build_request e send."""

    def __init__(self, *args, **kwargs):
        self.trigger_status = 200
        self.pdf_status = 200
        self.content_type = "application/pdf"
        self.chunks = [b"%PDF-1.4\n%Mockado123"]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def get(self, *args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = self.trigger_status
        return mock_resp

    def build_request(self, method, url, **kwargs):
        return MagicMock()

    async def send(self, request, stream=False, **kwargs):
        return MockAsyncResponseManager(self.pdf_status, self.content_type, self.chunks)

    async def aclose(self):
        pass


@pytest.fixture
def mock_httpx_success(monkeypatch):
    """Retorna um PDF legitimo mockado."""
    monkeypatch.setattr("api.httpx.AsyncClient", MockAsyncClient)


@pytest.fixture
def mock_httpx_fake_pdf(monkeypatch):
    """Retorna HTTP 200 e content_type pdf, mas com body HTML. Fake PDF upstream."""

    class FakePDFClient(MockAsyncClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.chunks = [b"<html>Acesso Negado ou Redirecionamento de Auth</html>"]

    monkeypatch.setattr("api.httpx.AsyncClient", FakePDFClient)


def test_magic_bytes_pass(mock_httpx_success):
    """
    DIRETRIZ 1: Teste dos Magic Bytes.
    Garante que quando o Sispubli envia um PDF correto com magic bytes '%PDF',
    nossa API valida e repassa pro Browser do usuario intocado.
    """
    response = client.get(f"/api/pdf/{valid_ticket}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:5] == b"%PDF-"


def test_anti_falso_pdf_block(mock_httpx_fake_pdf):
    """
    DIRETRIZ 2: Teste Anti-Falso PDF (Interceptacao).
    Agora a API deve retornar 502 Bad Gateway ao detectar HTML em vez de PDF
    antes mesmo de comecar o streaming pro cliente.
    """
    response = client.get(f"/api/pdf/{valid_ticket}")

    assert response.status_code == 502
    data = response.json()
    assert data["error"]["code"] == "fake_pdf"
    assert "PDF valido" in data["error"]["message"]


@pytest.fixture
def mock_httpx_timeout(monkeypatch):
    """Simula timeout do httpx."""
    import httpx

    class TimeoutClient(MockAsyncClient):
        async def get(self, *args, **kwargs):
            raise httpx.TimeoutException("Timeout simulado")

    monkeypatch.setattr("api.httpx.AsyncClient", TimeoutClient)


def test_tunnel_timeout_handling(mock_httpx_timeout):
    """Garante que timeouts no upstream retornam 504 Gateway Timeout."""
    response = client.get(f"/api/pdf/{valid_ticket}")
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "gateway_timeout"


@pytest.fixture
def mock_httpx_refusal(monkeypatch):
    """Simula recusa do upstream (403/500)."""

    class RefusalClient(MockAsyncClient):
        async def get(self, *args, **kwargs):
            mock = MagicMock()
            mock.status_code = 500
            return mock

    monkeypatch.setattr("api.httpx.AsyncClient", RefusalClient)


def test_tunnel_upstream_refusal(mock_httpx_refusal):
    """Garante que falhas no gatilho retornam 502 Bad Gateway."""
    response = client.get(f"/api/pdf/{valid_ticket}")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_error"


@pytest.mark.e2e
def test_e2e_real_pdf_tunnel():
    """
    DIRETRIZ 3: O Teste E2E Real (Live Debug - Falso PDF Sispubli).
    Testa se na origem real ele passa %PDF ou aborta.
    """
    cpf_teste = os.environ.get("CPF_TESTE")
    if not cpf_teste:
        pytest.skip("Variavel CPF_TESTE ausente. Abortando Live Test.")

    # 1. Faz Auth Local
    resp_auth = client.post("/api/auth/token", json={"cpf": cpf_teste})
    assert resp_auth.status_code == 200
    token = resp_auth.json()["access_token"]

    # 2. Lista os certificados reais
    resp_list = client.get("/api/certificados", headers={"Authorization": f"Bearer {token}"})
    assert resp_list.status_code == 200

    certificados = resp_list.json().get("data", {}).get("certificados", [])
    if not certificados:
        pytest.skip("Nao ha certificados na base para testar.")

    url_tunel = certificados[0].get("url_download")
    resp_pdf = client.get(url_tunel)

    # Se o Sispubli falhar, nossa API deve retornar 502 ou 200 OK com PDF real
    if resp_pdf.status_code == 502:
        print("✅ Interceptacao 502 funcionou para erro real do Sispubli.")
    else:
        assert resp_pdf.status_code == 200
        assert resp_pdf.content.startswith(b"%PDF")


def test_injecao_cpf_no_ticket_unitario(monkeypatch):
    """
    DIRETRIZ 4: Teste de Injecao de CPF (Anti-Blank Page).
    Garante que a API substitui o placeholder '{cpf}' pelo CPF real do usuario
    dentro do Ticket encriptado, evitando o erro de 'Pagina em Branco' do JasperReports.
    """
    from security import ler_ticket_pdf

    cpf_fake = "74839210055"
    mock_certs = {
        "usuario_id": "***.222.333-**",
        "total": 1,
        "certificados": [
            {
                "id_unico": "hash123",
                "titulo": "Certificado Teste",
                "url_download": "http://servidor.com/relat?cpf={cpf}&id=99",
                "ano": 2024,
                "tipo_codigo": 1,
                "tipo_descricao": "Participacao",
            }
        ],
    }

    # Mockamos o scraper para retornar o placeholder literal
    monkeypatch.setattr("api.fetch_all_certificates", lambda x: mock_certs)
    # Mockamos a validacao do token de sessao para retornar nosso CPF fake
    monkeypatch.setattr("api.ler_token_sessao", lambda x: cpf_fake)

    # Chamamos a rota de listagem (o token 'xyz' é ignorado pelo mock)
    response = client.get("/api/certificados", headers={"Authorization": "Bearer xyz"})

    assert response.status_code == 200
    data = response.json()["data"]
    url_com_ticket = data["certificados"][0]["url_download"]

    # Extraimos o ticket da URL /api/pdf/{ticket}
    ticket = url_com_ticket.replace("/api/pdf/", "")

    # Descriptografamos para ver se o CPF fake entrou no lugar de {cpf}
    url_real_decrypted = ler_ticket_pdf(ticket)

    assert cpf_fake in url_real_decrypted
    assert "{cpf}" not in url_real_decrypted
    assert url_real_decrypted == f"http://servidor.com/relat?cpf={cpf_fake}&id=99"
    print(f"\n[OK] Sucesso: CPF {cpf_fake} injetado corretamente no Ticket.")
