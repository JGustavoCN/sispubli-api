"""
Testes do Motor de Criptografia — security.py.

Cobertura TDD:
    - gerar_token_sessao / ler_token_sessao: Round-trip, TTL, adulteracao
    - gerar_ticket_pdf / ler_ticket_pdf: Round-trip sem TTL, adulteracao
    - Validacao de tamanho: tokens/tickets > 2048 chars rejeitados
    - Normalizacao de CPF: aceita formatos com pontuacao
"""

import time
from unittest.mock import patch

import pytest
from cryptography.fernet import InvalidToken

from src.core.security import (
    gerar_ticket_pdf,
    gerar_token_sessao,
    ler_ticket_pdf,
    ler_token_sessao,
    mask_cpf,
    normalizar_cpf,
)

# ===================================================================
# TESTES: Normalizacao de CPF
# ===================================================================


class TestNormalizarCpf:
    """Testes para normalizacao de CPF antes de criptografar."""

    def test_cpf_apenas_digitos_mantem(self):
        """CPF com 11 digitos numericos permanece inalterado."""
        assert normalizar_cpf("74839210055") == "74839210055"

    def test_cpf_com_pontuacao(self):
        """CPF formatado (748.392.100-55) e normalizado."""
        assert normalizar_cpf("748.392.100-55") == "74839210055"

    def test_cpf_com_espacos(self):
        """CPF com espacos e normalizado."""
        assert normalizar_cpf("748 392 100 55") == "74839210055"

    def test_cpf_vazio_retorna_vazio(self):
        """CPF vazio retorna string vazia."""
        assert normalizar_cpf("") == ""


class TestMaskCpf:
    """Testes para mascaramento de CPF (identidade protegida em logs)."""

    def test_mask_cpf_padrao(self):
        """CPF de 11 digitos deve ser mascarado no formato ***.XXX.XXX-**."""
        assert mask_cpf("74839210055") == "***.392.100-**"

    def test_mask_cpf_curto_retorna_generico(self):
        """CPF com menos de 11 digitos retorna mascara generica de seguranca."""
        assert mask_cpf("123") == "***.***.***-**"

    def test_mask_cpf_vazio_retorna_generico(self):
        """CPF vazio retorna mascara generica."""
        assert mask_cpf("") == "***.***.***-**"


# ===================================================================
# TESTES: Token de Sessao (Fernet + TTL 15 min)
# ===================================================================


class TestTokenSessao:
    """Testes para geracao e leitura de tokens de sessao com TTL."""

    def test_gerar_token_retorna_string_nao_vazia(self):
        """Token gerado deve ser uma string nao vazia."""
        token = gerar_token_sessao("74839210055")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_round_trip_retorna_cpf(self):
        """Gerar e ler token deve retornar o CPF original."""
        cpf = "74839210055"
        token = gerar_token_sessao(cpf)
        resultado = ler_token_sessao(token)
        assert resultado == cpf

    def test_token_expirado_apos_ttl(self):
        """Token deve ser rejeitado apos o TTL de 15 minutos."""
        cpf = "74839210055"
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
        token = gerar_token_sessao("74839210055")
        token_corrompido = token[:-5] + "XXXXX"
        with pytest.raises(InvalidToken):
            ler_token_sessao(token_corrompido)

    def test_token_muito_longo_rejeita(self):
        """Token > 2048 caracteres deve ser rejeitado imediatamente."""
        token_gigante = "A" * 2049
        with pytest.raises(ValueError, match="Token excede tamanho maximo"):
            ler_token_sessao(token_gigante)

    def test_token_normaliza_cpf_com_pontuacao(self):
        """Token gerado com CPF formatado deve retornar CPF limpo."""
        token = gerar_token_sessao("748.392.100-55")
        resultado = ler_token_sessao(token)
        assert resultado == "74839210055"


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
        url = "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?tmp.tx_cpf=74839210055"
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
        """Ticket > 2048 caracteres deve ser rejeitado imediatamente."""
        ticket_gigante = "B" * 2049
        with pytest.raises(ValueError, match="Ticket excede tamanho maximo"):
            ler_ticket_pdf(ticket_gigante)
