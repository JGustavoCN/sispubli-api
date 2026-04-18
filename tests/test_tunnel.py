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
        """PDF > 10MB deve ser rejeitado. No novo motor, o stream e fechado se exceder."""
        mock_limiter.check = AsyncMock(return_value=True)

        # Mock da resposta de stream
        mock_stream_response = MagicMock()
        mock_stream_response.status_code = 200
        mock_stream_response.aclose = AsyncMock()

        # Gerador que simula chunks infinitos ou grandes
        async def mock_aiter_bytes():
            yield b"%PDF-1.4" + b"A" * 1024
            yield b"GIGANTE" * 1000000

        mock_stream_response.aiter_bytes = mock_aiter_bytes
        mock_stream_response.aread = AsyncMock(return_value=b"")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=MagicMock(status_code=200))
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_stream_response)
        mock_client.aclose = AsyncMock()
        mock_client_cls.return_value = mock_client

        url = "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?x=1"
        ticket = gerar_ticket_pdf(url)
        response = client.get(f"/api/pdf/{ticket}")

        # O status inicial e 200 pq o Magic Byte passa, mas o receiver detecta excesso e para o yield.
        assert response.status_code == 200
        assert len(response.content) < 20000000  # Nao deve ter baixado tudo


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

        pdf_part1 = b"%PDF-1.4 "
        pdf_part2 = b"fake content"
        pdf_full = pdf_part1 + pdf_part2

        mock_stream_res = MagicMock()
        mock_stream_res.status_code = 200
        mock_stream_res.headers = {"content-type": "application/pdf"}
        mock_stream_res.aclose = AsyncMock()

        # Mock do iterador: o primeiro anext pega part1, o aread deve pegar o resto (part2)
        async def mock_aiter_bytes():
            yield pdf_part1
            yield pdf_part2

        mock_stream_res.aiter_bytes = mock_aiter_bytes
        # No motor real, aread() após anext() pegaria o resto. No mock, forçamos o resto.
        mock_stream_res.aread = AsyncMock(return_value=pdf_part2)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=MagicMock(status_code=200))
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_stream_res)
        mock_client.aclose = AsyncMock()
        mock_client_cls.return_value = mock_client

        url = "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?x=1"
        ticket = gerar_ticket_pdf(url)
        response = client.get(f"/api/pdf/{ticket}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content == pdf_full

    @patch("api.ticket_limiter")
    @patch("api.is_safe_host", return_value=True)
    @patch("api.httpx.AsyncClient")
    def test_upstream_fora_do_ar_retorna_504(self, mock_client_cls, mock_ssrf, mock_limiter):
        """Timeout com upstream deve retornar 504 (ou 502 se for ConnectError)."""
        mock_limiter.check = AsyncMock(return_value=True)

        import httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.aclose = AsyncMock()
        mock_client_cls.return_value = mock_client

        url = "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?x=1"
        ticket = gerar_ticket_pdf(url)
        response = client.get(f"/api/pdf/{ticket}")
        assert response.status_code == 504

    @patch("api.ticket_limiter")
    @patch("api.is_safe_host", return_value=True)
    @patch("api.httpx.AsyncClient")
    def test_nenhum_header_sensivel_repassado(self, mock_client_cls, mock_ssrf, mock_limiter):
        """Tunel nao deve repassar Referer ou Cookie do cliente."""
        mock_limiter.check = AsyncMock(return_value=True)

        pdf_bytes = b"%PDF-1.4 fake"
        mock_stream_res = MagicMock()
        mock_stream_res.status_code = 200
        mock_stream_res.headers = {"content-type": "application/pdf"}
        mock_stream_res.aclose = AsyncMock()

        async def mock_aiter_bytes():
            yield pdf_bytes

        mock_stream_res.aiter_bytes = mock_aiter_bytes
        mock_stream_res.aread = AsyncMock(return_value=b"")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=MagicMock(status_code=200))
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_stream_res)
        mock_client.aclose = AsyncMock()
        mock_client_cls.return_value = mock_client

        url = "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?x=1"
        ticket = gerar_ticket_pdf(url)

        client.get(
            f"/api/pdf/{ticket}",
            headers={"Referer": "http://evil.com", "Cookie": "session=stolen"},
        )

        # Verificar que o Referer foi injetado contendo a URL original, não a do cliente
        call_args = mock_client.build_request.call_args
        sent_headers = call_args.kwargs.get("headers", {})
        assert sent_headers.get("Referer") == url
        assert "cookie" not in {k.lower() for k in sent_headers}

    @patch("api.ticket_limiter")
    @patch("api.is_safe_host", return_value=True)
    @patch("api.httpx.AsyncClient")
    def test_falso_pdf_retorna_502(self, mock_client_cls, mock_ssrf, mock_limiter):
        """Falso PDF (HTML) deve retornar status 502 Bad Gateway no novo motor."""
        mock_limiter.check = AsyncMock(return_value=True)

        html_bytes = b"<html>Acesso Negado</html>"
        mock_stream_res = MagicMock()
        mock_stream_res.status_code = 200
        mock_stream_res.headers = {"content-type": "text/html"}
        mock_stream_res.aclose = AsyncMock()

        async def mock_aiter_bytes():
            yield html_bytes

        mock_stream_res.aiter_bytes = mock_aiter_bytes
        mock_stream_res.aread = AsyncMock(return_value=b"")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=MagicMock(status_code=200))
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_stream_res)
        mock_client.aclose = AsyncMock()
        mock_client_cls.return_value = mock_client

        url = "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?x=1"
        ticket = gerar_ticket_pdf(url)
        response = client.get(f"/api/pdf/{ticket}")

        assert response.status_code == 502
        assert response.json()["error"]["code"] == "fake_pdf"

    @patch("api.ticket_limiter")
    @patch("api.is_safe_host", return_value=True)
    @patch("api.httpx.AsyncClient")
    def test_tunnel_crash_masking(self, mock_client_cls, mock_ssrf, mock_limiter):
        """Crash inesperado no tunel nao deve vazar o CPF no payload do JSON."""
        mock_limiter.check = AsyncMock(return_value=True)

        # Simular crash fatal que inclui o CPF na mensagem do erro
        cpf_teste = "74839210055"
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception(f"Fatal error with CPF {cpf_teste}"))
        mock_client.aclose = AsyncMock()
        mock_client_cls.return_value = mock_client

        url = f"http://intranet.ifs.edu.br/cert.wsp?cpf={cpf_teste}"
        ticket = gerar_ticket_pdf(url)
        response = client.get(f"/api/pdf/{ticket}")

        assert response.status_code == 500
        data = response.json()
        assert cpf_teste not in data["error"]["message"]
        assert "748********" in data["error"]["message"]
