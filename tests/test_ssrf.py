"""
Testes de Prevenção a SSRF — Is Safe Host.

Garante que o túnel de PDF recusa domínios externos e tentativas de DNS Rebinding.
A injeção de host malicioso ou IPs proibidos na API deve falhar na fase inicial (Fail Fast).
"""

import socket
from unittest.mock import patch

from src.main import is_safe_host


class TestIsSafeHost:
    """Suíte de testes para a função is_safe_host do Túnel."""

    def test_hostname_legitimo(self):
        """Domínio correto deve passar na primeira validação."""
        # Se for o hostname oficial, e mockarmos uma resolução de DNS limpa.
        with patch("src.main.socket.gethostbyname") as mock_dns:
            mock_dns.return_value = "200.17.141.10"  # IP público fictício mas válido
            assert is_safe_host("intranet.ifs.edu.br") is True

    def test_hostname_proibido_falha_rapidamente(self):
        """Qualquer hostname que não seja exatamente intranet.ifs.edu.br deve falhar."""
        assert is_safe_host("google.com") is False
        assert is_safe_host("intranet.ifs.edu.br.evil.com") is False
        assert is_safe_host("localhost") is False

    def test_ip_privado_bloqueado(self):
        """IPs de subredes privadas (RFC 1918) devem ser barrados."""
        with patch("src.main.socket.gethostbyname") as mock_dns:
            mock_dns.return_value = "10.0.0.5"  # Range classe A
            assert is_safe_host("intranet.ifs.edu.br") is False

            mock_dns.return_value = "192.168.1.100"  # Range classe C
            assert is_safe_host("intranet.ifs.edu.br") is False

            mock_dns.return_value = "172.16.0.1"  # Range classe B
            assert is_safe_host("intranet.ifs.edu.br") is False

    def test_ip_loopback_bloqueado(self):
        """IPs de loopback (DNS rebinding atacando a própria Vercel)."""
        with patch("src.main.socket.gethostbyname") as mock_dns:
            mock_dns.return_value = "127.0.0.1"
            assert is_safe_host("intranet.ifs.edu.br") is False

    def test_ip_link_local_bloqueado(self):
        """IPs link-local (cloud metadata services - ex: 169.254.169.254) devem ser bloqueados."""
        with patch("src.main.socket.gethostbyname") as mock_dns:
            mock_dns.return_value = "169.254.169.254"
            assert is_safe_host("intranet.ifs.edu.br") is False

    def test_erro_resolucao_dns(self):
        """Se o socket.gethostbyname falhar, assume-se como host inseguro."""
        with patch("src.main.socket.gethostbyname", side_effect=socket.gaierror):
            assert is_safe_host("intranet.ifs.edu.br") is False
