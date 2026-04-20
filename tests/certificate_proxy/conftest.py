from unittest.mock import MagicMock

import pytest

from src.core.rate_limit import auth_limiter, ip_limiter, ticket_limiter


@pytest.fixture(autouse=True)
def _reset_limiters():
    """Reseta todos os rate limiters de infraestrutura entre cada teste do Proxy."""
    auth_limiter._requests.clear()
    ip_limiter._requests.clear()
    ticket_limiter._requests.clear()
    yield
    auth_limiter._requests.clear()
    ip_limiter._requests.clear()
    ticket_limiter._requests.clear()


# ===========================================================================
# INFRAESTRUTURA DE MOCK (Streaming/Async HTTP)
# ===========================================================================


class MockAsyncResponseManager:
    """Simula o gerenciador de contexto de uma resposta de streaming do httpx."""

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
    """Mock básico para httpx.AsyncClient() compatível com o domínio Proxy."""

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
    """Fixture: Simula entrega bem sucedida de um PDF real."""
    monkeypatch.setattr("src.certificate_proxy.services.httpx.AsyncClient", MockAsyncClient)


@pytest.fixture
def mock_httpx_fake_pdf(monkeypatch):
    """Fixture: Simula 'Falso PDF' (HTML disfarçado de PDF)."""

    class FakePDFClient(MockAsyncClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.chunks = [b"<html>Acesso Negado ou Redirecionamento de Auth</html>"]

    monkeypatch.setattr("src.certificate_proxy.services.httpx.AsyncClient", FakePDFClient)


@pytest.fixture
def mock_httpx_timeout(monkeypatch):
    """Fixture: Simula falha de timeout agressivo no upstream."""
    import httpx

    class TimeoutClient(MockAsyncClient):
        async def get(self, *args, **kwargs):
            raise httpx.TimeoutException("Timeout simulado")

    monkeypatch.setattr("src.certificate_proxy.services.httpx.AsyncClient", TimeoutClient)


@pytest.fixture
def mock_httpx_refusal(monkeypatch):
    """Fixture: Simula erro interno ou recusa do servidor Sispubli (500)."""

    class RefusalClient(MockAsyncClient):
        async def get(self, *args, **kwargs):
            mock = MagicMock()
            mock.status_code = 500
            return mock

    monkeypatch.setattr("src.certificate_proxy.services.httpx.AsyncClient", RefusalClient)
