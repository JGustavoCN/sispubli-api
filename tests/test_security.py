"""
Testes do Motor de Criptografia — security.py.

Cobertura TDD:
    - gerar_token_sessao / ler_token_sessao: Round-trip, TTL, adulteracao
    - gerar_ticket_pdf / ler_ticket_pdf: Round-trip sem TTL, adulteracao
    - derivar_session_hash: Determinismo, pepper obrigatorio
    - Validacao de tamanho: tokens/tickets > 500 chars rejeitados
    - Normalizacao de CPF: aceita formatos com pontuacao
"""

import time
from unittest.mock import patch

import pytest
from cryptography.fernet import InvalidToken

from security import (
    derivar_session_hash,
    gerar_ticket_pdf,
    gerar_token_sessao,
    ler_ticket_pdf,
    ler_token_sessao,
    normalizar_cpf,
)

# ===================================================================
# TESTES: Normalizacao de CPF
# ===================================================================


class TestNormalizarCpf:
    """Testes para normalizacao de CPF antes de criptografar."""

    def test_cpf_apenas_digitos_mantem(self):
        """CPF com 11 digitos numericos permanece inalterado."""
        assert normalizar_cpf("12345678900") == "12345678900"

    def test_cpf_com_pontuacao(self):
        """CPF formatado (123.456.789-00) e normalizado."""
        assert normalizar_cpf("123.456.789-00") == "12345678900"

    def test_cpf_com_espacos(self):
        """CPF com espacos e normalizado."""
        assert normalizar_cpf("123 456 789 00") == "12345678900"

    def test_cpf_vazio_retorna_vazio(self):
        """CPF vazio retorna string vazia."""
        assert normalizar_cpf("") == ""


# ===================================================================
# TESTES: Token de Sessao (Fernet + TTL 15 min)
# ===================================================================


class TestTokenSessao:
    """Testes para geracao e leitura de tokens de sessao com TTL."""

    def test_gerar_token_retorna_string_nao_vazia(self):
        """Token gerado deve ser uma string nao vazia."""
        token = gerar_token_sessao("12345678900")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_round_trip_retorna_cpf(self):
        """Gerar e ler token deve retornar o CPF original."""
        cpf = "12345678900"
        token = gerar_token_sessao(cpf)
        resultado = ler_token_sessao(token)
        assert resultado == cpf

    def test_token_expirado_apos_ttl(self):
        """Token deve ser rejeitado apos o TTL de 15 minutos."""
        cpf = "12345678900"
        token = gerar_token_sessao(cpf)

        # Simula passagem de tempo (16 minutos = 960 segundos)
        future_time = time.time() + 960
        with (
            patch("cryptography.fernet.time") as mock_time,
            pytest.raises(InvalidToken),
        ):
            mock_time.time.return_value = future_time
            ler_token_sessao(token)

    def test_token_adulterado_rejeita(self):
        """Token com bytes corrompidos deve ser rejeitado."""
        token = gerar_token_sessao("12345678900")
        token_corrompido = token[:-5] + "XXXXX"
        with pytest.raises(InvalidToken):
            ler_token_sessao(token_corrompido)

    def test_token_muito_longo_rejeita(self):
        """Token > 500 caracteres deve ser rejeitado imediatamente."""
        token_gigante = "A" * 501
        with pytest.raises(ValueError, match="Token excede tamanho maximo"):
            ler_token_sessao(token_gigante)

    def test_token_normaliza_cpf_com_pontuacao(self):
        """Token gerado com CPF formatado deve retornar CPF limpo."""
        token = gerar_token_sessao("123.456.789-00")
        resultado = ler_token_sessao(token)
        assert resultado == "12345678900"


# ===================================================================
# TESTES: Ticket de PDF (Fernet SEM TTL)
# ===================================================================


class TestTicketPdf:
    """Testes para tickets de PDF sem TTL (compartilhaveis)."""

    def test_gerar_ticket_retorna_string_nao_vazia(self):
        """Ticket gerado deve ser uma string nao vazia."""
        url = "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?x=1"
        ticket = gerar_ticket_pdf(url)
        assert isinstance(ticket, str)
        assert len(ticket) > 0

    def test_round_trip_retorna_url(self):
        """Gerar e ler ticket deve retornar a URL original."""
        url = "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?tmp.tx_cpf=12345678900"
        ticket = gerar_ticket_pdf(url)
        resultado = ler_ticket_pdf(ticket)
        assert resultado == url

    def test_ticket_nao_expira(self):
        """Ticket deve funcionar mesmo apos muito tempo (sem TTL).

        Como ler_ticket_pdf nao passa parametro ttl ao Fernet.decrypt,
        o ticket nunca expira — validamos apenas o round-trip.
        """
        url = "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?x=1"
        ticket = gerar_ticket_pdf(url)
        # Sem TTL — deve funcionar sempre
        resultado = ler_ticket_pdf(ticket)
        assert resultado == url

    def test_ticket_adulterado_rejeita(self):
        """Ticket com bytes corrompidos deve ser rejeitado."""
        url = "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?x=1"
        ticket = gerar_ticket_pdf(url)
        ticket_corrompido = ticket[:-5] + "ZZZZZ"
        with pytest.raises(InvalidToken):
            ler_ticket_pdf(ticket_corrompido)

    def test_ticket_muito_longo_rejeita(self):
        """Ticket > 500 caracteres deve ser rejeitado imediatamente."""
        ticket_gigante = "B" * 501
        with pytest.raises(ValueError, match="Ticket excede tamanho maximo"):
            ler_ticket_pdf(ticket_gigante)


# ===================================================================
# TESTES: Derivacao de Session Hash (SHA-256 + PEPPER)
# ===================================================================


class TestDerivarSessionHash:
    """Testes para derivacao do session_hash com SECRET_PEPPER."""

    def test_hash_retorna_string_hexadecimal(self):
        """Hash deve ser uma string hexadecimal de 64 caracteres."""
        token = gerar_token_sessao("12345678900")
        h = derivar_session_hash(token)
        assert isinstance(h, str)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_deterministico(self):
        """Mesmo token deve gerar o mesmo hash sempre."""
        token = gerar_token_sessao("12345678900")
        h1 = derivar_session_hash(token)
        h2 = derivar_session_hash(token)
        assert h1 == h2

    def test_tokens_diferentes_geram_hashes_diferentes(self):
        """Tokens de CPFs diferentes devem gerar hashes diferentes."""
        t1 = gerar_token_sessao("12345678900")
        t2 = gerar_token_sessao("98765432100")
        h1 = derivar_session_hash(t1)
        h2 = derivar_session_hash(t2)
        assert h1 != h2

    def test_hash_usa_pepper(self):
        """Hash com PEPPER deve diferir de hash sem PEPPER."""
        import hashlib

        token = gerar_token_sessao("12345678900")
        hash_sem_pepper = hashlib.sha256(token.encode("utf-8")).hexdigest()
        hash_com_pepper = derivar_session_hash(token)
        assert hash_com_pepper != hash_sem_pepper

    def test_mesmo_token_gera_mesmo_session_hash(self):
        """Token replay: reutilizar mesmo token gera mesmo hash (determinismo)."""
        cpf = "12345678900"
        token = gerar_token_sessao(cpf)
        hash_1 = derivar_session_hash(token)
        hash_2 = derivar_session_hash(token)
        assert hash_1 == hash_2, "Token replay deve gerar mesmo session_hash"
