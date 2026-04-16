"""
Testes do Tunel de Download — GET /api/pdf/{ticket}.

Cobertura TDD das 7 camadas de defesa:
    1. Ticket valido (Fernet decrypt)
    2. SSRF: hostname + DNS rebinding + IP privado
    3. Rate limit por ticket
    4. Semaphore de concorrencia
    5. User-Agent consistente
    6. Content-Length guard (10MB max)
    7. Streaming seguro (sem CPF, sem repasse de headers)
"""

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api import app, is_safe_host
from rate_limit import auth_limiter, ip_limiter, ticket_limiter
from security import gerar_ticket_pdf

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_limiters():
    """Reseta todos os rate limiters entre testes."""
    auth_limiter._requests.clear()
    ip_limiter._requests.clear()
    ticket_limiter._requests.clear()
    yield
    auth_limiter._requests.clear()
    ip_limiter._requests.clear()
    ticket_limiter._requests.clear()


# ===================================================================
# TESTES: Camada 1 — Ticket invalido
# ===================================================================


class TestTunnelTicketValidation:
    """Testes de validacao do ticket criptografado."""

    def test_ticket_invalido_retorna_400(self):
        """Ticket corrompido deve retornar 400."""
        response = client.get("/api/pdf/TICKET_LIXO_INVALIDO")
        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "invalid_ticket"

    def test_ticket_vazio_retorna_404(self):
        """Rota /api/pdf/ sem ticket deve retornar 404."""
        response = client.get("/api/pdf/")
        assert response.status_code in (404, 307)  # redirect ou 404


# ===================================================================
# TESTES: Camada 2 — SSRF Protection (is_safe_host)
# ===================================================================


class TestSsrfProtection:
    """Testes anti-SSRF: hostname, DNS rebinding, IP privado."""

    def test_host_correto_aceito(self):
        """intranet.ifs.edu.br deve ser aceito quando resolve para IP publico."""
        with patch("api.socket.gethostbyname", return_value="200.17.15.1"):
            assert is_safe_host("intranet.ifs.edu.br") is True

    def test_host_incorreto_rejeitado(self):
        """Host que nao e intranet.ifs.edu.br deve ser rejeitado."""
        assert is_safe_host("evil.com") is False

    def test_ip_privado_rejeitado(self):
        """DNS que resolve para IP privado deve ser rejeitado (anti-rebinding)."""
        with patch("api.socket.gethostbyname", return_value="192.168.1.1"):
            assert is_safe_host("intranet.ifs.edu.br") is False

    def test_ip_loopback_rejeitado(self):
        """DNS que resolve para 127.0.0.1 deve ser rejeitado."""
        with patch("api.socket.gethostbyname", return_value="127.0.0.1"):
            assert is_safe_host("intranet.ifs.edu.br") is False

    def test_ip_link_local_rejeitado(self):
        """DNS que resolve para IP link-local (169.254.x.x) deve ser rejeitado."""
        with patch("api.socket.gethostbyname", return_value="169.254.169.254"):
            assert is_safe_host("intranet.ifs.edu.br") is False

    def test_dns_falha_rejeitado(self):
        """Se DNS falhar, host deve ser rejeitado."""
        with patch("api.socket.gethostbyname", side_effect=socket.gaierror):
            assert is_safe_host("intranet.ifs.edu.br") is False

    @patch("api.is_safe_host", return_value=False)
    def test_ticket_com_url_ssrf_retorna_403(self, mock_ssrf):
        """Ticket com URL que falha SSRF deve retornar 403."""
        url = "http://evil.com/malware.pdf"
        ticket = gerar_ticket_pdf(url)
        response = client.get(f"/api/pdf/{ticket}")
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "ssrf_blocked"


# ===================================================================
# TESTES: Camada 3 — Rate Limit por Ticket
# ===================================================================


class TestTunnelRateLimit:
    """Testes de rate limit no tunel de download."""

    @patch("api.ticket_limiter")
    @patch("api.is_safe_host", return_value=True)
    def test_ticket_rate_limit_429(self, mock_ssrf, mock_limiter):
        """Ticket que excede rate limit deve retornar 429."""
        mock_limiter.check = AsyncMock(return_value=False)

        url = "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?x=1"
        ticket = gerar_ticket_pdf(url)
        response = client.get(f"/api/pdf/{ticket}")
        assert response.status_code == 429


# ===================================================================
# TESTES: Camada 6 — Content-Length guard
# ===================================================================


class TestContentLengthGuard:
    """Testes de protecao contra PDFs gigantes."""

    @patch("api.ticket_limiter")
    @patch("api.is_safe_host", return_value=True)
    @patch("api.httpx.AsyncClient")
    def test_pdf_gigante_rejeitado(self, mock_client_cls, mock_ssrf, mock_limiter):
        """PDF > 10MB deve ser rejeitado com 413."""
        mock_limiter.check = AsyncMock(return_value=True)

        # Simular resposta com Content-Length gigante
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": "50000000"}  # 50MB

        mock_response.aclose = AsyncMock()

        mock_prep_response = MagicMock()
        mock_prep_response.status_code = 200
        mock_prep_response.headers = {"content-type": "application/pdf"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_prep_response)
        mock_client.build_request = MagicMock(return_value="mock_request")
        mock_client.send = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()
        mock_client_cls.return_value = mock_client

        url = "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?x=1"
        ticket = gerar_ticket_pdf(url)
        response = client.get(f"/api/pdf/{ticket}")
        assert response.status_code == 413


# ===================================================================
# TESTES: Happy Path com Mock do upstream
# ===================================================================


class TestTunnelHappyPath:
    """Testes do streaming seguro de PDF."""

    @patch("api.ticket_limiter")
    @patch("api.is_safe_host", return_value=True)
    @patch("api.httpx.AsyncClient")
    def test_streaming_pdf_retorna_200(self, mock_client_cls, mock_ssrf, mock_limiter):
        """Ticket valido com URL segura deve streamar o PDF."""
        mock_limiter.check = AsyncMock(return_value=True)

        # Simular resposta valida
        pdf_bytes = b"%PDF-1.4 fake content"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {
            "content-length": str(len(pdf_bytes)),
            "content-type": "application/pdf",
        }
        mock_response.content = pdf_bytes

        async def mock_aiter_bytes(chunk_size):
            yield pdf_bytes

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.aclose = AsyncMock()

        mock_prep_response = MagicMock()
        mock_prep_response.status_code = 200
        mock_prep_response.headers = {"content-type": "application/pdf"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_prep_response)
        mock_client.build_request = MagicMock(return_value="mock_request")
        mock_client.send = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()
        mock_client_cls.return_value = mock_client

        url = "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?x=1"
        ticket = gerar_ticket_pdf(url)
        response = client.get(f"/api/pdf/{ticket}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    @patch("api.ticket_limiter")
    @patch("api.is_safe_host", return_value=True)
    @patch("api.httpx.AsyncClient")
    def test_upstream_fora_do_ar_retorna_502(self, mock_client_cls, mock_ssrf, mock_limiter):
        """Erro de conexao com upstream deve retornar 502."""
        mock_limiter.check = AsyncMock(return_value=True)

        import httpx

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("timeout"))
        mock_client.build_request = MagicMock(return_value="mock_request")
        mock_client.send = AsyncMock()
        mock_client.aclose = AsyncMock()
        mock_client_cls.return_value = mock_client

        url = "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?x=1"
        ticket = gerar_ticket_pdf(url)
        response = client.get(f"/api/pdf/{ticket}")
        assert response.status_code == 502

    @patch("api.ticket_limiter")
    @patch("api.is_safe_host", return_value=True)
    @patch("api.httpx.AsyncClient")
    def test_nenhum_header_sensivel_repassado(self, mock_client_cls, mock_ssrf, mock_limiter):
        """Tunel nao deve repassar Referer ou Cookie do cliente."""
        mock_limiter.check = AsyncMock(return_value=True)

        pdf_bytes = b"%PDF-1.4 fake"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {
            "content-length": str(len(pdf_bytes)),
            "content-type": "application/pdf",
        }
        mock_response.content = pdf_bytes

        async def mock_aiter_bytes(chunk_size):
            yield pdf_bytes

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.aclose = AsyncMock()

        mock_prep_response = MagicMock()
        mock_prep_response.status_code = 200
        mock_prep_response.headers = {"content-type": "application/pdf"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_prep_response)
        mock_client.build_request = MagicMock(return_value="mock_request")
        mock_client.send = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()
        mock_client_cls.return_value = mock_client

        url = "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?x=1"
        ticket = gerar_ticket_pdf(url)

        # Envia com headers maliciosos — nao devem ser repassados
        response = client.get(
            f"/api/pdf/{ticket}",
            headers={
                "Referer": "http://evil.com",
                "Cookie": "session=stolen",
            },
        )
        assert response.status_code == 200
        # Verificar que os headers nao foram repassados ao upstream
        call_kwargs = mock_client.build_request.call_args
        upstream_headers = call_kwargs.kwargs.get("headers", {})
        assert "referer" not in {k.lower() for k in upstream_headers}
        assert "cookie" not in {k.lower() for k in upstream_headers}
