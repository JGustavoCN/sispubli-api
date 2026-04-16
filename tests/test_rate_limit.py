"""
Testes de Rate Limiter e Filtros de IP.

Garante que:
1. Extração de IP segue as regras da CDN Vercel.
2. A janela deslizante do RateLimit (Sliding Window) funciona corretamente com locks.
"""

import time
from unittest.mock import Mock

import pytest

from rate_limit import RateLimiter, extrair_ip_real


class TestExtracaoIP:
    """Testes da extração de IP baseada em headers."""

    def _mock_request(self, headers, client_host=None):
        req = Mock()
        req.headers = headers
        if client_host:
            req.client = Mock()
            req.client.host = client_host
        else:
            req.client = None
        return req

    def test_x_forwarded_for_primeiro_ip(self):
        """Deve pegar o primeiro IP em caso de lista separada por vírgula."""
        req = self._mock_request({"x-forwarded-for": "200.1.1.1, 10.0.0.1"})
        assert extrair_ip_real(req) == "200.1.1.1"

    def test_x_real_ip(self):
        """Fallback para x-real-ip se ausente x-forwarded-for."""
        req = self._mock_request({"x-real-ip": "200.2.2.2"})
        assert extrair_ip_real(req) == "200.2.2.2"

    def test_fallback_client_host(self):
        """Usa host da conexão direta caso headers não existam."""
        req = self._mock_request({}, client_host="192.168.0.10")
        assert extrair_ip_real(req) == "192.168.0.10"

    def test_fallback_absoluto(self):
        """Retorna 0.0.0.0 em último caso, para não gerar exceção no limitador."""
        req = self._mock_request({})
        assert extrair_ip_real(req) == "0.0.0.0"


@pytest.mark.asyncio
class TestRateLimiter:
    """Testes assíncronos da janela deslizante do limitador (RateLimiter)."""

    async def test_fluxo_normal_permite(self):
        """O limitador não deve bloquear requisições abaixo do limite configurado."""
        limitador = RateLimiter(max_requests=2, window_seconds=10)

        # 1a vez
        assert await limitador.check("1.1.1.1") is True
        # 2a vez
        assert await limitador.check("1.1.1.1") is True

    async def test_excede_limite_bloqueia(self):
        """Deve retornar False após limite esgotado."""
        limitador = RateLimiter(max_requests=2, window_seconds=10)

        await limitador.check("2.2.2.2")
        await limitador.check("2.2.2.2")
        # 3a vez estoura limite
        assert await limitador.check("2.2.2.2") is False

    async def test_sliding_window_reseta(self):
        """Deve voltar a True após as requisições antigas caírem da janela (Sliding Window)."""
        limitador = RateLimiter(max_requests=1, window_seconds=1)

        assert await limitador.check("3.3.3.3") is True
        assert await limitador.check("3.3.3.3") is False  # Estourado

        # Simulando uma espera irreal para teste
        time.sleep(1.1)

        # Como o array de registros descarta items > 1 seg, ele reseta o contador
        assert await limitador.check("3.3.3.3") is True
