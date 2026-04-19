from unittest.mock import AsyncMock, MagicMock

from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from api import app, security_scheme

client = TestClient(app)

# =============================================================================
# TESTES DE CONFORMIDADE: POLÍTICA DE CACHE (ZERO LEAK)
# =============================================================================


def test_cache_policy_health_check(mocker):
    """GET / deve proibir cache (no-store)."""
    # Mock assíncrono para evitar TypeError: object bool can't be used in 'await'
    mocker.patch("api._check_upstream_connectivity", new_callable=AsyncMock, return_value=True)

    response = client.get("/")
    assert response.status_code == 200
    cache_control = response.headers.get("Cache-Control", "")
    assert "no-store" in cache_control
    assert "no-cache" in cache_control
    assert response.headers.get("X-Content-Type-Options") == "nosniff"


def test_cache_policy_auth_token_error():
    """POST /api/auth/token com erro deve proibir cache (no-store) via Middleware."""
    # Payload inválido causa 422
    response = client.post("/api/auth/token", json={"cpf": "curto"})
    assert response.status_code == 422
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"


def test_cache_policy_certificados(mocker):
    """GET /api/certificados deve usar cache PRIVADO por 5 min (300s)."""
    # Mock da dependencia de autenticacao nativo do FastAPI
    app.dependency_overrides[security_scheme] = lambda: HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="mock_token"
    )

    # Mocks para o scraper, seguranca e rate limit
    mocker.patch("api.ler_token_sessao", return_value="74839210055")
    mocker.patch("api.ip_limiter.check", new_callable=AsyncMock, return_value=True)
    mocker.patch(
        "api.fetch_all_certificates",
        return_value={"usuario_id": "123", "total": 0, "certificados": []},
    )

    response = client.get("/api/certificados")

    # Limpar overrides apos o teste para nao vazar para outros testes
    app.dependency_overrides.clear()

    assert response.status_code == 200
    cache_control = response.headers.get("Cache-Control", "")
    assert "private" in cache_control
    assert "max-age=300" in cache_control
    assert "s-maxage" not in cache_control  # Proibido cache na CDN para PII
    assert response.headers.get("X-Content-Type-Options") == "nosniff"


def test_cache_policy_pdf_tunnel(mocker):
    """GET /api/pdf/{ticket} deve usar cache PÚBLICO (CDN) por 24h."""
    mocker.patch("api.ler_ticket_pdf", return_value="https://intranet.ifs.edu.br/mock")
    mocker.patch("api.is_safe_host", return_value=True)

    # Mock complexo do stream do httpx para validar o fluxo do tunnel
    async def mock_stream(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        async def aiter_bytes():
            yield b"%PDF-1.4"
            yield b"dummy_content"

        mock_resp.aiter_bytes = aiter_bytes
        mock_resp.aclose = AsyncMock()  # Fechamento assíncrono
        return mock_resp

    mocker.patch(
        "api.httpx.AsyncClient.get",
        new_callable=AsyncMock,
        return_value=mocker.Mock(status_code=200),
    )
    mocker.patch("api.httpx.AsyncClient.send", side_effect=mock_stream)

    response = client.get("/api/pdf/mock_ticket")

    assert response.status_code == 200
    cache_control = response.headers.get("Cache-Control", "")
    assert "public" in cache_control
    assert "s-maxage=86400" in cache_control
    assert "stale-while-revalidate=86400" in cache_control
    assert response.headers.get("X-Content-Type-Options") == "nosniff"


def test_cache_policy_global_middleware_error():
    """Garante que qualquer erro nao mapeado (404) forca no-store para evitar cache de falhas."""
    response = client.get("/v1/endpoint-que-nao-existe")
    assert response.status_code == 404
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
