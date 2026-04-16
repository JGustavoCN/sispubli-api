"""
Testes do Rate Limiter — rate_limit.py.

Cobertura TDD:
    - extrair_ip_real: x-forwarded-for, x-real-ip, client.host
    - RateLimiter: sliding window em memoria com asyncio.Lock
    - Cenarios de bloqueio 429 (IP e Ticket)
    - Anti-enumeracao (auth rate limit)
    - Concorrencia: Lock previne race conditions
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from rate_limit import RateLimiter, extrair_ip_real

# ===================================================================
# TESTES: Extracao de IP Real
# ===================================================================


class TestExtrairIpReal:
    """Testes para resolucao do IP real do cliente."""

    def test_ip_de_x_forwarded_for(self):
        """Deve extrair IP do header x-forwarded-for."""
        request = MagicMock()
        request.headers = {"x-forwarded-for": "203.0.113.50"}
        request.client.host = "127.0.0.1"

        ip = extrair_ip_real(request)
        assert ip == "203.0.113.50"

    def test_x_forwarded_for_com_lista_virgulas(self):
        """x-forwarded-for com multiplos IPs: usar o primeiro."""
        request = MagicMock()
        request.headers = {"x-forwarded-for": "203.0.113.50, 70.41.3.18, 150.172.238.178"}
        request.client.host = "127.0.0.1"

        ip = extrair_ip_real(request)
        assert ip == "203.0.113.50"

    def test_ip_de_x_real_ip(self):
        """Fallback para x-real-ip quando x-forwarded-for nao existe."""
        request = MagicMock()
        request.headers = {"x-real-ip": "198.51.100.23"}
        request.client.host = "127.0.0.1"

        ip = extrair_ip_real(request)
        assert ip == "198.51.100.23"

    def test_fallback_client_host(self):
        """Ultimo recurso: usar request.client.host."""
        request = MagicMock()
        request.headers = {}
        request.client.host = "192.168.1.100"

        ip = extrair_ip_real(request)
        assert ip == "192.168.1.100"

    def test_x_forwarded_for_com_espacos(self):
        """x-forwarded-for com espacos apos virgula deve ser limpo."""
        request = MagicMock()
        request.headers = {"x-forwarded-for": "  10.0.0.1  , 20.0.0.1"}
        request.client.host = "127.0.0.1"

        ip = extrair_ip_real(request)
        assert ip == "10.0.0.1"

    def test_client_none_retorna_fallback(self):
        """Se request.client for None, retorna IP fallback."""
        request = MagicMock()
        request.headers = {}
        request.client = None

        ip = extrair_ip_real(request)
        assert ip == "0.0.0.0"  # noqa: S104


# ===================================================================
# TESTES: RateLimiter — Sliding Window
# ===================================================================


class TestRateLimiter:
    """Testes para o rate limiter com sliding window em memoria."""

    @pytest.mark.asyncio
    async def test_permite_dentro_do_limite(self):
        """Requisicoes dentro do limite devem ser permitidas."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert await limiter.check("192.168.1.1") is True

    @pytest.mark.asyncio
    async def test_bloqueia_acima_do_limite(self):
        """Requisicao que excede o limite deve ser bloqueada."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            await limiter.check("192.168.1.1")

        # Quarta requisicao deve ser bloqueada
        assert await limiter.check("192.168.1.1") is False

    @pytest.mark.asyncio
    async def test_chaves_diferentes_sao_independentes(self):
        """Rate limit de um IP nao afeta outro IP."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        await limiter.check("10.0.0.1")
        await limiter.check("10.0.0.1")

        # IP diferente deve ter seu proprio contador
        assert await limiter.check("10.0.0.2") is True

    @pytest.mark.asyncio
    async def test_janela_expira(self):
        """Entradas antigas fora da janela devem ser removidas."""
        limiter = RateLimiter(max_requests=2, window_seconds=1)
        await limiter.check("10.0.0.1")
        await limiter.check("10.0.0.1")

        # Esperar a janela expirar
        await asyncio.sleep(1.1)

        # Deve permitir novamente
        assert await limiter.check("10.0.0.1") is True

    @pytest.mark.asyncio
    async def test_ip_rate_limit_20_por_minuto(self):
        """Simulacao do rate limit de IP: 20 req/min."""
        limiter = RateLimiter(max_requests=20, window_seconds=60)
        for _ in range(20):
            assert await limiter.check("203.0.113.50") is True

        # 21a requisicao bloqueada
        assert await limiter.check("203.0.113.50") is False

    @pytest.mark.asyncio
    async def test_ticket_rate_limit_100_por_hora(self):
        """Simulacao do rate limit de ticket: 100 req/h."""
        limiter = RateLimiter(max_requests=100, window_seconds=3600)
        for _ in range(100):
            assert await limiter.check("ticket_abc123") is True

        # 101a requisicao bloqueada
        assert await limiter.check("ticket_abc123") is False

    @pytest.mark.asyncio
    async def test_auth_rate_limit_5_por_minuto(self):
        """Simulacao do rate limit de auth: 5 req/min (anti-enumeracao)."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert await limiter.check("10.0.0.1") is True

        # 6a tentativa de login bloqueada
        assert await limiter.check("10.0.0.1") is False

    @pytest.mark.asyncio
    async def test_concorrencia_com_lock(self):
        """Lock interno deve prevenir race conditions basicas."""
        limiter = RateLimiter(max_requests=10, window_seconds=60)

        # Dispara 15 requisicoes simultaneas
        results = await asyncio.gather(*[limiter.check("concurrent_ip") for _ in range(15)])

        # Exatamente 10 devem ser True, 5 devem ser False
        assert results.count(True) == 10
        assert results.count(False) == 5
